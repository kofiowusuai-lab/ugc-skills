# UGC Ad Package Template (distilled from the AI Mastery package)

This is the proven shape every `ugc-ad-strategist` brief must hit. It maps the
`killer-script-system` 5-step framework onto a short-form paid UGC ad. Built from
`~/aimastery_ads/ugc_verdiqt/AD_PACKAGE.md` (v4, Meta+TikTok proven, zero fails).

## The non-negotiables (learned the hard way)

1. **One claim per ad.** Pick a single capability/process claim. Everything else (origin story,
   escalation, mechanism) exists only to support that one claim. Multiple claims = weaker ad + more
   compliance surface.
2. **Capability claim, never income.** "I built X in 2 hours" passes. "Make $10k/month" fails. Income
   claims are the #1 scam pattern reviewers flag in 2026. Speed-of-build / capability claims with
   visible screen proof sit in the believable zone.
3. **First-person, past-tense testimonial.** "I built", "the guide got me building", "two hours got me
   to 80%". Present/second-person ("two hours GETS YOU 80%") reads as a guaranteed result and FAILS
   Meta. Move every claim into lived experience.
4. **Process proof beats outcome proof.** Real screen recording of the real product/app/pages, prompt
   visible, app responding. Show the thing working. This is the load-bearing believability element.
5. **Pre-handle the objection with honest 80/20.** A candid "two hours got me to 80%, the polish took
   longer, your results will vary" reads credible, not weak. It disarms the skeptic before they object.
6. **Persistent disclaimer, spoken AND on-screen.** "My results. Results vary." Spoken in the 80/20 beat
   + a persistent lower-third from clip 1. TikTok's FTC layer fails without the canonical qualifier;
   Meta warns if the on-screen disclaimer is inconspicuous. Do both.
