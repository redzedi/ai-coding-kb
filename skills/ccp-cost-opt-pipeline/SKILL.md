---
name: ccp-cost-opt-pipeline
description: >-
  End-to-end autonomous pipeline for CCP workflow cost optimization. Orchestrates
  the full lifecycle: analysis → recommendation selection → implementation →
  beta testing → A/B comparison → PR and documentation. Manages multiple
  recommendation tracks in parallel, persists state across sessions, and handles
  human checkpoints. One CCP workflow per pipeline run.
---

# CCP Cost Optimization Pipeline

## When to Use

Use when Suman asks to:
- Run the full cost optimization pipeline for a CCP workflow
- "Optimize workflow X end to end"
- "Take these recommendations through to PR"

Do NOT use for:
- Analysis only (use `/databricks-workflow-cost-optimization` directly)
- One-off beta testing (use `/ccp-beta-test` directly)
- Ad-hoc data comparison (use `/ccp-ab-compare` directly)

## Prerequisites

- All MCP servers: `dbx-dev`, `dbx-prod`, `plugin-atlassian-atlassian`, `user-bitbucket4`,`ccp-prod-metadata-db`, `groundcover`, `dashboard-db-prod`
- CCP CLI venv: `source ~/ccp_cli_project/ccp_cli_env/bin/activate`
- Agent types available: `@lead`, `@my-coder`, `@reviewer`, `@beta-ops`, `@analyst`
- Skills available: `databricks-workflow-cost-optimization`, `ccp-workflow-experiment`, `ccp-beta-test`, `ciq-data-copy`, `ccp-ab-compare`, `ccp-housework`, `databricks-query-profile-analysis`, `common-skills`, `start-build`

## State Management

All state persists in `claude-analysis/<jira-id>/orchestrator-state.json`. Every phase transition must update this file before proceeding. Any agent or session can resume from the recorded phase.

```json
{
  "workflow_name": "<ccp_workflow_name>",
  "jira_ticket": "<JIRA-ID>",
  "analysis_doc": "<path>",
  "misc_data_doc": "<path>",
  "lld_doc": "<path>",
  "current_phase": "analysis|prequalification|selection|implementation|beta_testing|comparison|approval|housework|done",
  "prequalification": {
    "round": 1,
    "recommendations_doc": "<path to latest temp_recommendations_vN.md>",
    "hypotheses": [
      {
        "id": "hyp-1",
        "description": "<recommendation description>",
        "type": "code|config|architecture",
        "autonomously_verifiable": true,
        "test_plan": "<which VTL module, control vs hypothesis query>",
        "threshold": "<pass/fail criteria>",
        "verdict": "UNVERIFIED|PASSED|REJECTED|NOT_VERIFIABLE",
        "reason": "<set when REJECTED>",
        "experiment_result": {
          "functional_equivalent": null,
          "control_duration_s": null,
          "hypothesis_duration_s": null,
          "observed_gain_pct": null
        }
      }
    ]
  },
  "tracks": [
    {
      "id": "track-1",
      "recommendation": "<description>",
      "type": "code|config|architecture",
      "phase": "<track-level phase>",
      "branch": "<feature-branch-name>",
      "feature_run": {
        "execution_id": "<id>",
        "client_id": "<id>",
        "status": "<COMPLETED|FAILED|IN_PROGRESS>",
        "duration_minutes": null,
        "output_tables": []
      },
      "control_run": {
        "execution_id": "<id>",
        "client_id": "<id>",
        "status": "<COMPLETED|FAILED|IN_PROGRESS>",
        "duration_minutes": null,
        "output_tables": []
      },
      "comparison": {
        "functional_equivalent": null,
        "runtime_delta_pct": null,
        "verdict": "PROCEED|NEEDS_INVESTIGATION|FAIL"
      },
      "reviewer_checkpoints": {
        "post_code": "PENDING|PASSED|FAILED",
        "post_comparison": "PENDING|PASSED|FAILED",
        "post_housework": "PENDING|PASSED|FAILED"
      }
    }
  ]
}
```

### Resuming From State

At the start of any session, check for an existing `orchestrator-state.json`:
1. Read the file and determine `current_phase`
2. Check each track's individual phase
3. Resume from the earliest incomplete phase
4. Report to Suman what was completed and what remains

---

## Phase 0: Analysis

Invoke `/databricks-workflow-cost-optimization` with the target workflow name.

