#!/usr/bin/env python3
"""
ugc_captions.py - word-level caption timings for the motion-graphics layer.

Extracts the audio from a video, transcribes it with word timestamps, and writes
a JSON array [{"text","start","end"}, ...] that the Remotion MotionVideo
composition turns into kinetic captions.

Backends, auto-selected:
  1. whisper.cpp (`whisper-cli`) if a ggml model is found — fast (Metal).
  2. openai-whisper (python) otherwise — auto-downloads a model.

USAGE
  ugc_captions.py --video in.mp4 --out words.json [--model base.en]
Prints {"ok":true,"count":N,"out":"..."} or {"ok":false,"error":...}.
"""
import argparse, json, os, shutil, subprocess, sys, glob, tempfile

def emit(obj, code=0):
    print(json.dumps(obj)); sys.exit(code)

def extract_wav(video, wav):
    subprocess.run(["ffmpeg", "-y", "-i", video, "-ar", "16000", "-ac", "1", wav],
                   capture_output=True, text=True)
    return os.path.exists(wav) and os.path.getsize(wav) > 1000

def find_ggml_model():
    cands = []
    for base in ("~/.hermes/skills/mlops/models/whisper", "~/.cache/whisper",
                 "~/whisper.cpp/models", "/opt/homebrew/share/whisper-cpp"):
        cands += glob.glob(os.path.expanduser(os.path.join(base, "ggml-*.bin")))
    # prefer english base/small
    for pref in ("base.en", "small.en", "base", "small", "medium.en", "medium"):
        for c in cands:
            if pref in os.path.basename(c):
                return c
    return cands[0] if cands else None

def via_whisper_cpp(wav, model):
    binp = shutil.which("whisper-cli") or shutil.which("whisper-cpp")
    if not binp:
        return None
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "out")
        # -ml 1 => one word per segment (word-level timestamps); -oj => json
        r = subprocess.run([binp, "-m", model, "-f", wav, "-ml", "1", "-oj", "-of", base],
                           capture_output=True, text=True)
        jf = base + ".json"
        if not os.path.exists(jf):
            return None
        data = json.load(open(jf))
        words = []
        for seg in data.get("transcription", []):
            off = seg.get("offsets", {})
            txt = (seg.get("text") or "").strip()
            if not txt:
                continue
            words.append({"text": txt,
                          "start": round(off.get("from", 0) / 1000.0, 3),
                          "end": round(off.get("to", 0) / 1000.0, 3)})
        return words or None

def via_openai_whisper(wav, model_name):
    try:
        import whisper
    except Exception:
        return None
    model = whisper.load_model(model_name if model_name else "base.en")
    r = model.transcribe(wav, word_timestamps=True)
    words = []
    for seg in r.get("segments", []):
        for w in seg.get("words", []):
            t = (w.get("word") or "").strip()
            if t:
                words.append({"text": t, "start": round(float(w["start"]), 3),
                              "end": round(float(w["end"]), 3)})
    return words or None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="base.en")
    args = ap.parse_args()
    if not os.path.exists(args.video):
        emit({"ok": False, "error": f"video not found: {args.video}"}, 1)

    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "a.wav")
        if not extract_wav(args.video, wav):
            emit({"ok": False, "error": "could not extract audio (silent clip?)"}, 1)
        words = None
        ggml = find_ggml_model()
        if ggml:
            try:
                words = via_whisper_cpp(wav, ggml)
            except Exception:
                words = None
        if not words:
            try:
                words = via_openai_whisper(wav, args.model)
            except Exception as e:
                emit({"ok": False, "error": f"transcription failed: {e}"}, 1)
        if not words:
            emit({"ok": False, "error": "no words transcribed"}, 1)

    json.dump(words, open(args.out, "w"))
    emit({"ok": True, "count": len(words), "out": os.path.abspath(args.out)})

if __name__ == "__main__":
    main()
