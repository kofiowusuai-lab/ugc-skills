---
name: ugc-video-producer
description: Use when the user wants an end-to-end hyper-realistic UGC avatar video/ad for a digital or physical product — a talking-head spokesperson clip where the character looks real enough to look twice, says scripted copy in a chosen voice with lip-sync, and (for digital products) shows the real ebook/app on a device screen or (for physical products) holds the real product. Handed only a product (no script), Phase 0 invokes ugc-ad-strategist to research the audience, pick the single claim, and write the hooks + beat sheet. Triggers: "make a UGC ad for <product>", "ship a UGC video", "spokesperson talking-head ad", "AI creator promoting the book/course", "testimonial-style ad with my product in it". Drives ugc-ad-strategist (research+script), Codex/Grok image gen, Grok image-to-video, ElevenLabs voice, and WaveSpeed lip-sync.
---

# UGC Video Producer

Produce a finished, hyper-realistic UGC talking-head ad from a product + script, using only tools that exist in this environment. Build ads as stitched 6–10s shots (Grok's hard limit), holding one consistent character across all of them.

> **READ FIRST: `reference/ugc_qa_bank.md`** — generation principles distilled from real productions
> (every entry is a mistake we already made, turned into a rule). It will save you the failures around
> clip length vs VO, flaky Grok video, voicing, screen/product staging, captions, and loudness. Append
> to it whenever a render breaks in a new way.

**Task monitor lane:** open this job's task monitor with `--lane ugc` so it routes to the UGC OPS chat (@UGCOPSbbot), separate from Before Freedom — e.g. `ID=$(~/.openclaw/scripts/task-monitor start "<short task name>" --lane ugc --stages "...")`.

## Phase 0 — get the script (when handed only a product)

If the user gives you a **product** ("make a UGC ad for the AI Mastery Collection") and **not** a finished
script, do NOT improvise the copy — that's the weak link that decides whether the ad converts. Invoke the
**`ugc-ad-strategist`** skill first. It researches the audience + live winning ads, picks the single claim,
writes the 6 hooks + the beat sheet (per-clip `dialogue`/`emotion`/`action`/`grok_prompt`/`overlay`),
sets the platform cuts + voice.

It returns **`brief.json`** (contract: `ugc-ad-strategist/reference/brief_schema.json`). Read it and drive
Phases 1–6 straight off it:
- `base_still_prompt` → Phase 1 character identity.
- each `clips[]` entry → one shot: `dialogue` is the spoken line, `grok_prompt` is the ready Phase-3 prompt,
  `emotion`/`action` are the delivery/camera directives, `overlay` is the burned caption.
- a clip with `screen_asset` (digital product proof beat) → Phase 5 via **`ugc-device-screen`** with that
  `pdf` + `pages`, `driven_by` telling you whether the avatar scrolls it or a video plays.
- a clip with `product_shot` (physical book beat, e.g. a true "hardcopies sold out" angle) → first build a
  photoreal hardcover from the REAL cover: `python3 scripts/book_mockup.py --book <vol> --hold hands`
  (or `--cover <product_shot.cover_image>`), run the codex/grok command it prints, then anchor that mockup
  into her hands (Phase 5 physical path). Never let Grok invent the cover. Only voice a sold-out line if
  `product_shot.scarcity` is set (the strategist sets it only when verified true).
- `voice.id`/`settings` → Phase 4. `hooks[]` → generate the hook clip per variant for testing (tag by `utm_content`).

If the user hands you a script directly, skip Phase 0 and start at Phase 1 (back-compat).

**If the user hands you an IMAGE ("bring this to life" / "animate this"), skip Phase 1 — that image IS the
identity anchor.** Go straight to Phase 3: `grok image_to_video image="<their image>" duration=10
resolution_name="720p" prompt="Continue from this exact still: same person, same wardrobe, same setting,
handheld micro-shake, natural blinks + small gestures, direct eye contact; he/she says: \"<line>\""`. Then
Phase 4 (voice via STS → pick a voice that matches the face, QA Bank D5). If the supplied image is low-res
or stylized, optionally do ONE Codex `image_edit` pass first ("render this person fully photorealistic, keep
the EXACT same face") — same trick as B1b — then animate. View a frame before voicing.

## Phase 0.5 — STAGE THE SHOT (intake + shot plan, BEFORE any still)

**Do NOT improvise a base-still prompt.** Composing the scene yourself is how every format
collapses into one lone talking-head in a generic room. Even in native (vision) mode, the
**shot planner writes the anchor prompt(s) for you** — after you lock the format, people,
camera angles, and continuity. The realism directives in `scripts/realism_prompts.md` are the
*ingredients*; the planner is what decides the *recipe* for this specific ad. Skipping it is the
mistake that produced the jump-cut-to-the-same-pose artifacts.

**Step A — intake (ask up front, in ONE batch, before generating anything).** If the user
handed you only "make a UGC video" with no specifics, you are missing the inputs the planner
needs. Collect them in a single `AskUserQuestion`/message round, never one at a time:
1. **What are we making** — the product + the core message/claim (the planner's `--request`/`--product`).
2. **Format** — talking_head / street_interview / podcast (or `auto` to let the planner pick).
3. **Spokesperson** — gender/age/vibe, or "I'll send a reference photo" (best likeness), or `me`.
4. **Continuity** — *"Should these chain into one continuous video (a different angle per cut), or
   are independent cuts from the same identity fine?"* → `--continuity continuous|multiclip|auto`.
5. **Platform + total length** — TikTok/Reels/Shorts and ~15/30/45s (drives how many 6–10s shots).

If Phase 0 already ran (`brief.json` exists), most of this is answered — use `base_still_prompt`
and the `clips[]` framings as the plan and skip straight to Phase 1. Phase 0.5 is for when you
were handed a bare product/idea and no brief. If the user handed you an IMAGE, skip this entirely
(that image IS the anchor — go to Phase 3).

**Step B — run the planner.** It picks format, people count, camera angles, and the continuity
treatment, and writes a ratio-correct, Photorealism-Engine-grade `image_prompt` per frame:
```bash
~/.openclaw/scripts/ugc_shot_planner.sh --request "<what the user asked>" \
  [--product "<...>"] [--context "<audience/claim/angle>"] \
  [--format auto|talking_head|street_interview|podcast] \
  [--continuity auto|continuous|multiclip] \
  --out <run>/shot_plan.json
```
Read `shot_plan.json` → `frames[].image_prompt`. Format rules the planner enforces (trust them):
- **talking_head / testimonial** → 1 frame, exactly ONE person, direct to camera.
- **street / public interview** → one TWO-person frame per location (interviewer frame-LEFT with a
  visible handheld mic, guest frame-RIGHT). NEVER one lone person; the mic is ALWAYS visible.
- **podcast** → several labelled angle frames (wide establishing, host close-up, guest close-up,
  optional over-shoulder), all the SAME people/wardrobe/set.

**Continuity standard:** when the plan is `continuous`/multi-angle, generate a SEPARATE anchor still
per `framing` (re-pose/re-frame the SAME identity via Codex/Grok `image_edit` — change camera
distance, height, and subject angle while holding face/wardrobe/set). That is what turns a
jump-cut-to-the-same-pose into a natural multi-angle edit. `multiclip` may reuse one anchor but
should still vary framing between clips. Re-run the planner on every new scene/location/hard cut;
continuation clips in the SAME setting chain from the previous clip's last frame instead.

**Native-mode handoff:** unlike MiniMax mode (which hands the prompt to the user), here YOU generate the
still — feed each `image_prompt` to Phase 1 (Codex `image_gen`/`-i` reference, or Grok `image_gen`)
and View it before animating. If Claude is unavailable, the interview-only fallback is
`python3 ~/.openclaw/scripts/ugc_interview_prompt.py --topic "<t>" --setting mall|street`.

## Pipeline (each stage uses a verified tool)

> ### ⚠️ CHECK YOUR MODEL FIRST
> Self-test: if you CANNOT Read/see an image, you are on **MiniMax** (Codex capped).
> - **On MiniMax → STOP and follow the `ugc-minimax-mode` skill instead.** It is the complete pipeline
>   (Claude shot-planning + scriptwriting + anchor handoff to the user + Grok candidates + Claude vision QA +
>   delivery + voice). Do NOT use the numbered steps below — you are blind and will collapse every format
>   into one lone person.
> - **On Codex / gpt-5.5 (native vision) → use the numbered steps below, unchanged.** Codex composes and
>   QAs natively; the MiniMax skill does not apply.

1. **Character identity** — generate ONE base still of the spokesperson. **Use the `image_prompt` from Phase 0.5's `shot_plan.json` (or `base_still_prompt` from `brief.json`) — do not write it from scratch.** Codex `image_gen.imagegen` (via `codex exec`) or Grok `image_gen`. Save it as the identity anchor; every later shot references it. The realism directives in `scripts/realism_prompts.md` are already baked into the planner output; apply them manually only if you're editing a prompt by hand, so it reads as a real phone photo, not AI gloss.
2. **Stage each shot / keyframes** — Grok or Codex `image_edit` from the base ref to make per-beat poses/expressions/settings, keeping the SAME person. For pose variety in one shot, make 2–4 keyframes.
3. **Animate** — Grok `image_to_video` (single still) or `reference_to_video` (multi-keyframe). 6 or 10s, 720p, no audio input. Put the spoken line in the prompt as dialogue; Grok renders native lip-synced motion + mannerisms. Use a LOCKED-OFF camera when a screen or product must stay pinnable in post.
4. **Voice + lip-sync** — **default to STS, not TTS** (QA Bank D1/D2). Grok already speaks the line inside the clip with matching lip motion, so `voiceswap` speech-to-speech swaps the timbre to the chosen voice while preserving timing + lip-sync — no stretch artifacts. If voiceswap's silence-segmenter rejects a chunk, STS the whole-clip audio and mux back (`reference/../../ugc_pipeline/vol1_soldout/sts_voice.sh` is a working reference: clean wav → `voiceswap.sts` → `ffmpeg -map 0:V:0`). Use `scripts/voice_and_lipsync.py` (ElevenLabs TTS, stretch, optional WaveSpeed re-sync) ONLY when the stretch factor stays ~0.8–1.25× — a long line in a 6s clip stretches to ~0.65× and chipmunks.
5. **Product in the scene:**
   - **Digital product** (ebook/course/app): use the **`ugc-video-producer` companion skill `ugc-device-screen`** to pin the REAL PDF/app on a phone/laptop screen with sharp text. Rule: a screen only moves when the avatar drives it or a real video plays in it.
   - **Physical product:** Grok cannot invent a real product faithfully. Feed a REAL product photo as a reference: either `reference_to_video` with the product photo + the staged character keyframe, or `image_edit` the product into her hands/desk in the still BEFORE animating. Keep the real photo as the source of truth for label/shape.
   - **Physical BOOK (digital product with a real/sold-out hardcover):** there's no product photo, so build one from the REAL cover. `python3 scripts/book_mockup.py --book vol1 --hold hands` resolves the true cover (`~/code/aimastery-salespage/covers/`), prints a leak-proof "wrap the exact cover on a 3D hardback" prompt + the codex/grok command. Generate the mockup, then anchor it (`image_edit` into her hands or `reference_to_video`). The cover stays identical; only its physical form is generated. **Dual-proof "sold out → ebook" ad:** one beat holds the sold-out hardcover (`book_mockup.py`) + a true scarcity line, a second beat shows the real ebook on her screen (`ugc-device-screen`), CTA → the ebook funnel. Run the sold-out line ONLY when it's actually true (else it's false and breaks house style).
6. **Trim tails, then stitch.**
   - **Trim trailing dead air FIRST** (especially for multi-shot pieces where short lines sit in fixed 6/10s containers): `python3 scripts/trim_clip_tails.py --glob '<dir>/clip*.mp4' --out-dir <dir>_trimmed --tail 0.5`. Each clip is cut to end **0.5s after the last spoken word**; clips that already end tight are padded with a held last frame so every clip ends with a uniform 0.5s tail. **Detect speech-end by DIRECT RMS windowing, NOT `silencedetect`** — Grok fills the post-speech tail with low-level room tone that never drops below −20 dB, so `silencedetect`/reversed-silence report ZERO trailing silence even when there's 1–3s of dead air. The RMS method (last window above ~6% of peak) finds the true voice end.
   - **Stitch** — `scripts/stitch_shots.sh out.mp4 shot1.mp4 shot2.mp4 ...` joins shots into one vertical ad (uniform 720x1280/24fps). Grok clips carry TWO video streams; force `-map 0:v:0 -map 0:a:0` per clip (the bundled stitch auto-selects, but map explicitly when scripting).

## Grok video model pin (MANDATORY)

Every Grok **video** call — `image_to_video`, `reference_to_video`, or any clip generation — MUST run on the `grok-build` model. The default `grok-composer-2.5-fast` does NOT expose the video tools as native first-turn tools, so a headless agent burns its whole turn budget and exits "max turns reached" with no MP4 (the old ~42% silent-fail rate). `image_gen` / `image_edit` are fine on the default model and need no pin.

- **Preferred:** `python3 ~/.openclaw/scripts/grok_imagine.py video --prompt "..." --image /abs/frame.png --out /abs/out.mp4` — already pins `-m grok-build`, `--max-turns 16`, a 600s timeout, and harvest/retry. Use it whenever you do not need session continuity.
- **Raw `grok` (only for `--single` seed-image or `--continue` last-frame chaining):** you MUST add `-m grok-build --max-turns 16`, e.g. `grok -m grok-build --max-turns 16 --single "Call the image_to_video tool exactly once. ..."`.
- **Never** run raw `grok --single/--continue/-p` for video without `-m grok-build`.

## Quick commands

```bash
# Base still (Codex). NOTE: -i is variadic and eats the prompt -> pass prompt via stdin.
echo "<realism prompt>" | codex exec --skip-git-repo-check -s workspace-write -i ref.png - 

# Animate (drive via the Grok CLI; it calls image_to_video / reference_to_video)
grok -m grok-build --max-turns 16 -p 'Call image_to_video image="/abs/shot.png" duration=10 resolution_name="720p" prompt="...she says: \"<line>\"..."' --always-approve

# Voice + lip-sync a finished shot
python3 ~/.claude/skills/ugc-video-producer/scripts/voice_and_lipsync.py \
  --clip shot1.mp4 --script "Okay so I finally read this..." \
  --voice kPzsL2i3teMYv0FxEYQ6 --out shot1_voiced.mp4

# Real ebook on her laptop (digital product)  -> see ugc-device-screen skill
# Stitch shots
~/.claude/skills/ugc-video-producer/scripts/stitch_shots.sh ad_final.mp4 s1_voiced.mp4 s2_voiced.mp4
```

## Best workflow ordering (proven)

Script-as-dialogue in Grok → Grok renders native lip-synced motion → ElevenLabs swaps the voice (timbre via speech-to-speech, or fresh TTS) → WaveSpeed re-syncs the mouth to the final track → composite product/screen → stitch. Animating first (not TTS-first) lets Grok set natural timing the lip-sync then locks onto.

## Hard constraints / gotchas

- **Grok video:** 6 or 10s only, 720p max, no audio-input param. Longer ads = multiple shots stitched.
- **WaveSpeed key required for real lip-sync:** `~/.voiceswap.env` currently has `ELEVENLABS_API_KEY` but NOT `WAVESPEED_API_KEY`. Until that key is added, `voice_and_lipsync.py --no-lipsync` only muxes the voice (mouth not re-synced). Tell the user to add the key for true lip-sync.
- **Codex usage-limited** (resets hourly) → fall back to Grok `image_edit` for stills.
- **Default casual UGC voice (female):** Brittney "Social Media Voice" `kPzsL2i3teMYv0FxEYQ6`, model `eleven_multilingual_v2`, settings stability 0.45 / similarity 0.75 / style 0.30. Add filler words ("okay so", "honestly", "I'm not gonna lie") to the script for realism — not the voice settings.
- **Male avatar voices** (match gender + age to the face — QA Bank D5): Eric `cjVigY5qzO86Huf0OWal` (smooth/trustworthy, best default for a male educator avatar), Charlie `IKne3meq5aSn9XLyUdCD` (deep/confident/energetic), Liam `TX3LPaxmHKxFdv7VOQHJ` (energetic social-media creator), Brian `nPczCjzI2devNBz1zQrb` (deep/authority). STS 2–3 onto the same clip and let the user pick. A user's **cloned voice is a drop-in swap** — only the `voice_id` in the STS step changes.
- **Using your own cloned voice:** register it with `export UGC_MY_VOICE="me=<your_elevenlabs_voice_id>"`, then **always STS via `ugc_add_voice.py --voice me`, never TTS** — TTS breaks lip-sync, and a cloned voice's stored ElevenLabs defaults (high style / stability) can drift to a generic accent. If yours drifts, add a `VOICE_SETTINGS` override for its `voice_id` (style 0 / stability 0.45 / similarity 1.0 / speaker_boost) in `ugc_add_voice.py`. A cloned voice is a drop-in swap: only the `voice_id` in the STS step changes.
- **Best likeness comes from a reference image, not text** (QA Bank B1b / realism_prompts.md): seed Codex with an existing portrait via `-i identity_ref.jpg`; if the source is illustrated, add "render FULLY PHOTOREALISTIC, NOT an illustration, keep this EXACT person."
- **Identity drift** across shots → always pass the base ref to `image_edit` and lock face/skin/wardrobe explicitly.
- **Match script length to clip:** ~10s ≈ 24–28 spoken words. `voice_and_lipsync.py` stretches the voice to the clip; keep the factor within ~0.8–1.25x or it sounds slow/fast. Too short → dead air; too long → chipmunked.

## Assets

- Ebook PDFs: `~/Desktop/AI Mastery Guide - Complete Series/`, `~/aimastery*_assets/`, `~/manifestation_workbook_assets/`.
- Voice/lip-sync engine: `~/voiceswap` (revoice, voiceswap, wavespeed modules).
- Reference build + test artifacts from the first end-to-end proof: `~/ugc_pipeline/`.

## Companion skills

- **ugc-device-screen** — REQUIRED for any digital-product shot that shows the product on a screen.
- ElevenLabs voice options live in `~/voiceswap`.
