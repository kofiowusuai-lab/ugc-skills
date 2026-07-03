"""Pitch-preserving time-stretch so each converted chunk fits its slot exactly.

Speech-to-speech keeps cadence very close to the source, but "very close" still
drifts over a long video. We snap every chunk to its original duration with the
``rubberband`` CLI (high quality, formant/pitch preserved), then hard-trim/pad
to the exact sample count so assembly is frame-perfect.
"""
import os
import subprocess
import tempfile
import warnings
from typing import Callable

import numpy as np
from scipy.io import wavfile
from scipy.io.wavfile import WavFileWarning


def time_factor(src_duration: float, target_duration: float) -> float:
    """rubberband time factor: output_len / input_len = target / src."""
    if src_duration <= 0:
        raise ValueError("src_duration must be positive")
    return target_duration / src_duration


def _snap(samples: np.ndarray, target_len: int) -> np.ndarray:
    """Trim or zero-pad to an exact sample count."""
    if samples.shape[0] > target_len:
        return samples[:target_len]
    if samples.shape[0] < target_len:
        pad = np.zeros(target_len - samples.shape[0], dtype=samples.dtype)
        return np.concatenate([samples, pad])
    return samples


def rubberband_stretch(samples: np.ndarray, sample_rate: int, factor: float) -> np.ndarray:
    """Time-stretch mono float32 samples by ``factor`` via the rubberband CLI."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.wav")
        dst = os.path.join(tmp, "out.wav")
        wavfile.write(src, sample_rate, samples.astype(np.float32))
        subprocess.run(
            ["rubberband", "--time", f"{factor:.6f}", "--pitch", "1.0", src, dst],
            check=True,
            capture_output=True,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", WavFileWarning)
            _, out = wavfile.read(dst)
    return out.astype(np.float32)


def fit_samples(
    samples: np.ndarray,
    sample_rate: int,
    target_duration: float,
    tolerance: float = 0.02,
    stretch_fn: Callable[[np.ndarray, int, float], np.ndarray] = rubberband_stretch,
) -> np.ndarray:
    """Return ``samples`` resized to exactly ``target_duration`` seconds.

    If the chunk is already within ``tolerance`` (fractional) of the target we
    skip the stretch to avoid needless quality loss, then snap to the exact
    target sample count either way.
    """
    target_len = int(round(target_duration * sample_rate))
    src_duration = samples.shape[0] / sample_rate
    factor = time_factor(src_duration, target_duration)

    if abs(factor - 1.0) > tolerance:
        samples = stretch_fn(samples, sample_rate, factor)

    return _snap(samples, target_len)
