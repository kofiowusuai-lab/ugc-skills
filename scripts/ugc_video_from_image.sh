#!/usr/bin/env bash
# ugc_video_from_image.sh
# -----------------------------------------------------------------------------
# LENGTH-AWARE image-first video. the user drops ONE anchor image + says the outcome
# and a total duration; this produces a finished video of that length by chaining
# multiple Grok clips with CONTINUITY (Grok caps at 6/10s per clip):
#
#   script the spoken beats (Claude) → for each beat: generate Grok candidates
#   seeded from the PREVIOUS clip's last frame → vision-QA against the dropped
#   anchor (identity lock) → pick the matching take → extract its last frame as
#   the next seed → ... → stitch all winners → final video (Grok voice kept).
#
# USAGE
#   ugc_video_from_image.sh --image ANCHOR --outcome "<what/vibe>" --duration 30 \
#       [--kind motivational|explainer|monologue|ad] [--persona "chill black guy"] \
#       [--dialogue "<full script; auto-split if given>"] [--clip-len 10|6] \
#       [--n 6] [--voice <name|id>] [--out <final.mp4>] [--job <DIR>]
#
# Prints JSON {ok,out,clips,job,report}. exit 0 = delivered, 1 = a beat couldn't
# pass QA (told which) or a step failed.
# -----------------------------------------------------------------------------
set -uo pipefail
S="$HOME/.openclaw/scripts"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
IMAGE="" OUTCOME="" DURATION=30 KIND="motivational" PERSONA="" DIALOGUE="" CLIPLEN=10
N=6 VOICE="" OUT="" JOB="" MINSCORE=0.80
MGFX=0 KEYWORDS="" BTITLE="" HANDLE="" ACCENT="#7CF5C4"
MON=1 CONT="auto" RETRIES=3 BIBLE="" PARALLEL=4
while [[ $# -gt 0 ]]; do case "$1" in
  --image) IMAGE="$2"; shift 2;; --outcome) OUTCOME="$2"; shift 2;;
  --duration) DURATION="$2"; shift 2;; --kind) KIND="$2"; shift 2;;
  --persona) PERSONA="$2"; shift 2;; --dialogue) DIALOGUE="$2"; shift 2;;
  --clip-len) CLIPLEN="$2"; shift 2;; --n) N="$2"; shift 2;;
  --voice) VOICE="$2"; shift 2;; --out) OUT="$2"; shift 2;; --job) JOB="$2"; shift 2;;
  --min) MINSCORE="$2"; shift 2;;
  --continuity) CONT="$2"; shift 2;; --retries) RETRIES="$2"; shift 2;; --bible) BIBLE="$2"; shift 2;;
  --no-monitor) MON=0; shift;;
  --motion-graphics) MGFX=1; shift;; --keywords) KEYWORDS="$2"; shift 2;;
  --brand-title) BTITLE="$2"; shift 2;; --handle) HANDLE="$2"; shift 2;; --accent) ACCENT="$2"; shift 2;;
  -h|--help) sed -n '2,24p' "$0"; exit 0;; *) echo "unknown arg: $1" >&2; exit 2;; esac; done

[[ -z "$IMAGE" || -z "$OUTCOME" ]] && { echo "ERROR: --image and --outcome required" >&2; exit 2; }
[[ ! -f "$IMAGE" ]] && { echo "ERROR: image not found: $IMAGE" >&2; exit 2; }
[[ "$CLIPLEN" != "6" && "$CLIPLEN" != "10" ]] && CLIPLEN=10
IMAGE="$(cd "$(dirname "$IMAGE")" && pwd)/$(basename "$IMAGE")"
[[ -z "$JOB" ]] && JOB="$HOME/ugc_pipeline/video_from_image_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$JOB/clips" "$JOB/winners" "$JOB/frames" "$JOB/refs"
[[ -z "$OUT" ]] && OUT="$JOB/final_delivery.mp4"
# Copy the dropped image into the job dir up front — Telegram/image-cache paths are
# ephemeral and can vanish mid-run; always work from the stable copy.
ANCHOR_COPY="$JOB/refs/anchor.${IMAGE##*.}"
cp "$IMAGE" "$ANCHOR_COPY" && IMAGE="$ANCHOR_COPY"

# Task monitoring is handled deterministically by the pre_tool_call hook
# (hermes_auto_monitor.sh) — one monitor per session, opened automatically when this
# (or any) job runs a terminal command. No per-script monitor needed here.

