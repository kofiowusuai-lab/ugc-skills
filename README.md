# UGC Skills for Claude Code

A complete toolkit for producing hyper-realistic UGC (user-generated-content) style avatar videos and ads with Claude Code. Clone the repo, run one install script, and your Claude Code gains five skills that research an angle, write the script, generate the character and video, add a voice, lip-sync, and deliver a finished clip.

These are [Claude Code Skills](https://docs.claude.com/en/docs/claude-code/skills). Once installed, you invoke them by name (`/ugc-video-producer`) or just by asking Claude in plain language ("make a UGC ad for my ebook").

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
