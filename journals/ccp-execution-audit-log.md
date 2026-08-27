---
name: ccp-execution-audit-log
description: CCP per-execution audit trail location (RDS Postgres, ccp-prod-metadata-db MCP server) — client/workflow/status/error history
metadata:
  type: reference
---

CCP's per-execution audit trail (one row per workflow invocation, with client, status, timing, and error message) lives in **RDS Postgres**, schema `ccp_execute_schema`, table `ccp_execution_request` — accessed via the `mcp__ccp-prod-metadata-db` MCP server (`execute_sql` tool). This is NOT in Databricks/Unity Catalog — don't waste time searching `dbx-prod`/`dbx-dev` catalogs for it.

Key columns: `execution_id, created_at, started_at, ended_at, execution_status, client_name, execution_entity_info` (jsonb: `name`=workflow name, `branch`, `project`), `execution_variables` (jsonb array of `{name, value}`, e.g. `client_id`, `child_client_id`, `automation`), `errors` (free text).

Other tables in that schema worth knowing about: `ccp_config`, `ccp_tasks`, `ccp_error_list`, `databricks_job_metadata`, `dynamic_queue_metadata`, `feature_flag`, `stuck_flows` (+ several dated backup/temp variants — check `flyway_schema_history` for schema evolution).

Example query — all executions of a workflow for a given client in a date range:
```sql
SELECT execution_id, created_at, started_at, ended_at, execution_status, execution_variables, errors
FROM ccp_execute_schema.ccp_execution_request
WHERE client_name = 'newell'
  AND execution_entity_info->>'name' = 'automation_resolve_wf'
  AND created_at >= '2026-05-13' AND created_at < '2026-06-23'
ORDER BY created_at
```

**Why this matters:** Databricks system tables (`system.lakeflow.job_run_timeline` etc.) do NOT carry job parameters like `client_id` — you cannot attribute a Databricks run to a specific CCP client/automation from system tables alone. This Postgres execution log is the only way to do per-client/per-automation root-cause analysis on CCP workflow failures. See [[automation-resolve-wf-cost-incident]]-style investigations (now tracked per-repo, not in global memory) for a worked example.
