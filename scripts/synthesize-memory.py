#!/usr/bin/env python3
"""
Incremental memory synthesis — two-phase approach.
Phase 1: Extract compact insights from new journals in batches (no MEMORY.md context → fast).
Phase 2: Single merge call combining all extracted insights with current MEMORY.md.
Journals are marked synthesized after phase 1 so crashes don't reprocess them.
"""
import hashlib, datetime, pathlib, sys, subprocess, json

KB_DIR      = pathlib.Path.home() / "personal/projects/ai-coding-kb"
RAW_DIR     = KB_DIR / "journals/raw"
MEMORY_FILE = KB_DIR / "journals/MEMORY.md"
SYNTH_LOG   = KB_DIR / "journals/.synthesized"
BACKUP_DIR  = KB_DIR / "journals/.backups"
LOG_FILE    = KB_DIR / "journals/.synthesis.log"

MODEL           = "claude-sonnet-4-6"
EXTRACT_BATCH   = 10   # journals per extraction call — no MEMORY.md, so can be larger
EXTRACT_TIMEOUT = 180  # seconds — fast, small prompts
MERGE_TIMEOUT   = 900  # seconds — includes MEMORY.md in context

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

def call_claude(prompt: str, timeout: int) -> str:
    result = subprocess.run(
        [
            "claude", "-p",
            "--model", MODEL,
            "--output-format", "json",
            "--append-system-prompt",
            "Do NOT use any memory, file creation, or file writing tools. "
            "Return your complete response as plain text only, with no preamble or meta-commentary.",
        ],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        log(f"ERROR: claude CLI failed: {result.stderr.strip()}")
        sys.exit(1)
    data = json.loads(result.stdout)
    return data["result"].strip()

def extract_insights(batch: list) -> str:
    """Phase 1: extract compact insights from a batch of journals. No MEMORY.md needed."""
    journal_text = "\n\n---\n\n".join(
        f"# Source: {f.name}\n\n{f.read_text()}" for f, _ in batch
    )
    prompt = f"""Extract actionable developer insights from these journal entries.
Output ONLY a compact bullet list. Each bullet: max 2 lines, ends with (source_filename).
Focus on: architectural decisions, gotchas, patterns, tool preferences, project-specific facts.
No headers, no preamble, no explanation. Just the bullet list.

{journal_text}"""
    return call_claude(prompt, EXTRACT_TIMEOUT)

def merge_into_memory(insights_text: str, current_memory: str) -> str:
    """Phase 2: single call to merge all extracted insights into MEMORY.md."""
    prompt = f"""You are a memory synthesis agent maintaining MEMORY.md for a software developer.
This file is loaded at the start of every Claude Code, Cursor, and Gemini CLI session.
Keep it dense, actionable, and scannable. No fluff. Each insight = 1-3 lines max.

## Current MEMORY.md
{current_memory or "(empty — this is the first synthesis run)"}

## New Insights to Integrate
{insights_text}

## Instructions
1. If a new insight SUPERSEDES or CONTRADICTS existing memory → update/replace it, move old to ## Superseded
2. If a new insight adds new info → merge it into the right section
3. COMPACT aggressively: merge duplicate or near-duplicate insights into single entries
4. Preserve these sections (add domain-specific subsections as needed):
   - ## Patterns & Conventions
   - ## Architecture Decisions
   - ## Gotchas & Watch-outs
   - ## Tool & Workflow Preferences
   - ## Project-Specific Notes (subsection per project)
   - ## Superseded (what changed, when, old value → new value)
5. Add at top: `<!-- last-updated: {datetime.date.today()} | journals: N -->`

Return ONLY the updated MEMORY.md. No preamble, no explanation."""
    return call_claude(prompt, MERGE_TIMEOUT)

def main():
    new = get_unprocessed()
    if not new:
        log("No new journals to synthesize.")
        return

    log(f"Found {len(new)} new journal(s) — extracting in batches of {EXTRACT_BATCH}")

    # Phase 1: extract insights from all batches (crash-safe: mark each batch immediately)
    all_insights = []
    total_batches = (len(new) + EXTRACT_BATCH - 1) // EXTRACT_BATCH
    for i in range(0, len(new), EXTRACT_BATCH):
        batch = new[i : i + EXTRACT_BATCH]
        batch_num = i // EXTRACT_BATCH + 1
        log(f"Extracting batch {batch_num}/{total_batches}: {[f.name for f, _ in batch]}")
        insights = extract_insights(batch)
        all_insights.append(insights)
        with open(SYNTH_LOG, "a") as f:
            for _, h in batch:
                f.write(h + "\n")

    # Phase 2: single merge into MEMORY.md
    log("Merging all insights into MEMORY.md...")
    current = MEMORY_FILE.read_text() if MEMORY_FILE.exists() else ""
    combined_insights = "\n\n".join(all_insights)

    BACKUP_DIR.mkdir(exist_ok=True)
    if MEMORY_FILE.exists():
        backup = BACKUP_DIR / f"MEMORY-{datetime.date.today()}.md"
        backup.write_text(current)
        log(f"Backed up to {backup}")

    updated = merge_into_memory(combined_insights, current)
    MEMORY_FILE.write_text(updated)
    log(f"MEMORY.md updated ({len(updated)} chars)")

if __name__ == "__main__":
    main()
