#!/usr/bin/env bash
# ugc_from_image.sh
# -----------------------------------------------------------------------------
# IMAGE-FIRST one-shot: the user drops an anchor image + says the outcome he wants,
# and this drives the whole back half — Grok candidates → Claude-vision QA (drift
# rejection + pick the match) → stitch/deliver → optional voice — to a finished
# clip. No need to compose or QA anything by hand.
#
# USAGE
#   ugc_from_image.sh --image ANCHOR --outcome "<what the video should do/say>" \
#       [--dialogue "<exact spoken line>"] [--n 6] [--duration 6] \
#       [--voice <name|id>] [--job <DIR>] --out <final.mp4>
#
# Pipeline: build Grok motion/dialogue prompt (continuity-locked to the anchor) →
# ugc_grok_candidates.sh (N takes) → ugc_claude_deliver.sh (QA + deliver, anchor =
# the dropped image). Prints the final path + report location.
# -----------------------------------------------------------------------------
set -uo pipefail
SCRIPTS="$HOME/.openclaw/scripts"
IMAGE="" OUTCOME="" DIALOGUE="" N=6 DURATION=6 VOICE="" JOB="" OUT="" MINSCORE=0.80
while [[ $# -gt 0 ]]; do case "$1" in
  --image) IMAGE="$2"; shift 2;; --outcome) OUTCOME="$2"; shift 2;;
  --dialogue) DIALOGUE="$2"; shift 2;; --n) N="$2"; shift 2;;
  --duration) DURATION="$2"; shift 2;; --voice) VOICE="$2"; shift 2;;
  --job) JOB="$2"; shift 2;; --out) OUT="$2"; shift 2;; --min) MINSCORE="$2"; shift 2;;
  -h|--help) sed -n '2,22p' "$0"; exit 0;; *) echo "unknown arg: $1" >&2; exit 2;; esac; done

[[ -z "$IMAGE" || -z "$OUTCOME" ]] && { echo "ERROR: --image and --outcome required" >&2; exit 2; }
[[ ! -f "$IMAGE" ]] && { echo "ERROR: image not found: $IMAGE" >&2; exit 2; }
IMAGE="$(cd "$(dirname "$IMAGE")" && pwd)/$(basename "$IMAGE")"
[[ -z "$JOB" ]] && JOB="$HOME/ugc_pipeline/from_image_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$JOB/clips" "$JOB/refs"
[[ -z "$OUT" ]] && OUT="$JOB/final_delivery.mp4"
# Copy the dropped image in up front — Telegram/image-cache paths are ephemeral.
ANCHOR_COPY="$JOB/refs/anchor.${IMAGE##*.}"
cp "$IMAGE" "$ANCHOR_COPY" && IMAGE="$ANCHOR_COPY"

# 1) Build the Grok motion/dialogue prompt, continuity-locked to the dropped anchor.
PROMPT="Continue from this EXACT source image as frame 1: keep the SAME person(s), same face, same "
PROMPT+="wardrobe, same setting and framing — no substitutions, no extra or missing people. "
PROMPT+="${OUTCOME}. Subtle handheld micro-shake, natural blinks and small natural movement, direct "
PROMPT+="eye contact where appropriate. Photoreal, real phone-video look, no on-screen text/captions/watermark."
if [[ -n "$DIALOGUE" ]]; then
  PROMPT+=" The person speaks naturally and says: \"${DIALOGUE}\""
fi

echo "[from-image] job=$JOB anchor=$(basename "$IMAGE") n=$N dur=${DURATION}s" >&2

# 2) Generate N Grok candidates from the anchor.
"$SCRIPTS/ugc_grok_candidates.sh" --image "$IMAGE" --prompt "$PROMPT" \
  --slot clip1 --n "$N" --out-dir "$JOB/clips" --duration "$DURATION"
GEN_RC=$?
if [[ $GEN_RC -ne 0 ]]; then
  echo "{\"ok\": false, \"error\": \"no Grok candidates produced\", \"job\": \"$JOB\"}"
  exit 1
fi

# 3) Claude-vision QA + delivery. Anchor = the dropped image. Generic continuity criteria
#    (works for any dropped image — single person, product, scene; not interview-specific).
CRITERIA="The clip must preserve the EXACT person(s), wardrobe, and setting shown in the anchor: no "
CRITERIA+="identity/wardrobe/location substitution, no extra or missing people, same shot scale. Drift "
CRITERIA+="to a different person, outfit, or place is a FAIL."

DELIVER_ARGS=(--job "$JOB" --anchor "$IMAGE" --pattern 'clips/clip*_candidate_*.mp4' \
  --out "$OUT" --criteria "$CRITERIA" --min "$MINSCORE")
[[ -n "$VOICE" ]] && DELIVER_ARGS+=(--voice "$VOICE")
"$SCRIPTS/ugc_claude_deliver.sh" "${DELIVER_ARGS[@]}"
DEL_RC=$?

if [[ -f "$OUT" ]]; then
  echo "{\"ok\": true, \"out\": \"$OUT\", \"job\": \"$JOB\", \"report\": \"$JOB/claude_delivery_report.json\"}"
  exit 0
else
  echo "{\"ok\": false, \"error\": \"delivery did not produce $OUT (see report)\", \"job\": \"$JOB\", \"report\": \"$JOB/claude_delivery_report.json\"}"
  exit 1
fi
