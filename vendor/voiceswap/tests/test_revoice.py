import io

import numpy as np
from scipy.io import wavfile

from voiceswap import audio
from voiceswap.align import Word
from voiceswap.revoice import revoice_video, measure_drift


def _wav_bytes(samples, sr=44100):
    buf = io.BytesIO()
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    wavfile.write(buf, sr, pcm)
    return buf.getvalue()


class FakeTTS:
    """Generates back-to-back 0.3s tone 'words' with matching timestamps."""

    def __init__(self, sr=44100):
        self.sr = sr
        self.calls = []

    def synthesize(self, text):
        self.calls.append(text)
        n = len(text.split())
        word_dur = 0.3
        total = np.array([], dtype=np.float32)
        words = []
        for i, tok in enumerate(text.split()):
            seg = 0.2 * np.sin(np.linspace(0, 50, int(self.sr * word_dur))).astype(np.float32)
            total = np.concatenate([total, seg])
            words.append(Word(tok, i * word_dur, (i + 1) * word_dur))
        return _wav_bytes(total, self.sr), words


def test_revoice_produces_synced_video(tone_video, tmp_path):
    # original cadence: "hello world" then a gap then "again"
    orig = [
        Word("hello", 0.2, 0.6),
        Word("world", 0.6, 1.0),
        Word("again", 1.8, 2.0),
    ]
    tts = FakeTTS()
    out = tmp_path / "out.mp4"

    summary = revoice_video(
        str(tone_video), str(out), tts,
        transcriber=lambda path, model_name="base", language=None: orig,
        max_gap=0.6,
    )

    assert out.exists()
    assert audio.has_audio_stream(str(out))
    assert abs(audio.probe_duration(str(out)) - 2.0) < 0.2
    # two phrases -> two TTS calls
    assert tts.calls == ["hello world", "again"]
    assert summary["phrases"] == 2
    assert summary["words"] == 3


def test_revoice_phrase_mode_produces_synced_video(tone_video, tmp_path):
    orig = [Word("hello", 0.2, 0.6), Word("world", 0.6, 1.0)]
    tts = FakeTTS()
    out = tmp_path / "out.mp4"
    summary = revoice_video(
        str(tone_video), str(out), tts,
        transcriber=lambda path, model_name="base", language=None: orig,
        align_mode="phrase",
    )
    assert out.exists()
    assert audio.has_audio_stream(str(out))
    assert summary["phrases"] == 1


def test_revoice_places_audio_at_original_word_times(tone_video, tmp_path):
    # one word at 1.0-1.4s; everything before/after must be silent
    orig = [Word("mark", 1.0, 1.4)]
    out = tmp_path / "out.mp4"
    revoice_video(
        str(tone_video), str(out), FakeTTS(),
        transcriber=lambda path, model_name="base", language=None: orig,
    )
    produced = tmp_path / "p.wav"
    audio.extract_audio(str(out), str(produced))
    sr, samples = audio.load_wav(str(produced))
    # energy should sit around 1.0-1.4s, not at the very start
    assert np.max(np.abs(samples[: int(0.8 * sr)])) < 0.02
    assert np.max(np.abs(samples[int(1.0 * sr): int(1.4 * sr)])) > 0.05


# ---- measure_drift ----------------------------------------------------------

def test_measure_drift_zero_when_aligned():
    a = [Word("x", 0.0, 0.5), Word("y", 1.0, 1.5)]
    assert measure_drift(a, a) == 0.0


def test_measure_drift_reports_max_start_offset():
    orig = [Word("x", 0.0, 0.5), Word("y", 1.0, 1.5)]
    measured = [Word("x", 0.05, 0.55), Word("y", 1.20, 1.70)]
    assert abs(measure_drift(orig, measured) - 0.20) < 1e-9


def test_measure_drift_aligns_by_text_when_words_dropped():
    # a middle word is missing from the measured transcription; the metric must
    # still compare like-for-like (a->a, c->c), not slide indices
    orig = [Word("a", 0.0, 0.5), Word("b", 1.0, 1.5), Word("c", 2.0, 2.5)]
    measured = [Word("a", 0.1, 0.6), Word("c", 2.1, 2.6)]
    assert abs(measure_drift(orig, measured) - 0.1) < 1e-9
