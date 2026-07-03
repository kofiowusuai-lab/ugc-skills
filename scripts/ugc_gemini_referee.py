#!/usr/bin/env python3
"""
ugc_gemini_referee.py - Gemini vision QA + winner selection for UGC takes.

This is the FALLBACK referee used when the headless Claude agent
(ugc_claude_deliver.sh) is unavailable or fails at runtime. It speaks the
EXACT same contract as the Claude path:

  - reads the supplied anchor as real pixels,
  - extracts frames from each candidate take and SEES them via Gemini,
  - judges identity / setting / composition drift against the contract,
  - selects the single highest-scoring PASS per clip slot,
  - writes <job>/claude_delivery_report.json in the same shape,
  - exits 0 when every slot has a winner, 1 when a slot has no passing take.

Delivery (voice / stitch / compliance) is handled by the bash caller so both
engines produce an identical finished mp4. This script does QA + SELECT only.

USAGE
  ugc_gemini_referee.py --job DIR --anchor IMG [--pattern '*.mp4'] \
      [--min 0.80] [--criteria '...'] [--model gemini-2.5-pro] \
      [--report PATH] [--frames 2] [--qa-only]

Gemini is natively multimodal, so unlike MiniMax it judges real pixels. Default
model is gemini-2.5-pro (strongest vision); pass --model gemini-2.5-flash for a
cheaper/faster pass on high candidate counts.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ENV_FILE = Path.home() / ".openclaw" / ".env"
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}

DEFAULT_CRITERIA = (
    "The take must show the SAME people as the anchor with NO substitution: same "
    "number of people, same left/right positions, each person's race/gender/age/hair "
    "unchanged, each person's clothing unchanged, each role unchanged (the one holding "
    "the mic stays the interviewer), the same setting/background type, and the same "
    "shot scale. Drift to a different person, swapped sides, changed outfit, a new "
    "location, or generic street/shopping b-roll is a FAIL."
)

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "anchor_description": {"type": "string"},
        "overall_score": {"type": "number"},
        "identity_match": {"type": "boolean"},
        "setting_match": {"type": "boolean"},
        "composition_match": {"type": "boolean"},
        "mismatches": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": "string"},
    },
    "required": [
        "anchor_description",
        "overall_score",
        "identity_match",
        "setting_match",
        "composition_match",
        "mismatches",
        "verdict",
    ],
}


def load_api_key() -> str:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "GEMINI_API_KEY":
                return v.strip().strip('"').strip("'")
    return os.environ.get("GEMINI_API_KEY", "")


def log(msg: str):
    print(f"[gemini-referee] {msg}", file=sys.stderr)


def mime_for(path: Path) -> str:
    s = path.suffix.lower()
    if s in (".jpg", ".jpeg"):
        return "image/jpeg"
    if s == ".webp":
        return "image/webp"
    return "image/png"


def image_part(path: Path) -> dict:
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return {"inlineData": {"mimeType": mime_for(path), "data": data}}


def video_duration(path: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def extract_frames(video: Path, frames_dir: Path, n: int) -> list:
    """Extract n frames spread across the clip. Returns list of frame paths."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    dur = video_duration(video)
    if dur <= 0:
        dur = 3.0
    # Sample points: skip the very first/last 5% to avoid black/transition frames.
    if n == 1:
        points = [dur * 0.5]
    else:
        lo, hi = dur * 0.10, dur * 0.85
        if hi <= lo:
            lo, hi = 0.15, max(0.3, dur - 0.2)
        step = (hi - lo) / (n - 1)
        points = [lo + step * i for i in range(n)]
    out = []
    stem = video.stem
    for i, t in enumerate(points):
        fp = frames_dir / f"{stem}__f{i}.jpg"
        r = subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(video),
             "-frames:v", "1", "-q:v", "3", str(fp)],
            capture_output=True, timeout=60,
        )
        if r.returncode == 0 and fp.exists() and fp.stat().st_size > 0:
            out.append(fp)
    return out


def slot_for(path: Path) -> str:
    """Derive the clip slot a candidate belongs to.

    clip3_candidate_2.mp4 -> clip3 ; shot02_take5.mp4 -> shot02 ;
    anything_candidate_*.mp4 -> stem before _candidate ; else the stem.
    """
    name = path.name
    m = re.search(r"(clip\d+)", name, re.I)
    if m:
        return m.group(1).lower()
    m = re.search(r"(shot\d+)", name, re.I)
    if m:
        return m.group(1).lower()
    m = re.search(r"(scene[_-]?\d+)", name, re.I)
    if m:
        return m.group(1).lower().replace("-", "_")
    stem = path.stem
    for sep in ("_candidate", "_take", "_cand", "-candidate", "-take"):
        if sep in stem:
            return stem.split(sep)[0]
    return stem


