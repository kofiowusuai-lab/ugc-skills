from voiceswap.sts import ElevenLabsConverter


class FakeSTS:
    def __init__(self, chunks):
        self._chunks = chunks
        self.calls = []

    def convert(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self._chunks)


class FakeClient:
    def __init__(self, chunks):
        self.speech_to_speech = FakeSTS(chunks)


def test_passes_voice_and_model_and_writes_streamed_bytes(tmp_path):
    src = tmp_path / "seg.wav"
    src.write_bytes(b"RIFFfake")
    out = tmp_path / "out.mp3"

    client = FakeClient([b"abc", b"def"])
    conv = ElevenLabsConverter(
        client=client, voice_id="VOICE123", model_id="eleven_multilingual_sts_v2"
    )
    result = conv.convert_file(str(src), str(out))

    assert result == str(out)
    assert out.read_bytes() == b"abcdef"

    call = client.speech_to_speech.calls[0]
    assert call["voice_id"] == "VOICE123"
    assert call["model_id"] == "eleven_multilingual_sts_v2"


def test_handles_single_bytes_return(tmp_path):
    # SDK may return raw bytes instead of a generator
    src = tmp_path / "seg.wav"
    src.write_bytes(b"x")
    out = tmp_path / "out.mp3"

    class BytesSTS:
        def convert(self, **kwargs):
            return b"wholefile"

    class C:
        speech_to_speech = BytesSTS()

    conv = ElevenLabsConverter(client=C(), voice_id="V", model_id="m")
    conv.convert_file(str(src), str(out))
    assert out.read_bytes() == b"wholefile"
