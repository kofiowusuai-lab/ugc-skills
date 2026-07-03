# Realism prompt patterns (proven)

Goal: most viewers look twice. The enemy is "AI gloss" — plasticky skin, perfect
symmetry, studio lighting, bokeh, even framing.

## Base character still (Codex/Grok image_gen)

Stack these directives:
- **Capture story:** "candid selfie shot on an iPhone front camera", "webcam still",
  "shot on a phone held a bit low and close"
- **Skin truth:** "natural unretouched skin with visible pores, slight under-eye
  shadows, a few flyaway hairs", "no makeup gloss, no beautification, no studio retouch"
- **Light truth:** "soft overcast daylight", "warm indoor window light", "realistic
  dynamic range with slightly blown highlights on the window" — NOT "studio lighting"
- **Framing truth:** "slightly imperfect framing", "mild lens distortion", "no bokeh,
  no shallow depth of field"
- **Context:** real, mundane setting (in a car, at a kitchen table, on a couch)
- **Aspect:** vertical 9:16 for UGC

## Seed the face from a reference image (BEST likeness — proven 2026-06-11)

Don't describe a face in words and hope. Pass an existing portrait as the identity anchor:
`echo "<prompt below>" | codex exec --skip-git-repo-check -s workspace-write -i identity_ref.jpg -`

The `-i` image fixes WHO; the prompt does the realism + wardrobe + setting. Proven prompt that turned a
stylized brand-character illustration into a real-looking UGC creator in one shot:

> Use the attached image as the IDENTITY REFERENCE. Generate ONE photorealistic image and save it as
> `<name>.png`. Keep this EXACT person: same skin tone, same hair, same beard, same facial structure.
> Render him FULLY PHOTOREALISTIC, NOT an illustration. Candid selfie shot on an iPhone front camera held
> slightly low and close. [wardrobe]. [real mundane setting] with soft warm window light. Natural
> unretouched skin with visible pores, faint under-eye shadows, a few flyaway hairs, no makeup gloss, no
> studio retouch. Realistic dynamic range with slightly blown window highlights, slightly imperfect
> framing, mild lens distortion, NO bokeh, NO shallow depth of field, NO AI gloss. Direct eye contact,
> calm confident faint smile. Vertical 9:16. No watermark, no captions, no text, no logos.

If the source is illustrated/stylized, the "render FULLY PHOTOREALISTIC, NOT an illustration" line is
load-bearing — omit it and you get a glossy cartoon back. Codex saves to `~/.codex/generated_images/<uuid>/`
then copies to the filename you named. View it before animating.

## Keep identity across shots (image_edit)

Always pass the base reference image and say: "keep this EXACT person identical —
same face, skin texture, freckles, hair, wardrobe — change ONLY <pose/expression/setting>."
Generate 2-4 keyframes per shot when you want pose variety, then feed them to Grok
`reference_to_video`.

## Animation (Grok image_to_video / reference_to_video)

- Hard limits: duration 6 or 10s, 720p max, NO audio input.
- Grok emits its OWN lip-synced speech audio. Put the actual line as dialogue in the
  prompt to control what she "says": `prompt: '...she says: "the exact line here"...'`
- Natural mannerisms: "blinks, small head tilts, eyebrow raises, subtle breathing,
  a faint genuine smile, a small hand gesture near her chest"
- Camera: handheld micro-shake for talking-head; LOCKED-OFF tripod when you need a
  screen/product to stay pinnable in post.

## Anti-leak

No watermarks, no captions, no UI overlays unless intended. Don't ask for logos or
brand names baked into the image (they come out garbled) — composite those in post.
