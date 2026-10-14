# UGC Skills for Claude Code

A complete toolkit for producing hyper-realistic UGC (user-generated-content) style avatar videos and ads with Claude Code. Clone the repo, run one install script, and your Claude Code gains five skills that research an angle, write the script, generate the character and video, add a voice, lip-sync, and deliver a finished clip.

These are [Claude Code Skills](https://docs.claude.com/en/docs/claude-code/skills). Once installed, you invoke them by name (`/ugc-video-producer`) or just by asking Claude in plain language ("make a UGC ad for my ebook").

> **Never used GitHub before?** Start with the [`Beginner's Guide`](docs/Get-the-UGC-Skills-Beginners-Guide.pdf) — plain-English, no account or `git` needed, with screenshots. Already comfortable with a terminal? Use the [`Setup Guide`](docs/UGC-Skills-Setup-Guide.pdf) instead: clone to first render in seven steps, with a prerequisites checklist and troubleshooting table.

## What you get

| Skill | What it does |
|-------|--------------|
| **ugc-video-producer** | The main pipeline. End-to-end talking-head spokesperson video for a digital or physical product: character generation, image-to-video, voice, and lip-sync. Handed only a product, it pulls in the strategist to write the script first. |
| **ugc-ad-strategist** | The brain for the words. Researches the audience, mines winning ads, picks one claim, and writes the hooks + beat sheet into a `brief.json` the producer consumes. |
| **ugc-device-screen** | Puts real, razor-sharp content on a phone or laptop screen inside the scene (an ebook, a checkout page, a scrolling PDF) using real pixels instead of generated text. |
| **ugc-minimax-mode** | The full pipeline adapted for a blind, text-only model. Runs Claude for shot planning, scriptwriting, and vision QA when the acting model cannot see images. |
| **ugc-vision-referee** | Deprecated. Folded into ugc-minimax-mode. Kept for reference. |

The `scripts/` folder holds the engine these skills call: Grok image and video generation, ElevenLabs voice swap, WaveSpeed lip-sync, Gemini vision QA, and the ffmpeg stitching and matte tools. The `vendor/voiceswap/` folder is the bundled voice-swap and lip-sync package the producer uses; the installer places it at `~/voiceswap` where the scripts expect it.

## Requirements

Before the pipeline runs, you need:

**External CLIs on your PATH**
- `grok` - xAI Grok CLI, for image and image-to-video generation
- `gemini` - Google Gemini CLI, for vision QA and drift detection
- `ffmpeg` and `ffprobe` - video processing (`brew install ffmpeg` on Mac, `apt install ffmpeg` on Linux)
- `rubberband` - time-stretch for voice fitting (`brew install rubberband` / `apt install rubberband-cli`)
- `node` - runs the ad-strategist workflow
- `python3` - runs the engine scripts

**Python packages** (installed by the step below)
- elevenlabs, opencv-python, numpy, scipy, Pillow, requests
- Optional: `openai-whisper` (only for on-screen captions and the revoice mode)

**API keys** (set in your `.env`)
- `ELEVENLABS_API_KEY` - voice
- `GEMINI_API_KEY` - vision QA
- `WAVESPEED_API_KEY` - lip-sync (optional; without it the voice is muxed on without re-syncing the mouth)

The motion-graphics finishing pass (kinetic captions, text-behind-avatar, b-roll) needs a separate Remotion project and is not bundled. The pipeline detects when it is missing and delivers the plain cut, so you can ignore the `--studio` / `--broll` / `--motion-graphics` flags unless you set that project up yourself.

Claude Code itself is the host. Install it from https://docs.claude.com/en/docs/claude-code.

## Install

```bash
git clone https://github.com/kofiowusuai-lab/ugc-skills.git
cd ugc-skills

# 1. install the skills and engine into your Claude Code setup
bash install.sh

# 2. add your API keys
cp .env.example .env
# edit .env, then load it in each shell you work in:
set -a; . ./.env; set +a

# 3. install the python dependencies
python3 -m pip install -r requirements.txt
```

`install.sh` copies the five skill folders into `~/.claude/skills/` and the engine scripts into `~/.openclaw/scripts/` (the path the skills call internally). If you already have a skill folder with the same name, it backs it up first.

## Verify it worked

Open Claude Code and type `/` - you should see the `ugc-` skills in the list. Or just ask:

```
make a UGC ad for a $27 ebook about meal prep
```

Claude picks up `ugc-video-producer`, which runs the strategist for the script, then generates the video.

## How the pieces fit

```
  you: "make a UGC ad for <product>"
        |
        v
  ugc-video-producer  (orchestrates the whole job)
        |
        +--> ugc-ad-strategist   -> brief.json (claim, hooks, beat sheet)
        +--> grok image gen       -> character anchor image
        +--> grok image-to-video  -> raw clips
        +--> ugc-device-screen    -> product shown on a real device screen
        +--> ElevenLabs voice      -> scripted VO in a chosen voice
        +--> WaveSpeed lip-sync    -> mouth matched to the audio
        +--> ffmpeg stitch         -> final delivered .mp4
```

`ugc-minimax-mode` swaps in when the acting model cannot see images: Claude handles the planning, writing, and vision QA that a blind model gets wrong.

## Notes for students

- Every API key is read from the environment. Nothing is hardcoded. Keep your `.env` private; it is already in `.gitignore`.
- The Telegram progress pings (via `scripts/task-monitor`) are optional. Leave `TELEGRAM_BOT_TOKEN` blank and the pipeline still runs; you just lose the phone notifications.
- To register your own cloned ElevenLabs voice without editing code:
  `export UGC_MY_VOICE="me=<your_voice_id>"` then pass `--voice me`.
- Costs are on you: Grok, ElevenLabs, Gemini, and WaveSpeed all bill per use. Start small.

## License

MIT. See [LICENSE](LICENSE). Use it, change it, teach with it.

## Operational status and direct commands

This repository is an agent skill bundle and local script toolkit, not a standalone hosted service. The host executes skill instructions and external tools. Installation copies files; it does not provision provider accounts, authenticate Grok/Gemini/Claude, or install the external CLIs. Some scripts call the `claude` executable directly, so Claude CLI access is required even when another acting model uses the bundle.

For a small image-first job, after installation and loading your private environment:

```bash
bash "$HOME/.openclaw/scripts/ugc_from_image.sh" \
  --image /absolute/path/anchor.png \
  --outcome "Explain the product benefit directly to camera" \
  --dialogue "Your approved spoken line" \
  --n 2 --duration 6 --job /absolute/path/job --out /absolute/path/job/final.mp4
```

For a multi-clip job, `ugc_video_from_image.sh` accepts `--duration`, `--kind`, `--clip-len` (6 or 10), `--n`, `--dialogue`, `--voice`, `--job`, and `--out`. Candidate counts multiply provider usage, so review the intended job before live execution. Run each script with `--help` for its implemented options.

## Configuration and output files

The example environment documents `ELEVENLABS_API_KEY`, `WAVESPEED_API_KEY`, `GEMINI_API_KEY`, optional `UGC_MY_VOICE`, `GROK_CLI_PATH`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_USER_ID`. Certain helpers also accept `CLAUDE_BIN` and `UGC_PRODUCER_SCRIPTS` to select the host CLI and producer-script directory. Do not treat the optional Telegram transport as a prerequisite for rendering.

Image-first scripts default to timestamped job directories under `~/ugc_pipeline/`, with an anchor copy in `refs/`, candidates in `clips/`, and `final_delivery.mp4` as the default delivery. Multi-clip jobs also stage `winners/` and `frames/`. Delivery QA writes `claude_delivery_report.json` with candidate verdicts and the delivered path. Keep job media and reports together for diagnosis; a report or candidate file alone is not a final delivery.

The strategist's brief contract is in [brief_schema.json](skills/ugc-ad-strategist/reference/brief_schema.json). The producer's [skill instructions](skills/ugc-video-producer/SKILL.md) define its production workflow. Device-screen compositing has its own [instructions](skills/ugc-device-screen/SKILL.md). The bundled [voiceswap README](vendor/voiceswap/README.md) explains voice fitting and re-narration.

## Validation and troubleshooting

There is no single top-level offline test runner for the whole agent workflow. The vendored package has offline fake-provider tests; they still require local FFmpeg/ffprobe/Rubber Band and test dependencies:

```bash
python3 -m pip install -e './vendor/voiceswap[dev]'
python3 -m pytest vendor/voiceswap/tests -q
bash scripts/ugc_from_image.sh --help
bash scripts/ugc_video_from_image.sh --help
```

- Skills missing from the host: verify the installer destination and restart/reopen the host skill list.
- Missing CLI: check the executable is on PATH and that its own authentication is complete; these CLI implementations are external dependencies.
- Missing producer scripts: check the installed `ugc-video-producer/scripts/` directory or `UGC_PRODUCER_SCRIPTS` override.
- No candidate passes QA: inspect the job report, anchor, and prompt before generating more takes.
- Voice works but mouth does not match: WaveSpeed is optional; audio muxing alone does not reanimate lips.
- Motion-graphics project unavailable: deliver/review the plain cut or configure the separate project; it is not installed by this bundle.

Keep provider moderation, licenses, authorized voices/likenesses, and automatically supplied provenance intact. Installation backs up existing same-name skills and `~/voiceswap`; engine scripts are copied into the shared script directory and can overwrite same-name scripts there. Review that destination before reinstalling.
