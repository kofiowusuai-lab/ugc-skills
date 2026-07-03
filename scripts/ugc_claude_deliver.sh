#!/usr/bin/env bash
# ugc_claude_deliver.sh
# -----------------------------------------------------------------------------
# Hand a UGC job to a HEADLESS CLAUDE agent that SEES the clips natively, does the
# visual QA against the supplied anchor, picks the matching takes, and drives
# delivery to a finished video. One handoff replaces "MiniMax -> referee script
# -> stitch -> voice".
#
# Why Claude: it is natively multimodal. With --allowedTools "Read Bash ..." a
# headless `claude -p` agent reads the anchor and the extracted frames as real
# pixels (not a lossy text description), judges identity/setting/composition,
# rejects Grok drift, then runs ffmpeg / the delivery scripts itself. Billing is
# the Claude Code subscription, independent of the capped Codex account.
#
# USAGE
#   ugc_claude_deliver.sh --job DIR --anchor IMG --pattern GLOB --out FILE \
#       [--brief brief.json] [--voice ELEVEN_VOICE_ID] [--criteria "..."] \
#       [--min 0.80] [--qa-only] [--model sonnet|opus] [--dry-run] \
#       [--engine auto|claude|gemini] [--gemini-model gemini-2.5-pro]
#
# ENGINE / FALLBACK
#   --engine auto (default): run the headless Claude agent; if the claude CLI is
#   missing or fails at runtime (rate limit / crash / no report), AUTOMATICALLY
#   fall back to the Gemini vision referee (ugc_gemini_referee.py), which judges
#   the same anchor-vs-take contract on real pixels and writes the same report,
#   then this script delivers (voice/stitch) deterministically.
#   --engine claude forces Claude (no fallback); --engine gemini forces Gemini.
#   Defaults also read from UGC_DELIVER_ENGINE / UGC_GEMINI_MODEL.
#
# MODES
#   default   : QA + select winners + assemble/stitch + (if --voice/--brief) voice
#               -> finished mp4 at --out.
#   --qa-only : QA + select winners only, copy the chosen take(s), write the
#               report. No voice/stitch. (Drop-in replacement for the referee.)
#
# OUTPUT
#   <job>/claude_delivery_report.json  - per-candidate verdicts + decisions.
#   --out                              - the finished/selected video.
#   Exit 0 = delivered/selected. Exit 1 = a clip had no passing take (drift) or a
#   delivery step failed; the report says which.
# -----------------------------------------------------------------------------
set -uo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
PRODUCER_SCRIPTS="${UGC_PRODUCER_SCRIPTS:-}"
for _c in "$HOME/.claude/skills/ugc-video-producer/scripts" "$HOME/.hermes/skills/marketing-and-ads/ugc-video-producer/scripts"; do
  [ -z "$PRODUCER_SCRIPTS" ] && [ -d "$_c" ] && PRODUCER_SCRIPTS="$_c"
done
[ -z "$PRODUCER_SCRIPTS" ] && PRODUCER_SCRIPTS="$HOME/.claude/skills/ugc-video-producer/scripts"
GEMINI_REFEREE="${GEMINI_REFEREE:-$HOME/.openclaw/scripts/ugc_gemini_referee.py}"
ADD_VOICE="${ADD_VOICE:-$HOME/.openclaw/scripts/ugc_add_voice.py}"
. "$HOME/.openclaw/scripts/ugc_engine_lib.sh"  # claude_live(), valid_json(), validate_engine()

# Engine selection: auto (default) tries Claude and falls back to the Gemini
# referee when Claude is missing or fails at runtime; claude/gemini force one.
# Override globally with UGC_DELIVER_ENGINE or per-call with --engine.
ENGINE="${UGC_DELIVER_ENGINE:-auto}"
GEMINI_MODEL="${UGC_GEMINI_MODEL:-gemini-2.5-pro}"

