#!/usr/bin/env bash
#
# ugc_character_bible.sh - Build a reusable "character bible" (model sheet) for a
# recurring video character so later videos keep her identity LOCKED while still
# having framing/expression/angle variety.
#
# CRITICAL PRINCIPLE
# ------------------
# The MASTER image is supplied by the human (the user). This script NEVER generates
# the master. It only DERIVES the rest of the model sheet FROM that approved
# master via identity-locked Grok image_edit, then QA-gates every derived still
# against the master with the vision referee, keeping only the stills that hold
# the identity.
#
# PIPELINE
#   1. Validate --master (hard error if missing/absent). Copy it in as the
#      canonical reference: <out-dir>/master.<ext>.
#   2. For each entry in the model-sheet table, run an identity-locked
#      grok_imagine.py edit FROM the master.
#   3. QA each derived still vs the master with ugc_clip_referee.py score.
#      Keep only identity_match==true AND overall_score>=MIN. Retry on fail
#      up to --retries, else drop the still.
#   4. Write <out-dir>/manifest.json (documented schema below).
#   5. Print a final JSON summary.
#
# MANIFEST SCHEMA  (<out-dir>/manifest.json)
#   {
#     "name":    "<character name>",
#     "master":  "master.png",            # filename, relative to out-dir
#     "aspect":  "9:16",
#     "created": <unix epoch seconds>,
#     "min":     0.80,                     # score threshold used
#     "stills": [
#       {
#         "id":         "closeup-neutral",
#         "role":       "closeup-neutral", # human label
#         "framing":    "closeup",         # closeup | medium
#         "expression": "neutral",         # neutral|smile-closed|smile-teeth|laughing|talking|listening
#         "angle":      "front",           # front | three-quarter-left | three-quarter-right
#         "file":       "closeup-neutral.png",  # relative to out-dir
#         "score":      0.90,              # referee overall_score
#         "identity_match": true
#       }, ...
#     ]
#   }
#
# FINAL STDOUT (single JSON line)
#   {"ok":true,"name":"...","kept":N,"dropped":M,"manifest":"<abs path>"}
#
# USAGE
#   ugc_character_bible.sh --master <IMG> --name <char> \
#       [--out-dir DIR] [--aspect 9:16] [--min 0.80] [--retries 1]
#
# bash 3.2 safe: no negative array subscripts, no mapfile, no associative arrays.

set -u

# ----------------------------------------------------------------------------
# Resolve tool paths
# ----------------------------------------------------------------------------
HOME_DIR="${HOME}"
SCRIPTS_DIR="${HOME_DIR}/.openclaw/scripts"
GROK="${SCRIPTS_DIR}/grok_imagine.py"
REFEREE="${SCRIPTS_DIR}/ugc_clip_referee.py"
PY="$(command -v python3 || echo python3)"

err() { echo "ERROR: $*" >&2; }

# ----------------------------------------------------------------------------
# Defaults / args
# ----------------------------------------------------------------------------
MASTER=""
NAME=""
OUT_DIR=""
ASPECT="9:16"
MIN="0.80"
RETRIES="1"
LIMIT="0"   # 0 = all entries; >0 = cap to first N entries (test/cost control)

while [ $# -gt 0 ]; do
  case "$1" in
    --master)  MASTER="${2:-}"; shift 2 ;;
    --name)    NAME="${2:-}"; shift 2 ;;
    --out-dir) OUT_DIR="${2:-}"; shift 2 ;;
    --aspect)  ASPECT="${2:-}"; shift 2 ;;
    --min)     MIN="${2:-}"; shift 2 ;;
    --retries) RETRIES="${2:-}"; shift 2 ;;
    --limit)   LIMIT="${2:-}"; shift 2 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *)
      err "unknown argument: $1"
      exit 2 ;;
  esac
done

# ----------------------------------------------------------------------------
# Validate required args. NEVER generate the master.
# ----------------------------------------------------------------------------
if [ -z "$NAME" ]; then
  err "--name is required"
  exit 2
fi
if [ -z "$MASTER" ]; then
  err "--master is REQUIRED. The master image must be supplied by the human;"
  err "this script never generates it."
  exit 2
fi
if [ ! -f "$MASTER" ]; then
  err "--master file not found: $MASTER (the master must be a real, approved image; never generated)"
  exit 2
fi
if [ ! -f "$GROK" ]; then
  err "grok_imagine.py not found at $GROK"
  exit 2
fi
if [ ! -f "$REFEREE" ]; then
  err "ugc_clip_referee.py not found at $REFEREE"
  exit 2
fi

if [ -z "$OUT_DIR" ]; then
  OUT_DIR="${HOME_DIR}/.openclaw/character_bibles/${NAME}"
fi

mkdir -p "$OUT_DIR" || { err "could not create out-dir: $OUT_DIR"; exit 1; }

# Absolute out-dir (bash 3.2 safe; no realpath dependency)
OUT_DIR_ABS="$(cd "$OUT_DIR" && pwd)"

