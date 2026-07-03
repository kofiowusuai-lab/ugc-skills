export const meta = {
  name: 'ugc-ad-strategist',
  description: 'Research + scriptwriting brain for a UGC ad. Resolves the funnel, mines voice-of-customer + live winning ads, picks ONE claim, writes a killer-script-system beat sheet, and emits brief.json for ugc-video-producer.',
  phases: [
    { title: 'Ground', detail: 'resolve product -> company -> live funnel + message-match' },
    { title: 'Research', detail: 'voice-of-customer + market angles + proven-winner ad mining + awareness stage' },
    { title: 'Brief', detail: 'synthesize one claim + angle + objections (killer-script Packaging/Outline)' },
    { title: 'Script', detail: 'write 6 hooks + beat sheet + grok prompts + platform cuts (killer-script Intro/Body/Outro)' },
    { title: 'Assemble', detail: 'merge + write brief.json (the producer contract)' },
  ],
}

const SKILL = (process.env.HOME || '~') + '/.claude/skills/ugc-ad-strategist'
const REQ_HINT = (args && args.requestPath) ? String(args.requestPath) : ''

// ---- schemas ----------------------------------------------------------------
const GROUND_SCHEMA = {
  type: 'object',
  required: ['product', 'company', 'kind', 'funnel', 'run_dir'],
  properties: {
    product: { type: 'string' },
    company: { type: 'string' },
    kind: { type: 'string', enum: ['digital', 'physical'] },
    industry: { type: 'string', description: 'ad industry: ecommerce/finance/health_supplements/etc' },
    niche_keywords: { type: 'array', items: { type: 'string' } },
    competitors: { type: 'array', items: { type: 'string' } },
    product_assets: { type: 'array', items: { type: 'string' }, description: 'abs paths to real PDFs/screens for device shots' },
    physical_status: { type: 'string', description: "verified physical-edition status from the request, e.g. 'hardcopy_sold_out' | 'in_stock' | 'digital_only'. Drives whether a true sold-out scarcity angle is allowed." },
    cover_image: { type: 'string', description: 'abs path to the REAL cover art for a physical hardcover mockup (truthful source), if a physical beat applies' },
    run_dir: { type: 'string', description: 'abs working dir for this run (where request.json lives)' },
    funnel: {
      type: 'object',
      required: ['lp_url', 'price', 'cta'],
      properties: {
        lp_url: { type: 'string' }, price: { type: 'string' }, anchor: { type: 'string' },
        cta: { type: 'string' }, lp_headlines: { type: 'array', items: { type: 'string' } },
        utm_meta: { type: 'string' }, utm_tiktok: { type: 'string' },
      },
    },
  },
}

const RESEARCH_SCHEMA = {
  type: 'object',
  required: ['summary'],
  properties: {
    summary: { type: 'string' },
    customer_words: { type: 'array', items: { type: 'string' } },
    pains: { type: 'array', items: { type: 'string' } },
    desires: { type: 'array', items: { type: 'string' } },
    objections: { type: 'array', items: { type: 'string' } },
    winning_angles: { type: 'array', items: { type: 'string' } },
    scam_flags: { type: 'array', items: { type: 'string' }, description: 'claim patterns reviewers flag now — avoid these' },
    awareness_stage: { type: 'string' },
    market_sophistication: { type: 'integer' },
    market_winners: { type: 'array', items: { type: 'object' } },
    citations: { type: 'array', items: { type: 'string' } },
  },
}

const BRIEF_SCHEMA = {
  type: 'object',
  required: ['avatar', 'awareness_stage', 'single_claim', 'angle', 'proof_object', 'message_match'],
  properties: {
    avatar: {
      type: 'object', required: ['segment', 'core_pain', 'core_desire'],
      properties: {
        segment: { type: 'string' }, core_pain: { type: 'string' }, core_desire: { type: 'string' },
        objections: { type: 'array', items: { type: 'string' } },
        customer_words: { type: 'array', items: { type: 'string' } },
      },
    },
    awareness_stage: { type: 'string' },
    market_sophistication: { type: 'integer' },
    single_claim: { type: 'string' },
    angle: { type: 'string' },
    proof_object: { type: 'string' },
    message_match: { type: 'string' },
    differentiation: { type: 'string', description: 'how this ad differs from the in-market winners' },
  },
}

