#!/usr/bin/env python3
"""
ugc_gemini_text.py - Gemini text/JSON generation, the FALLBACK brain for the UGC
text stages (shot planning + scriptwriting) when the headless Claude agent is
unavailable or fails.

It takes a prompt (the SAME prompt the Claude agent would get), runs it on
Gemini, and writes the result to --out. With --expect json it forces
responseMimeType=application/json so Gemini returns pure JSON (ignoring any "use
the Write tool / also print ..." lines carried over from the Claude prompt), then
validates the JSON parses and contains the required top-level keys. This mirrors
the existing success bar of the stage scripts (python3 -c json.load(open(OUT))).

Default model gemini-2.5-pro with an automatic Pro->Flash retry, plus 503/429
backoff (same resilience pattern as ugc_gemini_referee.py / analyze-youtube-references.py).

USAGE
  ugc_gemini_text.py --prompt-file P --out OUT --expect json \
      --require-keys format,people,frames [--model gemini-2.5-pro] [--system S]
  ugc_gemini_text.py --prompt "return {\"foo\":1}" --out t.json --expect json --require-keys foo
  cat prompt.txt | ugc_gemini_text.py --stdin --out OUT --expect json
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ENV_FILE = Path.home() / ".openclaw" / ".env"
DEFAULT_MODEL = os.environ.get("UGC_GEMINI_MODEL", "gemini-2.5-pro")
FALLBACK_MODEL = "gemini-2.5-flash"


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
    print(f"[gemini-text] {msg}", file=sys.stderr)


def call_gemini(prompt: str, api_key: str, model: str, expect: str,
                system: str = "", max_tokens: int = 8000) -> str:
    gen_cfg = {"temperature": 0.6 if expect == "text" else 0.4,
               "maxOutputTokens": max_tokens}
    if expect == "json":
        gen_cfg["responseMimeType"] = "application/json"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen_cfg}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    body = json.dumps(payload).encode()

    models_to_try = [model]
    if FALLBACK_MODEL != model:
        models_to_try.append(FALLBACK_MODEL)

    last = None
    for chosen in models_to_try:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{chosen}:generateContent?key={api_key}")
        for attempt in range(5):
            try:
                req = urllib.request.Request(
                    url, data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=300) as resp:
                    result = json.loads(resp.read().decode())
                cands = result.get("candidates")
                if not cands:
                    block = (result.get("promptFeedback", {}) or {}).get("blockReason", "none")
                    raise RuntimeError(f"no candidates returned (blockReason={block})")
                cand = cands[0]
                parts = cand.get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
                if not text.strip():
                    raise RuntimeError(f"empty response (finishReason="
                                       f"{cand.get('finishReason')})")
                if chosen != model:
                    log(f"used fallback model {chosen}")
                return text
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (503, 429, 500) and attempt < 4:
                    time.sleep([10, 20, 40, 60][attempt])
                    continue
                detail = ""
                try:
                    detail = e.read().decode()[:200]
                except Exception:
                    pass
                log(f"{chosen} HTTP {e.code}: {detail}")
                break  # try next model
            except Exception as e:
                last = e
                if attempt < 4:
                    time.sleep(5)
                    continue
                log(f"{chosen} error: {e}")
                break
    raise RuntimeError(f"all Gemini attempts failed: {last}")


def coerce_json(text: str) -> str:
    """Return a clean JSON string from a model response (strip code fences / prose)."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t).strip()
    try:
        json.loads(t)
        return t
    except Exception:
        pass
    # Fall back to the outermost {...} or [...] span.
    start = min((i for i in (t.find("{"), t.find("[")) if i != -1), default=-1)
    if start != -1:
        for end in range(len(t), start, -1):
            chunk = t[start:end]
            try:
                json.loads(chunk)
                return chunk
            except Exception:
                continue
    raise ValueError("response was not valid JSON")


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--prompt-file")
    src.add_argument("--prompt")
    src.add_argument("--stdin", action="store_true")
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect", choices=["json", "text"], default="json")
    ap.add_argument("--require-keys", default="")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--system", default="")
    ap.add_argument("--max-tokens", type=int, default=8000)
    args = ap.parse_args()

    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text()
    elif args.prompt:
        prompt = args.prompt
    else:
        prompt = sys.stdin.read()
    if not prompt.strip():
        sys.exit("ERROR: empty prompt")

    api_key = load_api_key()
    if not api_key:
        sys.exit("ERROR: GEMINI_API_KEY not set in ~/.openclaw/.env")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    log(f"model={args.model} expect={args.expect} -> {out}")
    try:
        text = call_gemini(prompt, api_key, args.model, args.expect,
                           args.system, args.max_tokens)
    except Exception as e:
        sys.exit(f"ERROR: {e}")

    if args.expect == "json":
        try:
            clean = coerce_json(text)
            obj = json.loads(clean)
        except Exception as e:
            out.with_suffix(out.suffix + ".raw").write_text(text)
            sys.exit(f"ERROR: model did not return valid JSON: {e} "
                     f"(raw saved to {out}.raw)")
        req = [k.strip() for k in args.require_keys.split(",") if k.strip()]
        missing = [k for k in req if not (isinstance(obj, dict) and k in obj)]
        if missing:
            out.with_suffix(out.suffix + ".raw").write_text(text)
            sys.exit(f"ERROR: JSON missing required keys: {missing} "
                     f"(raw saved to {out}.raw)")
        out.write_text(json.dumps(obj, indent=2))
    else:
        out.write_text(text)

    log(f"wrote {out}")
    sys.exit(0)


if __name__ == "__main__":
    main()