This skill produces:
- Cost optimization analysis document (`<wf_name>_cost_optimization.md`)
- Discovered data document (`misc_<ddMMyyyy>.md`)
- Low-level design document (`temp_sql_lld.md`) — for SQL workflows
- Recommendations table (`temp_recommendations_v1.md`)
- Jira ticket (parent ticket for the optimization effort)

After completion:
1. Create `claude-analysis/<jira-id>/` work directory
2. Move/copy all output documents into this directory
3. Initialize `orchestrator-state.json` with Phase 0 outputs
4. Update state: `current_phase: "prequalification"`

### Incremental Re-Invocation (called from Phase 0.5)

Phase 0.5 hands raw experiment evidence back here after every pre-qualification round. On an
incremental call, do **not** redo discovery or cost profiling — reuse the cached
`analysis_doc` / `misc_data_doc` from the initial run. Only re-run the skill's **Phase 3
(Analysis Patterns)** and **Phase 4 (LLD)** steps, seeded with:
- The full set of this round's experiment results (functional equivalence, control vs
  hypothesis duration, query profile evidence if available) for both PASSED and REJECTED hypotheses
- The existing analysis/misc-data context (already discovered, no re-fetch needed)

Brainstorm new hypotheses that account for what the evidence revealed (e.g., a rejected
hypothesis's profile shows the real bottleneck was elsewhere; a passed hypothesis's control
run reveals a second scan worth eliminating next). Output: newly drafted rows appended to the
working recommendations set, each tagged `UNVERIFIED` with its own test plan and threshold —
handed back to Phase 0.5 Step D for versioning. If this pass produces zero new hypotheses,
report that back so Phase 0.5 can exit its loop.

---

## Phase 0.5: Pre-Qualification (Autonomous Loop, SQL Workflows Only)

Beta testing (Phase 3) is expensive — a full CCP run can take hours. Many SQL refactoring
hypotheses can be cheaply pre-qualified before investing in a beta run, by compiling the
proposed VTL change to a read-only `SELECT`, running it against prod directly (no CCP job
needed), and comparing result + wall-clock latency against a control query. This phase uses
the existing `/ccp-workflow-experiment` skill to filter hypotheses before they ever reach
Suman or consume beta compute.

**No new skill or agent is used here** — this phase reuses `/ccp-workflow-experiment`
(already handles VTL→SQL compilation, variant isolation, prod execution, functional
equivalence) via `@my-coder`, with strict pass/fail evaluation by `@analyst`. New-idea
generation is **not** `@analyst`'s job here — it belongs to Phase 0's incremental
re-invocation (see below), which has the full analytical context (repos, DAG, cost profile)
to reason about what new evidence implies. `@analyst`'s role in this phase is narrow and
mechanical: does this specific hypothesis clear its own threshold, yes or no.

### Step A: Classify Hypotheses

For each row in `temp_recommendations_v1.md` (cross-referenced with `temp_sql_lld.md`), tag it:
- **Autonomously verifiable** — type is `code`, targets a SQL/VTL module, and the LLD has a
  concrete before/after snippet expressible as a `SELECT`
- **Not verifiable** (`NOT_VERIFIABLE`) — `config`, `architecture`, or `code` changes to
  pyspark/spark modules. No cheap offline test exists for these — they pass through
  untouched and are validated later only via the full Phase 3 beta A/B.

Each autonomously-verifiable hypothesis gets an explicit **test plan and threshold**, derived
from the LLD and the recommendation's expected gain:
- Test plan: which VTL module, what the control vs hypothesis query is
- Threshold: reuse the existing convention from `databricks-workflow-cost-optimization`'s
  Phase 5 — observed gain must be within 20-25% of expected gain to PASS; functional
  non-equivalence is an automatic REJECT regardless of latency

Record all hypotheses in `orchestrator-state.json` under `prequalification.hypotheses` with
`verdict: "UNVERIFIED"` (or `"NOT_VERIFIABLE"` for the non-testable ones).

### Step B: Parallel Experimentation

For every hypothesis that is `autonomously_verifiable` and `UNVERIFIED`, spawn `@my-coder`
with `run_in_background=true`, one per hypothesis, each in its own worktree:

```
@my-coder invokes /ccp-workflow-experiment with:
  - is_vtl_file_changes_done: F (my-coder applies the LLD snippet, then the skill compiles+runs it)
  - parameters: top client_id by p95 runtime (from misc_*.md) + matching prod rundate
```

This runs the skill through its Step 6 (execute control + hypothesis SELECTs against prod,
verify functional equivalence via row/checksum comparison, capture wall-clock duration for
each). Step 7-8 of that skill (query profile JSON, deep physical-plan analysis) is **not**
needed here — that human-handoff step stays reserved for the deeper Phase 4 comparison after
a hypothesis has already been implemented and beta-tested.

