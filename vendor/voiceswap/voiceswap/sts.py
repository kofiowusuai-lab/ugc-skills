"""ElevenLabs speech-to-speech (voice changer) wrapper.

Speech-to-speech transforms only the *timbre* of the input audio while keeping
the original cadence, rhythm and emotion, which is exactly why it preserves
timing. This wrapper takes a segment wav, runs it through the model, and writes
the raw returned audio bytes to disk. The SDK client is injected so the rest of
the pipeline and the tests never need a network call.
"""
import io
import os
from typing import Optional

DEFAULT_MODEL = "eleven_multilingual_sts_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


class ElevenLabsConverter:
    def __init__(
        self,
        client,
        voice_id: str,
        model_id: str = DEFAULT_MODEL,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        remove_background_noise: bool = False,
    ):
        self.client = client
        self.voice_id = voice_id
        self.model_id = model_id
        self.output_format = output_format
        self.remove_background_noise = remove_background_noise

    def convert_file(self, in_wav: str, out_path: str) -> str:
        """Run speech-to-speech on ``in_wav`` and write the result to ``out_path``."""
        # Read the bytes into memory and hand the SDK a fresh BytesIO. The ElevenLabs
        # client encodes the multipart body lazily, so a real file handle gets closed
        # (by the `with`) before httpx reads it -> "I/O operation on closed file".
        with open(in_wav, "rb") as fh:
            data = fh.read()
        audio = io.BytesIO(data)
        audio.name = os.path.basename(in_wav)
        result = self.client.speech_to_speech.convert(
            voice_id=self.voice_id,
            audio=audio,
            model_id=self.model_id,
            output_format=self.output_format,
            remove_background_noise=self.remove_background_noise,
        )

        with open(out_path, "wb") as out:
            if isinstance(result, (bytes, bytearray)):
                out.write(result)
            else:
                for chunk in result:
                    if chunk:
                        out.write(chunk)
        return out_path


def make_converter(
    voice_id: str,
    model_id: str = DEFAULT_MODEL,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    api_key: Optional[str] = None,
    remove_background_noise: bool = False,
) -> ElevenLabsConverter:
    """Build a converter backed by a real ElevenLabs client (lazy import)."""
    from elevenlabs import ElevenLabs

    client = ElevenLabs(api_key=api_key or os.environ.get("ELEVENLABS_API_KEY"))
    return ElevenLabsConverter(
        client=client,
        voice_id=voice_id,
        model_id=model_id,
        output_format=output_format,
        remove_background_noise=remove_background_noise,
    )
