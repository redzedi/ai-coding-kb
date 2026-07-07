---
name: dbx-dev-vs-prod-env
description: Use dbx-prod MCP server for real workflow/cost/data analysis; dbx-dev is a local testing env only
metadata:
  type: feedback
---

`dbx-dev` MCP server is a **local testing environment**, not a mirror of production data catalogs. It does sync/mirror `system.*` tables (billing, lakeflow job history, compute) from prod, which is why cost/job-run analysis against `system.billing.usage`, `system.lakeflow.job_run_timeline`, `system.compute.node_timeline` etc. worked fine there — but actual client data catalogs (e.g. `client_catalog`, `ciq_prod_client_catalog`) are NOT the real prod data; querying real tables (e.g. `DESCRIBE HISTORY` on an actual CCP output Delta table) must be done against **dbx-prod**, not dbx-dev.

**Why:** Suman corrected me mid-investigation (automation_resolve_wf cost spike analysis) after I tried to inspect `client_catalog.temp.automation_resolve` on dbx-dev and found it empty/missing — the real fix was to just use dbx-prod, which I have access to.

**How to apply:** For any CCP workflow cost/incident investigation: use `dbx-dev` for system-table queries only if dbx-prod is unavailable or as a quick sanity check; default to **dbx-prod** for anything involving real client data tables, `DESCRIBE HISTORY`, actual table contents, or when in doubt. See [[automation-resolve-wf-cost-incident]] and the `databricks-workflow-cost-optimization` skill.