JOB="" ANCHOR="" PATTERN="*.mp4" OUT="" BRIEF="" VOICE="" CRITERIA="" MIN="0.80"
QA_ONLY=0 MODEL="" DRYRUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --job) JOB="$2"; shift 2;;
    --anchor) ANCHOR="$2"; shift 2;;
    --pattern) PATTERN="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --brief) BRIEF="$2"; shift 2;;
    --voice) VOICE="$2"; shift 2;;
    --criteria) CRITERIA="$2"; shift 2;;
    --min) MIN="$2"; shift 2;;
    --qa-only) QA_ONLY=1; shift;;
    --model) MODEL="$2"; shift 2;;
    --engine) ENGINE="$2"; shift 2;;
    --gemini-model) GEMINI_MODEL="$2"; shift 2;;
    --dry-run) DRYRUN=1; shift;;
    -h|--help) sed -n '2,40p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

[[ -z "$JOB" || -z "$ANCHOR" ]] && { echo "ERROR: --job and --anchor required" >&2; exit 2; }
[[ ! -d "$JOB" ]] && { echo "ERROR: job dir not found: $JOB" >&2; exit 2; }
[[ ! -f "$ANCHOR" ]] && { echo "ERROR: anchor not found: $ANCHOR" >&2; exit 2; }
case "$ENGINE" in auto|claude|gemini) ;; *) echo "ERROR: --engine must be auto|claude|gemini" >&2; exit 2;; esac
# Claude presence is only fatal when the engine is forced to claude. In auto we
# fall back to Gemini; in gemini we never touch Claude.
if [[ "$ENGINE" == "claude" && ! -x "$CLAUDE_BIN" ]]; then
  echo "ERROR: --engine claude but claude CLI not found at $CLAUDE_BIN" >&2; exit 2
fi
ANCHOR="$(cd "$(dirname "$ANCHOR")" && pwd)/$(basename "$ANCHOR")"
JOB="$(cd "$JOB" && pwd)"
[[ -n "$OUT" ]] || OUT="$JOB/final_delivery.mp4"

DEFAULT_CRITERIA='The take must show the SAME people as the anchor with NO substitution: same number of people, same left/right positions, each person'"'"'s race/gender/age/hair unchanged, each person'"'"'s clothing unchanged, each role unchanged (the one holding the mic stays the interviewer), the same setting/background type, and the same shot scale. Drift to a different person, swapped sides, changed outfit, a new location, or generic street/shopping b-roll is a FAIL.'
[[ -n "$CRITERIA" ]] || CRITERIA="$DEFAULT_CRITERIA"

# ---- build the delivery instruction block (only when not qa-only) ----
DELIVERY_BLOCK="This run is QA + SELECT ONLY. After choosing the winning take for each clip slot, copy it to a clearly named final path inside the job dir, and STOP. Do not voice or stitch."
if [[ "$QA_ONLY" -eq 0 ]]; then
  read -r -d '' DELIVERY_BLOCK <<EOF
After QA + selection, DELIVER the finished video:
1. Order the winning takes by clip number (clip1, clip2, ...).
2. VOICE: the DEFAULT is to KEEP GROK'S NATIVE VOICE — do NOT voice-swap unless a voice was explicitly requested. A voice id was ${VOICE:+provided: $VOICE}${VOICE:-NOT provided}. Only if a voice id is present (or a brief.json at $BRIEF specifies a per-clip voice) swap it with speech-to-speech (preserves Grok lip-sync): python3 ~/.openclaw/scripts/ugc_add_voice.py --clip <take> --voice <id-or-name> --out <take>_voiced.mp4 . Otherwise leave every take on its native Grok audio and proceed.
3. Stitch the winners (voiced only if step 2 swapped them, else native) into one vertical cut: bash "$PRODUCER_SCRIPTS/stitch_shots.sh" "$OUT" <take1> <take2> ...
4. Confirm "$OUT" exists and is a valid non-empty mp4 (ffprobe).
EOF
fi

