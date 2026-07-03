#!/usr/bin/env python3
"""
voice_and_lipsync.py — give a Grok character clip a natural ElevenLabs voice and
lip-sync the mouth to it. Generalized from ~/voiceswap/examples/run_lipsync.py.

Two ways to get the script:
  --script "exact words she should say"      (scripted ad copy)
  (omit)  -> transcribe the clip's native Grok audio and reuse those words

Pipeline: ElevenLabs TTS (natural, no warp) -> uniform stretch to the clip length
-> WaveSpeed sync/lipsync-2 retargets the mouth to her new voice.

Requires ~/.voiceswap.env with ELEVENLABS_API_KEY and (for lipsync) WAVESPEED_API_KEY.
If WAVESPEED_API_KEY is missing, pass --no-lipsync to just mux the new voice on
(mouth won't be re-synced) so you still get a voiced clip.

Examples:
  python3 voice_and_lipsync.py --clip shot1.mp4 --script "Okay so this book..." \
      --voice kPzsL2i3teMYv0FxEYQ6 --out shot1_voiced.mp4
  python3 voice_and_lipsync.py --clip shot1.mp4 --no-lipsync --out shot1_voiced.mp4
"""
import argparse, contextlib, io, os, subprocess, sys

VOICESWAP = os.path.expanduser("~/voiceswap")
sys.path.insert(0, VOICESWAP)

from voiceswap import audio
from voiceswap.stretch import fit_samples

SR = 44100
DEFAULT_VOICE = "kPzsL2i3teMYv0FxEYQ6"  # Brittney - Social Media Voice (casual UGC)


def load_env():
    p = os.path.expanduser("~/.voiceswap.env")
    env = {}
    if os.path.exists(p):
        for l in open(p):
            l = l.strip()
            if "=" in l and not l.startswith("#"):
                k, v = l.split("=", 1); env[k] = v
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--script", help="exact words to speak; omit to reuse the clip's transcript")
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--el-model", default="eleven_multilingual_v2")
    ap.add_argument("--ws-model", default="sync/lipsync-2")
    ap.add_argument("--whisper", default="small")
    ap.add_argument("--no-lipsync", action="store_true",
                    help="skip WaveSpeed; just mux the new voice (use if no WaveSpeed key)")
    a = ap.parse_args()

    env = load_env()
    EL = env.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVENLABS_API_KEY")
    WS = env.get("WAVESPEED_API_KEY") or os.environ.get("WAVESPEED_API_KEY")
    if not EL:
        sys.exit("ELEVENLABS_API_KEY missing (add to ~/.voiceswap.env)")
    os.environ["ELEVENLABS_API_KEY"] = EL

    work = "/tmp/vls_work"; os.makedirs(work, exist_ok=True)
    video_dur = audio.probe_duration(a.clip)

    # 1) script
    script = a.script
    if not script:
        audio.extract_audio(a.clip, f"{work}/orig.wav", sample_rate=SR)
        from voiceswap.transcribe import transcribe_words
        with contextlib.redirect_stderr(io.StringIO()):
            words = transcribe_words(f"{work}/orig.wav", model_name=a.whisper)
        script = " ".join(w.text for w in words)
    print(f"script: {script}\n")

    # 2) natural ElevenLabs narration (UGC casual settings)
    from elevenlabs import ElevenLabs, VoiceSettings
    el = ElevenLabs(api_key=EL)
    raw = f"{work}/voice.mp3"
    with open(raw, "wb") as f:
        for ch in el.text_to_speech.convert(
                voice_id=a.voice, text=script, model_id=a.el_model,
                output_format="mp3_44100_128",
                voice_settings=VoiceSettings(stability=0.45, similarity_boost=0.75,
                                             style=0.30, use_speaker_boost=True)):
            f.write(ch)
    audio.to_wav(raw, f"{work}/voice.wav", sample_rate=SR)
    sr, samples = audio.load_wav(f"{work}/voice.wav")
    nat = samples.shape[0] / sr

    # 3) gentle uniform fit to clip length (no per-word warp)
    fitted = fit_samples(samples, sr, target_duration=video_dur, tolerance=0.0)
    audio.save_wav(f"{work}/voice_fit.wav", sr, fitted)
    print(f"voice {nat:.2f}s -> fit {video_dur:.2f}s (x{video_dur/nat:.3f})")

    # 4) lip-sync or plain mux
    if a.no_lipsync or not WS:
        if not a.no_lipsync and not WS:
            print("WARNING: WAVESPEED_API_KEY missing -> muxing voice WITHOUT lip-sync. "
                  "Add the key to ~/.voiceswap.env for real lip-sync.")
        # 0:V:0 = main video only (excludes Grok's embedded mjpeg cover-art stream,
        # which otherwise truncates the mux to a single frame under -shortest)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", a.clip, "-i", f"{work}/voice_fit.wav",
                        "-map", "0:V:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                        "-shortest", a.out], check=True)
    else:
        from voiceswap.wavespeed import make_client
        print(f"lip-syncing via WaveSpeed ({a.ws_model})...")
        client = make_client(WS)
        url = client.lipsync(a.clip, f"{work}/voice_fit.wav", model=a.ws_model)
        client.download(url, a.out)
    print(f"done -> {a.out}  ({audio.probe_duration(a.out):.2f}s)")


if __name__ == "__main__":
    main()
