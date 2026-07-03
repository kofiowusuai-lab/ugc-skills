#!/usr/bin/env python3
"""
ugc_sfx_pack.py - generate + cache a sound-effects pack for the motion-graphics
layer, using ElevenLabs text-to-sound-effects. Idempotent: only generates what's
missing. Files land in ~/.openclaw/motion-graphics/public/sfx/ so the Remotion
composition can play them via staticFile.

Pack (name -> prompt, duration):
  whoosh   transition whoosh between cuts
  riser    rising tension build-up into a reveal
  impact   punchy hit on a stat/number reveal
  drop     deep bass drop on a big reveal
  pop      short ui pop for keyword/word emphasis
  swoosh   exit swoosh leaving a graphic

USAGE
  ugc_sfx_pack.py            # generate any missing sfx
  ugc_sfx_pack.py --force    # regenerate all
  ugc_sfx_pack.py --list     # print the cached pack as JSON {name: path}
Prints {"ok":true,"pack":{name:path,...}} or {"ok":false,"error":...}.
"""
import argparse, json, os, sys
from pathlib import Path

SFX_DIR = Path.home() / ".openclaw" / "motion-graphics" / "public" / "sfx"
ENV_FILES = [Path.home() / ".openclaw" / ".env", Path.home() / ".hermes" / ".env"]

PACK = {
    "whoosh": ("fast clean cinematic whoosh transition, short, no music", 1.0),
    "riser":  ("rising tension riser build up, whoosh swell into a hit, cinematic", 1.6),
    "impact": ("punchy deep impact hit, trailer boom, short", 1.0),
    "drop":   ("deep sub bass drop, low boom, cinematic", 1.4),
    "pop":    ("short crisp UI pop click, subtle", 0.5),
    "swoosh": ("soft swoosh out transition, short", 0.8),
}

def load_key():
    if os.environ.get("ELEVENLABS_API_KEY"):
        return os.environ["ELEVENLABS_API_KEY"]
    for f in ENV_FILES:
        if f.exists():
            for line in f.read_text().splitlines():
                line = line.strip()
                if line.startswith("ELEVENLABS_API_KEY=") and "=" in line:
                    return line.split("=", 1)[1].strip()
    return ""

def fail(msg):
    print(json.dumps({"ok": False, "error": msg})); sys.exit(1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    SFX_DIR.mkdir(parents=True, exist_ok=True)

    if args.list:
        pack = {n: str(SFX_DIR / f"{n}.mp3") for n in PACK if (SFX_DIR / f"{n}.mp3").exists()}
        print(json.dumps({"ok": True, "pack": pack})); return

    missing = [n for n in PACK if args.force or not (SFX_DIR / f"{n}.mp3").exists()]
    if missing:
        key = load_key()
        if not key:
            fail("ELEVENLABS_API_KEY not found")
        try:
            from elevenlabs import ElevenLabs
        except Exception as e:
            fail(f"elevenlabs SDK missing: {e}")
        client = ElevenLabs(api_key=key)
        for name in missing:
            prompt, dur = PACK[name]
            out = SFX_DIR / f"{name}.mp3"
            try:
                audio = client.text_to_sound_effects.convert(
                    text=prompt, duration_seconds=float(dur), prompt_influence=0.6)
                with open(out, "wb") as f:
                    if isinstance(audio, (bytes, bytearray)):
                        f.write(audio)
                    else:
                        for chunk in audio:
                            if chunk:
                                f.write(chunk)
            except Exception as e:
                fail(f"sfx '{name}' failed: {e}")

    pack = {n: str(SFX_DIR / f"{n}.mp3") for n in PACK if (SFX_DIR / f"{n}.mp3").exists()}
    print(json.dumps({"ok": True, "pack": pack, "generated": missing}))

if __name__ == "__main__":
    main()
