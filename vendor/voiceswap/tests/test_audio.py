import numpy as np

from voiceswap import audio


def test_probe_duration(tone_video):
    assert abs(audio.probe_duration(str(tone_video)) - 2.0) < 0.1


def test_extract_audio_is_mono_at_requested_rate(tone_video, tmp_path):
    out = tmp_path / "a.wav"
    audio.extract_audio(str(tone_video), str(out), sample_rate=44100)
    sr, samples = audio.load_wav(str(out))
    assert sr == 44100
    assert samples.ndim == 1
    assert abs(samples.shape[0] / sr - 2.0) < 0.1


def test_detect_silences_finds_the_gap(gapped_wav):
    silences = audio.detect_silences(str(gapped_wav), noise_db=-40.0, min_silence=0.5)
    assert len(silences) == 1
    start, end = silences[0]
    # gap runs roughly 1.0s -> 2.5s
    assert 0.8 < start < 1.3
    assert 2.3 < end < 2.7


def test_no_silence_on_continuous_tone(tmp_path):
    import subprocess
    wav = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:sample_rate=44100", "-t", "2", "-ac", "1", str(wav)],
        check=True,
    )
    assert audio.detect_silences(str(wav), noise_db=-40.0, min_silence=0.5) == []


def test_load_save_roundtrip(tmp_path):
    sr = 44100
    samples = (0.3 * np.sin(np.linspace(0, 100, sr))).astype(np.float32)
    path = tmp_path / "rt.wav"
    audio.save_wav(str(path), sr, samples)
    out_sr, out = audio.load_wav(str(path))
    assert out_sr == sr
    assert out.shape[0] == samples.shape[0]
    assert np.max(np.abs(out - samples)) < 1e-3


def test_mux_audio_produces_video_with_audio_track(tone_video, tmp_path):
    sr = 44100
    new = (0.2 * np.sin(np.linspace(0, 200, sr * 2))).astype(np.float32)
    audio_path = tmp_path / "new.wav"
    audio.save_wav(str(audio_path), sr, new)
    out = tmp_path / "muxed.mp4"
    audio.mux_audio(str(tone_video), str(audio_path), str(out))
    assert out.exists()
    assert audio.has_audio_stream(str(out))
    assert abs(audio.probe_duration(str(out)) - 2.0) < 0.2
