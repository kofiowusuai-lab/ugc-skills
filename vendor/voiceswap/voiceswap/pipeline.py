"""End-to-end voice swap with timing preserved.

    video  ->  extract audio  ->  detect silences  ->  speech segments
           ->  per segment: speech-to-speech -> fit to exact slot
           ->  reassemble on a silent canvas at original offsets
           ->  mux back onto the original video

Because each chunk is snapped to its original duration and placed at its
original start, the rebuilt track stays frame-locked to the picture.
"""
import os
import tempfile
from typing import Callable, Optional

from . import audio
from .assemble import assemble
from .segment import compute_speech_segments
from .stretch import fit_samples

ProgressFn = Callable[[int, int], None]


def process_video(
    video_path: str,
    out_path: str,
    converter,
    sample_rate: int = 44100,
    noise_db: float = -30.0,
    min_silence: float = 0.5,
    fit_tolerance: float = 0.02,
    on_progress: Optional[ProgressFn] = None,
) -> str:
    """Replace the voice in ``video_path`` and write the result to ``out_path``.

    ``converter`` is any object with ``convert_file(in_wav, out_path)`` (an
    :class:`voiceswap.sts.ElevenLabsConverter` in production, an identity stub
    in tests).
    """
    with tempfile.TemporaryDirectory() as work:
        full_wav = os.path.join(work, "full.wav")
        audio.extract_audio(video_path, full_wav, sample_rate=sample_rate)

        sr, samples = audio.load_wav(full_wav)
        total_duration = samples.shape[0] / sr

        silences = audio.detect_silences(
            full_wav, noise_db=noise_db, min_silence=min_silence
        )
        segments = compute_speech_segments(total_duration, silences, min_silence)

        placed = []
        total = len(segments)
        for idx, (start, end) in enumerate(segments, start=1):
            seg_samples = samples[int(round(start * sr)): int(round(end * sr))]

            seg_in = os.path.join(work, f"seg_{idx}_in.wav")
            audio.save_wav(seg_in, sr, seg_samples)

            seg_raw = os.path.join(work, f"seg_{idx}_raw")
            converter.convert_file(seg_in, seg_raw)

            seg_wav = os.path.join(work, f"seg_{idx}_out.wav")
            audio.to_wav(seg_raw, seg_wav, sample_rate=sr)
            _, converted = audio.load_wav(seg_wav)

            fitted = fit_samples(
                converted, sr, target_duration=end - start, tolerance=fit_tolerance
            )
            placed.append((start, fitted))

            if on_progress:
                on_progress(idx, total)

        track = assemble(placed, sr, total_duration)
        new_wav = os.path.join(work, "new.wav")
        audio.save_wav(new_wav, sr, track)

        audio.mux_audio(video_path, new_wav, out_path)

    return out_path