def build_prompt(criteria: str, min_score: float) -> str:
    return (
        "You are the visual QA referee for a UGC video take. You are given an ANCHOR "
        "reference image followed by one or more FRAMES extracted from a candidate "
        "video take. The candidate is a Grok image-to-video output and may have "
        "DRIFTED off the anchor.\n\n"
        "IDENTITY / CONTINUITY CONTRACT (this is what the take must preserve):\n"
        f"{criteria}\n\n"
        "Compare the candidate frames against the anchor under that contract. Be "
        "skeptical: identity / continuity drift is the failure we are hunting. When "
        "unsure, score LOWER. Ignore video compression artifacts and lighting; judge "
        "the PEOPLE and the SETTING.\n\n"
        "Return a single JSON object:\n"
        "  anchor_description: one line describing exactly who/what is in the anchor.\n"
        "  overall_score: 0.0-1.0 CONFIDENCE that the candidate shows the SAME "
        "person(s) as the anchor. Score IDENTITY only. A different crop, camera "
        "angle, zoom, mirror/flip, distance, or lighting of the SAME person MUST "
        "still score high (>=0.85) — those are not identity changes. Lower the "
        "score ONLY when the PERSON looks different (face, build, age, hair, or a "
        "substitution). Do NOT lower it for framing/composition/background changes.\n"
        "  identity_match: true only if the same people are present with no substitution.\n"
        "  setting_match: true if the setting/background type matches.\n"
        "  composition_match: true if shot scale/framing matches (informational only).\n"
        "  mismatches: short concrete list of IDENTITY drift (empty if same person).\n"
        "  verdict: PASS or FAIL with a few words.\n"
        f"A take PASSES only if identity_match is true AND overall_score >= {min_score:.2f}."
    )


