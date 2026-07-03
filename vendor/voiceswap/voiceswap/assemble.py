"""Lay converted speech chunks back onto a silent canvas at exact offsets.

The canvas length is fixed to the original audio duration, and each chunk is
written starting at its original timestamp. Silent gaps between chunks are
preserved automatically, so the rebuilt track stays locked to the video.
"""
from typing import List, Tuple

import numpy as np


def assemble(
    segments: List[Tuple[float, np.ndarray]],
    sample_rate: int,
    total_duration: float,
) -> np.ndarray:
    """Build a mono float32 track of ``total_duration`` seconds.

    ``segments`` is a list of (start_time_seconds, samples). Each chunk is
    placed at ``round(start_time * sample_rate)``; anything past the end of the
    canvas is truncated so the output length is always exact.
    """
    length = int(round(total_duration * sample_rate))
    canvas = np.zeros(length, dtype=np.float32)

    for start_time, samples in segments:
        start = int(round(start_time * sample_rate))
        if start >= length:
            continue
        end = start + samples.shape[0]
        if end > length:
            samples = samples[: length - start]
            end = length
        canvas[start:end] = samples.astype(np.float32)

    return canvas
