---
name: ccp-beta-test
description: >-
  Beta test lifecycle for CCP workflow cost optimization. Links branch to beta
  CCP, determines test parameters, seeds beta with prod data via ciq-data-copy,
  triggers CCP run, monitors via background bash polling, copies output to
  comparison table. Handles both feature branch (treatment) and master branch
  (control) runs.
---

# CCP Beta Test

## When to Use

Use this skill when:
- Code changes for a cost optimization recommendation are committed and pushed to a feature branch
- @beta-ops or the uber orchestrator needs to run a feature-vs-control A/B test in beta
- You need to validate that an optimization produces correct output at reduced cost

Do NOT use for production deployments.

## Prerequisites

- CCP CLI installed and venv available: `source ~/ccp_cli_project/ccp_cli_env/bin/activate`
- MCP servers:
  - **`dbx-dev`** — beta catalog access for output verification and comparison table creation
  - **`dbx-prod`** — source data queries for ciq-data-copy input
- The `/ciq-data-copy` skill for seeding beta data
- Access to the Bitbucket repo containing the CCP workflow configs (`ccp-configs/`)
- Inputs required:
  - Feature branch name
  - Workflow name
  - Project name (from `project.yaml`)
  - Path to the `misc_*.md` analysis doc produced by the cost optimization skill

## Phase 1: Determine Test Parameters

Read the `misc_*.md` document from the cost optimization analysis to find:

1. **client_id**: Use the top client by p95 runtime — this client exercises the most expensive code path
2. **time period**: Use the same rundate/date range that was analyzed
3. **workflow variables**: Match the `executionVariables` from the workflow YAML definition
4. **output tables**: Read the workflow YAML (`ccp-configs/workflows/<wf_name>.yaml`) to identify all `outputModules` with their `schema` and `outputTable`

Document the chosen parameters in `claude-analysis/<jira-id>/tracks/<track-id>/test-parameters.md`:

```markdown
# Test Parameters — Track <track-id>

- client_id: <id>
- rundate: <date>
- workflow: <name>
- project: <PROJECT_NAME>
- feature_branch: <branch>
- output_modules:
  - name: <module_name>, schema: <schema>, table: <output_table>
```

## Phase 2: Seed Beta Data

Invoke the `/ciq-data-copy` skill to copy required input tables from AWS_PROD to AWS_BETA:

1. Identify input tables: trace `dependsOn` modules in the workflow YAML, find their source tables in the VTL/code
2. Build the copy request JSON with:
   - `source_env: "AWS_PROD"`
   - `target_env: "AWS_BETA"`
   - The chosen `client_id` and date range
   - `copy_mode: "OVERWRITE"` — confirm with Suman before proceeding (this is the default safe choice for isolated testing)
3. Run the data copy script and verify completion per the ciq-data-copy skill

**If data copy fails:** retry once. If the error requires human intervention, create a Jira ticket in project `DR` with the full payload and error response, inform Suman, and await instructions.

## Phase 3: Link and Trigger Feature Branch (Treatment Run)

```bash
# Activate CCP CLI venv
source ~/ccp_cli_project/ccp_cli_env/bin/activate

# Configure beta environment
ccp --env beta configure

# Link the feature branch
ccp link
```

**If `ccp link` fails:** retry once. If still failing, create a Jira in project `CR` with error details, inform Suman, and await instructions.

Construct the trigger payload using CLI tools (avoids manual JSON construction):

```bash
# Set variables from test parameters
JIRA="BIPLATFORM-123"
TRACK="track-1"
WORKFLOW="aws_prod_etl"
PROJECT="PROJECT_NAME"
BRANCH="feature-branch-name"
CLIENT_ID="12345"
RUNDATE="2026-06-19"
BRAND="brand-name"

# Build trigger payload via jq (avoids manual JSON editing)
jq -n \
  --arg clientName "$BRAND" \
  --arg branch "$BRANCH" \
  --arg workflow "$WORKFLOW" \
  --arg project "$PROJECT" \
  --arg client_id "$CLIENT_ID" \
  --arg rundate "$RUNDATE" \
  '{
    clientName: $clientName,
    executionEntityInfo: {
      branch: $branch,
      name: $workflow,
      project: $project
    },
    sqlConfig: {size: "SMALL"},
    executionVariables: [
      {name: "client_id", value: $client_id},
      {name: "rundate", value: $rundate}
    ]
  }' > claude-analysis/$JIRA/tracks/$TRACK/feature-payload.json

# Verify the payload
jq . claude-analysis/$JIRA/tracks/$TRACK/feature-payload.json
```