7. **Price spoken for paid.** Dark posts have no bio/DM. Speak the price in the CTA ("four books, fifty-
   nine ninety-nine, one payment") — qualifies clicks and satisfies FTC clear-and-conspicuous disclosure.
8. **Caption everything.** 40%+ watch muted. Burned-in overlay per beat.

## Killer-script-system -> UGC beat map

| killer-script step | UGC ad beat | job |
|---|---|---|
| Packaging (idea+title+expectation) | the **single claim** + the **hook** | lock the one promise; create the curiosity loop in <2.5s |
| Outline (prove novelty) | **angle + mechanism** | the differentiator — WHY this works when the viewer has seen the generic version |
| Intro (click-confirm, common belief, contrarian, plan, proof) | **hook -> proof** beats | confirm the promise fast, show the real proof object |
| Body (rising value, context/application/framing, re-hooks) | **mechanism -> escalation** | the system/secret, then the escalation that raises the stakes (the rising-value pattern) |
| Outro (recap, reality>expectation) | **honest 80/20 -> CTA** | disarm the objection, land the native CTA |
| Native-embed CTA | **CTA beat** | "tap learn more" (paid) / "DM BUILD" (organic) — feels native, not interruptive |

## Canonical 30s / 6-clip beat sheet

| beat | seconds | job | line shape |
|---|---|---|---|
| hook | 2.5 | curiosity loop, the claim teased | first-person, surprising, <25 words |
| proof | 6 | show the real product working | name the product + what it does, over a real screen recording |
| mechanism | 6 | the "why mine works" differentiator | calm, confiding, lowered voice — the secret/system |
| escalation | 5-6 | raise the stakes, rising value | matter-of-fact pride, a bigger lived result |
| honest_8020 | 5 | disarm the objection | candid, "X got me to 80%, polish took longer, results vary" |
| cta | 5 | native CTA + price (paid) | friendly, zero pressure, speak price, "tap learn more" |

15s cut = hook + proof + mechanism + cta (drop escalation + standalone 80/20; fold "results vary" into proof or cta).

## Hook variant menu (test 6, hold body+CTA constant)

Winning hook category is knowable within ~48h of spend. Tag each by `hook-id` in `utm_content`.

1. **Speed/capability flex (master):** "I built this in two hours. Zero code from me."
2. **Skeptic reversal:** "I thought the two-hour app thing was fake. Then my agent shipped this."
3. **Authority contrast:** "Devs quoted me three weeks. My agent did 80 percent in two hours."
4. **Confession:** "Nobody wants to say this out loud. You don't need to code anymore."
5. **Cold open on the proof (no avatar first):** screen recording plays, VO over it.
6. **Message-match (LP mirror):** the exact Chapter-01 / hero line of the landing page. Strongest
   ad->LP congruence. NOTE: a second-person personal-attribute callout ("You don't have an X problem")
   warns on Meta — run h6 on TikTok/organic only.

## Special angle: physical sold-out -> ebook still available (scarcity, ONLY when true)

When the product has a REAL physical edition that is genuinely sold out or a limited run, this is a strong,
legitimate angle: the avatar holds the physical book, notes the hardcopies are gone, and points to the
ebook as the still-available way in. It carries real urgency without a performance/income claim.

**HARD RULE — truthful scarcity only.** "Hard copies are sold out" is a scarcity claim. Run it ONLY when
the request confirms it's true (`physical_status: hardcopy_sold_out` or similar). False/invented scarcity
("sold out" when there was never a print run, or stock remains) fails the FTC layer, gets demonetized on
Meta/TikTok, and breaks the honest house style (no fake testimonials/guarantees by design). If scarcity
isn't verified true, drop the claim and use a true line that keeps the energy ("there's no print version,
the full thing is the instant digital set").

**Dual-proof structure (two real anchors):**
- A **physical beat** (`product_shot`): the avatar holds the real HARDCOVER. Grok can't invent a faithful
  book, so the producer builds a photoreal hardcover mockup from the REAL cover art via
  `ugc-video-producer/scripts/book_mockup.py` (covers live at `~/code/aimastery-salespage/covers/`:
  `ai-mastery-vol1/vol2/vol3/bonus.png`). The cover stays identical; only its physical form is generated.
- A **digital beat** (`screen_asset`): the real ebook PDF on her laptop/phone, sharp, scrolled by her hand.

Example beat line (true-scarcity): *"So the hardcovers are completely sold out, like gone, but the good
news is the full thing is still up as the ebook, you just download it."* CTA then points at the ebook funnel.
Pair with the persistent "My results. Results vary." disclaimer as usual; the scarcity line itself carries
no disclaimer need when it's factually true, but keep it factual (don't add a fake countdown).

## Platform cuts

- **Paid (Meta/TikTok dark post):** speak the price, native button "Learn More" (beats "Shop Now"
  ~20% on cold info-product traffic), persistent disclaimer, no DM CTA (dark posts have none).
- **Organic (Spark Ads / creator post):** DM CTA ("DM me BUILD"), present-tense allowed more loosely
  but keep claims honest, disclaimer still recommended.
- **Meta vs TikTok line swaps:** keep a per-platform swap list for any line one platform warns on
  (e.g. second-person callouts -> TikTok only; "working first try" -> organic only, never Meta paid).

## Delivery direction (feeds Grok animation prompts)

- Hook: surprised/amused, telling a friend something wild. NOT salesy excitement.
- Mechanism: calm, slight lean-in, confiding, slow down 10%.
- 80/20: candid, managing expectations like a friend.
- CTA: casual shrug energy, peer recommendation, point down once at the end.
- Edit at ~1.1x with a hard cut every beat. No dead air.

## Persona seed (generate ONCE, reuse across all clips)

One consistent avatar identity across every cut — audiences disengage when the face changes. Realism
directives (candid phone-camera, natural light, skin texture, slight grain, no logos/watermark/text)
per `ugc-video-producer/scripts/realism_prompts.md`. Optionally generate 2 seeds = 2 single-identity
ad accounts.

## Voice

Default casual UGC voice: Brittney "Social Media Voice" `kPzsL2i3teMYv0FxEYQ6`, `eleven_multilingual_v2`,
stability 0.45 / similarity 0.75 / style 0.30. Put filler words ("okay so", "honestly", "I'm not gonna
lie") in the script, not the voice settings. ~24-28 spoken words per 10s.
