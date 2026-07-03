# UGC Generation QA Bank

Hard-won principles from real productions. **Read this before generating a UGC ad.** Each entry is a
real mistake turned into a generation rule: *Mistake → Principle → How*. When a render goes wrong in a
new way, add the lesson here so the next generation doesn't repeat it.

Origin log:
- 2026-06-10 — AI Mastery Vol I "sold-out hardcover → ebook" ad (`~/ugc_pipeline/vol1_soldout/`). First
  full end-to-end production through the strategist + producer + device-screen + book-mockup stack.

---

## A. Script & beat sizing (ugc-ad-strategist)

**A1. Size dialogue to the clip's REAL renderable length.**
- *Mistake:* the strategist wrote 22–40 word lines and tagged beats 2.5s/5s. Grok only renders **6s or 10s**.
  ElevenLabs read the 22-word hook in 9.24s; forcing it into a 6s clip = **0.654× = chipmunked/rushed**.
- *Principle:* every clip's `seconds` is **6 or 10, nothing else**. Budget **~14–16 spoken words per 6s**,
  **~24–28 per 10s**. If a line needs more room, make it a 10s clip or split it into two beats. Total ad
  length = a sum of 6/10s clips (a "30s" ad is really 5×6s or 3×10s). Plan to that grid.
- *How:* count words per line against the clip seconds before locking the script. Over budget → trim or
  promote to 10s.

**A2. Only script on-screen content that is a REAL asset we possess.**
- *Mistake:* a beat's prompt said "a real ChatGPT window with a rewritten email" but the only real asset was
  the ebook PDF. We showed the ebook to stay truthful, creating a small VO/visual gap.
- *Principle:* the on-screen element must be something we can show truthfully — a real PDF, app, or screen
  recording we actually have. If the VO implies a UI we can't capture, **capture the real screen or change
  the VO/visual** to what we can show. Never fabricate a fake UI/screenshot.

**A3. Truthful scarcity only.** "Hardcovers sold out" runs ONLY when `physical_status: hardcopy_sold_out` is
verified true. False scarcity violates FTC rules, gets demonetized, and breaks house style.

**A4. The non-negotiables (reaffirm):** one claim per ad · capability not income · first-person past-tense
testimonial · process proof beats outcome proof · honest 80/20 to pre-handle the objection · persistent
"results vary" disclaimer · spoken price on paid · caption every beat.

---

## B. Character still (Phase 1)

**B1. Realism directives win.** Candid front-camera selfie, cluttered real desk, visible pores + smile
lines, slight sensor grain, mild lens distortion, no glamour retouching, no logos/text/watermark. (Positive:
the Vol I base still read as a real coworker, not an influencer — keep doing this.)

**B1b. SEED IDENTITY FROM A REFERENCE IMAGE — don't describe a face in text (proven 2026-06-11, the user avatar).**
- *Win:* the best likeness we've gotten came from passing an existing portrait to Codex as the identity
  anchor, not from a text description. `echo "<prompt>" | codex exec --skip-git-repo-check -s workspace-write -i identity_ref.jpg -`
  The `-i` image seeds the face; the prompt does the realism + wardrobe + setting. One shot, dead-on likeness.
- *If the reference is an ILLUSTRATION / brand-character (not a photo):* force the conversion explicitly —
  "Use the attached image as the IDENTITY REFERENCE. Render this person FULLY PHOTOREALISTIC, NOT an
  illustration. Keep this EXACT person: same skin tone, same hair, same beard, same facial structure."
  This turned a stylized cartoon brand avatar into a real-looking UGC creator that held identity through
  animation. Without the "NOT an illustration / render photorealistic" line you get a polished cartoon back.
- *Output location:* Codex writes to `~/.codex/generated_images/<uuid>/ig_*.png` then copies to the workspace
  filename you named in the prompt. Always name the output file in the prompt ("save it as influencer_base.png").
- *Then animate normally (C-section):* "Continue from this exact UGC selfie still: same man, same locs, same
  beard, same navy suit, same warm home office" held the face + wardrobe + room perfectly across the 10s clip.

**B2. Lock identity to the base still.** Every later shot references the base still; restate face/hair/
wardrobe explicitly in each `image_edit`/`image_to_video` prompt or the character drifts between cuts.

**B2b. Showing the BACK of her head? Build a 360 turnaround reference FIRST — never generate a fresh person.**
- *Mistake:* the over-the-shoulder POV keyframe was made with `image_gen` from scratch → it was a RANDOM
  different woman, not the spokesperson. From behind, identity = hair colour/length/cut/parting + wardrobe,
  and a fresh generation gets all of that wrong.
