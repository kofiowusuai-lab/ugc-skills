"""Turn detected silences into speech segments on the original timeline.

A "speech segment" is a (start, end) window of the original audio that gets
sent to ElevenLabs speech-to-speech as one chunk. Splitting only on
*significant* silence keeps each chunk natural for the model while preserving
exact start offsets, so the converted audio can be laid back down with no drift.
"""
from typing import List, Tuple


def _merge(intervals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Merge overlapping/touching intervals. Assumes input is unsorted."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def compute_speech_segments(
    total_duration: float,
    silences: List[Tuple[float, float]],
    min_silence: float = 0.5,
) -> List[Tuple[float, float]]:
    """Return non-silent (start, end) speech segments across [0, total_duration].

    Only silences at least ``min_silence`` seconds long act as split points;
    shorter pauses stay inside a segment so the model hears natural phrasing.
    Silences are clamped to the timeline and merged before complementing.
    """
    splits = []
    for start, end in silences:
        start = max(0.0, min(start, total_duration))
        end = max(0.0, min(end, total_duration))
        if end - start >= min_silence:
            splits.append((start, end))

    splits = _merge(splits)

    segments = []
    cursor = 0.0
    for start, end in splits:
        if start > cursor:
            segments.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < total_duration:
        segments.append((cursor, total_duration))

    return segments
