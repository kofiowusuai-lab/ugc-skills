# voiceswap

Replace the voice in a video with an ElevenLabs voice, **with the new words landing on the same frames as the original.**

Two modes, depending on what you want:

| Mode | Command | What it does | When |
|------|---------|--------------|------|
| **Voice swap** | `voiceswap` | ElevenLabs **speech-to-speech**: transforms only the *timbre* of the original audio, keeping its exact delivery. Timing perfect by construction. | Same words, same language, just change who it sounds like. |
| **Re-narrate** | `revoice` | **Whisper** transcribes the words → **ElevenLabs TTS** regenerates them → each word is warped onto its original timestamp. | Clean studio voice; the source audio is reused only as the script. |

Verified on a paced clip (phrases separated by multi-second pauses): naive TTS with no alignment drifts **5.9 s** by the end; `revoice` holds **180 ms** max word drift (Whisper's own measurement floor) — about **33x tighter**.

## Re-narrate mode (`revoice`)

```
video ─► extract audio ─► Whisper word timestamps (the script + the timing reference)
      ─► group into phrases on natural pauses
      ─► per phrase: ElevenLabs TTS with per-character timestamps
      ─► subsequence-align generated words to original words, warp each into its slot
      ─► reassemble at original offsets ─► mux onto the original video
```

```bash
python -m voiceswap.revoice_cli input.mp4 --voice <VOICE_ID>   # or: revoice input.mp4 --voice ...
# -> input.revoiced.mp4
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--voice` | (required) | ElevenLabs target voice id |
| `--out` | `<name>.revoiced.<ext>` | output path |
| `--model` | `eleven_multilingual_v2` | ElevenLabs TTS model |
| `--whisper-model` | `base` | Whisper size; `small`/`medium` tighten the timing reference |
| `--language` | auto | force transcription language |
| `--max-gap` | `0.6` | pause length (s) that starts a new phrase |
| `--api-key` | `$ELEVENLABS_API_KEY` | override the key |

Live proof, end to end (source → re-voice → measure drift vs naive):

```bash
python examples/demo_revoice_paced.py
```

## Voice-swap mode (`voiceswap`)

Uses ElevenLabs **speech-to-speech** (voice changer), which transforms only the *timbre* of the original audio while keeping its cadence, rhythm, pauses and emotion. Timing is preserved by the model rather than reconstructed, so there is no drift and the mouth still roughly matches.

## How it works (voice-swap)

```
video ─► extract audio ─► detect silences ─► speech segments (with exact start/end)
      ─► per segment: ElevenLabs speech-to-speech ─► rubberband-fit to the exact slot
      ─► reassemble on a silent canvas at original offsets (gaps preserved)
      ─► mux the new track onto the original video stream (video copied, not re-encoded)
```

The frame-lock comes from two guarantees:

1. Each chunk is **snapped to its original duration** with `rubberband` (pitch-preserving). Speech-to-speech keeps timing very close already, so the correction is tiny and inaudible, but it removes any sub-segment drift.
2. Each chunk is **placed at its original start offset** on a canvas whose length equals the source duration. Silences between chunks are preserved exactly.

## Requirements

System tools on `PATH`:

- `ffmpeg`, `ffprobe`
- `rubberband`

Python:

```bash
pip install -r requirements.txt   # elevenlabs, numpy, scipy
```

Environment:

```bash
export ELEVENLABS_API_KEY=...     # or pass --api-key
```

## Usage

```bash
python -m voiceswap input.mp4 --voice <ELEVENLABS_VOICE_ID>
# -> input.voiceswap.mp4
```

Options:

| Flag | Default | Meaning |
|------|---------|---------|
| `--voice` | (required) | ElevenLabs target voice id |
| `--out` | `<name>.voiceswap.<ext>` | output path |
| `--model` | `eleven_multilingual_sts_v2` | speech-to-speech model |
| `--noise-db` | `-30.0` | silence threshold (lower = stricter) |
| `--min-silence` | `0.5` | minimum silence (s) that splits a chunk |
| `--remove-background-noise` | off | ask ElevenLabs to denoise each chunk |
| `--api-key` | `$ELEVENLABS_API_KEY` | override the key |
| `--sample-rate` | `44100` | working sample rate |

Find a voice id with the ElevenLabs SDK:

```python
from elevenlabs import ElevenLabs
for v in ElevenLabs().voices.get_all().voices:
    print(v.voice_id, v.name)
```

## Programmatic use

```python
from voiceswap.pipeline import process_video
from voiceswap.sts import make_converter

conv = make_converter(voice_id="VOICE_ID")
process_video("input.mp4", "out.mp4", conv, on_progress=lambda i, n: print(i, n))
```

Any object with `convert_file(in_wav, out_path)` works as a converter, so the pipeline is testable without network calls.

## Tests

```bash
python -m pytest -q
```

The suite drives the **entire pipeline end-to-end** (real ffmpeg extract / silence-detect / `rubberband` stretch / mux) using an identity converter in place of ElevenLabs, so it is deterministic, offline and free. The only thing not exercised is the live ElevenLabs call itself, which is isolated behind `voiceswap/sts.py` and unit-tested with a fake SDK client.

## Notes / limits

- **Voice-only audio.** This path replaces the whole audio track. If your video has music or SFX under the voice, add a `demucs --two-stems=vocals` step before conversion and mix the `no_vocals` stem back in. (Left out here by design, the chosen scope was voice-only.)
- Speech-to-speech keeps the **original words and language**. To change the script or translate, that is a different pipeline (transcribe → align → TTS → fit) or the ElevenLabs Dubbing API.
- Long videos are chunked on silence, so very long monologues with no pauses become one large chunk; tune `--min-silence` / `--noise-db` if you want finer splits.
