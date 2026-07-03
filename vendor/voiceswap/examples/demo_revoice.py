"""Live end-to-end proof of the cadence-locked re-narration pipeline.

Builds a source 'video' (color + speech in voice A), re-voices it in voice B,
then transcribes the result and reports how far each word drifted from the
original timing. Run: python examples/demo_revoice.py
"""
import base64
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from voiceswap import audio              # noqa: E402
from voiceswap.revoice import revoice_video, measure_drift  # noqa: E402
from voiceswap.transcribe import transcribe_words           # noqa: E402
from voiceswap.tts import make_tts       # noqa: E402

KEY = [l.strip().split("=", 1)[1] for l in open(os.path.expanduser("~/.voiceswap.env"))
       if l.startswith("ELEVENLABS_API_KEY=")][0]
os.environ["ELEVENLABS_API_KEY"] = KEY

VOICE_A = "JBFqnCBsd6RMkjVDRZzb"   # George (source)
VOICE_B = "EXAVITQu4vr4xnSDxMaL"   # Sarah  (target)
SENTENCE = ("The quick brown fox jumps over the lazy dog, "
            "and then the sun sets slowly behind the hills.")


def main():
    work = tempfile.mkdtemp(prefix="revoice_demo_")
    from elevenlabs import ElevenLabs
    client = ElevenLabs(api_key=KEY)

    # 1) source speech in voice A
    src_mp3 = os.path.join(work, "src.mp3")
    a = client.text_to_speech.convert(voice_id=VOICE_A, text=SENTENCE,
                                      model_id="eleven_multilingual_v2",
                                      output_format="mp3_44100_128")
    with open(src_mp3, "wb") as f:
        for ch in a:
            f.write(ch)
    src_wav = audio.to_wav(src_mp3, os.path.join(work, "src.wav"))
    dur = audio.probe_duration(src_wav)

    # 2) wrap it in a video
    src_video = os.path.join(work, "source.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=25",
                    "-i", src_wav, "-t", f"{dur:.3f}", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", src_video], check=True)
    print(f"source: {dur:.2f}s, voice A -> {src_video}")

    # 3) re-voice in voice B, cadence-locked
    out_video = os.path.join(work, "revoiced.mp4")
    tts = make_tts(voice_id=VOICE_B, api_key=KEY)
    summary = revoice_video(src_video, out_video, tts,
                            on_progress=lambda i, n, t: print(f"  [{i}/{n}] {t}"))
    print(f"revoiced -> {out_video}")
    print(f"transcript: {summary['transcript']}")

    # 4) verify: transcribe the output, compare word starts to the original
    new_audio = audio.extract_audio(out_video, os.path.join(work, "out.wav"))
    new_words = transcribe_words(new_audio)
    drift = measure_drift(summary["orig_words"], new_words)

    # baseline: voice B spoken naturally (no alignment), placed from t=0
    nat = client.text_to_speech.convert(voice_id=VOICE_B, text=summary["transcript"],
                                        model_id="eleven_multilingual_v2",
                                        output_format="mp3_44100_128")
    nat_mp3 = os.path.join(work, "naive.mp3")
    with open(nat_mp3, "wb") as f:
        for ch in nat:
            f.write(ch)
    nat_wav = audio.to_wav(nat_mp3, os.path.join(work, "naive.wav"))
    nat_words = transcribe_words(nat_wav)
    naive_drift = measure_drift(summary["orig_words"], nat_words)

    print(f"\noriginal words: {len(summary['orig_words'])}  "
          f"aligned output words: {len(new_words)}")
    print(f"output duration: {audio.probe_duration(out_video):.2f}s "
          f"(source {dur:.2f}s)")
    print("\n--- max word-start drift vs original cadence ---")
    print(f"  naive (no alignment): {naive_drift*1000:4.0f} ms")
    print(f"  cadence-locked      : {drift*1000:4.0f} ms")
    print(f"  tightened ~{naive_drift/max(drift,1e-6):.1f}x")
    print(f"\nartifacts in: {work}")


if __name__ == "__main__":
    main()
