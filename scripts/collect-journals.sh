#!/usr/bin/env bash
# Collects journal files from cursor-analysis/ folders across all projects
# and from the journals/ folder itself into journals/raw/
# Uses content hashing to avoid duplicates.
set -euo pipefail

KB_DIR="$HOME/personal/projects/ai-coding-kb"
RAW_DIR="$KB_DIR/journals/raw"
PROCESSED="$KB_DIR/journals/.processed"
PROJECTS_ROOT="$HOME/personal/projects"

mkdir -p "$RAW_DIR"
touch "$PROCESSED"

collect_file() {
  local f="$1"
  local source_label="$2"
  local hash
  hash=$(md5 -q "$f" 2>/dev/null || md5sum "$f" | cut -d' ' -f1)
  if ! grep -qF "$hash" "$PROCESSED" 2>/dev/null; then
    local dest="$RAW_DIR/${source_label}_$(basename "$f")"
    cp "$f" "$dest"
    echo "$hash $dest" >> "$PROCESSED"
    echo "[collect] New: $dest"
  fi
}

# 1. Collect from cursor-analysis/ folders in all sibling projects
find "$PROJECTS_ROOT" -maxdepth 4 -type d -name "cursor-analysis" | while read -r dir; do
  project=$(basename "$(dirname "$dir")")
  find "$dir" -maxdepth 2 -type f \( -name "*.md" -o -name "*.txt" \) | while read -r f; do
    collect_file "$f" "$project"
  done
done

# 2. Also collect journals already in ai-coding-kb/journals/ (non-raw)
find "$KB_DIR/journals" -maxdepth 1 -type f -name "*.md" | while read -r f; do
  collect_file "$f" "ai-coding-kb"
done

echo "[collect] Done."
