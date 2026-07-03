---
name: ugc-ad-strategist
description: Use when a UGC ad needs a BRAIN for the words, not just the visuals — researching the audience, mining what's already winning in-market, picking the single claim, and writing the hook + beat sheet. Triggers: "what should the ad say", "write the UGC script/ad copy for <product>", "research the angle for this ad", "make the ad actually convert", or invoked as Phase 0 by ugc-video-producer for "make a UGC ad for <product>". Produces brief.json (one claim, 6 hooks, beat sheet, platform cuts) that ugc-video-producer turns into the finished video.
---

# UGC Ad Strategist — the research + scriptwriting brain

`ugc-video-producer` can make a real-looking person say words with synced lips and show a real product.
It has **no brain for the words**. This skill IS that brain: market research → one claim → killer-script
copy → `brief.json`. The producer consumes `brief.json` and renders the video.

**Scripting engine:** this skill delegates the narrative craft to the **`killer-script-system`** skill
(installed active at `~/.claude/skills/killer-script-system/`) — Packaging/Outline pick the claim + angle,
Intro/Body/Outro + native-CTA write the copy. This skill wraps it with the two things it lacks for paid
UGC: live research and short-form ad shaping.

> **MINIMAX MODE — offload the WRITING to Claude (self-test: can't see an image = MiniMax).** MiniMax
> writes stiff, ad-flavored dialogue. When on MiniMax this skill is Step 2 of the **`ugc-minimax-mode`**
> pipeline (follow that skill for the whole job). Do NOT let the Script stage write the copy itself —
> run `~/.openclaw/scripts/ugc_write_script.sh --product "<...>" --context "<...>" --format testimonial|two_person_interview|street_interview --clips <n> --out <run>/script.json` (natural, brief-schema JSON), then merge into `brief.json`. Research + brief stages can stay on MiniMax; only the dialogue/hook WRITING needs Claude. On **Codex/gpt-5.5**, skip this — Codex writes natural copy itself.

> **Generation principles:** the script you produce gets rendered by `ugc-video-producer`, whose
> `reference/ugc_qa_bank.md` is the bank of real production mistakes-turned-rules. The script-side ones
> (A1 size dialogue to 6/10s clips, A2 only script REAL on-screen assets, A3 truthful scarcity, A4 the
> non-negotiables) are enforced in the Script stage below — honor them.

## When to run

- The user asks what an ad should say / to write ad copy / to research the angle for a product.
- `ugc-video-producer` Phase 0 hands off a product (not a finished script).
- Fully autonomous by design: research → finished `brief.json` with no stops.

## How to run it (the launch sequence)

It's a `Workflow`-script pipeline (deterministic research fan-out), same pattern as
`ebook-from-scratch` and `deep-research`. The Workflow `args` channel is unreliable on this machine
(see the ebook args-not-delivered note), so the product spec is passed via a **request.json file** the
workflow reads, not via args alone.

1. **Write the request.** Pick a slug, make a run dir, write `request.json`:
   ```bash
   SLUG="aimastery-$(date +%s)"; RUN=~/aimastery_ads/strategist_runs/$SLUG; mkdir -p "$RUN"
   cat > "$RUN/request.json" <<'JSON'
   { "product": "The Complete AI Mastery Collection",
     "company": "claritybooks",
     "kind": "digital",
     "country": "US",
     "voice_id": "kPzsL2i3teMYv0FxEYQ6",
     "competitors": [],
     "notes": "4 books, $59.99 one-time. LP: aimastery-salespage.vercel.app" }
   JSON
   ```
   Only `product` is required; the workflow resolves the rest (company → `~/.openclaw/companies.json`,
   funnel → the live landing page, assets → the real PDFs).

2. **Launch the workflow**, passing the request path via args AND relying on the newest-request fallback:
   Call the `Workflow` tool with
   `{ scriptPath: "~/.claude/skills/ugc-ad-strategist/scripts/strategist_workflow.js",
      args: { requestPath: "<RUN>/request.json" } }`.

3. **On return**, the workflow gives you `brief_path` (default `<RUN>/brief.json`), the `single_claim`,
   `clip_count`, and `hook_count`. Read `brief.json` and hand it to `ugc-video-producer`.

## The 5 stages (what the workflow does)

| Stage | Job |
|---|---|
| **A · Ground** | product → company → LIVE funnel (offer, price, anchor, exact LP headlines for message-match), ad industry, niche keywords, real on-screen PDF assets. |
| **B · Research** | 3 parallel streams: voice-of-customer (`~/code/kojo-audience-scraper/exports/`), market/angle intel (web research: winning angles + 2026 scam-flag claim patterns to avoid + awareness stage + sophistication), proven-winner ad mining (`scripts/ad_library_scout.py` → Meta Ad Library + TikTok Creative Center, ranked by longevity). |
| **C · Brief** | killer-script Packaging+Outline → ONE claim (capability, never income), angle, proof object, objections, message-match line, differentiation vs in-market winners. |
| **D · Script** | killer-script Intro/Body/Outro → 6 hook variants, the 6-beat sheet (hook→proof→mechanism→escalation→honest-80/20→CTA) with per-beat dialogue/emotion/action/grok_prompt/overlay, platform cuts (paid speaks price for FTC; organic DM CTA), voice direction, UTM map. |
| **E · Assemble** | Merge everything into `brief.json` (the producer contract). |

## Output contract — `brief.json`

Defined by `reference/brief_schema.json`. The producer already expects per-clip `dialogue`, `base_still_prompt`,
`voice.id`, and (digital) `screen_asset.pages`. Key fields: `single_claim`, `clips[]`, `hooks[]`,
`platform_cuts`, `voice`, `utm_map`, `funnel`, `market_winners[]`.

## The non-negotiables (baked into the template, enforce them)

One claim per ad · capability not income · first-person past-tense testimonial · process proof beats
outcome proof · honest 80/20 to pre-handle the objection · persistent "results vary" disclaimer spoken +
on-screen · price spoken on paid · caption every beat. These are house-style writing rules — write to them
as you draft, not as a fix after the fact. Full rationale + the killer-script→UGC beat map:
`reference/ad_package_template.md`.

## Tools / standalone use

- **Ad mining only:** `python3 scripts/ad_library_scout.py --query "AI course" --min-days 30 --json`.
  Degrades to a URLs-to-check result when Meta is bot-gated — never fabricates ads.

## Gotchas

- **Reuses, doesn't reinvent:** `killer-script-system` (copy), `llm.sh`, the kojo exports,
  `deep-research` (heavier fallback for Stage B2), `ugc-device-screen`. Don't duplicate these.

## Companion skills

- **ugc-video-producer** — consumes `brief.json`, renders the video (this skill is its Phase 0).
- **killer-script-system** — the scripting engine this skill drives.
- **ugc-device-screen** — pins the real PDF on the device for `screen_asset` proof clips.
