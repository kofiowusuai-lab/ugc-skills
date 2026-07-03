from voiceswap.revoice_cli import build_parser, main


def test_parser_requires_video_and_voice():
    args = build_parser().parse_args(["clip.mp4", "--voice", "V1"])
    assert args.video == "clip.mp4"
    assert args.voice == "V1"


def test_default_out_uses_revoiced_suffix():
    captured = {}

    def fake_runner(video, out, tts, **kwargs):
        captured["out"] = out
        return {"phrases": 0, "words": 0}

    main(["/a/clip.mp4", "--voice", "V"], tts_factory=lambda **k: "TTS",
         runner=fake_runner)
    assert captured["out"] == "/a/clip.revoiced.mp4"


def test_main_wires_args():
    captured = {}

    def fake_factory(**kwargs):
        captured["factory"] = kwargs
        return "TTS"

    def fake_runner(video, out, tts, **kwargs):
        captured["runner"] = dict(video=video, out=out, tts=tts, **kwargs)
        return {"phrases": 3, "words": 12}

    rc = main(
        ["clip.mp4", "--voice", "V1", "--out", "r.mp4",
         "--model", "eleven_turbo_v2_5", "--whisper-model", "small",
         "--max-gap", "0.8", "--language", "en"],
        tts_factory=fake_factory, runner=fake_runner,
    )
    assert rc == 0
    assert captured["factory"]["voice_id"] == "V1"
    assert captured["factory"]["model_id"] == "eleven_turbo_v2_5"
    assert captured["runner"]["video"] == "clip.mp4"
    assert captured["runner"]["out"] == "r.mp4"
    assert captured["runner"]["tts"] == "TTS"
    assert captured["runner"]["model_name"] == "small"
    assert captured["runner"]["max_gap"] == 0.8
    assert captured["runner"]["language"] == "en"