# ----------------------------------------------------------------------------
# Copy the master in as the canonical reference: master.<ext>
# ----------------------------------------------------------------------------
MASTER_BASE="$(basename "$MASTER")"
MASTER_EXT="png"
case "$MASTER_BASE" in
  *.jpg)  MASTER_EXT="jpg" ;;
  *.jpeg) MASTER_EXT="jpeg" ;;
  *.png)  MASTER_EXT="png" ;;
  *.webp) MASTER_EXT="webp" ;;
  *.JPG)  MASTER_EXT="jpg" ;;
  *.PNG)  MASTER_EXT="png" ;;
  *)      MASTER_EXT="png" ;;
esac
MASTER_OUT="${OUT_DIR_ABS}/master.${MASTER_EXT}"
cp "$MASTER" "$MASTER_OUT" || { err "could not copy master into out-dir"; exit 1; }
echo "[bible] master locked -> $MASTER_OUT" >&2

# ----------------------------------------------------------------------------
# Identity-lock prefix prepended to every derived prompt.
# ----------------------------------------------------------------------------
IDLOCK="This is the SAME exact person, the same face and identity as the reference image. Do not change their identity, face shape, skin tone, hair, age, or features. Keep identical lighting, wardrobe, and overall look. Photorealistic. Only change the following: "

# ----------------------------------------------------------------------------
# Model-sheet table (DATA). One entry per line, fields pipe-delimited:
#   id|framing|expression|angle|variation-prompt
# bash 3.2 safe: plain indexed array, no associative arrays.
# 11 entries spanning expressions x framings x angles.
# ----------------------------------------------------------------------------
ENTRIES=()
ENTRIES[0]="closeup-neutral-front|closeup|neutral|front|a tight close-up head-and-shoulders portrait, neutral relaxed expression, mouth closed, looking straight at the camera"
ENTRIES[1]="closeup-smile-closed-front|closeup|smile-closed|front|a tight close-up head-and-shoulders portrait, soft warm closed-mouth smile, looking straight at the camera"
ENTRIES[2]="closeup-smile-teeth-3qleft|closeup|smile-teeth|three-quarter-left|a close-up head-and-shoulders portrait, big genuine smile showing teeth, head turned to a slight three-quarter angle to the left"
ENTRIES[3]="closeup-laughing-3qright|closeup|laughing|three-quarter-right|a close-up head-and-shoulders portrait, laughing naturally with eyes slightly crinkled, head turned to a slight three-quarter angle to the right"
ENTRIES[4]="closeup-talking-front|closeup|talking|front|a close-up head-and-shoulders portrait, talking mid-sentence with the mouth open mid-word, expressive engaged face, looking at the camera"
ENTRIES[5]="closeup-listening-3qleft|closeup|listening|three-quarter-left|a close-up head-and-shoulders portrait, attentive listening expression, mouth closed, head turned to a slight three-quarter angle to the left, eyes engaged"
ENTRIES[6]="medium-neutral-front|medium|neutral|front|a medium waist-up shot, neutral relaxed expression, mouth closed, facing the camera straight on"
ENTRIES[7]="medium-smile-closed-3qright|medium|smile-closed|three-quarter-right|a medium waist-up shot, soft closed-mouth smile, body and head turned to a slight three-quarter angle to the right"
ENTRIES[8]="medium-talking-front|medium|talking|front|a medium waist-up shot, talking mid-sentence with the mouth open mid-word, natural hand gesture near chest, facing the camera"
ENTRIES[9]="medium-smile-teeth-front|medium|smile-teeth|front|a medium waist-up shot, big genuine smile showing teeth, facing the camera straight on"
ENTRIES[10]="medium-listening-3qright|medium|listening|three-quarter-right|a medium waist-up shot, attentive listening expression, mouth closed, body turned to a slight three-quarter angle to the right"

