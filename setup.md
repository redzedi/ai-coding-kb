# Journal Sync & Memory System Setup

## Context
This sets up an automated journal collection and memory synthesis system for a developer
who uses Cursor, Gemini, and Claude Code. The knowledge base is at:
  ~/personal/projects/ai-coding-kb/

## What to do

Work through each task below in order. Before writing any file, show me the content and
confirm. After all files are written, show a summary of what was created.

---

## Task 1 — Create directory structure in ai-coding-kb

Create these directories if they don't exist:
  ~/personal/projects/ai-coding-kb/journals/raw/
  ~/personal/projects/ai-coding-kb/scripts/

Do NOT touch anything in .git/

---

## Task 2 — Create collect-journals.sh

Write this file to ~/personal/projects/ai-coding-kb/scripts/collect-journals.sh

```bash
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
```

After writing, run: chmod +x ~/personal/projects/ai-coding-kb/scripts/collect-journals.sh

---

## Task 3 — Create synthesize-memory.py

Write this file to ~/personal/projects/ai-coding-kb/scripts/synthesize-memory.py

```python
#!/usr/bin/env python3
"""
Incremental memory synthesis.
Reads new raw journals, sends them + current MEMORY.md to Claude API,
gets back an updated MEMORY.md with compaction and superseding applied.
Only processes journals not yet synthesized (tracked by hash in .synthesized).
"""
import os, json, hashlib, datetime, pathlib, sys
import urllib.request, urllib.error

KB_DIR      = pathlib.Path.home() / "personal/projects/ai-coding-kb"
RAW_DIR     = KB_DIR / "journals/raw"
MEMORY_FILE = KB_DIR / "journals/MEMORY.md"
SYNTH_LOG   = KB_DIR / "journals/.synthesized"
BACKUP_DIR  = KB_DIR / "journals/.backups"
LOG_FILE    = KB_DIR / "journals/.synthesis.log"

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL   = "claude-sonnet-4-20250514"

def log(msg):
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    line = f"{ts} {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def get_unprocessed():
    synth = set()
    if SYNTH_LOG.exists():
        synth = set(SYNTH_LOG.read_text().splitlines())
    files = []
    for f in sorted(RAW_DIR.glob("*.md")):
        h = hashlib.md5(f.read_bytes()).hexdigest()
        if h not in synth:
            files.append((f, h))
    return files

def call_claude(prompt: str) -> str:
    if not API_KEY:
        log("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"]

def synthesize(new_journals, current_memory):
    journal_text = "\n\n---\n\n".join(
        f"# Source: {f.name}\n\n{f.read_text()}" for f, _ in new_journals
    )
    prompt = f"""You are a memory synthesis agent maintaining MEMORY.md for a software developer.
This file is loaded at the start of every Claude Code, Cursor, and Gemini CLI session.
Keep it dense, actionable, and scannable. No fluff.

## Current MEMORY.md
{current_memory or "(empty — this is the first synthesis run)"}

## New Journal Entries
{journal_text}

## Instructions
1. Extract actionable insights: decisions, patterns, gotchas, architecture choices, tool preferences
2. If a new entry SUPERSEDES or CONTRADICTS existing memory → update/replace it, move old to ## Superseded
3. If a new entry adds new info → merge it into the right section
4. COMPACT: merge duplicate or near-duplicate insights into single entries
5. Each insight = 1-3 lines max + source filename in parentheses
6. Preserve these top-level sections (add domain-specific ones as needed):
   - ## Patterns & Conventions
   - ## Architecture Decisions
   - ## Gotchas & Watch-outs
   - ## Tool & Workflow Preferences
   - ## Project-Specific Notes (subsection per project)
   - ## Superseded (what changed, when, old value → new value)
7. Add a metadata line at the top: `<!-- last-updated: {datetime.date.today()} | journals: N -->`

Return ONLY the updated MEMORY.md. No preamble, no explanation."""
    return call_claude(prompt)

def main():
    new = get_unprocessed()
    if not new:
        log("No new journals to synthesize.")
        return

    log(f"Synthesizing {len(new)} new journal(s): {[str(f) for f,_ in new]}")
    current = MEMORY_FILE.read_text() if MEMORY_FILE.exists() else ""

    updated = synthesize(new, current)

    # Backup before overwriting
    BACKUP_DIR.mkdir(exist_ok=True)
    if MEMORY_FILE.exists():
        backup = BACKUP_DIR / f"MEMORY-{datetime.date.today()}.md"
        backup.write_text(current)
        log(f"Backed up to {backup}")

    MEMORY_FILE.write_text(updated)
    log(f"MEMORY.md updated ({len(updated)} chars)")

    # Mark synthesized
    with open(SYNTH_LOG, "a") as f:
        for _, h in new:
            f.write(h + "\n")

if __name__ == "__main__":
    main()
```