Wait for all of this round's experiments to complete (barrier — `@analyst` needs the full
round's results to look for cross-hypothesis clues in Step C).

### Step C: Analyst Evaluation (Strict Accept/Reject)

`@analyst` receives all experiment results for the round and, per hypothesis, checks it
**strictly against that hypothesis's own test plan and threshold** — no new-idea generation,
no lateral judgment calls beyond this pass/fail check:
- **PASSED** — functional equivalence held AND observed latency gain within 20-25% of the
  expected gain stated in the hypothesis AND (if query profile evidence was supplied) the
  profile supports the claimed mechanism
- **REJECTED** — with a specific, factual reason: functional mismatch, gain below threshold,
  gain implausibly above threshold, or profile evidence contradicting the hypothesis's claimed
  mechanism

Record each verdict and reason in `orchestrator-state.json`. Do not draft new hypotheses here.

### Step D: Handoff to Incremental Analysis (Back to Phase 0)

Once every hypothesis in the round has a verdict, package **all** of this round's raw
experiment data — for both PASSED and REJECTED hypotheses — and hand it back to **Phase 0's
incremental re-invocation**:
- Functional equivalence results
- Control vs hypothesis duration and observed gain %
- Query profile evidence, if any was gathered
- The verdict and reason from Step C

Phase 0 (incremental mode) uses this evidence plus its existing cached analysis context to
brainstorm new hypotheses — this is where new ideas come from, not from `@analyst`. It returns
zero or more new `UNVERIFIED` hypotheses (each with its own test plan and threshold).

### Step E: Version and Supersede

Write `temp_recommendations_v{N+1}.md`, superseding `temp_recommendations_v{N}.md`:
- Carries forward PASSED hypotheses (now ready for Selection)
- Drops REJECTED hypotheses from the active list, logging them in a
  `## Rejected Hypotheses (Round N)` appendix with reason — never silently discarded
- Adds any new hypotheses returned by Phase 0's incremental analysis (Step D) as `UNVERIFIED`
- Untouched `NOT_VERIFIABLE` recommendations carry forward as-is

Update `orchestrator-state.json`: `prequalification.round` incremented,
`prequalification.recommendations_doc` points at the new file, hypothesis verdicts updated.

### Loop and Exit

```
round = 1
while exists h in hypotheses where h.autonomously_verifiable and h.verdict == "UNVERIFIED":
  run Steps B-E for this round
  round += 1
  if round > 5:
    AskUserQuestion("Pre-qualification is still generating new hypotheses after 5 rounds
    for <workflow_name>. Continue looping, or proceed to Selection with what we have?")
proceed to Phase 1 (Selection) using the latest recommendations doc
```

The loop naturally terminates when Phase 0's incremental analysis (Step D) returns no new
hypotheses for a round — there is nothing left to classify as `UNVERIFIED`.

Selection (Phase 1) only ever sees PASSED + NOT_VERIFIABLE recommendations — REJECTED ones
are excluded but remain visible in the appendix if Suman wants to review them.

### Error Handling
- **Experiment execution fails** (VTL compile error, prod query error): mark the hypothesis
  REJECTED with the error as reason; do not block other hypotheses in the round
- **Round cap exceeded (>5 rounds):** escalate to Suman per the loop-exit logic above

Update state: `current_phase: "selection"` once the loop exits.

---

## Phase 1: Selection (Human-in-the-Loop)

Present the recommendations from the latest `temp_recommendations_vN.md` (post pre-qualification)
to Suman using `AskUserQuestion`. PASSED hypotheses carry their observed gain alongside the
originally expected gain; NOT_VERIFIABLE recommendations show only the expected gain from Phase 0:

```
"The cost optimization analysis for <workflow_name> produced these recommendations
(pre-qualification round <N> complete):

| # | Recommendation | Type | Expected Gain | Pre-Qual Verdict | Observed Gain |
|---|---|---|---|---|---|
| 1 | <desc> | code | -X% runtime | PASSED | -Y% (matches) |
| 2 | <desc> | config | -$Z/month | NOT_VERIFIABLE | — |
| ... | ... | ... | ... |

Which recommendations should I implement? (Select by number)
Also:
1. Should I bundle them into a single PR, or create separate PRs per recommendation?
2. Which Jira project should I create the ticket(s) in? (e.g., BIPLATFORM, MLE, etc.)"
```

