#!/usr/bin/env bash
# ugc_engine_lib.sh — shared engine-availability helpers for the UGC stages.
# Source this (do not execute it): . "$HOME/.openclaw/scripts/ugc_engine_lib.sh"
#
# Centralizes the "is Claude usable, else fall back to Gemini" logic so the shot
# planner, scriptwriter, and vision delivery stages all behave identically.

# CLAUDE_BIN may already be set by the sourcing script; default it here too.
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
GEMINI_TEXT="${GEMINI_TEXT:-$HOME/.openclaw/scripts/ugc_gemini_text.py}"

# claude_live: succeed (0) if the claude CLI is present/executable. When
# UGC_CLAUDE_PROBE=1, also fire a cheap one-token probe so a configured-but-down
# Claude (rate-limited / broken auth) is detected before a real call.
claude_live() {
  [[ -x "$CLAUDE_BIN" ]] || return 1
  if [[ "${UGC_CLAUDE_PROBE:-0}" == "1" ]]; then
    "$CLAUDE_BIN" -p "reply with: ok" --output-format text >/dev/null 2>&1 || return 1
  fi
  return 0
}

# valid_json <file>: succeed (0) if the file exists and parses as JSON. This is
# the exact success bar the stage scripts already use to accept Claude's output.
valid_json() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$f" 2>/dev/null
}

# validate_engine <value>: exit 2 on an unknown --engine value.
validate_engine() {
  case "$1" in
    auto|claude|gemini) return 0;;
    *) echo "ERROR: --engine must be auto|claude|gemini (got '$1')" >&2; exit 2;;
  esac
}
