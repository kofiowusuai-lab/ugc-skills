import base64

from voiceswap.tts import ElevenLabsTTS
from voiceswap.align import Word


class FakeAlignment:
    def __init__(self, chars, starts, ends):
        self.characters = chars
        self.character_start_times_seconds = starts
        self.character_end_times_seconds = ends


class FakeResp:
    def __init__(self, audio, alignment):
        # real ElevenLabs field name is audio_base_64
        self.audio_base_64 = base64.b64encode(audio).decode()
        self.alignment = alignment


class FakeTTSApi:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def convert_with_timestamps(self, **kwargs):
        self.calls.append(kwargs)
        return self._resp


class FakeClient:
    def __init__(self, resp):
        self.text_to_speech = FakeTTSApi(resp)


def test_synthesize_returns_audio_bytes_and_word_spans():
    align = FakeAlignment(list("hi yo"),
                          [0.0, 0.1, 0.2, 0.3, 0.4],
                          [0.1, 0.2, 0.3, 0.4, 0.5])
    client = FakeClient(FakeResp(b"AUDIO", align))
    tts = ElevenLabsTTS(client=client, voice_id="V1", model_id="eleven_multilingual_v2")

    audio, words = tts.synthesize("hi yo")

    assert audio == b"AUDIO"
    assert words == [Word("hi", 0.0, 0.2), Word("yo", 0.3, 0.5)]

    call = client.text_to_speech.calls[0]
    assert call["voice_id"] == "V1"
    assert call["text"] == "hi yo"
    assert call["model_id"] == "eleven_multilingual_v2"


def test_uses_normalized_alignment_when_plain_alignment_missing():
    align = FakeAlignment(list("ok"), [0.0, 0.1], [0.1, 0.2])
    resp = FakeResp(b"X", align)
    resp.alignment = None
    resp.normalized_alignment = align
    client = FakeClient(resp)
    tts = ElevenLabsTTS(client=client, voice_id="V", model_id="m")
    _, words = tts.synthesize("ok")
    assert words == [Word("ok", 0.0, 0.2)]
