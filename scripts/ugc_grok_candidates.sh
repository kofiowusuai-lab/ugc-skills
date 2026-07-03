#!/usr/bin/env bash
# ugc_grok_candidates.sh
# -----------------------------------------------------------------------------
# Generate N Grok image_to_video CANDIDATES for one clip slot from a supplied
# anchor image. Wraps the proven grok_imagine.py `video` driver (which harvests
# the MP4 reliably by session id — no /tmp-vs-/private/tmp path misses), so the
# agent never has to orchestrate Grok by hand. Output: clip<slot>_candidate_*.mp4.
#
# USAGE
#   ugc_grok_candidates.sh --image ANCHOR --prompt "<motion/dialogue>" \
#       --slot clip1 --n 6 --out-dir <DIR> [--duration 6] [--parallel 4]
#
# Each candidate is one image_to_video call seeded by ANCHOR as frame 1.
# Prints one JSON line: {ok, slot, made:[paths], failed:n, out_dir}.
# -----------------------------------------------------------------------------
set -uo pipefail
GROK_IMAGINE="${GROK_IMAGINE:-$HOME/.openclaw/scripts/grok_imagine.py}"
IMAGE="" PROMPT="" SLOT="clip1" N=6 OUTDIR="" DURATION=6 PAR=4
while [[ $# -gt 0 ]]; do case "$1" in
  --image) IMAGE="$2"; shift 2;; --prompt) PROMPT="$2"; shift 2;;
  --slot) SLOT="$2"; shift 2;; --n) N="$2"; shift 2;;
  --out-dir) OUTDIR="$2"; shift 2;; --duration) DURATION="$2"; shift 2;;
  --parallel) PAR="$2"; shift 2;;
  -h|--help) sed -n '2,20p' "$0"; exit 0;; *) echo "unknown arg: $1" >&2; exit 2;; esac; done

[[ -z "$IMAGE" || -z "$PROMPT" || -z "$OUTDIR" ]] && { echo "ERROR: --image, --prompt, --out-dir required" >&2; exit 2; }
[[ ! -f "$IMAGE" ]] && { echo "ERROR: anchor not found: $IMAGE" >&2; exit 2; }
mkdir -p "$OUTDIR"
IMAGE="$(cd "$(dirname "$IMAGE")" && pwd)/$(basename "$IMAGE")"
OUTDIR="$(cd "$OUTDIR" && pwd)"

echo "[grok-candidates] slot=$SLOT n=$N dur=${DURATION}s anchor=$(basename "$IMAGE")" >&2

# Pre-flight: confirm (and if needed self-heal) Grok video health BEFORE spending N
# parallel generation calls. Cached green = instant. Confirmed-unhealthy-and-unhealable
# blocks the batch (set GROK_PREFLIGHT_BLOCK=0 to proceed anyway).
GROK_REMEDIATE="${GROK_REMEDIATE:-$HOME/.openclaw/scripts/grok_remediate.py}"
if [[ "${GROK_PREFLIGHT:-1}" == "1" && -f "$GROK_REMEDIATE" ]]; then
  if ! python3 "$GROK_REMEDIATE" --preflight >/dev/null 2>&1; then
    if [[ "${GROK_PREFLIGHT_BLOCK:-1}" == "1" ]]; then
      echo "{\"ok\": false, \"slot\": \"$SLOT\", \"made\": [], \"failed\": $N, \"reason\": \"grok_unhealthy_preflight\", \"out_dir\": \"$OUTDIR\"}"
      echo "[grok-candidates] preflight RED and could not self-heal; not spending $N calls. See grok-health.log" >&2
      exit 1
    fi
    echo "[grok-candidates] preflight could not confirm Grok healthy; proceeding anyway (GROK_PREFLIGHT_BLOCK=0)" >&2
  fi
fi

pids=(); i=1
while [[ $i -le $N ]]; do
  out="$OUTDIR/${SLOT}_candidate_${i}.mp4"
  (
    python3 "$GROK_IMAGINE" video --image "$IMAGE" --prompt "$PROMPT" \
      --out "$out" --duration "$DURATION" >"$OUTDIR/.${SLOT}_c${i}.json" 2>"$OUTDIR/.${SLOT}_c${i}.err" \
      && echo "ok" >"$OUTDIR/.${SLOT}_c${i}.status" \
      || echo "fail" >"$OUTDIR/.${SLOT}_c${i}.status"
  ) &
  pids+=($!)
  # cap concurrency
  if (( ${#pids[@]} >= PAR )); then wait "${pids[0]}" 2>/dev/null; pids=("${pids[@]:1}"); fi
  i=$((i+1))
done
wait 2>/dev/null

# harvest results
made=(); failed=0; reasons=()
for j in $(seq 1 "$N"); do
  out="$OUTDIR/${SLOT}_candidate_${j}.mp4"
  if [[ -f "$out" && $(stat -f%z "$out" 2>/dev/null || echo 0) -gt 10000 ]]; then
    made+=("$out")
    # clean only the successful candidate's diagnostics
    rm -f "$OUTDIR/.${SLOT}_c${j}.status" "$OUTDIR/.${SLOT}_c${j}.err" "$OUTDIR/.${SLOT}_c${j}.json" 2>/dev/null
  else
    failed=$((failed+1))
    # RETAIN .err/.json for diagnosis; surface the reason_code if present
    rc=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('reason_code',''))" "$OUTDIR/.${SLOT}_c${j}.json" 2>/dev/null)
    [[ -n "$rc" ]] && reasons+=("$rc")
  fi
done

# dedup reasons
first_reason=""
[[ ${#reasons[@]} -gt 0 ]] && first_reason="${reasons[0]}"

# build the made[] JSON (guard empty-array expansion under set -u on bash 3.2)
made_json=""
[[ ${#made[@]} -gt 0 ]] && made_json=$(printf '"%s",' "${made[@]}")
made_json="[${made_json%,}]"
echo "{\"ok\": $([[ ${#made[@]} -gt 0 ]] && echo true || echo false), \"slot\": \"$SLOT\", \"made\": $made_json, \"failed\": $failed, \"reason\": \"${first_reason}\", \"out_dir\": \"$OUTDIR\"}"
echo "[grok-candidates] made=${#made[@]} failed=$failed${first_reason:+ reason=$first_reason (see $OUTDIR/.${SLOT}_c*.err)}" >&2

# Event-driven: a total wipeout despite a green pre-flight means Grok broke mid-run.
# Fire the self-heal loop in the BACKGROUND so it is fixed for next time; do not block
# this call's return. The remediation's single-flight lock prevents stacking.
if [[ ${#made[@]} -eq 0 && "${GROK_PREFLIGHT:-1}" == "1" && -f "$GROK_REMEDIATE" ]]; then
  echo "[grok-candidates] zero clips produced; triggering background Grok self-heal" >&2
  nohup python3 "$GROK_REMEDIATE" >/dev/null 2>&1 &
fi

[[ ${#made[@]} -gt 0 ]] && exit 0 || exit 1
