"""Word-level alignment between the original delivery and the new TTS audio.

The cadence lock works like this: Whisper tells us when each *original* word is
spoken, and ElevenLabs' per-character timestamps tell us when each *generated*
word is spoken. We then map each generated word onto its original word's slot,
so the new voice hits the same words at the same times.
"""
import re
from collections import namedtuple
from difflib import SequenceMatcher
from typing import List

Word = namedtuple("Word", "text start end")

# A chunk of generated audio [src_start, src_end] to be stretched to
# target_dur and placed at target_start on the final timeline (all seconds).
Placement = namedtuple("Placement", "target_start target_dur src_start src_end")


def words_from_char_alignment(
    text: str,
    characters: List[str],
    char_starts: List[float],
    char_ends: List[float],
) -> List[Word]:
    """Collapse ElevenLabs character timestamps into per-word spans."""
    words: List[Word] = []
    cur_chars: List[str] = []
    cur_start = None
    cur_end = None

    for ch, st, en in zip(characters, char_starts, char_ends):
        if ch.isspace():
            if cur_chars:
                words.append(Word("".join(cur_chars), cur_start, cur_end))
                cur_chars, cur_start, cur_end = [], None, None
            continue
        if cur_start is None:
            cur_start = st
        cur_end = en
        cur_chars.append(ch)

    if cur_chars:
        words.append(Word("".join(cur_chars), cur_start, cur_end))
    return words


def group_phrases(words: List[Word], max_gap: float = 0.6) -> List[List[Word]]:
    """Split a word stream into phrases wherever the silent gap exceeds max_gap."""
    if not words:
        return []
    phrases = [[words[0]]]
    for prev, cur in zip(words, words[1:]):
        if cur.start - prev.end > max_gap:
            phrases.append([cur])
        else:
            phrases[-1].append(cur)
    return phrases


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def phrase_placement(
    orig_words: List[Word], gen_words: List[Word]
) -> List[Placement]:
    """One placement per phrase: stretch the whole generated phrase into the
    original phrase window. Keeps the new voice's natural intra-phrase flow,
    locking only the phrase boundaries (smoother than per-word warping).
    """
    if not orig_words or not gen_words:
        return []
    return [
        Placement(
            target_start=orig_words[0].start,
            target_dur=orig_words[-1].end - orig_words[0].start,
            src_start=gen_words[0].start,
            src_end=gen_words[-1].end,
        )
    ]


def build_placements(
    orig_words: List[Word], gen_words: List[Word]
) -> List[Placement]:
    """Map generated words onto original word slots via subsequence alignment.

    Words that match (ignoring case/punctuation) are placed one-to-one in their
    exact original slot, which preserves the original pauses for the tightest
    cadence. Runs that genuinely differ are stretched as a block; words present
    only in the original become silence; words present only in the generated
    audio are dropped.
    """
    if not orig_words or not gen_words:
        return []

    o_norm = [_norm(w.text) for w in orig_words]
    g_norm = [_norm(w.text) for w in gen_words]
    sm = SequenceMatcher(None, o_norm, g_norm, autojunk=False)

    placements: List[Placement] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                o, g = orig_words[i1 + k], gen_words[j1 + k]
                placements.append(
                    Placement(o.start, o.end - o.start, g.start, g.end)
                )
        elif tag == "replace":
            # both sides non-empty: stretch the differing generated run into
            # the original run's window
            placements.append(
                Placement(
                    target_start=orig_words[i1].start,
                    target_dur=orig_words[i2 - 1].end - orig_words[i1].start,
                    src_start=gen_words[j1].start,
                    src_end=gen_words[j2 - 1].end,
                )
            )
        # 'delete' (orig-only words): no audio -> leave their slot silent
        # 'insert' (gen-only words): nothing to place them against -> drop
    return placements
