"""Whisper transcription with word-level timestamps.

This is the timing reference: each original word's start/end becomes the slot
the matching generated word must land in. The model loader is injected so tests
never load a real model, and so callers can swap model sizes.
"""
from typing import Callable, List, Optional

from .align import Word


def _default_loader(name: str):
    import whisper
    return whisper.load_model(name)


def transcribe_words(
    audio_path: str,
    model_name: str = "base",
    language: Optional[str] = None,
    _loader: Callable = _default_loader,
) -> List[Word]:
    """Transcribe ``audio_path`` and return a flat list of timed words."""
    model = _loader(model_name)
    result = model.transcribe(audio_path, word_timestamps=True, language=language)

    words: List[Word] = []
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            start, end = w.get("start"), w.get("end")
            if start is None or end is None:
                continue
            words.append(Word(w["word"].strip(), float(start), float(end)))
    return words