- *Principle:* any shot that shows her from the side or back must be anchored to a multi-angle reference of
  the SAME person. From the base still, `image_edit` a **turnaround sheet** — front, ¾-left, ¾-right,
  profile, and back-of-head — keeping hair/wardrobe identical. Then build side/back shots by `image_edit`
  (not `image_gen`) either from the base still or from the cropped back-view, so the hair + cardigan match.
  Verify the keyframe is recognizably her before animating.
- *How:* `image_edit base_still.jpg` → "character turnaround sheet, 5 views (front, ¾-left, ¾-right,
  profile, back), identical hair/cardigan/face." Reference: `~/ugc_pipeline/vol1_soldout/character_turnaround.jpg`,
  `her_backview.jpg`, `c34_pov_her_v2.jpg`. Identity from behind is mostly hair + wardrobe — specify both
  exactly in every prompt.

**B3. Talking-head beats = LOCK EYE CONTACT ON THE LENS.**
- *Mistake:* in talking-head beats she drifted to looking off into the distance — awkward and breaks the
  direct-address realism of a testimonial where she's explaining how the product helped her.
- *Principle:* for any to-camera beat, the `image_to_video` prompt must explicitly force sustained eye
  contact: "looks straight into the camera lens the entire time, steady direct eye contact, talking right
  to the viewer like a close friend on a video call; does NOT look away, down, or into the distance."
  A gesture (open hand, lean-in) is good; wandering eyes are not.

---

## C. Animate (Phase 3) — Grok `image_to_video`

**C1. `image_to_video` is FLAKY — expect transient failures and parallelize.**
- *Mistake:* "Failed to read video bytes: error decoding response body" hit repeatedly; one clip churned
  through ~8 internal retries and stalled 15+ min before it had to be killed.
- *Principle:* assume some calls fail transiently. **Fire all clips as parallel background jobs**, don't
  serialize. Don't let one stuck clip block the batch — cap the wait, kill it, and recover.
- *How:* `run_in_background: true` per clip; check back; `kill` a clip that's churned past ~a few minutes.

**C2. Harvest outputs from the session dir, not CLI stdout.**
- *Mistake:* the CLI sometimes reported only a filename ("3.mp4") or nothing; internal retries wrote numbered
  files `1.mp4 … 8.mp4` in the session dir, and the last valid one was the real success.
- *Principle:* find the output by globbing the Grok session videos dir and ffprobe-validating duration —
  don't rely on parsing the CLI message.
- *How:* `find ~/.grok/sessions/<urlencoded-cwd>/<session>/videos -name '*.mp4'`, pick the newest with a
  ~6s duration, copy it to `cN_raw.mp4`.

**C3. LOCKED-OFF camera for any beat with a screen or product to pin in post.** A static tripod keeps the
screen/product quad fixed so the composite holds across all frames.

**C4. Grok hard limits:** 6 or 10s only, 720p max, no audio-input param. Longer ad = stitched shots.

**C5b. CHAIN MULTI-CLIP ADS OFF THE PRIOR CLIP'S LAST FRAME — never generate each clip independently from the same anchor (the agent's continuity law, Hermes Main, proven 2026-06-13).**
- *Mistake:* the AI Mastery street-interview generated BOTH clips independently from the same base still. Each
  clip re-rolled the background crowd, so at the stitch the pedestrians/extras TELEPORTED — "stray people in
  the background reappear." A hard jump cut, instantly reads fake.
