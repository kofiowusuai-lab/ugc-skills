import subprocess

import pytest


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


@pytest.fixture
def tone_video(tmp_path):
    """2s test video: color pattern + a 440Hz tone (continuous speech-ish)."""
    out = tmp_path / "video.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "2", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out),
    )
    return out


@pytest.fixture
def gapped_video(tmp_path):
    """3s video whose audio is tone / silence / tone, so it splits in two."""
    out = tmp_path / "gapped.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24",
        "-f", "lavfi", "-i",
        "aevalsrc=0.5*sin(440*2*PI*t)*lt(t\\,1)+"
        "0.5*sin(440*2*PI*t)*gt(t\\,2):s=44100",
        "-t", "3", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out),
    )
    return out


@pytest.fixture
def gapped_wav(tmp_path):
    """4s mono wav: 1s tone, ~1.5s silence, 1.5s tone."""
    out = tmp_path / "gapped.wav"
    _ffmpeg(
        "-f", "lavfi", "-i",
        "aevalsrc=0.5*sin(440*2*PI*t)*lt(mod(t\\,2.5)\\,1)+"
        "0.5*sin(440*2*PI*t)*gt(t\\,2.5):s=44100",
        "-t", "4", "-ac", "1", str(out),
    )
    return out
