---
name: ugc-device-screen
description: Use when a UGC avatar video needs REAL content shown on a phone or laptop screen in the scene — putting one of our ebooks/PDFs on the character's laptop, having her scroll a document, showing a checkout/dashboard page, or playing a video inside the on-screen interface. Triggers: "put the book on her screen", "make her scroll the PDF", "show the ebook on the laptop", "screen recording in the avatar's hands", "every ebook" UGC ad with the product visible on a device. Keeps on-screen text razor sharp (real pixels, not generated) and only moves the screen when the avatar drives it.
---

<!-- MINIMAX_VISION_GATE:BEGIN -->
> **Model-conditional (UGC / video gen — NOT Before Freedom).** If this instance is on **MiniMax** (Codex capped; self-test: you cannot Read/see an image) you are BLIND and a weak composer — Grok clips drift off the anchor and you collapse formats to one lone person. Let Claude plan the shots (`~/.openclaw/scripts/ugc_shot_planner.sh`), write the script (`ugc_write_script.sh`), and run QA+delivery (`ugc_claude_deliver.sh`); see the **`ugc-vision-referee`** skill. Keep Grok native voice unless asked (`ugc_add_voice.py`). On **Codex/gpt-5.5** (native vision), ignore this and use the normal flow. Never apply to Before Freedom / america250 (FAL pipeline).
<!-- MINIMAX_VISION_GATE:END -->


# UGC Device Screen

Put a REAL document (any ebook PDF) or a real video onto a phone/laptop screen inside a Grok-animated UGC character clip, with sharp, readable content. Works for every ebook in the catalog.

## The one rule (never break it)

**A screen never has self-moving graphics.** On-screen motion is allowed ONLY when it is motivated:

1. **Avatar drives it** — her hand is on the trackpad/screen and the scroll is timed to her actual hand motion, eyes tracking the screen.
2. **A real video is playing** inside the interface (a warped video layer, not a scroll).

Otherwise the screen stays **static**. A document that scrolls while her hands are in her lap reads as fake instantly. This is the failure we engineered out — do not reintroduce it.

## Why composite instead of letting Grok animate the screen

Grok `image_to_video` softens and hallucinates dense text during motion. The fix is to never run the real content through the video model: generate the character with a blank screen, then perspective-pin the real pixels (PDF pages or video frames) onto the detected screen quad in post. Text stays pixel-perfect.

## Pipeline

1. **Scene still** — Codex `image_gen`/`image_edit` (fallback: Grok `image_edit`) from the locked character reference. Compose the device so the screen is **near head-on (~8° tilt, not steep)**, her body **3/4 to camera (not pure profile)**, **eyes down on the screen reading**, **one hand on the trackpad**. Screen shows a flat, evenly lit, light-gray blank rectangle (placeholder, unobstructed, no glare).
2. **Animate** — Grok `image_to_video`, duration 6 or 10s, 720p, with a **LOCKED-CAMERA** prompt: "locked-off tripod, camera does NOT move, laptop/desk perfectly still, only the woman moves." For a scroll, tell her to rest her hand on the trackpad and make slow repeated upward swipes with reading pauses, eyes tracking down. The locked camera keeps the screen quad static so a fixed-quad composite holds (verified: bbox constant across all 241 frames).
3. **Composite** — run the engine. It renders the pages, auto-detects the screen quad, drives the scroll from her measured hand motion, pins sharp content on, and muxes Grok's audio back.

## The engine (one command, any ebook)

```bash
python3 ~/.claude/skills/ugc-device-screen/scripts/pdf_screen.py \
  --clip <grok_character_clip.mp4> \
  --pdf "<any book PDF>" \
  --pages 9-14 \
  --out final.mp4
```

`--pages` accepts ranges and lists: `8-13` or `7,9,11`. The screen quad is auto-detected from frame 0; pass `--quad screen_quad.json` (corners TL,TR,BR,BL) to override.

### Modes (`--mode`)

| mode | use | extra args |
|------|-----|-----------|
| `handdriven` (default) | scroll advances only when her hand moves, pauses when she pauses | `--roi x0,y0,x1,y1` to override the trackpad region; `--settle 0.5` start delay |
| `video` | a real video plays inside the interface | `--screen-video promo.mp4` |
| `static` | screen holds one page, no motion | — |
| `continuous` | smooth eased scroll (only if the clip has no clear hand input) | — |
| `stepped` | 3 discrete page jumps | — |

## Per-video inputs vs automated

- **You provide:** the character/scene clip, which ebook, the page range per beat, and the script/voice.
- **Automated:** PDF rendering, scroll-strip build, screen-quad detection, hand-driven scroll timing, perspective pinning, audio mux.

## Book catalog

Ebook PDFs live in `~/Desktop/AI Mastery Guide - Complete Series/` (Vol I/II/III + Workbook), `~/aimastery*_assets/`, `~/manifestation_workbook_assets/`, and `~/Desktop/` (Manifestation, You Were Born Rich). Any of them drop straight into `--pdf`.

## Common mistakes

- **Screen scrolls with hands in lap** → use `handdriven` and make sure the scene has her hand on the trackpad. If the clip lacks a hand on the device, the screen must be `static`.
- **Steep screen angle / side profile / gaze off into distance** → regenerate the scene still with the composition requirements above; these three are the exact v1 failures.
- **Camera drifts so the quad slides off** → the animate prompt MUST say locked-off tripod, laptop/desk still. Re-check quad stability by sampling frames before compositing.
- **Codex usage-limited** → fall back to Grok `image_edit` for the scene still (same identity-lock discipline).
- **`codex exec -i img.png` eats the prompt** → `-i` is variadic; pass the prompt via stdin with a trailing `-`.

## Related

ElevenLabs revoice + lipsync tail to swap the avatar's voice while the screen scroll stays sharp: see the voiceswap tool. Reference build + test artifacts: `~/ugc_pipeline/pdf_test/` (v2 is the good one).
