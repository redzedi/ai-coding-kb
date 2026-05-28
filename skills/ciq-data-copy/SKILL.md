---
name: ciq-data-copy
description: >-
  Copy Databricks table data between CIQ environments (AWS_PROD→AWS_QA,
  AWS_PROD→AWS_BETA, etc.) using the Data Copy Tool V3 API. Given one or more
  tables with client/date/column filters, triggers an async copy, polls until
  completion, then runs SQL verification queries via Databricks MCP to confirm
  data arrived correctly in the target. Use when setting up representative test
  data in QA/BETA for CCP workflow development, ETL debugging, or end-to-end
  non-prod testing.
---

# CIQ Data Copy (V3)

## When to Use

Use this skill when Suman asks to:
- Seed QA or BETA with prod data for a specific client and date range
- Prepare test data for a CCP workflow end-to-end test
- Pull production table snapshots into non-prod environments for debugging
- Verify that a data copy completed correctly

Do NOT use for copies targeting `AWS_PROD` or `GCP_PROD` — those require admin privileges.

## Prerequisites

- Python 3.6+ available in the terminal (`python3 --version`)
- Script: `skills/ciq-data-copy/scripts/data_copy_v3.py`
- API base URL: `https://db-admin-tools.prod.commerceiq.ai`
- Auth: The service may be accessible over the internal network without a token.
  If you get HTTP 401/403, ask Suman for a bearer token and pass it via `--token`.
- MCP servers available:
  - **`dbx-prod`** — query source tables in AWS_PROD / GCP_PROD
  - **`dbx-dev`** — query target tables in AWS_QA / AWS_BETA / GCP_QA / GCP_BETA

## Allowed Copy Routes

| Source → Target | Notes |
|---|---|
| AWS_PROD → AWS_QA or AWS_BETA | Most common for test data setup |
| AWS_PROD → GCP_QA or GCP_BETA | Cross-cloud copies |
| AWS_QA → AWS_BETA | QA-to-BETA promotion |
| GCP_PROD → AWS_QA / AWS_BETA / GCP_QA / GCP_BETA | GCP source routes |

Copies **to** any PROD environment are admin-only and should not be attempted here.

## Phase 1: Build the Request Config

Create a JSON config that describes the copy. Save it to `cursor-analysis/` (gitignored).

```json
{
  "source_env": "AWS_PROD",
  "target_env": "AWS_QA",
  "requested_by": "suman.y@commerceiq.ai",
  "tables": [
    {
      "table_name": "client_catalog.aramus.alert_sales_decrease",
      "clients": ["1001", "1007"],
      "copy_mode": "OVERWRITE",
      "date_filter": {
        "param": "feed_date",
        "start_date": "2026-01-01",
        "end_date": "2026-05-01"
      },
      "column_filters": {
        "retailer": ["amazon"]
      },
      "excluded_columns": []
    }
  ]
}
```

**Field reference**

| Field | Required | Notes |
|---|---|---|
| `source_env` | Yes | `AWS_PROD`, `AWS_QA`, `AWS_BETA`, `GCP_PROD`, `GCP_QA`, `GCP_BETA` |
| `target_env` | Yes | Must differ from source; see allowed routes |
| `requested_by` | Yes | Defaults to `suman.y@commerceiq.ai` in the script |
| `tables[].table_name` | Yes | Fully-qualified: `catalog.schema.table` |
| `tables[].clients` | Yes for `client_catalog`; optional for `common_catalog` | List of client_id strings |
| `tables[].copy_mode` | Yes | `APPEND` — add rows without clearing target; `OVERWRITE` — truncate then insert (data loss risk!) |
| `tables[].date_filter` | Yes for `common_catalog`; optional for `client_catalog` | `{param, start_date, end_date}` |
| `tables[].column_filters` | No | `{"col": ["val1", "val2"]}` → `WHERE col IN (...)` |
| `tables[].excluded_columns` | No | Columns to skip during copy |

**Choosing `copy_mode`:**
- Use `APPEND` when adding new date ranges to existing target data.
- Use `OVERWRITE` only when you want a clean slate — it truncates the target partition first.
  For `client_catalog` tables partitioned by `client_id`, overwrite clears data for ALL copied clients.

## Phase 2: Trigger and Poll

Run the script. It triggers the copy and polls until completion (or timeout).

```bash
python3 skills/ciq-data-copy/scripts/data_copy_v3.py cursor-analysis/copy_request.json
```

**Common options:**

```bash
# Increase poll interval for large copies (minutes per table):
python3 skills/ciq-data-copy/scripts/data_copy_v3.py copy_request.json --poll-interval 60

# Extend timeout for very large tables (default: 2h):
python3 skills/ciq-data-copy/scripts/data_copy_v3.py copy_request.json --timeout 14400

# Trigger only — don't wait (returns request_id immediately):
python3 skills/ciq-data-copy/scripts/data_copy_v3.py copy_request.json --skip-poll

# Resume polling a previously triggered request:
python3 skills/ciq-data-copy/scripts/data_copy_v3.py --request-id 01960a3b-... copy_request.json

# With bearer token (if auth required):
python3 skills/ciq-data-copy/scripts/data_copy_v3.py copy_request.json --token <TOKEN>
```

**Terminal states:**

| Status | Exit code | Meaning |
|---|---|---|
| `COMPLETED` | 0 | All tables copied successfully |
| `PARTIALLY_COMPLETE` | 2 | Some tables succeeded, some failed |
| `FAILED` | 3 | All tables failed |

**Task-level statuses** (per-table `tasks[].status` in the status response):

| Status | Meaning |
|---|---|
| `SHARE_PENDING` | Delta Share propagation in progress (cross-env table access setup) |
| `IN_PROGRESS` | Databricks copy job running |
| `COMPLETED` | Table copied successfully |
| `FAILED` | Table copy failed — check `error_message` |

