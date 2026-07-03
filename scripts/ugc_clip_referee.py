#!/usr/bin/env python3
"""
ugc_clip_referee.py - Vision referee for the UGC Grok image_to_video pipeline.

WHY THIS EXISTS
---------------
Grok's image_to_video is a weak conditioner: handed an anchor image as loose
prose context, it drifts toward its training prior (generic street / mall /
shopping vox-pop) and changes the people, clothing, sides, or setting. When
Codex/gpt-5.5 drove the pipeline it had VISION, so it silently scored every
candidate against the anchor, threw away the drifted ones, and regenerated until
one matched. MiniMax (text-only, no image input) cannot do that, so Grok's drift
now reaches the final cut uncorrected.

This script is the missing referee. It gives a text-only reasoning brain
(MiniMax) a pair of eyes ON DEMAND: it compares each Grok candidate clip to the
supplied anchor image on the exact dimensions Grok breaks (identity, race,
gender, clothing, side/role, setting, composition), returns a structured score,
and either ranks a candidate set or gates a single clip for a regenerate loop.

BACKENDS (auto-selected, first that works)
  1. Gemini 2.5 Flash  (GEMINI_API_KEY in ~/.openclaw/.env) - multi-image, fast.
  2. Local vision proxy (claude-cli-vision @ 127.0.0.1:8717) - fallback.

MODES
  score   anchor + 1 clip            -> JSON verdict (one candidate)
  rank    anchor + N clips           -> ranked JSON, copies winner to --out
  gate    anchor + 1 clip + --min    -> exit 0 (pass) / 1 (fail) for shell loops

USAGE
  ugc_clip_referee.py score --anchor a.jpg --clip c.mp4
  ugc_clip_referee.py rank  --anchor a.jpg --clips "c1.mp4,c2.mp4,c3.mp4" --out best.mp4
  ugc_clip_referee.py rank  --anchor a.jpg --clips-dir ./clips --glob 'clip1_candidate_*.mp4' --out best.mp4
  ugc_clip_referee.py gate  --anchor a.jpg --clip c.mp4 --min 0.75

  # custom identity criteria (overrides the default mall-interview lock):
  ugc_clip_referee.py rank --anchor a.jpg --clips-dir ./clips \
      --criteria "Same single woman, blonde, red dress, holding the blue book." --out best.mp4

Every run prints ONE JSON object to stdout. Human-readable notes go to stderr.
"""

import argparse
import base64
import glob as globmod
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path

ENV_FILE = Path.home() / ".openclaw" / ".env"
VISION_PROXY_URL = "http://127.0.0.1:8717/v1/chat/completions"
GEMINI_MODEL = "gemini-2.5-flash"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".m4v")

# The dimensions Grok drifts on. This is the default contract for a two-person
# public-interview UGC clip; override with --criteria for other formats.
DEFAULT_CRITERIA = (
    "The clip must show the SAME people as the anchor with NO substitutions:\n"
    "- same number of people, in the same left/right positions,\n"
    "- each person's apparent race, gender, age, hairstyle unchanged,\n"
    "- each person's clothing (color, type) unchanged,\n"
    "- each person's role unchanged (e.g. the interviewer holding the mic stays the interviewer),\n"
    "- the same setting / location / background type as the anchor,\n"
    "- the same framing and shot scale (no surprise close-up or wide reset).\n"
    "Drift to a different person, swapped sides, changed outfit, new location, "
    "or generic street/shopping b-roll is a FAIL."
)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def die(error, reason_code, **extra):
    obj = {"ok": False, "error": str(error), "reason_code": reason_code}
    obj.update(extra)
    print(json.dumps(obj))
    sys.exit(2)


def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def b64_image(path):
    data = Path(path).read_bytes()
    ext = Path(path).suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/png")
    return base64.b64encode(data).decode(), mime


def ffprobe_duration(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip())
    except Exception:
        return None


def extract_frames(clip, tmpdir, n=2):
    """Pull representative frames from a video clip. Returns list of PNG paths.

    First frame (t=0.15s) catches Grok's frame-0 substitution; a later frame
    catches mid-motion identity swaps. Images pass through unchanged.
    """
    ext = Path(clip).suffix.lower()
    if ext in IMAGE_EXTS:
        return [clip]
    dur = ffprobe_duration(clip) or 6.0
    # sample points biased to start + middle (where drift shows first)
    points = [0.15]
    if n >= 2:
        points.append(round(dur * 0.5, 2))
    if n >= 3:
        points.append(round(max(dur - 0.3, 0.3), 2))
    frames = []
    base = Path(clip).stem
    for i, t in enumerate(points):
        fp = os.path.join(tmpdir, f"{base}_f{i}.png")
        r = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(t), "-i", clip, "-frames:v", "1",
             "-q:v", "2", fp],
            capture_output=True, text=True, timeout=60)
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            frames.append(fp)
    if not frames:
        raise RuntimeError(f"could not extract any frame from {clip}")
    return frames


