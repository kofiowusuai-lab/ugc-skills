#!/usr/bin/env bash
# ugc_broll_plan.sh
# -----------------------------------------------------------------------------
# Claude decides the MOTION-GRAPHIC B-ROLL timeline for a talking-head video:
# which spoken spans cut away from the avatar to a full-screen animated graphic,
# and which graphic (kinetic typography / quote card / stat punch) shows what.
# Driven by whisper word-timings so cutaways land exactly on the words.
#
# USAGE
#   ugc_broll_plan.sh --words words.json --out segments.json \
#       [--max-coverage 0.4] [--min-gap 2.0] [--model sonnet|opus]
#
# words.json = [{"text","start","end"}...] (from ugc_captions.py)
# OUT segments.json = [{"kind":"kinetic|quote|stat","start","end",
#                       "payload":{"text"|"number"|"label"|"keywords"}}...]
# -----------------------------------------------------------------------------
set -uo pipefail
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
WORDS="" OUT="" MAXCOV="0.4" MINGAP="2.0" MODEL=""
while [[ $# -gt 0 ]]; do case "$1" in
  --words) WORDS="$2"; shift 2;; --out) OUT="$2"; shift 2;;
  --max-coverage) MAXCOV="$2"; shift 2;; --min-gap) MINGAP="$2"; shift 2;;
  --model) MODEL="$2"; shift 2;;
  -h|--help) sed -n '2,18p' "$0"; exit 0;; *) echo "unknown arg: $1" >&2; exit 2;; esac; done
[[ -z "$WORDS" || -z "$OUT" ]] && { echo "ERROR: --words and --out required" >&2; exit 2; }
[[ ! -f "$WORDS" ]] && { echo "ERROR: words file not found: $WORDS" >&2; exit 2; }
WORDS="$(cd "$(dirname "$WORDS")" && pwd)/$(basename "$WORDS")"
OUT="$(cd "$(dirname "$OUT")" 2>/dev/null && pwd || echo .)/$(basename "$OUT")"
TOTAL=$(python3 -c "import json;w=json.load(open('$WORDS'));print(round(w[-1]['end'],2) if w else 0)")

PF="$(mktemp -t broll_plan)"; trap 'rm -f "$PF"' EXIT
cat > "$PF" <<EOF
You are the MOTION-GRAPHIC B-ROLL editor for a talking-head video. Read the word-level
transcript with timings here: ${WORDS} (JSON array of {text,start,end}, total ~${TOTAL}s).

Decide which spoken spans should CUT AWAY from the avatar's face to a full-screen animated
graphic (b-roll), and which graphic type to use. Everywhere else the avatar shows.

Graphic types:
- "kinetic": big animated typography of the exact spoken phrase. Use for punchy, quotable,
  or emphatic lines. payload: {"text": "<the exact words spoken in that span>", "keywords": ["<1-2 words to accent>"]}.
- "quote": a clean full-screen card holding ONE strong statement. Use for the single best
  line and the closing line. payload: {"text": "<the line>", "label": "<optional short tag or empty>"}.
- "stat": a giant number + short label. Use ONLY when a real number/percentage/quantity is
  spoken. payload: {"number": "<e.g. 90%>", "label": "<short label>"}.
- "image": a full-screen B-ROLL IMAGE (with a short caption) illustrating something CONCRETE
  and VISUAL the line mentions (a place, object, action, scene — e.g. "the gym", "a notebook",
  "my savings", "a busy street"). Use it when a real picture says more than text. payload:
  {"image_prompt": "<a vivid photo-realistic image-gen prompt for that visual, no text/logos/watermark>",
   "text": "<2-4 word caption, optional>"}.

Each segment may also set:
- "transition": one of "punch" (default), "dissolve", "slide" — how it enters/exits.

RULES:
- Align every start/end to the word timings (a segment must cover whole words). Read the actual
  start/end values from the file.
- Each cutaway 1.5 to 3.0 seconds. Leave at least ${MINGAP}s of avatar between cutaways (let his
  face breathe). Do NOT cover more than ${MAXCOV} of the total runtime with graphics.
- Never overlap segments. Order them by start time.
- text payloads must be the ACTUAL words spoken during that span (so it matches the audio).
- Use "image" only when the line names something genuinely visual; otherwise prefer kinetic.
- Pick the strongest moments, not every line. A typical 20s video gets 2-4 cutaways; a 60s video
  gets 6-10. Mix the types: mostly kinetic, an image or two when visual, quote for the best/closing
  line, stat only for real numbers.

Output ONLY a JSON array (no prose) to ${OUT} using the Write tool:
[{"kind":"kinetic","start":1.6,"end":3.1,"transition":"punch","payload":{"text":"you're not behind","keywords":["behind"]}},
 {"kind":"image","start":7.0,"end":9.2,"transition":"dissolve","payload":{"image_prompt":"a cozy home gym at dawn, soft light, photoreal","text":"show up daily"}}]
If there are no good moments, write [].
EOF

echo "[broll-plan] planning cutaways over ${TOTAL}s ..." >&2
ARGS=(-p "$(cat "$PF")" --allowedTools "Read Write" --permission-mode bypassPermissions \
      --add-dir "$(dirname "$OUT")" --add-dir "$(dirname "$WORDS")" --output-format text)
[[ -n "$MODEL" ]] && ARGS+=(--model "$MODEL")
"$CLAUDE_BIN" "${ARGS[@]}" >/dev/null 2>&1

if [[ -f "$OUT" ]] && python3 -c "import json;a=json.load(open('$OUT'));assert isinstance(a,list)" 2>/dev/null; then
  n=$(python3 -c "import json;print(len(json.load(open('$OUT'))))")
  echo "{\"ok\": true, \"segments\": $n, \"out\": \"$OUT\"}"
  exit 0
else
  echo "[]" > "$OUT"   # safe fallback: no cutaways
  echo "{\"ok\": true, \"segments\": 0, \"out\": \"$OUT\", \"note\": \"planner produced nothing; empty timeline\"}"
  exit 0
fi