- *Principle (the law):* clip 1 is generated from the anchor; **clip 2 is generated from the LAST FRAME of
  clip 1, clip 3 from clip 2's last frame, etc.** Extract the trimmed last frame (`ffmpeg -sseof -0.05 -i
  cN.mp4 -update 1 -frames:v 1 cN_last.png`) and pass it as the `image=` to `image_to_video` with a
  "Continue from this EXACT last frame, NOT a new take — same people, wardrobe, mic, camera, lighting,
  background" prompt. Background crowd, wardrobe, mic, and light then carry through continuously.
- *Duplicate-frame glitch:* clipN+1's first frame == clipN's last frame, so the same frame shows twice at the
  seam = a visible stutter. **Trim the duplicate** — drop ~1 frame off the start of the next clip
  (`ffmpeg -ss 0.0417 ...`) before stitching. (Companion trim rule from Hermes: trim clip 1 to the end of the
  host's audio with no dead-air buffer.)
- *Verify:* contact-sheet clipN_last vs clipN+1_first (must be identical) and sample frames across the seam
  (no teleport, no stutter). Reference run: `~/ugc_pipeline/aimastery_interview/` (CHAIN_FINAL).

**C5c. The ANCHOR must be photoreal BEFORE animating — Grok cannot make a realistic first-frame still (the agent, 2026-06-13).**
- *Rule:* AI-generated stills look uncanny and every chained clip inherits that. The anchor must pass real-life
  photorealism QA first. Codex was the anchor-maker; when Codex auth is down, **Grok is NOT a substitute for
  the still** (it animates fine, but its stills read AI). Routes, in order of preference: (1) a REAL stock
  photo matching the scene (the agent's standing preference — real photos as video anchors); (2) generate the
  first frame in ChatGPT (sign into chatgpt.com in Chromium and prompt it); (3) Grok still only as a last
  resort, flag it as likely-uncanny. Confirm the anchor looks real before spending clip renders on it.

**C5d. Mic logic + no character drift for interviews (Hermes continuity_principles + PRODUCTION_RULES).**
- Speaker holds the mic at their OWN mouth while speaking; at the end of the host's question the host moves
  the mic in front of the guest, and the guest-answer clip starts from the host clip's last frame. The mic
  must NOT "fly to the camera" at a clip start (recurring defect). Keep it visible at normal interview distance.
- Same characters throughout — no role/gender/wardrobe drift. It's a public INTERVIEW: people stand facing each
  other at interview distance. NOT a couple, NOT walking together, NOT holding hands, NO kissing (a rejected
  drift). Mask/occlusion (a silent foreground shopper crossing close to lens) belongs ONLY in the final ~0.25s
  of a clip as a join mask — never at clip start.

**C5. Selfie + walking → Grok reframes to a third-person tracking shot and drops props.**
- *Mistake:* a "handheld selfie while walking through the airport" prompt produced a WIDE third-person shot
  of her walking and waving, the book gone, not talking to the lens. Grok resolves "walking" as locomotion
  filmed from outside, abandoning the selfie POV.
- *Principle:* for a selfie talking-vlog, keep the camera at the selfie distance and minimize locomotion.
  State explicitly: "front-facing iPhone selfie, her extended arm holding the phone stays in frame, framing
  stays CLOSE on face+upper body the entire time, do NOT zoom out to a wide third-person shot, she takes at
  most a slow casual step (mostly stationary), she does NOT wave, the [prop] stays in her other hand." A
  paused/slow selfie at a location reads as natural UGC; full walking does not survive. Verify the framing
  on the first clip before batching the rest.

---

## D. Voice (Phase 4)

**D0. Grok INVENTS its own dialogue — hard-lock the script and TRANSCRIBE every clip to verify (CRITICAL).**
- *Mistake:* clips set in an airport made Grok ad-lib travel-vlog lines ("Hey everyone, I'm at the airport,
  got this book for the flight...") instead of the scripted dialogue. Its mouth then lip-syncs the WRONG
  words. Framing looked perfect, so the problem was invisible until the audio was transcribed. Contextual
  scenes (airport/travel) and short lines trigger improv hardest; a wrong prop label (a book titled "Project
  Management") also pulls the ad-lib toward that topic.
- *Why it matters:* without a WaveSpeed key you CANNOT retarget the mouth, and STS only swaps timbre (it
  keeps whatever words Grok said). So the only fix is making Grok speak the exact line.
- *Principle:* in every `image_to_video` prompt, HARD-LOCK the dialogue: "CRITICAL DIALOGUE: she says these
  EXACT words and NOTHING else — no greeting, and she must NOT mention <the scene context: airport, flight,
  hotel, reading, the prop's topic>. Her only spoken words, lip-synced exactly, are: '<line>'." Then
  **transcribe each rendered clip with whisper** (`import whisper; whisper.load_model('base').transcribe(wav)`)
  and reject any clip whose transcript ≠ the script. Verify dialogue, not just framing.
- *Also:* neutralize props that carry text (a book with a wrong title) — they leak into the ad-lib.

**D0b. A VIBRANT/SCENIC background is itself a dialogue attractor — the scene out-shouts the script for abstract lines (proven 2026-06-13, AI Mastery street-interview vox-pop).**
- *Mistake:* a street-interview clip set on a busy NYC sidewalk (storefronts, crowds, a foam mic in frame)
  made Grok ad-lib "I love this neighborhood, the energy is so vibrant…" — a vox-pop tour answer — instead
  of the scripted AI-frustration hook. It failed **8/8 takes** even with the D0 hard-lock + an explicit
  forbidden-topics list. The SAME setting + lock rendered the OTHER clip's line correctly on the 2nd try.
- *Why:* `image_to_video` free-associates speech from what's IN the frame. A scenic/lively background is a
  strong "describe my surroundings" prior. An **abstract or filler-opening line** ("Okay honestly? I had
  forty tabs…") has weak anchoring and loses to the scene; a **concrete, noun-heavy, declarative line**
  ("Then I followed one prompt framework from this AI Mastery guide and turned a three-hour task into eleven
  minutes…") anchors strongly and survives.
- *Principle / the fix (two levers, apply both):* (1) **Rewrite the line concrete + declarative** — open on
  a real action/subject, not "okay/honestly/so", front-load the specific nouns. (2) **Strip ALL scene
  reinforcement from the prompt** and name the speech SUBJECT: "keep the background exactly as-is and do NOT
  describe it. This is a testimonial about <topic>. It is NOT a video about the city/neighborhood/street/
  surroundings and she does NOT comment on her location at all." Repeat the exact line twice (before+after
  the constraints). Then **fire 3 attempts in parallel and transcribe-pick** the matching take — even with
  the fix, ~1-in-3 still wanders, so render redundancy, don't serialize-and-pray. This took the AI Mastery
  hook from 0/8 to a clean match (whisper sim 0.86) on the next batch.



**D0c. Scripted dialogue in a 2-PERSON street/vox-pop scene: use SHORT "Dialogue only: INTERVIEWER:/GUEST:" exchanges, expect ~1/4 adherence, and chained continuations adhere WORSE (proven 2026-06-13, AI Mastery ChatGPT-anchor build).**
- *Mistake chain:* a photoreal 2-person sidewalk interview (ChatGPT anchor) ignored the dialogue lock almost every time, ad-libbing canonical vox-pop small talk ("Excuse me, how's the shopping going?"). Forcing ONE speaker to talk while the other stays silent failed 0/7. A LONG single-speaker guest line (~20 words) failed 0/4 then 0/6.
- *What worked:* the Hermes mall format — a SHORT two-line exchange rendered as `Dialogue only: INTERVIEWER: <≤10-word Q> GUEST: <≤10-word A>. No narrator, no small talk about shopping/the city, no captions.` — landed an EXACT match (whisper sim 1.00) at ~1/4. Carry a longer message across MULTIPLE short exchange clips, not one long line.
- *Chained clips are harder:* clip 1 off the CLEAN ChatGPT still hit 1/4; clip 2 generated off clip 1's LAST FRAME (a conversation-in-progress frame) hit 0/6 — the in-progress frame strengthens the "improv a fresh vox-pop" prior. Budget more attempts for chained clips, or accept the continuity/adherence tradeoff.
- *Always:* fire a BATCH (4-6) in parallel and whisper-transcribe-pick the exact match; never serialize-and-pray. Negative constraints ("do NOT mention shopping") help only weakly — short concrete scripted lines + batch+pick is what actually works.
- *RULED OUT — session/context isolation does NOT help (tested 2026-06-13).* Hypothesis: chained-clip adlib came from Grok conflating context across the same CLI session/cwd. Tested by rerunning the 0/4 chained clip from a PRISTINE isolated cwd (own fresh session namespace, zero prior artifacts) → **0/11, identical "how's the shopping going" adlib.** Reason: `image_to_video` is a STATELESS server-side call — it only ever receives (image, prompt); the CLI session/cwd context never reaches the video model. So a fresh session can't change adherence. The real driver is the INPUT IMAGE: a 2-person-on-a-busy-shopping-street frame makes the model improv canonical vox-pop dialogue regardless of the text prompt. Evidence: clip 1 off a CLEAN photographic still (ChatGPT anchor) = 1/4; clip 2 off a GROK-rendered last-frame of the same conversation = 0/15. Levers that DO matter: (a) a cleaner/less-iconic anchor image (a still that doesn't scream "street interview"), (b) solo talking-head instead of 2-person (solo last-frame chains adhere fine — see C5b), (c) short single-exchange lines + brute-force batch+pick. Continuity (chain off last frame) vs dialogue-adherence (clean still) is a real tradeoff in busy 2-person scenes.
- *Two-speaker voicing (one voice per speaker from a single clip):* whisper `word_timestamps=True` to find the speaker boundary, split the audio there, STS each segment to its own voice (interviewer→Eric, guest→Brittney), pad/trim each STS segment back to its exact source length so it stays locked to the lip motion, concat, mux `-map 0:V:0`. Reference: `~/ugc_pipeline/aimastery_interview/` (2c1_voiced.mp4).

**D1. Prefer speech-to-speech (STS) over fresh TTS when Grok already speaks the line in-clip.**
- *Mistake:* `voice_and_lipsync.py` (TTS + stretch) compressed a 9.24s read into 6s = 0.654× = rushed. Another failed review used a separate continuous voiceover over talking-face footage; the user rejected it because the lips were visibly off.
- *Principle:* Grok must speak the exact script first, because that creates the mouth timing. Then **`voiceswap` STS swaps
  the timbre to the target voice while preserving Grok's exact timing AND lip-sync** — no stretch artifacts. Do not place external TTS/continuous VO over a visible talking face. Use TTS/VO only on product-only, hands-only, or screen/book b-roll where no mouth is visible.
  Only use TTS+stretch when the stretch factor stays within ~0.8–1.25× and the mouth has been re-synced.
- *How:* `PYTHONPATH=~/voiceswap python3 -m voiceswap <clip> --voice <id> --out <clip>.sts.mp4` — OR, if the
  silence-segmentation rejects a chunk (see D2), STS the whole clip audio and mux it back.

**D2. STS the whole-clip audio; bypass the silence-segmenter when it chokes.**
- *Mistake:* voiceswap's segmenter produced a chunk ElevenLabs rejected as "File is corrupted." Also `sts.py`
  handed the SDK a file handle that got closed before the multipart upload ("I/O operation on closed file"
  — fixed 2026-06-10 by reading bytes into a BytesIO).
- *Principle:* extract one clean `44100 Hz mono pcm_s16le` wav → run STS on the whole thing → mux back.
- *How:* `ffmpeg -i clip.mp4 -vn -ac 1 -ar 44100 -c:a pcm_s16le clean.wav`; call `sts.make_converter(...)
  .convert_file('clean.wav','out.mp3')`; then mux per D3. (Reusable: `~/ugc_pipeline/vol1_soldout/sts_voice.sh`.)

**D3. Mux with `-map 0:V:0` (capital V).** Grok mp4s carry an embedded mjpeg cover stream; `-map 0:v` or
`-shortest` without `0:V:0` truncates the video to 1 frame. `ffmpeg -i clip.mp4 -i voice.mp3 -map 0:V:0
-map 1:a:0 -c:v copy -c:a aac -shortest out.mp4`.

**D4. Lip-sync without WaveSpeed = Grok-native motion + STS timbre (good enough).** True mouth re-sync needs
`WAVESPEED_API_KEY` in `~/.voiceswap.env`. Until then, STS is the best path (D1), not TTS.

**D5. Match voice gender + age to the avatar; render 2–3 candidates and let the user pick (proven 2026-06-11).**
The skill default (Brittney `kPzsL2i3teMYv0FxEYQ6`) is FEMALE — wrong for a male avatar. Proven male premade
voices (available to all accounts), pick by the avatar's look + the funnel goal:
- `cjVigY5qzO86Huf0OWal` — **Eric**, smooth/trustworthy, middle-aged → mature exec look + selling a paid product (best default for a male AI-educator avatar).
- `IKne3meq5aSn9XLyUdCD` — **Charlie**, deep/confident/energetic, young → higher energy.
- `TX3LPaxmHKxFdv7VOQHJ` — **Liam**, energetic social-media creator, young → most casual short-form.
- `nPczCjzI2devNBz1zQrb` — **Brian**, deep/resonant, middle-aged → authority/narration.
STS each one onto the SAME clip (`sts_<name>.mp3` → mux with `-map 0:V:0`) so the user compares on the real
avatar. List the account's voices via `GET https://api.elevenlabs.io/v1/voices` (filter `labels.gender`).