# continuity mode: talking-head/monologue formats re-anchor to the original (no drift,
# parallel); action formats chain from the prior last frame.
if [[ "$CONT" == "auto" ]]; then
  case "$KIND" in
    motivational|explainer|monologue|talking_head|testimonial|talkinghead) CONT="reanchor";;
    *) CONT="chain";;
  esac
fi

# number of clips to cover the duration
NCLIPS=$(( (DURATION + CLIPLEN - 1) / CLIPLEN ))
[[ $NCLIPS -lt 1 ]] && NCLIPS=1
if [[ $NCLIPS -gt 60 ]]; then
  echo "{\"ok\": false, \"error\": \"$NCLIPS clips (~$((NCLIPS*CLIPLEN))s) exceeds the 60-clip/run cap — split into segments\", \"job\": \"$JOB\"}"; exit 2
fi

echo "[video-from-image] duration=${DURATION}s -> ${NCLIPS}x${CLIPLEN}s clips | kind=$KIND | continuity=$CONT" >&2
WORDS=$(( CLIPLEN * 25 / 10 ))   # ~natural spoken words for the clip length

# ---- 1) SCRIPT: get NCLIPS spoken beats (split provided --dialogue, else Claude) ----
BEATS_JSON="$JOB/beats.json"
if [[ -n "$DIALOGUE" ]]; then
  DIALOGUE="$DIALOGUE" NCLIPS="$NCLIPS" python3 - "$BEATS_JSON" <<'PY'
import os,sys,json,re
text=os.environ["DIALOGUE"]; n=int(os.environ["NCLIPS"])
sent=re.split(r'(?<=[.!?])\s+',text.strip())
sent=[s for s in sent if s]
# distribute sentences across n beats as evenly as possible
beats=[[] for _ in range(n)]
for i,s in enumerate(sent): beats[i%n if n<=len(sent) else i].append(s) if False else None
# simple contiguous chunking
import math
per=max(1,math.ceil(len(sent)/n))
beats=[" ".join(sent[i*per:(i+1)*per]) for i in range(n)]
beats=[b for b in beats if b] or [text]
while len(beats)<n: beats.append(beats[-1])
json.dump(beats[:n],open(sys.argv[1],"w"))
print("split provided dialogue into",len(beats[:n]),"beats")
PY
else
  PF="$(mktemp -t vfi_beats)"; trap 'rm -f "$PF"' EXIT
  cat > "$PF" <<EOF
Write the spoken script for a ${DURATION}-second ${KIND} talking-head video.
Speaker/persona: ${PERSONA:-the person in the anchor image}. Topic/vibe: ${OUTCOME}.
Split it into EXACTLY ${NCLIPS} consecutive beats, one per clip, each about ${WORDS} words
(natural spoken pace for a ${CLIPLEN}-second clip). The beats must flow as ONE continuous
piece (beat 2 continues from beat 1, etc.). Write for the EAR: contractions, real rhythm,
short then long, specific not generic. No ad-speak, no hashtags, no CTA unless the kind is
"ad". First person, direct to camera.
Output ONLY a JSON array of exactly ${NCLIPS} strings (the beats), nothing else.
Write it to: ${BEATS_JSON}  (use the Write tool)
EOF
  "$CLAUDE_BIN" -p "$(cat "$PF")" --allowedTools "Write" --permission-mode bypassPermissions \
    --add-dir "$JOB" --output-format text >/dev/null 2>&1
fi
if [[ ! -f "$BEATS_JSON" ]] || ! python3 -c "import json,sys;a=json.load(open('$BEATS_JSON'));assert isinstance(a,list) and a" 2>/dev/null; then
  echo "{\"ok\": false, \"error\": \"could not produce script beats\", \"job\": \"$JOB\"}"; exit 1
fi
NBEATS=$(python3 -c "import json;print(len(json.load(open('$BEATS_JSON'))))")
echo "[video-from-image] script: $NBEATS beats" >&2

CRITERIA="The clip must show the SAME subject(s) as the anchor — same face(s), hair, skin, wardrobe, "
CRITERIA+="and setting, with the SAME number of people (no extra or missing people). No identity/wardrobe/"
CRITERIA+="location substitution, same framing. Drift to a different person, outfit, or place is a FAIL."

