"""ElevenLabs text-to-speech with per-word timing.

Uses the ``convert_with_timestamps`` endpoint so we get character-level
timestamps for the generated speech, which we collapse into word spans. Those
spans are what let us warp the new audio onto the original cadence. The SDK
client is injected so the pipeline and tests stay offline.
"""
import base64
import os
from typing import List, Optional, Tuple

from .align import Word, words_from_char_alignment

DEFAULT_MODEL = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


class ElevenLabsTTS:
    def __init__(
        self,
        client,
        voice_id: str,
        model_id: str = DEFAULT_MODEL,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
    ):
        self.client = client
        self.voice_id = voice_id
        self.model_id = model_id
        self.output_format = output_format

    def synthesize(self, text: str) -> Tuple[bytes, List[Word]]:
        """Return (audio_bytes, word_spans) for ``text``."""
        resp = self.client.text_to_speech.convert_with_timestamps(
            voice_id=self.voice_id,
            text=text,
            model_id=self.model_id,
            output_format=self.output_format,
        )
        b64 = getattr(resp, "audio_base_64", None) or getattr(resp, "audio_base64")
        audio = base64.b64decode(b64)

        alignment = getattr(resp, "alignment", None) or getattr(
            resp, "normalized_alignment", None
        )
        words = words_from_char_alignment(
            text,
            alignment.characters,
            alignment.character_start_times_seconds,
            alignment.character_end_times_seconds,
        )
        return audio, words


def make_tts(
    voice_id: str,
    model_id: str = DEFAULT_MODEL,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    api_key: Optional[str] = None,
) -> ElevenLabsTTS:
    """Build a TTS wrapper backed by a real ElevenLabs client."""
    from elevenlabs import ElevenLabs

    client = ElevenLabs(api_key=api_key or os.environ.get("ELEVENLABS_API_KEY"))
    return ElevenLabsTTS(
        client=client,
        voice_id=voice_id,
        model_id=model_id,
        output_format=output_format,
    )