---

## Task 4 — Create enqueue-session.sh

Write this file to ~/personal/projects/ai-coding-kb/scripts/enqueue-session.sh

```bash
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
```

After writing, run: chmod +x ~/personal/projects/ai-coding-kb/scripts/enqueue-session.sh

---

## Task 5 — Update ~/.claude/settings.json

Read the current contents of ~/.claude/settings.json first.
Then merge in the SessionEnd hook — do NOT overwrite other existing keys.

The hook to add under "hooks" > "SessionEnd":
```json
{
  "hooks": {
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/Users/sumanyadav/personal/projects/ai-coding-kb/scripts/enqueue-session.sh"
          }
        ]
      }
    ]
  }
}
```

Show me the merged result before writing.

---

## Task 6 — Create ~/.claude/CLAUDE.md

Write this file to ~/.claude/CLAUDE.md

```markdown
# Claude Code — Global Memory

<!-- Auto-loaded at every session start -->

@/Users/sumanyadav/personal/projects/ai-coding-kb/AGENTS.md
@/Users/sumanyadav/personal/projects/ai-coding-kb/journals/MEMORY.md
```

Note: MEMORY.md may not exist yet on first run — that is fine, Claude Code will skip missing imports gracefully.

---

## Task 7 — Create symlinks in ~/.claude/

Run these commands to symlink agents and skills from ai-coding-kb into ~/.claude/:

```bash
ln -sf /Users/sumanyadav/personal/projects/ai-coding-kb/agents /Users/sumanyadav/.claude/agents
ln -sf /Users/sumanyadav/personal/projects/ai-coding-kb/skills /Users/sumanyadav/.claude/skills
```

Check if ~/.claude/agents or ~/.claude/skills already exist before symlinking. If they do, tell me.

---

## Task 8 — Add crontab entry

Show me the current crontab with: crontab -l

Then add these lines (do not replace existing entries):
```
# Journal collection + memory synthesis (runs every 30 min)
*/30 * * * * /Users/sumanyadav/personal/projects/ai-coding-kb/scripts/collect-journals.sh >> /Users/sumanyadav/personal/projects/ai-coding-kb/journals/.cron.log 2>&1 && python3 /Users/sumanyadav/personal/projects/ai-coding-kb/scripts/synthesize-memory.py >> /Users/sumanyadav/personal/projects/ai-coding-kb/journals/.cron.log 2>&1
```

Use: (crontab -l; echo "<new line>") | crontab -

---

## Task 9 — Bootstrap: run initial collection and synthesis

Run:
```bash
/Users/sumanyadav/personal/projects/ai-coding-kb/scripts/collect-journals.sh
python3 /Users/sumanyadav/personal/projects/ai-coding-kb/scripts/synthesize-memory.py
```

Show me the output of both commands. If synthesis fails due to missing ANTHROPIC_API_KEY,
tell me and skip — the cron job will handle it once the key is available in the shell environment.

---

## Task 10 — Update .gitignore in ai-coding-kb

Read the current .gitignore. Add these lines if not already present:
```
# Journal system internals
journals/raw/
journals/.processed
journals/.synthesized
journals/.queue
journals/.cron.log
journals/.synthesis.log
journals/.backups/
```

journals/MEMORY.md should NOT be gitignored — it should be committed so Cursor and Gemini also get it.

---

## Done

Show a summary table of every file created/modified and its purpose.