TOTAL=${#ENTRIES[@]}
if [ "$LIMIT" -gt 0 ] 2>/dev/null; then
  if [ "$LIMIT" -lt "$TOTAL" ]; then
    TOTAL="$LIMIT"
  fi
fi
echo "[bible] deriving up to $TOTAL stills from master for '$NAME' (min=$MIN, retries=$RETRIES)" >&2

# ----------------------------------------------------------------------------
# Helper: extract a numeric/boolean field from the referee's JSON via python3.
# Args: <json> <key>. Prints the value (empty if absent).
# ----------------------------------------------------------------------------
json_field() {
  printf '%s' "$1" | "$PY" -c '
import sys, json
key = sys.argv[1]
try:
    obj = json.loads(sys.stdin.read())
    v = obj.get(key)
    if isinstance(v, bool):
        print("true" if v else "false")
    elif v is None:
        print("")
    else:
        print(v)
except Exception:
    print("")
' "$2"
}

# Helper: float >= compare (a >= b). Returns 0 (true) / 1 (false).
fge() {
  "$PY" -c 'import sys
try:
    print("1" if float(sys.argv[1]) >= float(sys.argv[2]) else "0")
except Exception:
    print("0")' "$1" "$2" | grep -q '^1$'
}

# ----------------------------------------------------------------------------
# Build the manifest stills array incrementally (as JSON object lines we later
# assemble with python3). We collect kept entries into parallel arrays.
# ----------------------------------------------------------------------------
KEPT=0
DROPPED=0
KEPT_JSON_FILE="$(mktemp -t bible_stills.XXXXXX)"
: > "$KEPT_JSON_FILE"

i=0
while [ "$i" -lt "$TOTAL" ]; do
  line="${ENTRIES[$i]}"
  i=$((i + 1))

  id="$(printf '%s' "$line" | cut -d'|' -f1)"
  framing="$(printf '%s' "$line" | cut -d'|' -f2)"
  expression="$(printf '%s' "$line" | cut -d'|' -f3)"
  angle="$(printf '%s' "$line" | cut -d'|' -f4)"
  variation="$(printf '%s' "$line" | cut -d'|' -f5-)"

  out_file="${OUT_DIR_ABS}/${id}.png"
  prompt="${IDLOCK}${variation}."

  echo "[bible] ($i/$TOTAL) deriving '$id' ..." >&2

  # Attempt = 1 initial + RETRIES retries
  attempt=0
  max_attempts=$((RETRIES + 1))
  kept_this=0
  best_score="0"

  while [ "$attempt" -lt "$max_attempts" ]; do
    attempt=$((attempt + 1))

    gout="$("$PY" "$GROK" edit --prompt "$prompt" --ref "$MASTER_OUT" --out "$out_file" --aspect "$ASPECT" 2>>"${OUT_DIR_ABS}/derive.log")"
    gok="$(json_field "$gout" ok)"
    if [ "$gok" != "true" ]; then
      echo "[bible]   attempt $attempt: grok edit failed ($(json_field "$gout" reason_code))" >&2
      continue
    fi
    if [ ! -f "$out_file" ]; then
      echo "[bible]   attempt $attempt: grok reported ok but no file at $out_file" >&2
      continue
    fi

    # QA vs master
    sout="$("$PY" "$REFEREE" score --anchor "$MASTER_OUT" --clip "$out_file" 2>>"${OUT_DIR_ABS}/referee.log")"
    score="$(json_field "$sout" overall_score)"
    idmatch="$(json_field "$sout" identity_match)"
    if [ -z "$score" ]; then score="0"; fi
    best_score="$score"

    echo "[bible]   attempt $attempt: score=$score identity_match=$idmatch" >&2

    if [ "$idmatch" = "true" ] && fge "$score" "$MIN"; then
      kept_this=1
      break
    fi
    echo "[bible]   attempt $attempt: below threshold, ${attempt} of ${max_attempts}" >&2
  done

  if [ "$kept_this" = "1" ]; then
    KEPT=$((KEPT + 1))
    # Emit a JSON object for this still (one per line) via python3 (safe escaping).
    "$PY" -c '
import json, sys
obj = {
  "id": sys.argv[1],
  "role": sys.argv[1],
  "framing": sys.argv[2],
  "expression": sys.argv[3],
  "angle": sys.argv[4],
  "file": sys.argv[5],
  "score": float(sys.argv[6]),
  "identity_match": True,
}
print(json.dumps(obj))
' "$id" "$framing" "$expression" "$angle" "${id}.png" "$best_score" >> "$KEPT_JSON_FILE"
    echo "[bible]   KEPT '$id' (score=$best_score)" >&2
  else
    DROPPED=$((DROPPED + 1))
    # Remove the failing artifact so the bible only contains locked stills.
    [ -f "$out_file" ] && rm -f "$out_file"
    echo "[bible]   DROPPED '$id' after $max_attempts attempt(s)" >&2
  fi
done

# ----------------------------------------------------------------------------
# Assemble manifest.json
# ----------------------------------------------------------------------------
MANIFEST="${OUT_DIR_ABS}/manifest.json"
"$PY" -c '
import json, sys, time
name, master_file, aspect, minv, stills_file, manifest = sys.argv[1:7]
stills = []
with open(stills_file) as f:
    for ln in f:
        ln = ln.strip()
        if ln:
            stills.append(json.loads(ln))
doc = {
    "name": name,
    "master": master_file,
    "aspect": aspect,
    "created": int(time.time()),
    "min": float(minv),
    "stills": stills,
}
with open(manifest, "w") as out:
    json.dump(doc, out, indent=2)
    out.write("\n")
' "$NAME" "master.${MASTER_EXT}" "$ASPECT" "$MIN" "$KEPT_JSON_FILE" "$MANIFEST"

rm -f "$KEPT_JSON_FILE"

# ----------------------------------------------------------------------------
# Final JSON summary
# ----------------------------------------------------------------------------
"$PY" -c '
import json, sys
print(json.dumps({
  "ok": True,
  "name": sys.argv[1],
  "kept": int(sys.argv[2]),
  "dropped": int(sys.argv[3]),
  "manifest": sys.argv[4],
}))
' "$NAME" "$KEPT" "$DROPPED" "$MANIFEST"
