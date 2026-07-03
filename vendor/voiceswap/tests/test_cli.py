from voiceswap.cli import build_parser, main, default_out_path


def test_parser_requires_video_and_voice():
    args = build_parser().parse_args(["clip.mp4", "--voice", "V123"])
    assert args.video == "clip.mp4"
    assert args.voice == "V123"


def test_default_out_path_inserts_suffix():
    assert default_out_path("/a/b/clip.mp4") == "/a/b/clip.voiceswap.mp4"


def test_main_wires_args_into_runner():
    captured = {}

    def fake_factory(**kwargs):
        captured["factory"] = kwargs
        return "CONVERTER"

    def fake_runner(video, out, converter, **kwargs):
        captured["runner"] = dict(video=video, out=out, converter=converter, **kwargs)
        return out

    rc = main(
        ["clip.mp4", "--voice", "V123", "--out", "result.mp4",
         "--model", "eleven_multilingual_sts_v2", "--min-silence", "0.7",
         "--noise-db", "-35"],
        converter_factory=fake_factory,
        runner=fake_runner,
    )

    assert rc == 0
    assert captured["factory"]["voice_id"] == "V123"
    assert captured["factory"]["model_id"] == "eleven_multilingual_sts_v2"
    assert captured["runner"]["video"] == "clip.mp4"
    assert captured["runner"]["out"] == "result.mp4"
    assert captured["runner"]["converter"] == "CONVERTER"
    assert captured["runner"]["min_silence"] == 0.7
    assert captured["runner"]["noise_db"] == -35.0


def test_main_uses_default_out_when_omitted():
    captured = {}

    def fake_runner(video, out, converter, **kwargs):
        captured["out"] = out
        return out

    main(["clip.mp4", "--voice", "V"], converter_factory=lambda **k: "C",
         runner=fake_runner)
    assert captured["out"] == "clip.voiceswap.mp4"