def call_gemini(parts: list, api_key: str, model: str, max_retries: int = 4) -> dict:
    body = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 1200,
            "responseMimeType": "application/json",
            "responseSchema": VERDICT_SCHEMA,
        },
    }).encode()
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={api_key}")
    last = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
            cands = result.get("candidates")
            if not cands:
                # No candidates => safety block or empty. Fail-safe: the caller
                # treats this as a non-passing take (never a false accept).
                block = (result.get("promptFeedback", {}) or {}).get("blockReason", "none")
                raise RuntimeError(f"no candidates returned (blockReason={block})")
            parts = cands[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            if not text.strip():
                raise RuntimeError(f"empty candidate (finishReason={cands[0].get('finishReason')})")
            return json.loads(text)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (503, 429, 500) and attempt < max_retries - 1:
                time.sleep([5, 10, 20, 30][attempt])
                continue
            detail = ""
            try:
                detail = e.read().decode()[:200]
            except Exception:
                pass
            raise RuntimeError(f"Gemini HTTP {e.code}: {detail}") from e
        except Exception as e:
            last = e
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            raise RuntimeError(f"Gemini call failed: {last}") from e
    raise RuntimeError(f"Gemini retries exhausted: {last}")


def judge_candidate(anchor: Path, candidate: Path, frames_dir: Path,
                    api_key: str, model: str, criteria: str, min_score: float,
                    n_frames: int) -> dict:
    parts = [{"text": "ANCHOR (reference the take must preserve):"}, image_part(anchor)]

    if candidate.suffix.lower() in IMG_EXT:
        frame_paths = [candidate]
    else:
        frame_paths = extract_frames(candidate, frames_dir, n_frames)
    if not frame_paths:
        return {
            "file": str(candidate),
            "overall_score": 0.0,
            "identity_match": False,
            "setting_match": False,
            "composition_match": False,
            "mismatches": ["could not extract any frame from candidate"],
            "verdict": "FAIL (unreadable)",
            "anchor_description": "",
            "passed": False,
        }

    parts.append({"text": f"CANDIDATE FRAMES ({len(frame_paths)}) from {candidate.name}:"})
    for fp in frame_paths:
        parts.append(image_part(fp))
    parts.append({"text": build_prompt(criteria, min_score)})

    v = call_gemini(parts, api_key, model)
    score = float(v.get("overall_score", 0.0) or 0.0)
    identity = bool(v.get("identity_match", False))
    passed = identity and score >= min_score
    return {
        "file": str(candidate),
        "overall_score": round(score, 3),
        "identity_match": identity,
        "setting_match": bool(v.get("setting_match", False)),
        "composition_match": bool(v.get("composition_match", False)),
        "mismatches": v.get("mismatches", []) or [],
        "verdict": v.get("verdict", ""),
        "anchor_description": v.get("anchor_description", ""),
        "passed": passed,
    }


def clip_sort_key(slot: str):
    m = re.search(r"(\d+)", slot)
    return (int(m.group(1)) if m else 9999, slot)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--anchor", required=True)
    ap.add_argument("--pattern", default="*.mp4")
    ap.add_argument("--min", type=float, default=0.80)
    ap.add_argument("--criteria", default="")
    ap.add_argument("--model", default="gemini-2.5-pro")
    ap.add_argument("--report", default="")
    ap.add_argument("--frames", type=int, default=2)
    ap.add_argument("--qa-only", action="store_true")  # accepted for parity; QA+select either way
    ap.add_argument("--out", default="")               # accepted for parity; delivery is the caller's job
    args = ap.parse_args()

    job = Path(args.job).resolve()
    anchor = Path(args.anchor).resolve()
    if not job.is_dir():
        sys.exit(f"ERROR: job dir not found: {job}")
    if not anchor.is_file():
        sys.exit(f"ERROR: anchor not found: {anchor}")

    api_key = load_api_key()
    if not api_key:
        sys.exit("ERROR: GEMINI_API_KEY not set in ~/.openclaw/.env")

    criteria = args.criteria.strip() or DEFAULT_CRITERIA
    report_path = Path(args.report).resolve() if args.report else job / "claude_delivery_report.json"
    frames_dir = job / ".gemini_qa_frames"

    candidates = sorted(p for p in job.glob(args.pattern)
                        if p.is_file() and p.resolve() != anchor)
    if not candidates:
        sys.exit(f"ERROR: no candidates in {job} matching {args.pattern}")

    log(f"job={job.name} anchor={anchor.name} pattern={args.pattern} "
        f"candidates={len(candidates)} model={args.model} min={args.min}")

    results = []
    anchor_desc = ""
    by_slot = {}
    for cand in candidates:
        try:
            r = judge_candidate(anchor, cand, frames_dir, api_key, args.model,
                                criteria, args.min, args.frames)
        except Exception as e:
            r = {
                "file": str(cand), "overall_score": 0.0, "identity_match": False,
                "setting_match": False, "composition_match": False,
                "mismatches": [f"referee error: {e}"], "verdict": "ERROR",
                "anchor_description": "", "passed": False,
            }
        if not anchor_desc and r.get("anchor_description"):
            anchor_desc = r["anchor_description"]
        slot = slot_for(cand)
        r["slot"] = slot
        by_slot.setdefault(slot, []).append(r)
        results.append(r)
        mark = "PASS" if r["passed"] else "FAIL"
        log(f"  {mark} {cand.name} score={r['overall_score']} "
            f"id={r['identity_match']} slot={slot}")

    winners = []
    failed_slots = []
    for slot in sorted(by_slot, key=clip_sort_key):
        passing = [r for r in by_slot[slot] if r["passed"]]
        if passing:
            best = max(passing, key=lambda r: r["overall_score"])
            winners.append({"slot": slot, "file": best["file"], "score": best["overall_score"]})
        else:
            top = max(by_slot[slot], key=lambda r: r["overall_score"], default=None)
            reason = "all takes drifted off the anchor"
            if top and top["mismatches"]:
                reason = "all takes drifted: " + "; ".join(top["mismatches"][:2])
            failed_slots.append({"slot": slot, "reason": reason})

    status = "selected" if not failed_slots else "blocked"

    # Strip the internal 'passed' helper from the persisted candidate records.
    cand_out = [{k: v for k, v in r.items() if k not in ("passed",)} for r in results]

    report = {
        "engine": f"gemini:{args.model}",
        "anchor": str(anchor),
        "anchor_description": anchor_desc,
        "candidates": cand_out,
        "winners": winners,
        "failed_slots": failed_slots,
        "delivered": None,
        "status": status,
    }
    report_path.write_text(json.dumps(report, indent=2))
    log(f"report: {report_path} (status={status})")

    passed_n = sum(1 for r in results if r["passed"])
    print(f"Gemini referee ({args.model}): {passed_n}/{len(results)} takes passed, "
          f"{len(winners)} winners, {len(failed_slots)} slot(s) failed.")
    for w in winners:
        print(f"  winner {w['slot']}: {Path(w['file']).name} ({w['score']})")
    for fseg in failed_slots:
        print(f"  FAILED {fseg['slot']}: {fseg['reason']}")
    print("RESULT: OK" if status == "selected" else "RESULT: BLOCKED")

    sys.exit(0 if status == "selected" else 1)


if __name__ == "__main__":
    main()
