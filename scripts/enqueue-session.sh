#!/usr/bin/env bash
# Fast SessionEnd hook — just logs to queue, never blocks Claude Code exit
# The cron job does the actual processing
set -euo pipefail

KB_DIR="$HOME/personal/projects/ai-coding-kb"
QUEUE="$KB_DIR/journals/.queue"

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('session_id','unknown'))" 2>/dev/null || echo "unknown")
CWD=$(echo "$INPUT" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('cwd',''))" 2>/dev/null || echo "")

echo "$(date -Iseconds) | session=$SESSION_ID | cwd=$CWD" >> "$QUEUE"
