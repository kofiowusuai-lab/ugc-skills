from voiceswap.align import (
    Word,
    words_from_char_alignment,
    group_phrases,
    build_placements,
    phrase_placement,
)


# ---- words_from_char_alignment ---------------------------------------------

def test_two_words_from_char_timestamps():
    chars = list("hi yo")
    starts = [0.0, 0.1, 0.2, 0.3, 0.4]
    ends = [0.1, 0.2, 0.3, 0.4, 0.5]
    words = words_from_char_alignment("hi yo", chars, starts, ends)
    assert words == [Word("hi", 0.0, 0.2), Word("yo", 0.3, 0.5)]


def test_punctuation_stays_with_its_word():
    chars = list("hi, yo")
    starts = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    ends = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    words = words_from_char_alignment("hi, yo", chars, starts, ends)
    assert [w.text for w in words] == ["hi,", "yo"]
    assert words[0].start == 0.0 and words[0].end == 0.3


def test_leading_and_trailing_spaces_ignored():
    chars = list(" hi ")
    starts = [0.0, 0.1, 0.2, 0.3]
    ends = [0.1, 0.2, 0.3, 0.4]
    words = words_from_char_alignment(" hi ", chars, starts, ends)
    assert words == [Word("hi", 0.1, 0.3)]


# ---- group_phrases ----------------------------------------------------------

def test_group_splits_on_long_gap():
    words = [Word("a", 0.0, 1.0), Word("b", 1.1, 2.0), Word("c", 5.0, 6.0)]
    phrases = group_phrases(words, max_gap=0.6)
    assert [[w.text for w in p] for p in phrases] == [["a", "b"], ["c"]]


def test_group_keeps_one_phrase_when_gaps_small():
    words = [Word("a", 0.0, 1.0), Word("b", 1.1, 2.0)]
    phrases = group_phrases(words, max_gap=0.6)
    assert len(phrases) == 1


def test_group_empty():
    assert group_phrases([], max_gap=0.6) == []


# ---- build_placements -------------------------------------------------------

def test_word_level_placements_use_original_times_and_generated_spans():
    orig = [Word("one", 0.0, 0.5), Word("two", 1.0, 1.4)]   # original cadence
    gen = [Word("one", 0.0, 0.3), Word("two", 0.3, 0.9)]    # TTS cadence
    placements = build_placements(orig, gen)
    assert len(placements) == 2
    # each generated word is mapped onto the original word's slot
    assert placements[0].target_start == 0.0
    assert placements[0].target_dur == 0.5
    assert placements[0].src_start == 0.0 and placements[0].src_end == 0.3
    assert placements[1].target_start == 1.0
    assert round(placements[1].target_dur, 6) == 0.4
    assert placements[1].src_start == 0.3 and placements[1].src_end == 0.9


def test_matched_words_placed_exactly_despite_punctuation_and_extra_word():
    # "don't" ~ "dont" should still match; the extra generated "now" is dropped,
    # and both real words land in their exact original slots (pauses preserved).
    orig = [Word("dont", 0.0, 0.4), Word("stop", 0.5, 1.0)]
    gen = [Word("don't", 0.0, 0.3), Word("stop", 0.35, 0.7), Word("now", 0.7, 0.9)]
    placements = build_placements(orig, gen)
    assert len(placements) == 2
    assert placements[0].target_start == 0.0 and placements[0].target_dur == 0.4
    assert placements[0].src_start == 0.0 and placements[0].src_end == 0.3
    assert placements[1].target_start == 0.5 and placements[1].target_dur == 0.5
    assert placements[1].src_start == 0.35 and placements[1].src_end == 0.7


def test_replaced_run_uses_block_level_span():
    # genuinely different words -> stretch the whole differing block into place
    orig = [Word("cat", 0.0, 0.5)]
    gen = [Word("dog", 0.0, 0.4)]
    placements = build_placements(orig, gen)
    assert len(placements) == 1
    p = placements[0]
    assert p.target_start == 0.0 and p.target_dur == 0.5
    assert p.src_start == 0.0 and p.src_end == 0.4


def test_phrase_placement_is_one_block_preserving_natural_flow():
    # whole generated phrase stretched into the original phrase window;
    # no per-word warping, so the new voice keeps its natural delivery
    orig = [Word("one", 0.0, 0.5), Word("two", 1.0, 1.4)]
    gen = [Word("one", 0.0, 0.3), Word("two", 0.3, 0.9)]
    placements = phrase_placement(orig, gen)
    assert len(placements) == 1
    p = placements[0]
    assert p.target_start == 0.0
    assert round(p.target_dur, 6) == 1.4          # orig phrase span
    assert p.src_start == 0.0 and p.src_end == 0.9  # full generated span


def test_phrase_placement_empty_inputs():
    assert phrase_placement([], []) == []


def test_dropped_word_leaves_others_exact():
    # generated audio is missing a middle word -> the present words stay exact
    orig = [Word("one", 0.0, 0.4), Word("two", 0.5, 0.9), Word("three", 1.0, 1.5)]
    gen = [Word("one", 0.0, 0.3), Word("three", 0.3, 0.7)]
    placements = build_placements(orig, gen)
    # one and three matched exactly; two has no audio -> silence in its slot
    starts = [(p.target_start, p.target_dur) for p in placements]
    assert (0.0, 0.4) in starts
    assert (1.0, 0.5) in starts
