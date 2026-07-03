from voiceswap.segment import compute_speech_segments


def test_no_silence_returns_whole_timeline():
    assert compute_speech_segments(10.0, []) == [(0.0, 10.0)]


def test_single_significant_silence_splits_into_two_segments():
    # silence 4.0-5.0 (1s, >= default min_silence) splits the timeline
    segs = compute_speech_segments(10.0, [(4.0, 5.0)], min_silence=0.5)
    assert segs == [(0.0, 4.0), (5.0, 10.0)]


def test_short_silence_is_ignored_and_kept_as_speech():
    # 0.2s silence is below min_silence, so no split
    segs = compute_speech_segments(10.0, [(4.0, 4.2)], min_silence=0.5)
    assert segs == [(0.0, 10.0)]


def test_silence_at_start_and_end_is_trimmed():
    segs = compute_speech_segments(10.0, [(0.0, 1.0), (9.0, 10.0)], min_silence=0.5)
    assert segs == [(1.0, 9.0)]


def test_overlapping_silences_are_merged():
    segs = compute_speech_segments(10.0, [(4.0, 5.0), (4.5, 6.0)], min_silence=0.5)
    assert segs == [(0.0, 4.0), (6.0, 10.0)]


def test_silences_are_clamped_to_timeline_bounds():
    # ffmpeg can report a silence_end past the probed duration
    segs = compute_speech_segments(10.0, [(9.5, 11.0)], min_silence=0.5)
    assert segs == [(0.0, 9.5)]


def test_entirely_silent_timeline_returns_no_segments():
    segs = compute_speech_segments(10.0, [(0.0, 10.0)], min_silence=0.5)
    assert segs == []
