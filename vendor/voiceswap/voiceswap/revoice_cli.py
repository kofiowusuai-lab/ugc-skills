"""CLI for cadence-locked re-narration (Whisper script + ElevenLabs TTS).

    revoice clip.mp4 --voice <ELEVENLABS_VOICE_ID>

Transcribes the original words, regenerates them in the chosen voice, and warps
the result so every word lands on the original's timing.
"""
import argparse
import os
import sys
from typing import Callable, List, Optional

from .revoice import revoice_video
from .tts import DEFAULT_MODEL, DEFAULT_OUTPUT_FORMAT, make_tts


def default_out_path(video: str) -> str:
    root, ext = os.path.splitext(video)
    return f"{root}.revoiced{ext}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="revoice",
        description="Re-narrate a video in an ElevenLabs voice, locked to the "
                    "original cadence via Whisper word timestamps.",
    )
    p.add_argument("video", help="path to the input video")
    p.add_argument("--voice", required=True, help="ElevenLabs target voice id")
    p.add_argument("--out", help="output path (default: <name>.revoiced.<ext>)")
    p.add_argument("--model", default=DEFAULT_MODEL, help="ElevenLabs TTS model id")
    p.add_argument("--output-format", default=DEFAULT_OUTPUT_FORMAT)
    p.add_argument("--whisper-model", default="base",
                   help="Whisper model size (tiny/base/small/medium/large)")
    p.add_argument("--language", default=None, help="force transcription language")
    p.add_argument("--max-gap", type=float, default=0.6,
                   help="pause length (s) that starts a new phrase")
    p.add_argument("--align", choices=["word", "phrase"], default="word",
                   help="word = tightest cadence (per-word warp); "
                        "phrase = smoother, natural delivery, locks phrase bounds")
    p.add_argument("--api-key", default=None, help="overrides ELEVENLABS_API_KEY")
    p.add_argument("--sample-rate", type=int, default=44100)
    return p


def main(
    argv: Optional[List[str]] = None,
    tts_factory: Callable = make_tts,
    runner: Callable = revoice_video,
) -> int:
    args = build_parser().parse_args(argv)
    out = args.out or default_out_path(args.video)

    tts = tts_factory(
        voice_id=args.voice,
        model_id=args.model,
        output_format=args.output_format,
        api_key=args.api_key,
    )

    def progress(i: int, n: int, text: str) -> None:
        preview = (text[:48] + "…") if len(text) > 48 else text
        print(f"  [{i}/{n}] {preview}", file=sys.stderr)

    print(f"Re-voicing: {args.video} -> {out}", file=sys.stderr)
    summary = runner(
        args.video, out, tts,
        sample_rate=args.sample_rate,
        max_gap=args.max_gap,
        model_name=args.whisper_model,
        language=args.language,
        align_mode=args.align,
        on_progress=progress,
    )
    print(f"Done: {out}  ({summary['phrases']} phrases, {summary['words']} words)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