# --- optional CHARACTER BIBLE (reanchor only): seed each beat from a locked
# model-sheet still (close-up/medium rotation) for framing variety, instead of always
# the same anchor. Identity is QA'd against the master; framing/expression may vary. ---
QA_ANCHOR="$IMAGE"; QA_CRITERIA="$CRITERIA"
BIBLE_SEEDS=()
if [[ -n "$BIBLE" ]]; then
  bman="$BIBLE/manifest.json"; [[ -f "$BIBLE" ]] && bman="$BIBLE"   # accept a dir OR a manifest path
  if [[ -f "$bman" ]]; then
    bdir="$(cd "$(dirname "$bman")" && pwd)"
    bmaster=$(python3 -c "import json,os;d=json.load(open('$bman'));print(os.path.join('$bdir',d.get('master','master.png')))" 2>/dev/null)
    [[ -f "$bmaster" ]] && QA_ANCHOR="$bmaster"
    while IFS= read -r f; do [[ -n "$f" && -f "$f" ]] && BIBLE_SEEDS+=("$f"); done < <(python3 -c "
import json,os,itertools
d=json.load(open('$bman')); st=d.get('stills',[])
cu=[s for s in st if s.get('framing')=='closeup']; md=[s for s in st if s.get('framing')!='closeup']
order=[]
for a,b in itertools.zip_longest(cu,md):
    if a: order.append(a)
    if b: order.append(b)
for s in order: print(os.path.join('$bdir', s['file']))
" 2>/dev/null)
    QA_CRITERIA="The clip must show the SAME person as the reference — same face, hair, skin, identity. The FRAMING, camera angle, and expression MAY differ. A different person/identity is a FAIL."
    echo "[video-from-image] character bible: ${#BIBLE_SEEDS[@]} stills; identity QA vs master $(basename "$QA_ANCHOR")" >&2
  else
    echo "[video-from-image] --bible given but no manifest at $bman — ignoring (using the anchor)" >&2
  fi
fi
# Seed for beat $1: a rotating bible still if a bible is loaded, else the original anchor.
beat_seed() {
  if [[ ${#BIBLE_SEEDS[@]} -gt 0 ]]; then
    local i=$(( ($1 - 1) % ${#BIBLE_SEEDS[@]} )); printf '%s' "${BIBLE_SEEDS[$i]}"
  else
    printf '%s' "$IMAGE"
  fi
}

# ---- 2) GENERATION: branch on continuity mode ---------------------------------
#   CONT=chain    : sequential, each beat seeds from the prior winner's last frame.
#   CONT=reanchor : every beat seeds from the ORIGINAL anchor (independent), so the
#                   candidate batches are launched IN PARALLEL (capped concurrency),
#                   then QA-picked afterward.
# Both modes auto-retry a beat's generate->QA up to RETRIES rounds before blocking.
# Winners always land at $JOB/winners/clip<k>.mp4 (fixed names, clip order) so the
# stitch step works regardless of the order beats were produced in.

# Build the Grok motion/dialogue prompt for beat $1 (text loaded into $beat).
build_prompt() {
  local beat="$1"
  local p="Continue from this EXACT source image as frame 1: SAME person, same face, same wardrobe, same "
  p+="setting, no substitutions. The person speaks to camera, natural delivery, subtle handheld "
  p+="micro-shake, natural blinks and small gestures, direct eye contact. ${OUTCOME}. "
  p+="They say: \"${beat}\". Photoreal phone-video, no on-screen text/captions/watermark."
  printf '%s' "$p"
}

# Read beat $1's text (1-based index) out of the beats JSON.
beat_text() {
  python3 -c "import json;print(json.load(open('$BEATS_JSON'))[$1-1])"
}

# Generate one beat's candidate batch from a given seed.
#   gen_beat <k> <seed>
# Clears any stale candidates for the slot first so retries never re-rank old fails.
gen_beat() {
  local k="$1" seed="$2" beat prompt
  beat=$(beat_text "$k")
  prompt=$(build_prompt "$beat")
  # Clear stale candidates AND any prior-round winner for this slot so file-presence
  # always reflects the CURRENT round (the referee only writes --out when score>0, so
  # a total-drift retry would otherwise leave a stale sub-threshold winner behind).
  rm -f "$JOB/clips/clip${k}_candidate_"*.mp4 "$JOB/winners/clip${k}.mp4" 2>/dev/null
  "$S/ugc_grok_candidates.sh" --image "$seed" --prompt "$prompt" --slot "clip$k" \
    --n "$N" --out-dir "$JOB/clips" --duration "$CLIPLEN" --parallel "$PARALLEL" \
    >/dev/null 2>>"$JOB/gen.log" || true
}

# QA-pick beat $1's winner into $JOB/winners/clip<k>.mp4 (identity locked to the
# DROPPED anchor). Echoes "yes <score>" / "no <score>"; writes the winner file on pass.
qa_beat() {
  local k="$1" win="$JOB/winners/clip$1.mp4" RANKJSON
  RANKJSON=$(python3 "$S/ugc_clip_referee.py" rank --anchor "$QA_ANCHOR" --clips-dir "$JOB/clips" \
    --glob "clip${k}_candidate_*.mp4" --out "$win" --criteria "$QA_CRITERIA" 2>>"$JOB/qa.log" || true)
  MINSCORE="$MINSCORE" python3 - "$RANKJSON" <<'PY'
import json,sys,os
try:
    d=json.loads(sys.argv[1]); w=d.get("winner") or {}
    ok=bool(w.get("identity_match")) and float(w.get("overall_score",0))>=float(os.environ["MINSCORE"])
    print(("yes" if ok else "no")+" "+str(w.get("overall_score",0)))
except Exception:
    print("no 0")
PY
}

# Run generate->QA for one beat with auto-retry. Returns 0 on pass (winner written),
# 1 after RETRIES dry rounds. gen_beat_with_retry <k> <seed>
gen_beat_with_retry() {
  local k="$1" seed="$2" attempt=1 verdict score PASS win="$JOB/winners/clip$1.mp4"
  while [[ $attempt -le $RETRIES ]]; do
    echo "[video-from-image] beat $k/$NBEATS — round $attempt/$RETRIES, $N candidates (seed=$(basename "$seed"))" >&2
    gen_beat "$k" "$seed"
    PASS=$(qa_beat "$k")
    verdict="${PASS%% *}"; score="${PASS#* }"
    if [[ -f "$win" && "$verdict" == "yes" ]]; then
      echo "[video-from-image] beat $k accepted (score=$score, round $attempt)" >&2
      LAST_SCORE="$score"
      return 0
    fi
    echo "[video-from-image] beat $k round $attempt MISS (best=$score, need >=$MINSCORE) — retrying" >&2
    attempt=$((attempt+1))
  done
  LAST_SCORE="$score"
  return 1
}

# Apply the optional voice swap to a beat winner in place (updates winners/clip<k>.mp4).
voice_beat() {
  local k="$1" win="$JOB/winners/clip$1.mp4"
  [[ -z "$VOICE" || ! -f "$win" ]] && return 0
  if python3 "$S/ugc_add_voice.py" --clip "$win" --voice "$VOICE" --out "${win%.mp4}_voiced.mp4" \
       >/dev/null 2>>"$JOB/voice.log" && [[ -f "${win%.mp4}_voiced.mp4" ]]; then
    mv -f "${win%.mp4}_voiced.mp4" "$win"
  fi
}

declare -a WINNERS
LAST_SCORE="0"

if [[ "$CONT" == "reanchor" ]]; then
  # --- REANCHOR: every beat seeds from the ORIGINAL anchor -> beats are independent.
  # Launch all candidate batches in parallel, capped at $PARALLEL concurrent beats
  # (bash-3.2 pid-array pattern: when count >= cap, wait for the OLDEST pid, then drop it).
  echo "[video-from-image] reanchor mode — launching $NBEATS beats in parallel (cap=$PARALLEL)" >&2
  pids=(); slots=()
  for k in $(seq 1 "$NBEATS"); do
    gen_beat "$k" "$(beat_seed "$k")" &
    pids+=($!); slots+=("$k")
    if [[ ${#pids[@]} -ge $PARALLEL ]]; then
      wait "${pids[0]}" 2>/dev/null
      pids=("${pids[@]:1}")
    fi
  done
  wait 2>/dev/null

  # QA each beat. A beat that fails QA is retried (generate+QA) SEQUENTIALLY up to
  # RETRIES rounds — the first parallel pass already counts as round 1.
  for k in $(seq 1 "$NBEATS"); do
    win="$JOB/winners/clip$k.mp4"
    PASS=$(qa_beat "$k")
    verdict="${PASS%% *}"; score="${PASS#* }"
    if [[ -f "$win" && "$verdict" == "yes" ]]; then
      echo "[video-from-image] beat $k accepted (score=$score, parallel round 1)" >&2
    else
      echo "[video-from-image] beat $k round 1 MISS (best=$score, need >=$MINSCORE) — retrying sequentially" >&2
      # rounds 2..RETRIES, reseeding from the original anchor each time
      attempt=2; ok=0
      while [[ $attempt -le $RETRIES ]]; do
        echo "[video-from-image] beat $k — round $attempt/$RETRIES, $N candidates (seed=$(basename "$(beat_seed "$k")"))" >&2
        gen_beat "$k" "$(beat_seed "$k")"
        PASS=$(qa_beat "$k")
        verdict="${PASS%% *}"; score="${PASS#* }"
        if [[ -f "$win" && "$verdict" == "yes" ]]; then
          echo "[video-from-image] beat $k accepted (score=$score, round $attempt)" >&2
          ok=1; break
        fi
        echo "[video-from-image] beat $k round $attempt MISS (best=$score) — retrying" >&2
        attempt=$((attempt+1))
      done
      if [[ $ok -ne 1 ]]; then
        echo "{\"ok\": false, \"error\": \"beat $k: no take passed QA after $RETRIES rounds (best score=$score, need >=$MINSCORE) — regenerate this beat\", \"job\": \"$JOB\", \"beats_done\": $((k-1))}"
        exit 1
      fi
    fi
    voice_beat "$k"
    WINNERS+=("$win")
  done
else
  # --- CHAIN: sequential, each beat seeds from the prior winner's last frame.
  seed="$IMAGE"
  for k in $(seq 1 "$NBEATS"); do
    if ! gen_beat_with_retry "$k" "$seed"; then
      echo "{\"ok\": false, \"error\": \"beat $k: no take passed QA after $RETRIES rounds (best score=$LAST_SCORE, need >=$MINSCORE) — regenerate this beat\", \"job\": \"$JOB\", \"beats_done\": $((k-1))}"
      exit 1
    fi
    win="$JOB/winners/clip$k.mp4"
    voice_beat "$k"
    WINNERS+=("$win")
    # extract last frame -> seed for the next beat (continuity). NOTE: use "$win"
    # (not ${WINNERS[-1]} — macOS bash 3.2 has no negative array subscripts).
    if [[ $k -lt $NBEATS ]]; then
      seed="$JOB/frames/clip${k}_last.png"
      ffmpeg -y -sseof -0.2 -i "$win" -frames:v 1 -q:v 2 "$seed" >/dev/null 2>&1
      [[ -f "$seed" ]] || seed="$IMAGE"   # fall back to original anchor if extraction fails
    fi
  done
fi

# ---- 3) STITCH winners in order -> final (uniform 720x1280/30fps) ----
LIST="$JOB/concat.txt"; : > "$LIST"
for w in "${WINNERS[@]}"; do
  norm="${w%.mp4}_norm.mp4"
  ffmpeg -y -i "$w" -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=30" \
    -c:v libx264 -preset veryfast -crf 18 -c:a aac -ar 48000 "$norm" >/dev/null 2>>"$JOB/stitch.log"
  echo "file '$norm'" >> "$LIST"
done
ffmpeg -y -f concat -safe 0 -i "$LIST" -c copy "$OUT" >/dev/null 2>>"$JOB/stitch.log" \
  || ffmpeg -y -f concat -safe 0 -i "$LIST" -c:v libx264 -preset veryfast -crf 18 -c:a aac "$OUT" >/dev/null 2>>"$JOB/stitch.log"

if [[ -f "$OUT" && $(stat -f%z "$OUT" 2>/dev/null || echo 0) -gt 20000 ]]; then
  # ---- 4) optional MOTION-GRAPHICS finish (kinetic captions + brand + keyword pops) ----
  if [[ "$MGFX" -eq 1 ]]; then
    echo "[video-from-image] motion-graphics pass (Remotion)..." >&2
    MGOUT="${OUT%.mp4}_motion.mp4"
    MGARGS=(--video "$OUT" --out "$MGOUT" --accent "$ACCENT")
    [[ -n "$KEYWORDS" ]] && MGARGS+=(--keywords "$KEYWORDS")
    [[ -n "$BTITLE" ]] && MGARGS+=(--brand-title "$BTITLE")
    [[ -n "$HANDLE" ]] && MGARGS+=(--handle "$HANDLE")
    if "$S/ugc_motion_render.sh" "${MGARGS[@]}" >>"$JOB/motion.log" 2>&1 && [[ -f "$MGOUT" ]]; then
      OUT="$MGOUT"
    else
      echo "[video-from-image] motion-graphics step failed — keeping the plain cut (see $JOB/motion.log)" >&2
    fi
  fi
  dur=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT" 2>/dev/null)
  echo "{\"ok\": true, \"out\": \"$OUT\", \"clips\": $NBEATS, \"duration_s\": \"${dur:-?}\", \"job\": \"$JOB\"}"
  echo "[video-from-image] DONE — $NBEATS clips stitched -> $OUT (${dur:-?}s)" >&2
  exit 0
else
  echo "{\"ok\": false, \"error\": \"stitch failed (see $JOB/stitch.log)\", \"job\": \"$JOB\", \"winners\": ${#WINNERS[@]}}"
  exit 1
fi