PROMPT=$(cat <<EOF
You are the visual QA + delivery agent for a UGC video job. You have native vision: USE the Read tool on image files to actually SEE them. Work only inside: $JOB

ANCHOR (the supplied reference every take must preserve): $ANCHOR
First, Read the anchor and write one line describing exactly who/what is in it.

CANDIDATE TAKES: files in $JOB matching the glob "$PATTERN" (use Glob/Bash to list them). These are Grok image_to_video outputs and many will have DRIFTED off the anchor.

IDENTITY / CONTINUITY CONTRACT:
$CRITERIA

QA PROCEDURE (do this for every candidate take):
- Extract 2 frames with ffmpeg: one near the start (-ss 0.15) and one near the middle. Save to a temp path inside the job dir.
- Read the anchor AND both frames. Compare them against the contract above. Be skeptical: identity/continuity drift is the failure we are hunting; when unsure, score lower. Ignore video compression artifacts, judge people + setting.
- Give each take: overall_score 0.0-1.0, identity_match true/false, setting_match, composition_match, and a short list of concrete mismatches.
- A take PASSES only if identity_match is true AND overall_score >= $MIN.

SELECTION:
- If several candidates are clip variants of the same slot (e.g. clip1_candidate_*), pick the single highest-scoring PASS per slot as the winner.
- If a slot has NO passing take, do NOT lower the bar. Record it as FAILED and name the drift. The job is not deliverable until it is regenerated.

$DELIVERY_BLOCK

ALWAYS, at the end, write $JOB/claude_delivery_report.json with this shape:
{
  "anchor": "$ANCHOR",
  "anchor_description": "<what you saw>",
  "candidates": [ {"file":"...","overall_score":0.0,"identity_match":false,"setting_match":false,"composition_match":false,"mismatches":["..."],"verdict":"..."} ],
  "winners": [ {"slot":"clip1","file":"<path>","score":0.95} ],
  "failed_slots": [ {"slot":"clip2","reason":"all takes drifted: different woman"} ],
  "delivered": "<path to $OUT or null>",
  "status": "delivered" | "selected" | "blocked"
}
Then print a 3-line human summary: how many takes passed/failed, the winners, and whether $OUT was produced. If any slot FAILED or delivery did not complete, make the LAST line exactly: RESULT: BLOCKED. Otherwise the last line: RESULT: OK.
EOF
)

REPORT="$JOB/claude_delivery_report.json"

report_status() {  # echo the status field of the report, or "missing"
  [[ -f "$REPORT" ]] || { echo missing; return; }
  python3 -c "import json,sys;print(json.load(open('$REPORT')).get('status','unknown'))" 2>/dev/null || echo unknown
}

# claude_live() is provided by ugc_engine_lib.sh (sourced above).

