#!/usr/bin/env python3
"""
ugc_add_voice.py - On-demand voice swap for a UGC clip (speech-to-speech).

DEFAULT BEHAVIOUR OF THE PIPELINE IS TO KEEP GROK'S NATIVE VOICE. This tool is
the opt-in path: run it ONLY when the user says "add a voice" / "swap the voice" /
"use <name>'s voice" on a clip. It applies ElevenLabs speech-to-speech (timbre
swap) which preserves the original timing, so Grok's lip-sync still lines up.

The ElevenLabs key is already in the environment (ELEVENLABS_API_KEY in
~/.openclaw/.env and ~/.hermes/.env) - nothing to set up.

USAGE
  ugc_add_voice.py --clip in.mp4 --voice eric                 # -> in_voiced.mp4
  ugc_add_voice.py --clip in.mp4 --voice kPzsL2i3teMYv0FxEYQ6 --out out.mp4
  ugc_add_voice.py --list                                     # show named voices

--voice accepts a friendly NAME from the registry below or a raw ElevenLabs
voice_id (a cloned voice is a drop-in: pass its id). Output keeps the original
video stream untouched and only replaces the audio.

Prints ONE JSON line: {"ok": true, "out": "...", "voice": "...", "voice_id": "..."}
or {"ok": false, "error": "...", "reason_code": "..."}.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Friendly name -> ElevenLabs voice_id. Match gender + age to the on-screen face
# (UGC QA Bank D5). These are stock ElevenLabs library voices, safe to use with
# any account. Add your OWN cloned voice by dropping a line here (name -> voice_id)
# or by setting UGC_MY_VOICE=<name>=<voice_id> in the environment, or just pass a
# raw voice_id to --voice.
VOICE_REGISTRY = {
    "brittney": "kPzsL2i3teMYv0FxEYQ6",  # female, casual social-media voice (default female)
    "eric":     "cjVigY5qzO86Huf0OWal",  # male, smooth/trustworthy (default male educator)
    "charlie":  "IKne3meq5aSn9XLyUdCD",  # male, deep/confident/energetic
    "liam":     "TX3LPaxmHKxFdv7VOQHJ",  # male, energetic social-media creator
    "brian":    "nPczCjzI2devNBz1zQrb",  # male, deep/authority
}

# Optional: register your own cloned voice without editing this file.
#   export UGC_MY_VOICE="me=<your_elevenlabs_voice_id>"
_my = os.environ.get("UGC_MY_VOICE", "")
if "=" in _my:
    _name, _vid = _my.split("=", 1)
    if _name.strip() and _vid.strip():
        VOICE_REGISTRY[_name.strip()] = _vid.strip()

# Per-voice STS setting overrides. A voice's stored ElevenLabs defaults can carry
# accent-drift settings (high style / maxed stability) that push an unwanted
# accent onto every swap. Override style->0 keeps the source accent. Add an entry
# keyed by voice_id for any cloned voice that drifts.
VOICE_SETTINGS = {}

VOICESWAP_DIR = str(Path.home() / "voiceswap")
ENV_FILES = [Path.home() / ".openclaw" / ".env", Path.home() / ".hermes" / ".env"]


def fail(error, reason_code, **extra):
    print(json.dumps({"ok": False, "error": str(error), "reason_code": reason_code, **extra}))
    sys.exit(1)


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


def resolve_voice(v):
    key = v.strip().lower()
    if key in VOICE_REGISTRY:
        return VOICE_REGISTRY[key], key
    # treat as a raw ElevenLabs voice_id (incl. cloned voices)
    return v.strip(), v.strip()


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main():
    ap = argparse.ArgumentParser(description="Voice-swap a UGC clip (STS).")
    ap.add_argument("--clip", help="input video clip")
    ap.add_argument("--voice", help="registry name or raw ElevenLabs voice_id")
    ap.add_argument("--out", help="output video path (default: <clip>_voiced.mp4)")
    ap.add_argument("--model", default="eleven_multilingual_sts_v2",
                    help="ElevenLabs STS model id")
    ap.add_argument("--list", action="store_true", help="list named voices and exit")
    args = ap.parse_args()

    if args.list:
        print(json.dumps({"ok": True, "voices": VOICE_REGISTRY}, indent=2))
        sys.exit(0)
    if not args.clip or not args.voice:
        fail("--clip and --voice are required (or use --list)", "bad_args")
    if not os.path.exists(args.clip):
        fail(f"clip not found: {args.clip}", "bad_args")

    api_key = load_key()
    if not api_key:
        fail("ELEVENLABS_API_KEY not found in env or ~/.openclaw/.env", "no_key")

    voice_id, voice_label = resolve_voice(args.voice)
    out = args.out or str(Path(args.clip).with_suffix("")) + "_voiced.mp4"

    with tempfile.TemporaryDirectory() as tmp:
        src_wav = os.path.join(tmp, "src.wav")
        out_audio = os.path.join(tmp, "swapped.mp3")

        # 1) pull the clip's audio to a clean wav
        r = run(["ffmpeg", "-y", "-i", args.clip, "-vn", "-ac", "1", "-ar", "44100",
                 "-c:a", "pcm_s16le", src_wav])
        if not os.path.exists(src_wav) or os.path.getsize(src_wav) == 0:
            fail(f"could not extract audio from clip: {r.stderr[-300:]}", "no_audio")

        # 2) speech-to-speech: swap timbre, keep timing (lip-sync preserved).
        # Calls the ElevenLabs SDK directly (pip install elevenlabs). Any per-voice
        # setting override in VOICE_SETTINGS is passed through so a cloned voice
        # never inherits accent-drift defaults stored on the voice.
        settings = VOICE_SETTINGS.get(voice_id)
        sts = (
            "import os,sys,io,json\n"
            "from elevenlabs import ElevenLabs\n"
            "cl = ElevenLabs(api_key=os.environ['ELEVENLABS_API_KEY'])\n"
            "data = open(%r,'rb').read(); a = io.BytesIO(data); a.name='src.wav'\n"
            "kw = dict(voice_id=%r, audio=a, model_id=%r,\n"
            "    output_format='mp3_44100_128', remove_background_noise=True)\n"
            "s = %r\n"
            "if s: kw['voice_settings'] = json.dumps(s)\n"
            "res = cl.speech_to_speech.convert(**kw)\n"
            "out=open(%r,'wb')\n"
            "out.write(res) if isinstance(res,(bytes,bytearray)) else [out.write(c) for c in res if c]\n"
            "out.close()\n"
            % (src_wav, voice_id, args.model, settings, out_audio)
        )
        env = dict(os.environ, ELEVENLABS_API_KEY=api_key)
        r = run([sys.executable, "-c", sts], env=env)
        if not os.path.exists(out_audio) or os.path.getsize(out_audio) == 0:
            fail(f"STS conversion failed: {r.stderr[-500:] or r.stdout[-300:]}",
                 "sts_error", voice=voice_label, voice_id=voice_id)

        # 3) mux swapped audio back onto the original video (video untouched)
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        r = run(["ffmpeg", "-y", "-i", args.clip, "-i", out_audio,
                 "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                 "-c:a", "aac", "-b:a", "192k", "-shortest", out])
        if not os.path.exists(out) or os.path.getsize(out) == 0:
            fail(f"mux failed: {r.stderr[-300:]}", "mux_error")

    print(json.dumps({"ok": True, "out": os.path.abspath(out),
                      "voice": voice_label, "voice_id": voice_id, "model": args.model}))
    sys.exit(0)


if __name__ == "__main__":
    main()
