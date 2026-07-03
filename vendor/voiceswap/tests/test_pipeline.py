import shutil

from voiceswap import audio
from voiceswap.pipeline import process_video


class IdentityConverter:
    """Stand-in for ElevenLabs: returns the input segment unchanged.

    Lets us drive the whole pipeline end-to-end with zero network calls while
    still exercising real ffmpeg extract / silence-detect / stretch / mux.
    """

    def __init__(self):
        self.calls = 0

    def convert_file(self, in_wav, out_path):
        self.calls += 1
        shutil.copy(in_wav, out_path)
        return out_path


def test_single_segment_video_keeps_duration_and_audio(tone_video, tmp_path):
    out = tmp_path / "out.mp4"
    conv = IdentityConverter()
    process_video(str(tone_video), str(out), conv)

    assert out.exists()
    assert audio.has_audio_stream(str(out))
    assert abs(audio.probe_duration(str(out)) - 2.0) < 0.2
    assert conv.calls == 1


def test_gapped_video_splits_into_two_segments(gapped_video, tmp_path):
    out = tmp_path / "out.mp4"
    conv = IdentityConverter()
    process_video(str(gapped_video), str(out), conv,
                  noise_db=-40.0, min_silence=0.5)

    assert conv.calls == 2  # tone / silence / tone -> two speech chunks
    assert audio.has_audio_stream(str(out))
    assert abs(audio.probe_duration(str(out)) - 3.0) < 0.2


def test_output_audio_length_matches_source_timeline(tone_video, tmp_path):
    out = tmp_path / "out.mp4"
    process_video(str(tone_video), str(out), IdentityConverter())
    # extract the produced audio and confirm it is locked to the 2s source
    produced = tmp_path / "produced.wav"
    audio.extract_audio(str(out), str(produced))
    sr, samples = audio.load_wav(str(produced))
    assert abs(samples.shape[0] / sr - 2.0) < 0.2


def test_progress_callback_is_invoked_per_segment(gapped_video, tmp_path):
    out = tmp_path / "out.mp4"
    events = []
    process_video(str(gapped_video), str(out), IdentityConverter(),
                  noise_db=-40.0, min_silence=0.5,
                  on_progress=lambda i, n: events.append((i, n)))
    assert events == [(1, 2), (2, 2)]
