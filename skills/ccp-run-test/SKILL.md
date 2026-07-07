---
name: ccp-run-test
description: >-
  Standalone CCP workflow test run. Checks for uncommitted changes, optionally
  commits and pushes, links the current branch to beta CCP, builds or accepts
  a trigger payload, triggers the run, and monitors to completion. Use when
  Suman wants to quickly test a CCP workflow branch in beta without the full
  cost optimization pipeline.
---

# CCP Run Test

## When to Use

Use when Suman asks to:
- Test a CCP workflow branch in beta
- "Run this in beta" or "trigger a test run"
- Validate a feature branch change via CCP before raising a PR

This is the **standalone** version — no data seeding, no A/B comparison, no output table copying.
For the full cost optimization pipeline, use `/ccp-cost-opt-pipeline` instead.

## Prerequisites

- CCP CLI venv: `source ~/ccp_cli_project/ccp_cli_env/bin/activate`
- Current working directory must be a CCP workflow repo (has `ccp-configs/` directory)
- The repo must have `ccp-configs/project.yaml` and at least one workflow YAML

## Step 1: Pre-Flight Check

### 1a. Detect current branch
```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Current branch: $BRANCH"
```

If on `master` or `main`: inform Suman and ask if they want to test master directly or switch to a feature branch.

### 1b. Check for uncommitted changes
```bash
git status --short
```

If there are uncommitted changes and the branch is a feature branch, ask Suman using `AskUserQuestion`:

```
"You have uncommitted changes on branch '<branch>':

<git status output>

Should I:
1. Commit and push these changes before triggering the test run?
2. Stash changes and test what's already pushed?
3. Cancel — I'll handle it myself."
```

**If commit requested:**
- Ask Suman for a commit message, or suggest one based on the changed files
- Stage, commit, and push:
  ```bash
  git add -A
  git status  # show what will be committed
  git commit -m "<message>"
  git push origin <branch>
  ```

**If stash requested:**
- `git stash` and proceed with what's already on remote

### 1c. Verify branch is pushed
```bash
git log origin/<branch>..<branch> --oneline
```
If there are unpushed commits, ask Suman whether to push them.

## Step 2: CCP Link

Ask Suman to confirm the target CCP environment using `AskUserQuestion`:

```
"Ready to link branch '<branch>' to CCP. The default environment is beta.

Which CCP environment should I use?
1. beta (default)
2. qa
3. prod"
```

```bash
source ~/ccp_cli_project/ccp_cli_env/bin/activate
ccp --env <selected_env> configure
ccp link
```

If `ccp link` fails: retry once. If still fails, create Jira in project `CR` with error details, inform Suman.

If pyspark module changes are detected (changes in `ccp-configs/pyspark/` or a code repo with `pyproject.toml`):
```bash
ccp pyspark publish
```

## Step 3: Build or Accept Payload

Ask Suman using `AskUserQuestion`:

```
"Branch '<branch>' is linked to beta. Ready to trigger.

Do you have a payload JSON to use, or should I help build one?

1. I have a payload — I'll paste it or give you the file path
2. Build one together — I'll need workflow name, client_id, and any variables"
```

### Option 1: Suman provides payload
- Accept the JSON directly or read from the file path provided
- Validate it has the required structure:
  ```json
  {
    "clientName": "...",
    "executionEntityInfo": {
      "branch": "...",
      "name": "...",
      "project": "..."
    },
    "sqlConfig": {"size": "..."},
    "executionVariables": [...]
  }
  ```
- Confirm `executionEntityInfo.branch` matches the current branch — warn if it doesn't

### Option 2: Build payload interactively
1. Read `ccp-configs/project.yaml` to get the project name
2. List available workflows:
   ```bash
   ls ccp-configs/workflows/*.yaml
   ```
3. Ask Suman which workflow to run (if multiple) and for the required variables:
   ```
   "Available workflows: <list>

   Which workflow should I trigger?
   And please provide:
   - client_id (or client name)
   - Any date parameters (rundate, min_report_date, max_report_date)
   - Warehouse size preference (default: SMALL)
   - Any other workflow-specific variables"
   ```
4. Read the selected workflow YAML to discover required variables and their defaults
5. Construct the payload, filling in provided values and using defaults where not specified
6. Show the constructed payload to Suman for confirmation before triggering

Save payload to `claude-analysis/ccp-run-test-<branch>-<date>/payload.json`.

## Step 4: Trigger

```bash
source ~/ccp_cli_project/ccp_cli_env/bin/activate
ccp trigger --file_name <path-to-payload.json>
```

If trigger fails: retry once (known to succeed on retry). If second attempt fails, create Jira in `CR`, inform Suman.

Capture the `execution_id` from the response.

## Step 5: Monitor

Run monitoring as a background bash command (`run_in_background=true`):

```bash
source ~/ccp_cli_project/ccp_cli_env/bin/activate && \
EXEC_ID="<execution_id>" && \
START=$(date +%s) && \
while true; do
  STATUS=$(ccp status --execution_id $EXEC_ID 2>&1)
  echo "[$(date '+%H:%M:%S')] $STATUS"
  if echo "$STATUS" | grep -qE 'COMPLETED|FAILED|CANCELLED'; then
    echo "TERMINAL_STATE_REACHED"
    break
  fi
  ELAPSED=$(( $(date +%s) - START ))
  if [ $ELAPSED -gt 3600 ]; then
    echo "WARNING: Run exceeding 1 hour. Elapsed: ${ELAPSED}s"
  fi
  sleep 60
done
```

If the run shows QUEUED for >1 hour or appears stuck: create Jira in `CR` with execution_id and timestamps, inform Suman.

## Step 6: Report

Once the run reaches a terminal state, report to Suman:

**If COMPLETED:**
```
"CCP run completed successfully.

- Branch: <branch>
- Workflow: <workflow_name>
- Execution ID: <id>
- Duration: <X> minutes
- CCP UI: http://ccp-execute-beta.commerceiq.ai/ccp/execute/<execution_id>/details

What would you like to do next?
1. Check the output tables
2. Trigger another run (different params)
3. Compare with a master branch run (I can use /ccp-beta-test for the full A/B flow)
4. Done for now"
```

**If FAILED:**
```
"CCP run failed.

- Execution ID: <id>
- Error: <error from status>

Should I:
1. Retry with the same payload
2. Check the Databricks logs for details
3. Raise a support ticket in CR"
```

## Key Gotchas

- **Always activate the CCP venv** before any `ccp` command: `source ~/ccp_cli_project/ccp_cli_env/bin/activate`
- **`ccp trigger` sometimes fails on first attempt** — always retry once
- **`clientName` must be a valid client name** even if the workflow doesn't use it
- **Payload `branch` must match the linked branch** — mismatches cause silent failures
- **Use `claude-analysis/` as the work directory** (not `cursor-analysis/`)