**D6. A cloned voice is a drop-in swap.** When the user clones their own voice (ElevenLabs Instant ≈1–3 min
audio, Professional ≈30+ min), nothing in the pipeline changes except the `voice_id` in the STS step —
re-run D1 and re-mux. Image, video, and lip-timing are untouched.

---

## E. Product & screen (Phase 5)

**E1. Physical book = animate the MOCKUP as a hands-only product shot.**
- *Mistake risk:* compositing a book into a face/selfie shot creates two-hands conflicts and lets Grok
  redraw the cover.
- *Principle:* `book_mockup.py` wraps the REAL cover on a 3D hardback held in hands. **Animate that mockup
  directly as a close product shot (no face needed — her VO carries the identity).**

**E1b. Generate the printed book via image_edit, then use it as a STATIC PLATE — never composite a flat cover onto a blank book (that's the sticker look), never animate a scene cover.**
- *Two mistakes, both rejected by the user:*
  1. Sending an `image_edit` book mockup to `image_to_video` animated the PRINTED scene (the cover's
     money-printer ran, money moved). A printed cover is static ink — it must not move.
  2. Compositing the flat real cover PNG onto a separate BLANK gray book (cover_on_book.py) looked like a
     "flat 2D cover sticker pasted on a generic blank book" — visible paste border, blank book showing
     around it, no edge-wrap, no spine, no print texture. Exactly what to avoid.
- *Principle (the fix):* the book must be ONE real manufactured object. `image_edit` the REAL cover PNG into
  a photo of a real published hardcover where the artwork is PRINTED INTO the cover and wraps the book
  geometry — slight 3/4 angle so the SPINE (designed, same language, title down it) and the cream page block
  show, linen/matte print texture, room light/shadow across the ink, fingers wrapping the edge, NO floating
  panel / paste border / blank book. Then make THAT a **static plate** (loop the still 6s) + gentle 2D
  Ken-Burns push-in, so the printed scene physically cannot animate. No face in this beat → VO is voiceover,
  no lip-sync. Same static-plate principle as the laptop (E6).
- *How:* `image_edit cover.png` with the "real printed hardcover, spine visible, printed into the cover, not
  a sticker/panel, keep artwork identical" prompt (generate 2-3, pick the most book-like) → `ffmpeg -loop 1`
  to 6s → `ffmpeg zoompan` push-in → mux VO. Reference: `~/ugc_pipeline/vol1_soldout/book_real_B.jpg →
  c2_realbook.mp4`. The old `cover_on_book.py` composite is DEPRECATED for this — it makes the sticker look.
  Heuristic: a scene/action cover (people, machines, motion) must never be animated; a flat typographic
  cover could survive direct animation but the static-plate printed-book route is the reliable default.

**E2. Device-screen beats need a staged keyframe, then composite — don't make Grok render the content.**
- *Mistake avoided:* Grok softens/hallucinates on-screen text if asked to render it.
- *Principle:* `image_edit` the base still so the laptop/phone faces the camera with a **blank light-gray
  screen + a hand on the trackpad/device**, lock the camera, animate, THEN composite the real PDF with
  `ugc-device-screen/pdf_screen.py --mode handdriven`. Real pixels = sharp text.

**E2b. A PDF on a screen must look like a PDF VIEWER, not a fullscreen image.**
- *Mistake:* the ebook was pinned edge-to-edge filling the whole laptop screen → read as a fullscreen
  picture, not a real reader. A real laptop PDF (macOS Preview) shows the page floating on a dark gray
  matte with side margins, a top toolbar (window dots), and a "Page N of M" pill.
- *Principle:* render the page(s) inside viewer chrome before pinning. `pdf_screen.py --chrome preview`
  (now the DEFAULT) does this: charcoal matte, page fit-to-height centered with gutters, toolbar + live
  page-counter pill that tracks the hand-driven scroll. Use `--chrome none` only if you deliberately want
  the old edge-to-edge fill. Portrait page on a landscape screen → big side gutters, which is correct/real.

**E3. A screen moves only when the avatar drives it or a real video plays in it.** Otherwise it stays
static. A doc that scrolls with no hand input reads fake instantly.

**E4. Device interaction = OVER-THE-SHOULDER POV, never face-to-camera + hand-on-keyboard.**
- *Mistake:* the device beats faced the laptop screen AT the camera while her hand reached the keyboard —
  physically impossible (if the screen faces the viewer, the keyboard faces away from her). The hand
  appeared to type "through" the screen. Impossible geometry instantly kills realism.
- *Principle:* split the two jobs cleanly. (a) **Talking-head** beats: she faces camera, hands off the
  device, just talks (B3). (b) **Device-demo** beats: cut to an **over-the-shoulder POV** — camera behind/
  above her, we see the screen at a natural reading angle + the keyboard + her hands, NO face. This is the
  only physically correct way to show both her hands and the screen content. Generate the POV as its own
  keyframe (blank screen), animate locked, composite the PDF onto the angled screen quad (measure/pass
  `--quad` since the screen is a trapezoid + the bright window fools auto-detect). No face → VO is pure
  voiceover, no lip-sync cost. Reference: `~/ugc_pipeline/vol1_soldout/c34_pov_keyframe.jpg → c3_pov_*`.
- *Sub-rule:* **don't animate typing for no reason.** If she's reading a PDF, she just SCROLLS (trackpad
  two-finger gesture). Only show typing if the action genuinely requires a text field (search box, form),
  and then the keystrokes MUST actually appear on the screen (composite the typed text) and her fingers
  press real keys. When in doubt, scroll — don't type. (Recurring miss — state "two-finger SCROLL on the
  trackpad, does NOT type, no key-pecking" explicitly in the animation prompt every time.)

**E5. The composited screen must sit INSIDE the bezel — inset the quad, don't let content bleed off.**
- *Mistake:* the pinned viewer bled past the screen edges so it looked like the display was "coming off"
  the laptop. The quad was set to the outer screen/bezel, and any drift pushed content onto the bezel/desk.
- *Principle:* measure the quad to the INNER lit screen area and inset it a few px on every side so the
  composite reads as pixels behind the glass, never overlapping the black bezel. On an angled POV the
  screen is a trapezoid — pass `--quad` (auto-detect grabs the bright window).

**E6. For a rock-solid rigid screen, composite onto a STATIC PLATE — a Grok-animated laptop MORPHS and no tracking can fix that (CRITICAL).**
- *Mistake chain:* (1) pinned the PDF to ONE fixed quad → bled off as the laptop drifted. (2) Added per-frame
  planar tracking → still wrong, because the underlying Grok-animated laptop doesn't just translate, it
  NON-RIGIDLY MORPHS/breathes frame to frame (bezel and keys deform). Tracking a deforming surface makes the
  rigid PDF swim with it; the screen never reads as a real rigid display. A dense frame sequence (not just
  mid+end) exposed the laptop swinging/warping.
- *Principle (the fix):* a real display cannot deform, so the laptop under it must not deform either. Build
  device-screen beats on a **STATIC laptop plate** — a single still POV image looped to the beat length —
  so the laptop is physically rigid and the screen plane is perfectly fixed. Composite the PDF onto that
  fixed quad (`--no-track`, since the plate doesn't move) and scroll it (`--mode continuous` or handdriven).
  Add life with a gentle **2D Ken-Burns push-in** (ffmpeg `zoompan`) on the whole frame — a rigid transform
  that keeps the screen perfectly planar. Result reads as a real screen-recording insert composited on
  filmed footage: rigid, rectangular, contained, no warp/swim/bleed. This intercuts cleanly as b-roll
  between the moving talking-head beats; a brief "static" POV is normal and far better than a morphing one.
- *How:* `ffmpeg -loop 1 -i pov_plate.jpg -t 6 -r 24 ... plate6s.mp4` → `pdf_screen.py --clip plate6s.mp4
  --mode continuous --chrome preview --quad q.json --no-track` → `ffmpeg ... zoompan` push-in → mux VO.
  Vary the Ken-Burns framing between the two POV beats so they don't look identical. Reference:
  `~/ugc_pipeline/vol1_soldout/c34_plate_6s.mp4 → c3_plate_kb.mp4 / c4_plate_kb.mp4`.
- *Tracking (`--track`) still exists* for cases where you must composite onto real filmed (rigid) footage or
  a barely-moving clip — but for Grok-generated laptops, prefer the static plate.

---

## F. Caption & stitch (Phase 6)

**F0. CAPTIONS OFF BY DEFAULT (the agent's standing preference, 2026-06-10).**
- *Mistake:* the first Vol I cut burned in BOTH a per-beat caption and a persistent "results vary"
  disclaimer. the agent wanted ZERO on-screen subtitles ("there are two sets of subtitles — I don't want any").
- *Principle:* do NOT burn captions or any on-screen text unless the user explicitly asks for them. Stitch
  the ad straight from the voiced/composited clips (`cN_voiced` / `cN_screen`), skip the caption step.
- *How:* keep captioning as a separate, optional step so the no-caption cut is just a re-stitch of the
  pre-caption clips — no re-render. Reference: `~/ugc_pipeline/vol1_soldout/vol1_soldout_ad_NOCAPS_FINAL.mp4`
  (stitch c1_voiced,c2_voiced,c3_screen,c4_screen,c5_voiced,c6_voiced → loudnorm).
- *Compliance caveat:* the on-screen "results vary" disclaimer helped satisfy FTC clear-and-conspicuous for
  PAID. With captions off, rely on the SPOKEN disclaimer (beat 5); flag to the user that paid placement may
  want the on-screen disclaimer back.

**F1. IF captions are explicitly requested:** overlays stay punchy — ≤ ~6 words, wrapped to ≤ ~20 chars/line
(long captions wrap badly and bury the point), and spoken disclaimer alone covers organic.

**F3. Caption on the normalized geometry, then stitch.** `stitch_shots.sh` re-encodes to 720×1280/24fps;
burn captions on that same scale/crop so text placement is consistent, then concat.

**F4. Loudness-normalize the final mix.**
- *Mistake:* per-clip mean volume varied −21 to −34 dB — jarring on playback.
- *Principle:* finish with `ffmpeg -af "loudnorm=I=-16:TP=-1.5:LRA=11"` on the stitched ad for an even level.

---

## G. Truthful creative (copy + visuals)

**G1. Keep paid creative truthful — copy AND visuals.** A clean script can still render a non-compliant
frame (before/after imagery, fake charts, luxury-wealth props, a generated UI, burned-in text that
overpromises). Before any paid spend, eyeball the final cut + every key still and fix the offending shot
(re-render the frame, remove the prop, swap the burned-in line). First-person testimonial framing, an
explicit "results vary", and a spoken price on paid are the claim rules that keep Meta/TikTok placements clean.

---

## H. Build-ops (for the agent driving the render)

**H1. Use Python, not zsh loops, for multi-file orchestration.** Complex zsh loops with nested
grep/quoting broke mid-render ("command not found"). A short Python block over the file list is reliable.

**H2. Frame-grab and VIEW each generated still/clip before building on it.** Catch identity drift, a
non-facing screen, or a redrawn cover early — before you animate/voice/composite on top of a bad asset.

**H3. Keep a clean run dir under `~/ugc_pipeline/<slug>/`.** Copy each session output to `cN_raw.mp4` with an
ffprobe duration check; name stages `cN_raw → cN_voiced → cN_screen → cN_final`; the stitched result is the
only thing you hand off.

## Trailing dead air after speech (multi-shot pieces) — trim to speech+0.5s
**Symptom:** stitched episode runs long with awkward pauses; short lines placed in fixed 6/10s
Grok containers leave 1–3s of "silence" after the speaker finishes.
**Trap:** `silencedetect` (and reversed-audio silencedetect) report ZERO trailing silence — Grok
fills the post-speech tail with low-level room tone that never drops below ~−20 dB, so threshold-
based silence detection is blind to it.
**Fix:** detect the true voice-end by DIRECT RMS windowing (last 0.1s window above ~6% of the clip's
peak RMS), then cut each clip to `speech_end + 0.5s`. Clips already ending tight get a held-frame pad
to a uniform 0.5s tail. Tool: `scripts/trim_clip_tails.py --glob '<clips>/clip*.mp4' --out-dir <...>_trimmed --tail 0.5`.
Run it BEFORE the stitch. On the ClarityBooks 3-host podcast this removed 52.5s across 35/47 clips
(7.2min → 6.4min) with no clipped words.

---

# Whiteboard talking-head avatar — lessons (Systems Gladiator build, 2026-06)

Full playbook: `~/ugc_pipeline/systems_gladiator_v2/PRODUCTION_BIBLE.md` + `QA_CHECKLIST.md` +
`character.json`. The high-value, reusable failure→rule pairs:

## V1. STS inherits the SOURCE accent — do not self-clone the operator
A user's own PVC swapped over Grok's American-cadence audio came out sounding American/wrong, because
speech-to-speech preserves the source's prosody and accent and only recolors timbre. **Rule:** for an
avatar, pick a voice whose accent matches the (American) Grok source so the whole video unifies. To use
the operator's *real* accent you need TTS-from-clone + a lip-sync re-animation pass (WaveSpeed), not STS.

## V2. STS does NOT re-animate the mouth — Grok must actually talk on every shot
Voice ran while the mouth stayed closed on writing/board-turned shots (Grok under-animates speech when
the face is angled at the board). **Rule:** every talking shot prompt must say "talks continuously, mouth
clearly opening and closing on every word, never silent or still," and keep writing shots in 3/4 view with
"lips moving even while he writes." Fix only the failing shots, not the whole video. Proper fix if a valid
`WAVESPEED_API_KEY` exists: `sync/lipsync-2` re-animates the mouth to the new audio (stored key was 401).

## V3. Pace without breaking lip-sync
To speed delivery ~1.15x, apply `setpts=PTS/1.15` (video) AND `atempo=1.15` (audio) TOGETHER on the final
stitch. Equal factor keeps lips synced; atempo preserves pitch. Free post-process, no credits.

## V4. Contractions = the naturalness lever
Formal "it is / you are / here is / I would" reads robotic. Write "it's / you're / here's / I'd." Combined
with stability 0.4 (down from 0.5) and the 1.15x pace, this is what made the read sound human.

## V5. Grok hallucinates number-finger gestures
He threw up two fingers on "building one system." **Rule:** prompt "natural open hands only, no
finger-counting, no peace sign, no holding up a number." A counted gesture that mismatches the spoken
number is an instant reject. QA every shot with a hand-region frame strip.

## V6. Whisper mis-transcribes "I'd" → caption typos
Captions showed "3 ODD BUILD" / "I BUILD FIRST" for "three I'd build" / "I'd build first" (audio was
fine). **Rule:** apply a caption correction map before burning (`ODD→I'D`, `I BUILD FIRST→I'D BUILD
FIRST`) and re-transcribe from the FINAL swapped+sped audio. Caption-text fixes are free (re-burn only).

## V7. `ugc_add_voice.py` returns voice_not_found on valid voices
Bypass it; call the ElevenLabs STS REST endpoint directly. Working reference:
`~/ugc_pipeline/systems_gladiator_v2/swap_all.py`.

## V8. Voice-audition economics
STS ~1000 credits/min; a full multi-shot re-swap of a 3-min video ~3000 credits. Audition any new voice
on ONE shot (~170 credits) before committing to the full swap. Failed (404) swaps don't bill.

## V9. macOS file lock on delivery
Overwriting a Desktop file that's open in a player throws "Operation not permitted." Write a new version
name (e.g. `_v3`) instead, or close the player first.
