"""Command-line entry point: swap the voice in a video, keep the timing.

    voiceswap clip.mp4 --voice <ELEVENLABS_VOICE_ID>

Needs ELEVENLABS_API_KEY in the environment (or --api-key), plus ffmpeg,
ffprobe and rubberband on PATH.
"""
import argparse
import os
import sys
from typing import Callable, List, Optional

from .pipeline import process_video
from .sts import DEFAULT_MODEL, DEFAULT_OUTPUT_FORMAT, make_converter


def default_out_path(video: str) -> str:
    root, ext = os.path.splitext(video)
    return f"{root}.voiceswap{ext}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="voiceswap",
        description="Replace the voice in a video with an ElevenLabs voice, "
                    "preserving timing via speech-to-speech.",
    )
    p.add_argument("video", help="path to the input video")
    p.add_argument("--voice", required=True, help="ElevenLabs target voice id")
    p.add_argument("--out", help="output path (default: <name>.voiceswap.<ext>)")
    p.add_argument("--model", default=DEFAULT_MODEL, help="speech-to-speech model id")
    p.add_argument("--output-format", default=DEFAULT_OUTPUT_FORMAT,
                   help="ElevenLabs output format")
    p.add_argument("--api-key", default=None, help="overrides ELEVENLABS_API_KEY")
    p.add_argument("--sample-rate", type=int, default=44100)
    p.add_argument("--noise-db", type=float, default=-30.0,
                   help="silence threshold in dB (lower = stricter)")
    p.add_argument("--min-silence", type=float, default=0.5,
                   help="minimum silence (s) that splits a segment")
    p.add_argument("--remove-background-noise", action="store_true",
                   help="ask ElevenLabs to denoise each chunk")
    return p


def main(
    argv: Optional[List[str]] = None,
    converter_factory: Callable = make_converter,
    runner: Callable = process_video,
) -> int:
    args = build_parser().parse_args(argv)
    out = args.out or default_out_path(args.video)

    converter = converter_factory(
        voice_id=args.voice,
        model_id=args.model,
        output_format=args.output_format,
        api_key=args.api_key,
        remove_background_noise=args.remove_background_noise,
    )

    def progress(i: int, n: int) -> None:
        print(f"  [{i}/{n}] segment converted", file=sys.stderr)

    print(f"Swapping voice: {args.video} -> {out}", file=sys.stderr)
    runner(
        args.video,
        out,
        converter,
        sample_rate=args.sample_rate,
        noise_db=args.noise_db,
        min_silence=args.min_silence,
        on_progress=progress,
    )
    print(f"Done: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
