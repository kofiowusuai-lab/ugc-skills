#!/usr/bin/env bash
#
# install.sh - install the UGC skills + engine into your Claude Code setup.
#
# What it does:
#   1. Copies the 5 skill folders into  ~/.claude/skills/
#   2. Copies the engine scripts into   ~/.openclaw/scripts/  (the path the skills call)
#   3. Marks the scripts executable
#   4. Prints the remaining setup steps (API keys, CLIs, python deps)
#
# It backs up any skill folder you already have before overwriting.
# Run from the repo root:  bash install.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$REPO_DIR/skills"
SCRIPTS_SRC="$REPO_DIR/scripts"
VENDOR_SRC="$REPO_DIR/vendor/voiceswap"

SKILLS_DST="$HOME/.claude/skills"
SCRIPTS_DST="$HOME/.openclaw/scripts"
VOICESWAP_DST="$HOME/voiceswap"

STAMP="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo backup)"

say() { printf "\033[1;36m==>\033[0m %s\n" "$1"; }
warn() { printf "\033[1;33m[!]\033[0m %s\n" "$1"; }

say "Installing UGC skills from: $REPO_DIR"

# --- 1. skills ---------------------------------------------------------------
mkdir -p "$SKILLS_DST"
for skill_path in "$SKILLS_SRC"/*/; do
  name="$(basename "$skill_path")"
  target="$SKILLS_DST/$name"
  if [ -e "$target" ]; then
    warn "existing $name -> backing up to ${target}.bak-$STAMP"
    mv "$target" "${target}.bak-$STAMP"
  fi
  cp -R "$skill_path" "$target"
  say "installed skill: $name"
done

# --- 2. engine scripts -------------------------------------------------------
mkdir -p "$SCRIPTS_DST"
copied=0
for f in "$SCRIPTS_SRC"/*; do
  cp "$f" "$SCRIPTS_DST/"
  copied=$((copied + 1))
done
# make shell + task-monitor executable
chmod +x "$SCRIPTS_DST"/*.sh 2>/dev/null || true
chmod +x "$SCRIPTS_DST/task-monitor" 2>/dev/null || true
say "installed $copied engine scripts into $SCRIPTS_DST"

# --- 2b. voiceswap package (voice swap + lip-sync engine) --------------------
if [ -d "$VENDOR_SRC" ]; then
  if [ -e "$VOICESWAP_DST" ]; then
    warn "existing ~/voiceswap -> backing up to ${VOICESWAP_DST}.bak-$STAMP"
    mv "$VOICESWAP_DST" "${VOICESWAP_DST}.bak-$STAMP"
  fi
  cp -R "$VENDOR_SRC" "$VOICESWAP_DST"
  say "installed voiceswap package into $VOICESWAP_DST"
fi

# --- 3. next steps -----------------------------------------------------------
cat <<'EOF'

------------------------------------------------------------------
Skills installed. Three things left before the pipeline runs:

1) API keys. Copy the template and fill in your keys:
     cp .env.example .env
     # edit .env, then load it in each shell you work in:
     set -a; . ./.env; set +a

2) Python dependencies:
     python3 -m pip install -r requirements.txt

3) External CLIs on your PATH:
     - grok      (xAI Grok CLI, image + video generation)   grok.com / your Grok CLI install
     - gemini    (Google Gemini CLI, used for vision QA)
     - ffmpeg    (brew install ffmpeg  /  apt install ffmpeg)
     - node      (for the ad-strategist workflow script)

Verify Claude Code sees the skills:
     Open Claude Code and run  /ugc-video-producer  (or ask "make a UGC ad").

Full setup notes live in README.md.
------------------------------------------------------------------
EOF