# ---- shared deterministic delivery (used by the Gemini path) -----------------
# Reads winners from $REPORT, optionally voice-swaps, stitches into $OUT,
# validates the mp4, and records delivered/status back into the report.
# The Claude agent self-delivers, so this is only the Gemini path.
do_delivery() {
  local takes=() voiced status
  while IFS= read -r f; do [[ -n "$f" ]] && takes+=("$f"); done < <(
    python3 -c "
import json
d=json.load(open('$REPORT'))
for w in d.get('winners',[]):
    print(w['file'])
")
  if [[ ${#takes[@]} -eq 0 ]]; then
    echo "[deliver] no winners to assemble" >&2; return 1
  fi

  local final=()
  for t in "${takes[@]}"; do
    if [[ -n "$VOICE" && -f "$ADD_VOICE" ]]; then
      voiced="${t%.*}_voiced.mp4"
      if python3 "$ADD_VOICE" --clip "$t" --voice "$VOICE" --out "$voiced" >&2; then
        final+=("$voiced")
      else
        echo "[deliver] voice swap failed for $t, using native audio" >&2
        final+=("$t")
      fi
    else
      final+=("$t")
    fi
  done

  echo "[deliver] stitching ${#final[@]} take(s) -> $OUT" >&2
  bash "$PRODUCER_SCRIPTS/stitch_shots.sh" "$OUT" "${final[@]}" >&2 || {
    echo "[deliver] stitch failed" >&2; return 1; }

  if ! ffprobe -v error "$OUT" >/dev/null 2>&1 || [[ ! -s "$OUT" ]]; then
    echo "[deliver] ERROR: $OUT missing or not a valid mp4" >&2; return 1
  fi

  python3 -c "
import json
d=json.load(open('$REPORT'))
d['delivered']='$OUT'
d['status']='delivered'
json.dump(d,open('$REPORT','w'),indent=2)
"
  echo "[deliver] delivered: $OUT" >&2
  return 0
}

# ---- Gemini referee path -----------------------------------------------------
run_gemini() {
  echo "[deliver] engine=gemini model=$GEMINI_MODEL job=$JOB anchor=$(basename "$ANCHOR") pattern=$PATTERN qa_only=$QA_ONLY" >&2
  local gargs=(--job "$JOB" --anchor "$ANCHOR" --pattern "$PATTERN" --min "$MIN"
               --model "$GEMINI_MODEL" --report "$REPORT")
  [[ -n "$CRITERIA" ]] && gargs+=(--criteria "$CRITERIA")
  [[ "$QA_ONLY" -eq 1 ]] && gargs+=(--qa-only)

  python3 "$GEMINI_REFEREE" "${gargs[@]}"
  local rc=$?
  [[ "$(report_status)" == "selected" ]] || return $rc  # blocked/failed: nothing to deliver

  if [[ "$QA_ONLY" -eq 1 ]]; then
    return 0
  fi
  do_delivery
}

# ---- Claude agent path -------------------------------------------------------
run_claude() {
  echo "[deliver] engine=claude job=$JOB anchor=$(basename "$ANCHOR") pattern=$PATTERN qa_only=$QA_ONLY" >&2
  cd "$JOB" || return 2
  local cargs=(-p "$PROMPT" --allowedTools "Read Bash Glob Grep Write" \
               --permission-mode bypassPermissions --add-dir "$JOB" --output-format text)
  [[ -n "$MODEL" ]] && cargs+=(--model "$MODEL")
  "$CLAUDE_BIN" "${cargs[@]}"
  return $?
}

if [[ "$DRYRUN" -eq 1 ]]; then
  echo "=== DRY RUN ==="
  echo "engine=$ENGINE (claude_live: $(claude_live && echo yes || echo no)) gemini_model=$GEMINI_MODEL"
  echo "--- claude prompt that would be sent to claude -p ---"
  echo "$PROMPT"
  echo "--- gemini fallback invocation ---"
  echo "python3 $GEMINI_REFEREE --job '$JOB' --anchor '$ANCHOR' --pattern '$PATTERN' --min $MIN --model $GEMINI_MODEL --report '$REPORT'${CRITERIA:+ --criteria ...}${QA_ONLY:+ --qa-only}"
  exit 0
fi

# ---- dispatch ----------------------------------------------------------------
case "$ENGINE" in
  gemini)
    run_gemini; RC=$?
    ;;
  claude)
    run_claude; RC=$?
    ;;
  auto)
    if claude_live; then
      run_claude; RC=$?
      if [[ ! -f "$REPORT" ]]; then
        echo "[deliver] claude produced no report (rc=$RC) -> falling back to Gemini" >&2
        run_gemini; RC=$?
      fi
    else
      echo "[deliver] claude CLI unavailable -> using Gemini referee" >&2
      run_gemini; RC=$?
    fi
    ;;
esac

STATUS="$(report_status)"
echo "[deliver] report: $REPORT (status=$STATUS)" >&2
case "$STATUS" in
  delivered|selected) exit 0;;
  blocked)            exit 1;;
  missing|unknown)    exit "${RC:-1}";;
  *)                  exit "${RC:-1}";;
esac
