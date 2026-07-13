#!/bin/bash
# Unattended driver for the /wohnung-search skill, run on a schedule by launchd.
#
# Runs Claude Code in print mode (`claude -p`) so the LLM photo-evaluation and
# report-writing steps draw on the Claude subscription rather than API credits.
# launchd starts this with a minimal environment, so we set PATH explicitly.
#
# Usage: wohnung-cron.sh [pages]   (pages = portal pages per source; default 10)
set -uo pipefail

# Repo root = parent of this script's directory (no hardcoded path).
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAGES="${1:-10}"

# launchd gives us almost no PATH; spell out everything the skill shells out to:
# uv + pandoc (homebrew), git (/usr/bin), claude (~/.local/bin).
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin"

cd "$REPO" || exit 1
mkdir -p logs
LOG="logs/cron-search.log"

ts() { date "+%Y-%m-%d %H:%M:%S"; }

echo "[$(ts)] === wohnung-search start (pages=$PAGES) ===" >> "$LOG"

# --dangerously-skip-permissions: this is an unattended run, so Claude cannot
# stop to approve tools. The skill needs broad access (Bash, web/Playwright),
# which a fixed allowlist can't practically cover.
claude -p "/wohnung-search $PAGES" \
  --dangerously-skip-permissions \
  >> "$LOG" 2>&1
status=$?

echo "[$(ts)] === wohnung-search end (exit=$status) ===" >> "$LOG"
exit $status