PROMPT_TEMPLATE = """You are a strict visual continuity referee for a UGC video pipeline.

IMAGE 1 is the ANCHOR: the exact people and setting the final clip must preserve.
The remaining images are FRAMES sampled from ONE candidate video clip.

Compare the candidate frames against the anchor on these criteria:
{criteria}

Be skeptical. Identity and continuity drift is the failure we are hunting; when
unsure, score lower. Judge people and setting, not video compression artifacts.

Reply with ONLY a JSON object, no prose, no markdown fence:
{{
  "overall_score": <float 0.0-1.0, how well the candidate preserves the anchor>,
  "identity_match": <true/false, are the SAME people present, unswapped>,
  "setting_match": <true/false, same location/background type>,
  "composition_match": <true/false, same sides/roles/framing>,
  "mismatches": [<short strings naming each concrete drift you see>],
  "verdict": "<one sentence>"
}}"""


def parse_json_blob(text):
    """Parse the referee's JSON reply. Falls back to regex salvage when the reply
    is truncated (token cap) or fence-wrapped, so a good clip is never scored 0
    just because the tail of a long mismatches array got cut off."""
    import re
    t = text.strip()
    if "```" in t:
        # take the contents of the first fenced block
        m = re.search(r"```(?:json)?\s*(.+?)```", t, re.S)
        if m:
            t = m.group(1).strip()
        else:
            t = t.split("```", 1)[-1]  # opened fence, never closed (truncated)
    s, e = t.find("{"), t.rfind("}")
    if s != -1 and e != -1 and e > s:
        t = t[s:e + 1]
    try:
        return json.loads(t)
    except Exception:
        pass
    # Salvage: pull the fields we actually gate on out of a truncated blob.
    def grab(pat, cast, default):
        m = re.search(pat, text, re.I)
        if not m:
            return default
        try:
            return cast(m.group(1))
        except Exception:
            return default
    score = grab(r'"overall_score"\s*:\s*([0-9]*\.?[0-9]+)', float, None)
    if score is None:
        raise ValueError("no overall_score in reply")
    truthy = lambda s: str(s).strip().lower() == "true"
    return {
        "overall_score": score,
        "identity_match": grab(r'"identity_match"\s*:\s*(true|false)', truthy, False),
        "setting_match": grab(r'"setting_match"\s*:\s*(true|false)', truthy, False),
        "composition_match": grab(r'"composition_match"\s*:\s*(true|false)', truthy, False),
        "mismatches": [],
        "verdict": "(recovered from truncated referee reply)",
        "_salvaged": True,
    }


def call_gemini(anchor, frames, criteria, api_key):
    parts = [{"text": "IMAGE 1 = ANCHOR (reference):"}]
    ab64, amime = b64_image(anchor)
    parts.append({"inlineData": {"mimeType": amime, "data": ab64}})
    parts.append({"text": f"\nThe next {len(frames)} image(s) are CANDIDATE frames:"})
    for f in frames:
        fb64, fmime = b64_image(f)
        parts.append({"inlineData": {"mimeType": fmime, "data": fb64}})
    parts.append({"text": "\n" + PROMPT_TEMPLATE.format(criteria=criteria)})

    body = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1500},
    }).encode()
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={api_key}")
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read().decode())
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode()[:150]}"
            if e.code in (429, 503) and attempt < 3:
                time.sleep([4, 8, 16][attempt]); continue
            raise RuntimeError(last)
        except Exception as e:
            last = str(e)
            if attempt < 3:
                time.sleep(4); continue
            raise RuntimeError(last)
    raise RuntimeError(f"gemini failed: {last}")