Trigger:

```bash
ccp trigger --file_name claude-analysis/<jira-id>/tracks/<track-id>/feature-payload.json
```

**If trigger fails:** retry once (known to succeed on retry). If the second attempt also fails, create a Jira in `CR`, inform Suman.

Capture the `execution_id` from the response.

## Phase 4: Monitor Feature Run

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

**If the run shows QUEUED for >1 hour or appears stuck:** create a Jira in `CR` with the execution_id and timestamps, inform Suman.

**If the run FAILS:** capture the error and determine the cause:
- Data issue → try a different client_id
- Code bug → return to the implementation phase
- Infrastructure issue → create a Jira in `CR`

## Phase 5: Save Feature Run Output

After successful completion, copy the output table data to a comparison table using the `dbx-dev` MCP:

```sql
-- Run via dbx-dev MCP — one statement per outputModule
CREATE TABLE IF NOT EXISTS client_view_catalog.temp_<client_id>.feature_<track_id>_<output_table>
AS SELECT * FROM client_view_catalog.temp_ccp_<client_id>.e<execution_id>__<output_module_name>;
```

Do this for each `outputModule` listed in the workflow YAML.

Record in the track state:
- execution_id
- start/end time
- result_state
- output table locations

## Phase 6: Link and Trigger Master Branch (Control Run)

Repeat Phases 3–5 for the master branch:

1. Ensure you are on the master branch in the repo
2. `ccp link` (master also needs linking each time — not permanently linked)
3. Construct the control payload via CLI (same variables as feature, but `branch: "master"`):

```bash
# Reuse the same variables and rebuild payload with master branch
jq -n \
  --arg clientName "$BRAND" \
  --arg workflow "$WORKFLOW" \
  --arg project "$PROJECT" \
  --arg client_id "$CLIENT_ID" \
  --arg rundate "$RUNDATE" \
  '{
    clientName: $clientName,
    executionEntityInfo: {
      branch: "master",
      name: $workflow,
      project: $project
    },
    sqlConfig: {size: "SMALL"},
    executionVariables: [
      {name: "client_id", value: $client_id},
      {name: "rundate", value: $rundate}
    ]
  }' > claude-analysis/$JIRA/tracks/$TRACK/control-payload.json
```

4. `ccp trigger` with the control payload
5. Monitor via background bash poll
6. Save output to `client_view_catalog.temp_<client_id>.control_<track_id>_<output_table>`

## Phase 7: Report

Create `claude-analysis/<jira-id>/tracks/<track-id>/beta-test-report.md`:

```markdown
# Beta Test Report — Track <track-id>

## Parameters
- client_id: <id>
- rundate: <date>
- workflow: <name>

## Feature Run (Treatment)
- Execution ID: <id>
- Duration: <time>
- Status: COMPLETED
- Output tables: <list>

## Control Run (Master)
- Execution ID: <id>
- Duration: <time>
- Status: COMPLETED
- Output tables: <list>

## Runtime Delta
- Feature: <X> minutes
- Control: <Y> minutes
- Delta: <Z>% faster/slower

## Next Steps
Both runs completed. Ready for A/B comparison via /ccp-ab-compare.
```

## Key Gotchas

- **Always activate the CCP venv** before any `ccp` command: `source ~/ccp_cli_project/ccp_cli_env/bin/activate`
- **Table names in SQL must be lowercase** — uppercase causes Unity Catalog resolution errors
- **CCP intermediate tables are ephemeral** (expire after ~7 days) — copy to comparison tables immediately after each run completes
- **`clientName` in the payload must be a valid client name** even if the workflow does not use it
- **`ccp trigger` is known to sometimes fail on first attempt** — always retry once before escalating
- **Use `claude-analysis/` as the work directory** (not `cursor-analysis/`)
