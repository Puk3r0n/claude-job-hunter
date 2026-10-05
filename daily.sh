#!/bin/zsh
# Daily job search: fetch -> score -> tailor top -> digest -> desktop notification.
# Scheduled via scheduling/ (launchd on macOS, cron on Linux).
# launchd/cron start with a minimal PATH, so add where `claude`, `python3` and `pdflatex` live.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/Library/TeX/texbin:$PATH${JOBHUNT_EXTRA_PATH:+:$JOBHUNT_EXTRA_PATH}"
PYTHON="${JOBHUNT_PYTHON:-python3}"
cd "$(dirname "$0")"
mkdir -p logs
LOG="logs/daily-$(date +%F).log"
{
  echo "=== $(date) ==="
  $PYTHON -m jobhunt fetch
  $PYTHON -m jobhunt score --limit 80 --workers 4
  $PYTHON -m jobhunt tailor --top 5
  $PYTHON -m jobhunt digest
} >> "$LOG" 2>&1
N=$(grep -oE '^[0-9]+ jobs ->' "$LOG" | tail -1 | grep -oE '^[0-9]+')
MSG="New matching jobs: ${N:-0}. Digest: out/digest-$(date +%F).md"
if command -v osascript >/dev/null; then
  osascript -e "display notification \"$MSG\" with title \"claude-job-hunter\" sound name \"Glass\""
elif command -v notify-send >/dev/null; then
  notify-send "claude-job-hunter" "$MSG"
fi
