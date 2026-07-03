"""Thin, well-behaved wrappers over ffmpeg / ffprobe and WAV I/O.

Everything here shells out to the system ffmpeg/ffprobe and keeps audio as mono
float32 in numpy, normalized to [-1, 1]. No pydub/soundfile dependency.
"""
import re
import subprocess
from typing import List, Tuple

import numpy as np
from scipy.io import wavfile

_SILENCE_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


def _run(args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, text=True)


def probe_duration(path: str) -> float:
    """Duration in seconds via ffprobe."""
    out = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ]).stdout.strip()
    return float(out)


def has_audio_stream(path: str) -> bool:
    out = _run([
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "csv=p=0", path,
    ]).stdout.strip()
    return bool(out)


def extract_audio(video_path: str, out_wav: str, sample_rate: int = 44100) -> str:
    """Pull a mono PCM wav out of a video at ``sample_rate``."""
    _run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", out_wav,
    ])
    return out_wav


def to_wav(src: str, out_wav: str, sample_rate: int = 44100) -> str:
    """Normalize any audio file (e.g. ElevenLabs mp3) to mono wav at ``sample_rate``."""
    _run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", src,
        "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", out_wav,
    ])
    return out_wav


def detect_silences(
    audio_path: str, noise_db: float = -30.0, min_silence: float = 0.5
) -> List[Tuple[float, float]]:
    """Return (start, end) silence intervals via ffmpeg's silencedetect filter."""
    proc = subprocess.run(
        ["ffmpeg", "-i", audio_path, "-af",
         f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    log = proc.stderr
    silences: List[Tuple[float, float]] = []
    pending_start = None
    for line in log.splitlines():
        m = _SILENCE_START.search(line)
        if m:
            pending_start = float(m.group(1))
            continue
        m = _SILENCE_END.search(line)
        if m and pending_start is not None:
            silences.append((pending_start, float(m.group(1))))
            pending_start = None
    if pending_start is not None:
        silences.append((pending_start, probe_duration(audio_path)))
    return silences


def load_wav(path: str) -> Tuple[int, np.ndarray]:
    """Load a wav as (sample_rate, mono float32 in [-1, 1])."""
    sr, data = wavfile.read(path)
    data = np.asarray(data)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if np.issubdtype(data.dtype, np.integer):
        max_val = float(np.iinfo(data.dtype).max)
        data = data.astype(np.float32) / max_val
    else:
        data = data.astype(np.float32)
    return sr, data


def save_wav(path: str, sample_rate: int, samples: np.ndarray) -> str:
    """Write mono float32 samples as 16-bit PCM wav."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    wavfile.write(path, sample_rate, pcm)
    return path


def mux_audio(video_path: str, audio_path: str, out_path: str) -> str:
    """Replace the video's audio with ``audio_path`` (video stream copied)."""
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video_path, "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-shortest", out_path,
    ])
    return out_path