// Script package schema mirrors reference/brief_schema.json (the producer contract).
const SCRIPT_SCHEMA = {
  type: 'object',
  required: ['base_still_prompt', 'clips', 'hooks', 'platform_cuts', 'voice', 'utm_map'],
  properties: {
    base_still_prompt: { type: 'string' },
    clips: {
      type: 'array', minItems: 4,
      items: {
        type: 'object',
        required: ['id', 'seconds', 'beat', 'dialogue', 'emotion', 'action', 'grok_prompt', 'overlay'],
        properties: {
          id: { type: 'string' }, seconds: { type: 'number', enum: [6, 10] }, beat: { type: 'string' },
          dialogue: { type: 'string' }, emotion: { type: 'string' }, action: { type: 'string' },
          grok_prompt: { type: 'string' }, overlay: { type: 'string' },
          screen_asset: {
            type: 'object',
            properties: {
              pdf: { type: 'string' }, pages: { type: 'string' },
              device: { type: 'string' }, driven_by: { type: 'string' },
            },
          },
          product_shot: {
            type: 'object',
            properties: {
              cover_image: { type: 'string' }, book: { type: 'string' },
              staging: { type: 'string' }, scarcity: { type: 'string' },
            },
          },
        },
      },
    },
    hooks: {
      type: 'array', minItems: 6, maxItems: 6,
      items: {
        type: 'object', required: ['id', 'category', 'line', 'overlay'],
        properties: {
          id: { type: 'string' }, category: { type: 'string' }, line: { type: 'string' },
          overlay: { type: 'string' }, platform_note: { type: 'string' },
        },
      },
    },
    platform_cuts: {
      type: 'object', required: ['paid', 'organic'],
      properties: {
        paid: { type: 'object' }, organic: { type: 'object' },
        persistent_disclaimer: { type: 'string' },
      },
    },
    voice: { type: 'object', required: ['id'], properties: { id: { type: 'string' }, model: { type: 'string' }, settings: { type: 'object' } } },
    utm_map: { type: 'object' },
  },
}

const ASSEMBLE_SCHEMA = {
  type: 'object',
  required: ['brief_path'],
  properties: {
    brief_path: { type: 'string' },
    clip_count: { type: 'integer' },
    hook_count: { type: 'integer' },
    note: { type: 'string' },
  },
}

// ---- pipeline ---------------------------------------------------------------

phase('Ground')
const ground = await agent(
  `You are Stage A (Ground) of the ugc-ad-strategist. Resolve the product, its company, and the LIVE funnel.

1. Find the run request. Try reading this path first: "${REQ_HINT}". If empty/missing, run:
   ls -t ~/aimastery_ads/strategist_runs/*/request.json 2>/dev/null | head -1
   and read the newest. The request names the product (and may name voice, assets, competitors, country).
2. Map the product -> company key using ~/.openclaw/companies.json.
3. Read the LIVE landing page source for message-match. For AI Mastery the LP is
   ~/code/aimastery-salespage/index.html (live at aimastery-salespage.vercel.app). Pull the exact
   offer, price, anchor, the CTA destination, and 3-5 verbatim hero/headline lines the ad must mirror.
   If the product LP source isn't local, WebFetch the live URL named in the request.
4. Pick the ad industry (ecommerce for info products/books, else the closest of
   finance/health_supplements/crypto/gambling/alcohol/dating).
5. Identify 3-6 niche_keywords and any named competitors for ad-library mining.
6. List real product_assets (abs paths to the actual PDF/app) for on-screen device shots if kind=digital.
   AI Mastery PDFs live under ~/Desktop/AI Mastery Guide - Complete Series/ and ~/aimastery*_assets/.
7. Read physical_status from the request (e.g. "hardcopy_sold_out", "in_stock", "digital_only"). This is the
   ONLY basis for a sold-out scarcity claim. If the request does NOT confirm a real sold-out/limited physical
   edition, set physical_status to "digital_only" and do not enable any scarcity angle. When a physical
   edition applies, resolve the REAL cover art for the named volume from ~/code/aimastery-salespage/covers/
   (ai-mastery-vol1/vol2/vol3/bonus.png) and report it as cover_image.
8. Report run_dir = the directory the request.json lives in.

Return ONLY the structured object.`,
  { schema: GROUND_SCHEMA, phase: 'Ground', label: 'ground' }
)

const runDir = ground.run_dir || '~/aimastery_ads/strategist_runs/run'
const industry = ground.industry || 'ecommerce'
const kw = (ground.niche_keywords || [ground.product]).slice(0, 3)
const competitors = (ground.competitors || []).join(',')

