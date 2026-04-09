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
