"""Run the cadence-locked re-narration on a real video and verify the result."""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from voiceswap import audio                                   # noqa: E402
from voiceswap.revoice import revoice_video, measure_drift    # noqa: E402
from voiceswap.transcribe import transcribe_words             # noqa: E402
from voiceswap.tts import make_tts                            # noqa: E402

KEY = [l.strip().split("=", 1)[1] for l in open(os.path.expanduser("~/.voiceswap.env"))
       if l.startswith("ELEVENLABS_API_KEY=")][0]
os.environ["ELEVENLABS_API_KEY"] = KEY

VIDEO = os.path.expanduser("~/Desktop/6da13117ad914df3b886f59b1e627c60.MOV")
OUT = os.path.expanduser("~/Desktop/brittney_revoiced.mov")
VOICE = "kPzsL2i3teMYv0FxEYQ6"   # Brittney - Social Media Voice

print(f"input : {VIDEO}")
print(f"output: {OUT}")
print("transcribing with Whisper 'small' (downloads once) + re-voicing...\n")

tts = make_tts(voice_id=VOICE, api_key=KEY)
summary = revoice_video(
    VIDEO, OUT, tts,
    model_name="small",
    on_progress=lambda i, n, t: print(f"  [{i}/{n}] {t}"),
)

print(f"\ntranscript ({summary['words']} words, {summary['phrases']} phrases):")
print(f"  {summary['transcript']}")

# verify timing lock
new_audio = audio.extract_audio(OUT, "/tmp/_brittney_out.wav")
drift = measure_drift(summary["orig_words"], transcribe_words(new_audio, model_name="small"))
print(f"\nsource duration : {summary['duration']:.2f}s")
print(f"output duration : {audio.probe_duration(OUT):.2f}s")
print(f"max word drift  : {drift*1000:.0f} ms")
print(f"\nDONE -> {OUT}")