phase('Research')
// Four parallel research streams -> barrier, because the brief needs all of them together.
const streams = await parallel([
  () => agent(
    `Stage B1 — Voice-of-customer for "${ground.product}". Read the existing exports in
     ~/code/kojo-audience-scraper/exports/ (buyer_dictionary.md, sales_page_copy_bank.md,
     repeated_phrases.csv, product_spec_inputs.md). Extract the audience's ACTUAL words, top pains,
     top desires, and the 3 objections most likely to kill the sale. If the exports don't fit this
     product, say so and infer from the funnel. Return the research object (focus customer_words,
     pains, desires, objections).`,
    { schema: RESEARCH_SCHEMA, phase: 'Research', label: 'voc' }
  ),
  () => agent(
    `Stage B2 — Market/angle intel for "${ground.product}" (a ${ground.kind} product, niche: ${kw.join(', ')}).
     Do focused web research (WebSearch + WebFetch): what UGC ad angles are converting in this niche right
     now, the top buyer objections, and the exact claim PATTERNS ad reviewers + viewers flag as scammy in
     2026 (so we avoid them). Return winning_angles, scam_flags, awareness_stage (unaware..most_aware),
     market_sophistication (1-5), and citations (urls).`,
    { schema: RESEARCH_SCHEMA, phase: 'Research', label: 'market' }
  ),
  () => agent(
    `Stage B3 — Proven-winner ad mining. Run:
       python3 ${SKILL}/scripts/ad_library_scout.py --query "${kw[0]}" ${competitors ? `--advertisers "${competitors}"` : ''} --min-days 30 --out ${runDir}/ad_winners.json --json
     Read its JSON output. If degraded=true, fall back: WebSearch/WebFetch the Meta Ad Library and TikTok
     Creative Center URLs it printed, and pull a few real active competitor ads (advertiser, hook, format,
     start date if shown, offer, CTA). Rank by longevity (ads live >=30 days are likely winners — log the
     dates, don't assume). Return market_winners (array) + winning_angles + a one-line summary. NEVER invent ads.`,
    { schema: RESEARCH_SCHEMA, phase: 'Research', label: 'ad-library' }
  ),
])
const [voc, market, adlib] = streams.map(s => s || {})

phase('Brief')
const brief = await agent(
  `You are Stage C (Creative Brief) of ugc-ad-strategist. This is killer-script-system's Packaging + Outline
   step applied to a paid UGC ad. READ the framework first:
     ${SKILL}/reference/ad_package_template.md   (the proven shape + non-negotiables)
     ${process.env.HOME || '~'}/.claude/skills/killer-script-system/SKILL.md   (the 5-step psychology engine, optional companion skill)

   Inputs:
   - Funnel: ${JSON.stringify(ground.funnel)}
   - Product: ${ground.product} (${ground.kind}), industry ${industry}
   - Voice-of-customer: ${JSON.stringify({ words: voc.customer_words, pains: voc.pains, desires: voc.desires, objections: voc.objections })}
   - Market intel: ${JSON.stringify({ angles: market.winning_angles, scam_flags: market.scam_flags, awareness: market.awareness_stage, soph: market.market_sophistication })}
   - In-market winners: ${JSON.stringify((adlib.market_winners || []).slice(0, 8))}

   Produce a ONE-PAGE strategic brief:
   - avatar (segment, core_pain, core_desire, 2-3 objections to pre-handle, customer_words verbatim)
   - awareness_stage + market_sophistication (these dictate hook style and proof depth)
   - THE single_claim: one capability/process claim, never income, that the whole ad supports
   - angle that carries it; proof_object (the real thing shown on screen)
   - message_match: the exact line mirroring the landing page hero
   - differentiation: how this ad is NOT the same as the in-market winners
   Honor the non-negotiables (one claim, first-person past-tense, process proof, honest 80/20, disclaimer).
   Return ONLY the structured object.`,
  { schema: BRIEF_SCHEMA, phase: 'Brief', label: 'brief' }
)

