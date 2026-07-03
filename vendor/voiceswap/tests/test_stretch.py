import numpy as np
import pytest

from voiceswap.stretch import time_factor, fit_samples


def test_factor_is_one_when_durations_match():
    assert time_factor(2.0, 2.0) == 1.0


def test_factor_stretches_when_target_is_longer():
    # source 2s must become 4s -> rubberband time factor 2.0
    assert time_factor(2.0, 4.0) == 2.0


def test_factor_compresses_when_target_is_shorter():
    assert time_factor(4.0, 2.0) == 0.5


def test_zero_source_duration_raises():
    with pytest.raises(ValueError):
        time_factor(0.0, 2.0)


def test_fit_samples_skips_stretch_within_tolerance():
    # 1000 samples at 1000 Hz = 1.0s; target 1.0s within tolerance -> unchanged,
    # converter must not be called
    samples = np.ones(1000, dtype=np.float32)
    calls = []

    def fake_stretch(arr, sr, factor):
        calls.append(factor)
        return arr

    out = fit_samples(samples, 1000, target_duration=1.0, tolerance=0.02,
                      stretch_fn=fake_stretch)
    assert calls == []
    assert out.shape[0] == 1000


def test_fit_samples_stretches_when_outside_tolerance():
    samples = np.ones(1000, dtype=np.float32)  # 1.0s at 1000 Hz
    captured = {}

    def fake_stretch(arr, sr, factor):
        captured["factor"] = factor
        # emulate rubberband producing factor * len samples
        return np.ones(int(round(arr.shape[0] * factor)), dtype=np.float32)

    out = fit_samples(samples, 1000, target_duration=1.5, tolerance=0.02,
                      stretch_fn=fake_stretch)
    assert captured["factor"] == pytest.approx(1.5)
    # result is snapped to the exact target sample count
    assert out.shape[0] == 1500


def test_fit_samples_snaps_to_exact_target_length():
    # even if the stretcher returns a slightly-off length, output is exact
    samples = np.ones(1000, dtype=np.float32)

    def sloppy_stretch(arr, sr, factor):
        return np.ones(1497, dtype=np.float32)  # 3 samples short of 1500

    out = fit_samples(samples, 1000, target_duration=1.5, tolerance=0.02,
                      stretch_fn=sloppy_stretch)
    assert out.shape[0] == 1500


def test_real_rubberband_stretches_to_target_duration():
    # 1.0s 440Hz tone at 44100 -> stretch to 1.5s, assert real output length
    import numpy as _np
    from voiceswap.stretch import fit_samples
    sr = 44100
    t = _np.linspace(0, 1.0, sr, endpoint=False)
    tone = (0.3 * _np.sin(2 * _np.pi * 440 * t)).astype(_np.float32)
    out = fit_samples(tone, sr, target_duration=1.5)  # real rubberband
    assert abs(out.shape[0] / sr - 1.5) < 0.01
