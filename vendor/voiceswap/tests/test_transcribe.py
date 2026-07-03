from voiceswap.transcribe import transcribe_words
from voiceswap.align import Word


class FakeModel:
    def __init__(self, result):
        self._result = result
        self.kwargs = None

    def transcribe(self, path, **kwargs):
        self.kwargs = kwargs
        return self._result


def test_flattens_segments_into_words_and_strips_whitespace():
    result = {
        "segments": [
            {"words": [
                {"word": " Hello", "start": 0.0, "end": 0.4},
                {"word": " world", "start": 0.4, "end": 0.9},
            ]},
            {"words": [
                {"word": " again", "start": 2.0, "end": 2.5},
            ]},
        ]
    }
    model = FakeModel(result)
    words = transcribe_words("a.wav", _loader=lambda name: model)
    assert words == [
        Word("Hello", 0.0, 0.4),
        Word("world", 0.4, 0.9),
        Word("again", 2.0, 2.5),
    ]


def test_requests_word_timestamps():
    model = FakeModel({"segments": []})
    transcribe_words("a.wav", _loader=lambda name: model)
    assert model.kwargs.get("word_timestamps") is True


def test_skips_words_missing_timing():
    result = {"segments": [{"words": [
        {"word": "ok", "start": 0.0, "end": 0.2},
        {"word": "bad", "start": None, "end": None},
    ]}]}
    words = transcribe_words("a.wav", _loader=lambda name: FakeModel(result))
    assert words == [Word("ok", 0.0, 0.2)]