phase('Script')
const defaultPdf = (ground.product_assets || [])[0] || ''
const script = await agent(
  `You are Stage D (Script package) of ugc-ad-strategist. Run killer-script-system's Intro -> Body -> Outro
   + native-CTA steps, then shape the copy into the short-form UGC beat sheet from
   ${SKILL}/reference/ad_package_template.md. Re-read that template and the producer contract
   ${SKILL}/reference/brief_schema.json so your JSON matches exactly what ugc-video-producer consumes.

   Brief to execute: ${JSON.stringify(brief)}
   Funnel: ${JSON.stringify(ground.funnel)}
   Product kind: ${ground.kind}; real on-screen asset (digital only): ${defaultPdf || '(none)'}
   Physical status: ${ground.physical_status || 'digital_only'}; real cover art: ${ground.cover_image || '(none)'}

   WRITING RULES — write the copy to these from the start (house style, applied as you draft):
   First-person past-tense testimonial voice only; never a guaranteed/second-person result ("gets you",
   "you will"); no income/earnings claims; capability/process framing; truthful scarcity only. These apply to
   every dialogue line, hook line, CTA, overlay, AND every grok_prompt (on-screen/burned-in text counts too).

   Produce:
   - base_still_prompt: ONE persona-seed for the spokesperson, realism-directive compliant
     (candid phone-camera, natural light, skin texture, slight grain, no logos/text/watermark).
   - clips[]: the 6-beat sheet (hook, proof, mechanism, escalation, honest_8020, cta). Each clip:
     id (c1..), seconds — MUST be exactly 6 or 10 (Grok renders ONLY 6s or 10s; do NOT use 2.5/5),
     beat, dialogue, emotion (delivery), action (gesture/camera; LOCKED-OFF when a screen must stay
     pinnable), grok_prompt (ready-to-paste image_to_video prompt that ends with: says: "<dialogue>"),
     overlay (burned caption, <=6 words). CRITICAL — size dialogue to the clip length so the spoken VO
     fits at natural pace (QA Bank A1): ~14-16 words for a 6s clip, ~24-28 words for a 10s clip. If a line
     needs more room, set seconds:10; never overstuff a 6s clip (it forces a chipmunked voice). On-screen
     content must be a REAL asset we have (QA Bank A2) — only reference a PDF/app/screen we can truthfully
     show; never script a fake UI/screenshot. For the PROOF beat on a digital product, attach
     screen_asset {pdf:"${defaultPdf}", pages:"<range>", device:"laptop", driven_by:"avatar_scroll"}
     — screen only moves when the avatar drives it or a video plays.
   - SOLD-OUT SCARCITY (only if Physical status above is "hardcopy_sold_out"): use the dual-proof angle from
     the template. Make the PROOF/hook region a PHYSICAL beat where the avatar holds the real hardcover and
     says a TRUE sold-out line (e.g. "the hardcovers are completely sold out, gone, but the full thing is
     still up as the ebook"), with product_shot {cover_image:"${ground.cover_image || ''}", staging:"hands",
     scarcity:"hardcopy_sold_out"} on that clip; keep a separate ebook screen_asset beat as digital proof,
     and route the CTA to the ebook. If Physical status is NOT hardcopy_sold_out, DO NOT mention sold-out or
     any scarcity — it would be false. Never invent stock numbers, countdowns, or "selling fast".
   - hooks[]: exactly 6 swappable variants (h1..h6) across the categories speed_flex, skeptic_reversal,
     contrast, confession, cold_open, message_match. <2.5s spoken, <25 words, each with overlay +
     platform_note (flag any second-person-attribute hook as TikTok/organic only).
   - platform_cuts: paid {cta_line (SPEAKS the price for FTC), native_button:"Learn More", meta_safe_swaps[],
     tiktok_swaps[]} and organic {cta_line (DM CTA)}, plus persistent_disclaimer ("My results. Results vary.").
   - voice: { id:"kPzsL2i3teMYv0FxEYQ6", model:"eleven_multilingual_v2", settings:{stability:0.45,similarity:0.75,style:0.30} }
     unless the request names another voice.
   - utm_map: { meta:"<lp_url>?utm_source=meta&utm_medium=paid&utm_campaign=ugc&utm_content=<hook-id>",
                tiktok:"...utm_source=tiktok..." } using the real lp_url.
   Return ONLY the structured object.`,
  { schema: SCRIPT_SCHEMA, phase: 'Script', label: 'script' }
)

// Assemble the full brief.json (strategist output contract) and write it for ugc-video-producer.
phase('Assemble')
const assembled = await agent(
  `You are Stage E (Assemble) of ugc-ad-strategist. Build brief.json — the producer contract.

   1. Merge these into ONE object and write valid JSON to ${runDir}/brief.json:
      ${JSON.stringify({
        product: { name: ground.product, company: ground.company, kind: ground.kind },
        avatar: brief.avatar, awareness_stage: brief.awareness_stage,
        market_sophistication: brief.market_sophistication, single_claim: brief.single_claim,
        angle: brief.angle, proof_object: brief.proof_object, message_match: brief.message_match,
        funnel: ground.funnel,
        market_winners: (adlib.market_winners || []).slice(0, 8),
      })}
      plus the script package fields base_still_prompt, clips, hooks, platform_cuts, voice, utm_map from:
      ${JSON.stringify(script)}
      Keep ALL keys. Write the file.

   2. Re-read ${runDir}/brief.json and confirm it parses. Return brief_path=${runDir}/brief.json,
      clip_count, hook_count, and a short note.`,
  { schema: ASSEMBLE_SCHEMA, phase: 'Assemble', label: 'assemble' }
)

return {
  product: ground.product,
  company: ground.company,
  kind: ground.kind,
  run_dir: runDir,
  brief_path: assembled.brief_path || `${runDir}/brief.json`,
  single_claim: brief.single_claim,
  angle: brief.angle,
  clip_count: assembled.clip_count,
  hook_count: assembled.hook_count,
  market_winners: (adlib.market_winners || []).length,
  note: assembled.note || 'brief.json assembled for ugc-video-producer',
}
