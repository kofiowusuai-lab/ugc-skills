"""Natural voice + lip-sync: the real fix for 'out of time' on a talking head.

1. Transcribe the original (Whisper) to get the script.
2. Generate Brittney NATURALLY (no warping -> no clipping).
3. Gently fit her audio to the clip length (one uniform, inaudible stretch).
4. Lip-sync the video to her audio via WaveSpeed -> the mouth follows her voice.
"""
import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from voiceswap import audio                          # noqa: E402
from voiceswap.stretch import fit_samples            # noqa: E402
from voiceswap.transcribe import transcribe_words    # noqa: E402
from voiceswap.wavespeed import make_client          # noqa: E402

env = dict(l.strip().split("=", 1) for l in open(os.path.expanduser("~/.voiceswap.env"))
           if "=" in l and not l.startswith("#"))
EL_KEY = env["ELEVENLABS_API_KEY"]
WS_KEY = env.get("WAVESPEED_API_KEY")
os.environ["ELEVENLABS_API_KEY"] = EL_KEY
os.environ["WAVESPEED_API_KEY"] = WS_KEY or ""

VIDEO = os.path.expanduser("~/Desktop/6da13117ad914df3b886f59b1e627c60.MOV")
OUT = os.path.expanduser("~/Desktop/brittney_lipsynced.mov")
VOICE = "kPzsL2i3teMYv0FxEYQ6"          # Brittney - Social Media Voice
MODEL = os.environ.get("WS_MODEL", "sync/lipsync-2")
SR = 44100


def main():
    if not WS_KEY:
        sys.exit("Add WAVESPEED_API_KEY=... to ~/.voiceswap.env first.")

    from elevenlabs import ElevenLabs
    el = ElevenLabs(api_key=EL_KEY)

    work = "/tmp/lipsync_work"
    os.makedirs(work, exist_ok=True)

    # 1) script from the original
    audio.extract_audio(VIDEO, f"{work}/orig.wav", sample_rate=SR)
    video_dur = audio.probe_duration(VIDEO)
    with contextlib.redirect_stderr(io.StringIO()):
        words = transcribe_words(f"{work}/orig.wav", model_name="small")
    script = " ".join(w.text for w in words)
    print(f"script ({len(words)} words): {script}\n")

    # 2) natural Brittney narration
    raw = f"{work}/brittney.mp3"
    with open(raw, "wb") as f:
        for ch in el.text_to_speech.convert(voice_id=VOICE, text=script,
                model_id="eleven_multilingual_v2", output_format="mp3_44100_128"):
            f.write(ch)
    audio.to_wav(raw, f"{work}/brittney.wav", sample_rate=SR)
    sr, samples = audio.load_wav(f"{work}/brittney.wav")
    nat_dur = samples.shape[0] / sr

    # 3) gentle uniform fit to the clip length (no per-word warp)
    fitted = fit_samples(samples, sr, target_duration=video_dur, tolerance=0.0)
    audio.save_wav(f"{work}/brittney_fitted.wav", sr, fitted)
    print(f"Brittney natural: {nat_dur:.2f}s -> fitted to clip {video_dur:.2f}s "
          f"(factor {video_dur/nat_dur:.3f})")

    # 4) lip-sync the video to her audio
    print(f"\nuploading + lip-syncing via WaveSpeed ({MODEL})... this can take a minute")
    client = make_client(WS_KEY)
    url = client.lipsync(VIDEO, f"{work}/brittney_fitted.wav", model=MODEL)
    client.download(url, OUT)

    print(f"\nDONE -> {OUT}")
    print(f"output duration: {audio.probe_duration(OUT):.2f}s")


if __name__ == "__main__":
    main()