`SHARE_PENDING` is not documented in Confluence but appears in practice; it resolves automatically.

**Script output:** The script prints a JSON blob to stdout containing:
- `request_id`
- `final_status` (full API response with per-task detail)
- `verification_queries` (pre-built SQL for each table)
- `mcp_hint` (`{"source": "dbx-prod", "target": "dbx-dev"}`)

Progress logs go to stderr so they don't pollute the JSON output.

## Phase 3: Verify the Copy

After the script finishes, run the verification queries from `verification_queries` in the output.
The script also prints a human-readable guide to stderr showing which MCP to use.

**MCP selection:**
- Source queries (count check against prod) → `dbx-prod`
- Target queries (count, date range, sample) → `dbx-dev`

### 3a — Row count comparison

Run `source_count_sql` on `dbx-prod` and `target_count_sql` on `dbx-dev`.
The counts need not be identical (APPEND may accumulate duplicates; OVERWRITE should match exactly).
Acceptable for OVERWRITE: target count = source count ± 1%.
Flag any table where target is 0 or far below source.

### 3b — Date range check

Run `target_date_range_sql` on `dbx-dev`. Confirm:
- `min_date` ≥ requested `start_date`
- `max_date` ≤ requested `end_date`
- Neither is null (null means no rows landed)

### 3c — Sample spot check

Run `target_sample_sql` on `dbx-dev`. Confirm:
- Rows exist for the expected clients
- Key columns are non-null and look structurally correct
- No obviously wrong values (e.g., wrong client_id, future dates)

### 3d — Failed task investigation

If any task `status == "FAILED"`, check `error_message` in the output.
Common causes:
- Table does not exist in source or target catalog
- Client has no data in the requested date range (copy succeeds with 0 rows, not a failure)
- Warehouse capacity issue — retry the copy for the failed table only

## Phase 4: Report

Summarise findings to Suman:

```
Copy Summary
============
Request ID : 01960a3b-...
Status     : COMPLETED (2/2 tables)

Table: client_catalog.aramus.alert_sales_decrease
  Source rows  : 48,230  (AWS_PROD via dbx-prod)
  Target rows  : 48,230  (AWS_QA  via dbx-dev)   ✓ match
  Date range   : 2026-01-03 → 2026-04-30         ✓ within requested range
  Sample check : 5 rows, client_ids=[1001,1007], data looks correct ✓

...
```

If any table is FAILED or the row counts diverge significantly, surface the
`error_message` and recommend next steps (retry, check source data, contact DTP team).

## Curl Fallback (manual trigger without Python)

If the Python script is unavailable, remember the API has mixed casing
(top-level camelCase, tables-list snake_case):

```bash
# Trigger — use camelCase for the three top-level keys; keep everything inside tables[] as snake_case
curl -s -X POST https://db-admin-tools.prod.commerceiq.ai/v1/copy-data/trigger \
  -H 'Content-Type: application/json' \
  -d '{
    "sourceEnv": "AWS_PROD",
    "targetEnv": "AWS_BETA",
    "requestedBy": "suman.y@commerceiq.ai",
    "tables": [{
      "table_name": "client_catalog.aramus.alert_sales_decrease",
      "clients": ["1007"],
      "copy_mode": "APPEND",
      "date_filter": {"param": "feed_date", "start_date": "2026-01-01", "end_date": "2026-04-30"}
    }]
  }'

# Poll status (replace REQUEST_ID)
curl -s https://db-admin-tools.prod.commerceiq.ai/v1/copy-data/status/REQUEST_ID | jq .
```

## Key Gotchas

- **API uses camelCase keys, Confluence docs show snake_case**: The Confluence user guide
  shows `source_env`, `table_name`, `copy_mode`, etc. but the actual API expects
  `sourceEnv`, `tableName`, `copyMode`. The script handles this conversion automatically —
  always write config files in snake_case as shown in this skill.
- **`clients` field uses string IDs**, not integers: `["1001"]` not `[1001]`.
- **No duplicate table names** in a single request — split into separate requests if needed.
- **`common_catalog` tables require `date_filter`**; `client_catalog` tables require `clients`.
- **OVERWRITE truncates by client partition** — any existing data for those clients is gone,
  not just data in the requested date range. Double-check before using OVERWRITE on tables
  that are expensive to repopulate.
- **API is asynchronous** — HTTP 202 means accepted, not done. Always poll before assuming success.
- **0-row copies are not failures** — if source has no data for the client/date combo, the task
  will show `COMPLETED` with `estimated_row_count: 0`. Verify the source actually has data first.
- **`dbx-dev` accesses BETA catalog directly** — use for verifying data copied to AWS_BETA or AWS_QA.
  For GCP target environments, verification access may differ; check with Suman.
- **The old V1 API** (`data-copy-service.commerceiq.ai/data-copy/`) is still referenced in the
  `ciq_bi-platform_debug` skill. The V3 API at `db-admin-tools.prod.commerceiq.ai` is the
  current recommended path with richer filter options. Do not mix the two.

## Example: Full End-to-End Test Data Setup for a CCP Workflow

Given: "Set up test data for `alert_sales_decrease_wf` for client 1007, Jan–Apr 2026 in BETA"

1. Identify the output table: `client_catalog.aramus.alert_sales_decrease` (and any input tables the workflow reads)
2. Build `copy_request.json` for all needed tables with `source_env: AWS_PROD`, `target_env: AWS_BETA`
3. Run the script → wait for COMPLETED
4. Run verification queries via `dbx-dev` MCP
5. Report row counts and sample rows to Suman
6. Trigger the CCP workflow in BETA and observe output against the seeded data