Based on selection:
1. Create one track per selected recommendation (or group if bundled)
2. Create Jira parent ticket in the specified project + subtasks per track if multiple tracks
3. Update state with tracks, Jira project, and `current_phase: "implementation"`

---

## Phase 2: Implementation (Per Track, Parallelizable)

For each track, invoke `@lead` → `@my-coder` with:
- The LLD document section for this recommendation
- The feature branch name (derived from Jira subtask ID)
- The target repo and file paths

### Steps per track:
1. Create feature branch from master: `git checkout -b <JIRA-SUBTASK-ID>`
2. Implement changes per the LLD document
3. Commit with prefix: `<JIRA-SUBTASK-ID>: <brief description>`
4. Push to remote
5. If pyspark module: `source ~/ccp_cli_project/ccp_cli_env/bin/activate && ccp pyspark publish`

### Reviewer Checkpoint #1 (Post-Code)

Invoke `@reviewer` with:
- The PR diff (or branch diff against master)
- The LLD document section
- The original recommendation

**Validates:**
- Code matches LLD exactly
- No regression on shared modules (check all workflows using any modified module)
- Deterministic window functions have tie-breaker columns
- No security concerns
- Commit messages follow convention

If reviewer rejects: send feedback to `@my-coder` via `@lead`. Loop up to 3 times. After 3 rejections, escalate to Suman.

### Parallelization
Independent tracks (different modules, different repos) can run in parallel:
- Spawn each `@lead` invocation with `run_in_background=true`
- Each track works in its own worktree to avoid conflicts
- Wait for all tracks to reach PASSED on checkpoint #1 before proceeding

Update state: track phase → `"implemented"`, then `current_phase: "beta_testing"` when all tracks pass.

---

## Phase 3: Beta Testing (Per Track, Parallelizable)

For each track, invoke `@beta-ops` with the `/ccp-beta-test` skill.

### Inputs to @beta-ops:
- Feature branch name
- Workflow name and project name (from `ccp-configs/project.yaml`)
- The `misc_*.md` document (for client_id and time period selection)
- Track ID for file naming

### What @beta-ops does (per /ccp-beta-test):
1. Determines test parameters (top p95 client, date range)
2. Seeds beta with prod data via `/ciq-data-copy`
3. Links feature branch → triggers feature run → monitors → saves output
4. Links master branch → triggers control run → monitors → saves output
5. Produces beta test report

### Monitoring Strategy
CCP jobs are monitored via background bash polling (`run_in_background=true`):
```bash
source ~/ccp_cli_project/ccp_cli_env/bin/activate && \
while true; do
  STATUS=$(ccp status --execution_id <ID> 2>&1)
  if echo "$STATUS" | grep -qE 'COMPLETED|FAILED|CANCELLED'; then
    echo "TERMINAL: $STATUS"; break
  fi
  sleep 60
done
```

### Error Handling (per plan):
- CCP failures → retry once, then Jira in project `CR`, inform Suman
- Data copy failures → retry once, then Jira in project `DR`, inform Suman
- Run FAILED → check if data issue or code bug; escalate appropriately

