"""Proof on a *paced* source: phrases separated by long pauses, the case where
natural TTS drifts badly and cadence-locking matters.

Builds a source whose phrases are spaced out with multi-second gaps (like real
speech with dramatic pauses), re-voices it, and compares naive vs locked drift.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from voiceswap import audio                                   # noqa: E402
from voiceswap.revoice import revoice_video, measure_drift    # noqa: E402
from voiceswap.transcribe import transcribe_words             # noqa: E402
from voiceswap.tts import make_tts                            # noqa: E402

KEY = [l.strip().split("=", 1)[1] for l in open(os.path.expanduser("~/.voiceswap.env"))
       if l.startswith("ELEVENLABS_API_KEY=")][0]
os.environ["ELEVENLABS_API_KEY"] = KEY

VOICE_A = "JBFqnCBsd6RMkjVDRZzb"   # George (source)
VOICE_B = "EXAVITQu4vr4xnSDxMaL"   # Sarah  (target)
SR = 44100

# (text, seconds of silence BEFORE this phrase)
PHRASES = [
    ("This is the opening line.", 0.0),
    ("Then, after a long pause, it continues.", 2.5),
    ("A shorter beat.", 1.5),
    ("And finally, the closing thought.", 2.0),
]


def synth(client, voice, text, work, name):
    from_bytes = client.text_to_speech.convert(voice_id=voice, text=text,
                    model_id="eleven_multilingual_v2", output_format="mp3_44100_128")
    mp3 = os.path.join(work, name + ".mp3")
    with open(mp3, "wb") as f:
        for ch in from_bytes:
            f.write(ch)
    wav = audio.to_wav(mp3, os.path.join(work, name + ".wav"), sample_rate=SR)
    _, samples = audio.load_wav(wav)
    return samples


def main():
    work = tempfile.mkdtemp(prefix="revoice_paced_")
    from elevenlabs import ElevenLabs
    client = ElevenLabs(api_key=KEY)

    # 1) build a paced source in voice A: phrase, gap, phrase, gap...
    timeline = np.array([], dtype=np.float32)
    for i, (text, gap) in enumerate(PHRASES):
        if gap:
            timeline = np.concatenate([timeline, np.zeros(int(gap * SR), dtype=np.float32)])
        timeline = np.concatenate([timeline, synth(client, VOICE_A, text, work, f"a{i}")])
    src_wav = audio.save_wav(os.path.join(work, "src.wav"), SR, timeline)
    dur = len(timeline) / SR

    src_video = os.path.join(work, "source.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25",
                    "-i", src_wav, "-t", f"{dur:.3f}", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", src_video], check=True)
    print(f"paced source: {dur:.2f}s with multi-second gaps -> voice A")

    # 2) re-voice in voice B, cadence-locked
    out_video = os.path.join(work, "revoiced.mp4")
    tts = make_tts(voice_id=VOICE_B, api_key=KEY)
    summary = revoice_video(src_video, out_video, tts,
                            on_progress=lambda i, n, t: print(f"  [{i}/{n}] {t}"))

    new_audio = audio.extract_audio(out_video, os.path.join(work, "out.wav"))
    drift = measure_drift(summary["orig_words"], transcribe_words(new_audio))

    # 3) naive baseline: voice B speaks the whole transcript continuously from t=0
    nat = synth(client, VOICE_B, summary["transcript"], work, "naive")
    nat_wav = audio.save_wav(os.path.join(work, "naive_only.wav"), SR, nat)
    naive_drift = measure_drift(summary["orig_words"], transcribe_words(nat_wav))

    print(f"\nphrases: {summary['phrases']}  words: {summary['words']}")
    print(f"output duration: {audio.probe_duration(out_video):.2f}s (source {dur:.2f}s)")
    print("\n--- max word-start drift vs original cadence ---")
    print(f"  naive (no alignment): {naive_drift*1000:5.0f} ms")
    print(f"  cadence-locked      : {drift*1000:5.0f} ms")
    print(f"  tightened ~{naive_drift/max(drift,1e-6):.1f}x")
    print(f"\nartifacts in: {work}")


if __name__ == "__main__":
    main()