def call_vision_proxy(anchor, frames, criteria):
    """Fallback: the local claude-cli-vision proxy. Accepts multiple images."""
    content = [{"type": "text", "text": "IMAGE 1 = ANCHOR (reference)."}]
    for label, img in [("ANCHOR", anchor)] + [("CANDIDATE", f) for f in frames]:
        b64, mime = b64_image(img)
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"}})
    content.append({"type": "text",
                    "text": PROMPT_TEMPLATE.format(criteria=criteria)})
    body = json.dumps({
        "model": "claude-cli-vision",
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(VISION_PROXY_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read().decode())
    return result["choices"][0]["message"]["content"]


def score_clip(anchor, clip, criteria, env, backend_pref="auto"):
    with tempfile.TemporaryDirectory() as tmp:
        frames = extract_frames(clip, tmp, n=2)
        key = env.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
        raw, backend = None, None
        errors = []
        order = []
        if backend_pref in ("auto", "gemini") and key:
            order.append("gemini")
        if backend_pref in ("auto", "proxy"):
            order.append("proxy")
        for b in order:
            try:
                if b == "gemini":
                    raw = call_gemini(anchor, frames, criteria, key); backend = "gemini"
                else:
                    raw = call_vision_proxy(anchor, frames, criteria); backend = "vision_proxy"
                break
            except Exception as e:
                errors.append(f"{b}: {e}")
                continue
        if raw is None:
            raise RuntimeError("no vision backend available: " + " | ".join(errors))
        try:
            v = parse_json_blob(raw)
        except Exception:
            v = {"overall_score": 0.0, "identity_match": False, "setting_match": False,
                 "composition_match": False, "mismatches": ["unparseable referee reply"],
                 "verdict": raw[:160]}
        v["candidate"] = os.path.abspath(clip)
        v["backend"] = backend
        v["frames_checked"] = len(frames)
        try:
            v["overall_score"] = float(v.get("overall_score", 0.0))
        except (TypeError, ValueError):
            v["overall_score"] = 0.0
        return v


def gather_clips(args):
    clips = []
    if args.clips:
        clips += [c.strip() for c in args.clips.split(",") if c.strip()]
    if args.clips_dir:
        pattern = os.path.join(args.clips_dir, args.glob)
        clips += sorted(globmod.glob(pattern))
    # de-dup, keep order
    seen, out = set(), []
    for c in clips:
        ap = os.path.abspath(c)
        if ap not in seen and os.path.exists(c):
            seen.add(ap); out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser(description="Vision referee for UGC Grok clips")
    ap.add_argument("mode", choices=["score", "rank", "gate"])
    ap.add_argument("--anchor", required=True, help="the supplied reference image")
    ap.add_argument("--clip", help="single candidate (score/gate)")
    ap.add_argument("--clips", help="comma-separated candidates (rank)")
    ap.add_argument("--clips-dir", help="directory of candidates (rank)")
    ap.add_argument("--glob", default="*.mp4", help="glob within --clips-dir")
    ap.add_argument("--out", help="copy the winning clip here (rank)")
    ap.add_argument("--min", type=float, default=0.75, help="pass threshold (gate)")
    ap.add_argument("--criteria", help="override identity/continuity contract")
    ap.add_argument("--backend", default="auto", choices=["auto", "gemini", "proxy"])
    args = ap.parse_args()

    if not os.path.exists(args.anchor):
        die(f"anchor not found: {args.anchor}", "bad_args")
    criteria = args.criteria or DEFAULT_CRITERIA
    env = load_env()

    if args.mode in ("score", "gate"):
        if not args.clip or not os.path.exists(args.clip):
            die(f"clip not found: {args.clip}", "bad_args")
        log(f"[referee] scoring {os.path.basename(args.clip)} vs "
            f"{os.path.basename(args.anchor)} ...")
        try:
            v = score_clip(args.anchor, args.clip, criteria, env, args.backend)
        except Exception as e:
            die(e, "referee_error")
        if args.mode == "score":
            print(json.dumps({"ok": True, **v}))
            sys.exit(0)
        # gate
        passed = v["overall_score"] >= args.min and v.get("identity_match", False)
        v.update({"ok": True, "passed": passed, "threshold": args.min})
        print(json.dumps(v))
        log(f"[referee] {'PASS' if passed else 'FAIL'} "
            f"score={v['overall_score']:.2f} min={args.min}")
        sys.exit(0 if passed else 1)

    # rank
    clips = gather_clips(args)
    if not clips:
        die("no candidate clips found", "bad_args")
    log(f"[referee] ranking {len(clips)} candidates against "
        f"{os.path.basename(args.anchor)} ...")
    results = []
    for c in clips:
        try:
            v = score_clip(args.anchor, c, criteria, env, args.backend)
        except Exception as e:
            v = {"candidate": os.path.abspath(c), "overall_score": 0.0,
                 "identity_match": False, "mismatches": [f"error: {e}"],
                 "verdict": "scoring failed", "backend": None}
        log(f"  {v['overall_score']:.2f} {'OK ' if v.get('identity_match') else 'DRIFT'} "
            f"{os.path.basename(c)}  {v.get('verdict','')[:80]}")
        results.append(v)
    results.sort(key=lambda r: (r.get("identity_match", False), r["overall_score"]),
                 reverse=True)
    winner = results[0]
    copied = None
    if args.out and winner["overall_score"] > 0:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        shutil.copy2(winner["candidate"], args.out)
        copied = os.path.abspath(args.out)
        log(f"[referee] winner -> {copied}  (score={winner['overall_score']:.2f})")
    print(json.dumps({"ok": True, "winner": winner, "out": copied,
                      "ranked": results}))
    sys.exit(0)


if __name__ == "__main__":
    main()