### Parallelization
- Independent tracks can run their beta tests in parallel
- Within a track: feature run first, then control run (sequential — don't waste compute on control if feature fails)

Update state: track phase → `"beta_tested"`, then `current_phase: "comparison"` when all tracks complete.

---

## Phase 4: Comparison & Validation

For each track, invoke `@analyst` with the `/ccp-ab-compare` skill.

### Inputs to @analyst:
- Beta test report (execution IDs, output table locations, runtimes)
- Original cost optimization analysis doc (expected gain benchmarks)
- Track ID

### What @analyst does (per /ccp-ab-compare):
1. Bidirectional EXCEPT for functional equivalence
2. Aggregate checksum validation
3. Runtime and DBU cost delta calculation
4. Requests query profiles from Suman via `AskUserQuestion`
5. If profiles provided: invokes `/databricks-query-profile-analysis`
6. Produces comparison report

### Reviewer Checkpoint #2 (Post-Comparison)

Invoke `@reviewer` with:
- The comparison report
- The original recommendation and expected gain

**Validates:**
- Functional equivalence confirmed (zero EXCEPT differences, or justified conditional pass)
- Performance gain within ±25% of expected
- DBU cost reduction aligns with analysis projections
- No unexplained anomalies

If reviewer flags issues: document as `NEEDS_INVESTIGATION`, escalate to Suman.

Update state: track phase → `"compared"`, comparison verdict recorded, then `current_phase: "approval"`.

---

## Phase 5: Approval (Human-in-the-Loop)

Present the consolidated results to Suman using `AskUserQuestion`:

```
"Cost optimization validation complete for <workflow_name>.

Track 1: <recommendation>
  - Functional equivalence: PASS
  - Performance: -33% runtime (expected -35%) — ALIGNED
  - Verdict: PROCEED

Track 2: <recommendation>
  - Functional equivalence: CONDITIONAL PASS (tie-breaker ordering)
  - Performance: -12% runtime (expected -20%) — PARTIALLY VALIDATED
  - Verdict: NEEDS_INVESTIGATION

Proceed with PR and documentation for passing tracks?
For Track 2: should I investigate further, proceed anyway, or drop it?"
```

Based on response:
- PROCEED tracks → advance to Phase 6
- INVESTIGATE tracks → return to Phase 4 with additional analysis
- DROP tracks → mark as `"dropped"` in state

Update state: `current_phase: "housework"` for approved tracks.

---

## Phase 6: Housework

### Implementation Work (via @lead → @my-coder)
1. Version bumps (if pyspark/spark modules changed)
2. Unit test additions (for code changes)
3. Final commit and push
4. PR creation via Bitbucket

### Documentation (via @analyst with /ccp-housework)
1. Ask Suman for Confluence parent page location
2. Create wiki page with: problem statement, changes, expected vs observed gains, beta evidence
3. Update Jira ticket with PR link and Confluence page

### Reviewer Checkpoint #3 (Post-Housework)

Invoke `@reviewer` with:
- The final PR
- The Confluence page content
- The comparison report

**Validates:**
- PR contains all expected changes and nothing extra
- Unit tests are meaningful
- Version numbers correctly bumped
- Confluence page accurately reflects beta evidence
- PR description links to Jira

Update state: track phase → `"done"`, `current_phase: "done"` when all tracks complete.

---

## Phase Summary

```
Phase 0    ANALYSIS           /databricks-workflow-cost-optimization        Orchestrator
                              (+ incremental re-invocation from 0.5)
Phase 0.5  PRE-QUALIFICATION  @my-coder + /ccp-workflow-experiment          Loop with Phase 0,
                              + @analyst strict accept/reject                (SQL workflows only)
Phase 1    SELECTION          AskUserQuestion                              Orchestrator
Phase 2    IMPLEMENTATION     @lead → @my-coder + @reviewer #1             Per track (parallel)
Phase 3    BETA TESTING       @beta-ops + /ccp-beta-test                   Per track (parallel)
Phase 4    COMPARISON         @analyst + /ccp-ab-compare + @reviewer #2    Per track
Phase 5    APPROVAL           AskUserQuestion                              Orchestrator
Phase 6    HOUSEWORK          @lead + @analyst + @reviewer #3              Per track
```

## Model Tiering

| Agent | Model | Used In |
|---|---|---|
| Orchestrator (this skill) | Opus (inherit) | All phases |
| @analyst | Opus (inherit) | Phases 0.5, 4, 6 |
| @reviewer | Opus (inherit) | Phases 2, 4, 6 |
| @lead | Opus (inherit) | Phases 2, 6 |
| @my-coder | Sonnet (fast) | Phases 0.5, 2, 6 |
| @beta-ops | Sonnet (fast) | Phase 3 |

## Key Gotchas

- Always activate CCP venv before any `ccp` command: `source ~/ccp_cli_project/ccp_cli_env/bin/activate`
- Master branch needs `ccp link` each time — it is NOT permanently linked to beta
- CCP intermediate tables expire after ~7 days — run comparison soon after beta test
- Table names in SQL must be **lowercase** for Unity Catalog
- `ccp trigger` is known to sometimes fail on first attempt — always retry once
- Use `claude-analysis/` as the work directory (not `cursor-analysis/`)
- One workflow per pipeline run — don't mix recommendations from different workflows
- State file is the source of truth — update it at every phase transition
- When resuming: always re-read state file, report progress to Suman, confirm next steps
- Pre-qualification (Phase 0.5) only applies to autonomously-verifiable SQL/VTL hypotheses — pyspark/spark code, config, and architecture recommendations skip it entirely and go straight to Selection
- Pre-qualification runs against **prod** read-only queries (not beta) — it never touches beta CCP or triggers a CCP job; only Phase 3 does
- `@analyst` in Phase 0.5 only accepts/rejects against each hypothesis's own threshold — it does not invent new hypotheses. New ideas come from Phase 0's incremental re-invocation, which has the full analytical context (repos, DAG, cost profile) that `@analyst` in this narrow role does not
- `temp_recommendations_vN.md` versions supersede each other — always reference the latest version in state, never an older one
