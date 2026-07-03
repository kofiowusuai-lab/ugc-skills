"""Re-narrate a video with an ElevenLabs voice, locked to the original cadence.

    video -> extract audio
          -> Whisper word timestamps  (the timing reference / the script)
          -> group into phrases on natural pauses
          -> per phrase: ElevenLabs TTS with timestamps
          -> warp each generated word onto its original word's time slot
          -> reassemble on a silent canvas at original offsets
          -> mux onto the original video

The original spoken words are reused verbatim as the script, and every word in
the new voice is stretched/placed to hit the same moment as the original, so the
cadence matches.
"""
import os
import tempfile
from typing import Callable, List, Optional

from difflib import SequenceMatcher

from . import audio
from .align import (
    Word,
    _norm,
    build_placements,
    group_phrases,
    phrase_placement,
)
from .assemble import assemble
from .stretch import fit_samples
from .transcribe import transcribe_words

ProgressFn = Callable[[int, int, str], None]


def measure_drift(orig: List[Word], measured: List[Word]) -> float:
    """Max absolute difference in word start times between two word lists.

    Words are aligned by text (ignoring case/punctuation) before comparing, so a
    dropped or extra word in the measured transcription doesn't slide every later
    comparison out of register. Only matched words are compared.
    """
    if not orig or not measured:
        return 0.0
    o_norm = [_norm(w.text) for w in orig]
    m_norm = [_norm(w.text) for w in measured]
    sm = SequenceMatcher(None, o_norm, m_norm, autojunk=False)
    worst = 0.0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                worst = max(worst, abs(orig[i1 + k].start - measured[j1 + k].start))
    return worst


def revoice_video(
    video_path: str,
    out_path: str,
    tts,
    transcriber: Callable = transcribe_words,
    sample_rate: int = 44100,
    max_gap: float = 0.6,
    model_name: str = "base",
    language: Optional[str] = None,
    align_mode: str = "word",
    on_progress: Optional[ProgressFn] = None,
) -> dict:
    """Rebuild ``video_path``'s narration with ``tts``, keeping the timing.

    ``tts`` is anything with ``synthesize(text) -> (audio_bytes, gen_words)``.
    ``align_mode`` is "word" (tightest cadence, per-word warp) or "phrase"
    (smoother, natural delivery, locks phrase boundaries only).
    Returns a summary dict (phrases, words, transcript, original word timings).
    """
    placement_fn = phrase_placement if align_mode == "phrase" else build_placements
    with tempfile.TemporaryDirectory() as work:
        full_wav = os.path.join(work, "full.wav")
        audio.extract_audio(video_path, full_wav, sample_rate=sample_rate)
        sr, full = audio.load_wav(full_wav)
        total_duration = full.shape[0] / sr

        orig_words = transcriber(full_wav, model_name=model_name, language=language)
        phrases = group_phrases(orig_words, max_gap=max_gap)

        placed = []
        for idx, phrase in enumerate(phrases, start=1):
            text = " ".join(w.text for w in phrase)

            audio_bytes, gen_words = tts.synthesize(text)
            raw = os.path.join(work, f"phrase_{idx}.bin")
            with open(raw, "wb") as fh:
                fh.write(audio_bytes)
            gen_wav = os.path.join(work, f"phrase_{idx}.wav")
            audio.to_wav(raw, gen_wav, sample_rate=sr)
            _, gen = audio.load_wav(gen_wav)

            for p in placement_fn(phrase, gen_words):
                cut = gen[int(round(p.src_start * sr)): int(round(p.src_end * sr))]
                if cut.size == 0:
                    continue
                fitted = fit_samples(cut, sr, target_duration=p.target_dur)
                placed.append((p.target_start, fitted))

            if on_progress:
                on_progress(idx, len(phrases), text)

        track = assemble(placed, sr, total_duration)
        new_wav = os.path.join(work, "new.wav")
        audio.save_wav(new_wav, sr, track)
        audio.mux_audio(video_path, new_wav, out_path)

    return {
        "phrases": len(phrases),
        "words": len(orig_words),
        "transcript": " ".join(w.text for w in orig_words),
        "orig_words": orig_words,
        "duration": total_duration,
    }
