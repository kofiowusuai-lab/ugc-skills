import numpy as np

from voiceswap.assemble import assemble


def test_output_length_matches_total_duration():
    sr = 1000
    canvas = assemble([], sr, total_duration=2.0)
    assert canvas.shape[0] == 2000


def test_empty_timeline_is_all_silence():
    canvas = assemble([], 1000, total_duration=1.0)
    assert np.count_nonzero(canvas) == 0


def test_segment_lands_at_its_start_offset():
    sr = 1000
    tone = np.ones(500, dtype=np.float32)
    canvas = assemble([(0.5, tone)], sr, total_duration=2.0)
    # silence before 0.5s, tone from sample 500..1000, silence after
    assert np.count_nonzero(canvas[:500]) == 0
    assert np.all(canvas[500:1000] == 1.0)
    assert np.count_nonzero(canvas[1000:]) == 0


def test_two_segments_keep_the_gap_between_them():
    sr = 1000
    a = np.full(200, 1.0, dtype=np.float32)
    b = np.full(200, 2.0, dtype=np.float32)
    canvas = assemble([(0.0, a), (1.0, b)], sr, total_duration=2.0)
    assert np.all(canvas[0:200] == 1.0)
    assert np.count_nonzero(canvas[200:1000]) == 0  # the gap survives
    assert np.all(canvas[1000:1200] == 2.0)


def test_segment_overflowing_the_canvas_is_truncated():
    sr = 1000
    tone = np.ones(800, dtype=np.float32)
    canvas = assemble([(1.5, tone)], sr, total_duration=2.0)
    assert canvas.shape[0] == 2000
    assert np.all(canvas[1500:2000] == 1.0)  # only 500 samples fit
