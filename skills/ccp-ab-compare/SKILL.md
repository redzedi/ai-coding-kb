---
name: ccp-ab-compare
description: >-
  A/B comparison of CCP workflow outputs between a feature branch (treatment)
  and master branch (control). Validates functional equivalence via
  bidirectional EXCEPT queries, computes runtime and DBU cost deltas, and
  coordinates query profile analysis with Suman. Use after both feature and
  control beta test runs have completed successfully.
---

# CCP A/B Comparison Skill

## When to Use

- After `/ccp-beta-test` completes both feature and control runs
- When @analyst or the uber orchestrator needs to validate a cost optimization change
- Do NOT use before both runs have terminal COMPLETED status

## Prerequisites

- MCP server: `dbx-dev` (access to beta catalog where comparison tables live)
- Both feature and control output tables exist in `client_view_catalog.temp_<client_id>`
- The beta test report from `/ccp-beta-test` with execution IDs, table locations, and runtimes
- The original cost optimization analysis doc (for expected gain benchmarks)
- The `/databricks-query-profile-analysis` skill (for query profile analysis if profiles are provided)

---

## Phase 1: Functional Equivalence Check

For each output table in the workflow, run both directions via `dbx-dev` MCP:

```sql
-- Feature rows not in Control
SELECT * FROM client_view_catalog.temp_<client_id>.feature_<track_id>_<table>
EXCEPT
SELECT * FROM client_view_catalog.temp_<client_id>.control_<track_id>_<table>;

-- Control rows not in Feature
SELECT * FROM client_view_catalog.temp_<client_id>.control_<track_id>_<table>
EXCEPT
SELECT * FROM client_view_catalog.temp_<client_id>.feature_<track_id>_<table>;
```

**Interpreting results:**

- Both EXCEPT queries return 0 rows → **PASS** — functional equivalence confirmed
- Rows appear in one direction only → **INVESTIGATE** — the change altered output data
  - Check if differences are in non-deterministic columns (e.g., `ROW_NUMBER()` without tie-breakers)
  - If differences are only in ordering or tie-breaking: **CONDITIONAL PASS** — document which columns differ
  - If differences are in business-critical columns (metrics, IDs, dates): **FAIL** — the optimization changed behavior

Document results per table in the comparison report.

---

## Phase 2: Aggregate Checksum Validation

For additional confidence, run aggregate checks:

```sql
-- Row count comparison
SELECT 'feature' AS source, COUNT(*) AS row_count
FROM client_view_catalog.temp_<client_id>.feature_<track_id>_<table>
UNION ALL
SELECT 'control' AS source, COUNT(*) AS row_count
FROM client_view_catalog.temp_<client_id>.control_<track_id>_<table>;

-- Key metric sums (adapt columns to the specific table)
SELECT 'feature' AS source,
  COUNT(DISTINCT client_id) AS distinct_clients,
  SUM(CAST(some_metric AS DOUBLE)) AS metric_sum
FROM client_view_catalog.temp_<client_id>.feature_<track_id>_<table>
UNION ALL
SELECT 'control' AS source,
  COUNT(DISTINCT client_id) AS distinct_clients,
  SUM(CAST(some_metric AS DOUBLE)) AS metric_sum
FROM client_view_catalog.temp_<client_id>.control_<track_id>_<table>;
```

Identify key metric columns from the workflow's output table schema. Flag any numeric column where the sum differs by more than 0.01%.

---

## Phase 3: Runtime and Cost Delta

Calculate from the beta test report data:

```markdown
| Metric               | Feature Run | Control Run | Delta      | Delta % |
|---|---|---|---|---|
| Wall-clock duration  | X min       | Y min       | (Y-X) min  | Z%      |
| Estimated DBU cost   | $A          | $B          | $(B-A)     | Z%      |
```

Compare the observed delta against the **expected gain** from the original cost optimization recommendation:

- If observed gain is within ±25% of expected → **ALIGNED** — hypothesis validated
- If observed gain is significantly less than expected (>25% below) → **PARTIALLY VALIDATED** — hypothesis may be partially wrong; document which assumptions didn't hold
- If observed gain is significantly more than expected (>25% above) → **INVESTIGATE** — may indicate a different code path was exercised, or a compounding effect; document for Suman's review
- If feature run is **slower** than control → **REGRESSION** — the change made things worse; flag immediately

---

## Phase 4: Performance Deep-Dive

This step requires Suman's manual intervention to fetch data from the Databricks Spark UI and job logs.

Use `AskUserQuestion` to request three things:

```
"Both beta test runs have completed. To analyze the performance differences, I need three things from each run:

1. **Module-level latency summary** — from the job logs, the printed summary showing each module's execution time.
   (Look in the Databricks job run → Spark UI → Driver Logs, or the CCP execution logs. It typically shows lines like:
   `Module <name> completed in <X>s` or a summary table at the end of the run.)

   Feature run: execution_id <feature_id>
   Control run: execution_id <control_id>

2. **A sample temp table name from the logs** (SQL workflows only) — during each run, CCP creates
   intermediate temp tables with a dynamic prefix (e.g., `e12345__module_name`). Knowing this prefix
   lets me query intermediate module outputs for functional equivalence checks and performance
   investigation on modules beyond the final output tables.

   Please grab any one temp table name from the logs for each run, e.g.:
   Feature run: `e<xxxxx>__<any_module_name>`
   Control run: `e<yyyyy>__<any_module_name>`

   (I only need the prefix — I can derive the rest from the workflow DAG.)

3. **Query profiles** — for specific modules I want to investigate deeper.
   Based on the runtime delta and the recommendation, I'm most interested in these modules:
   <list the modules that were changed or are expected to show improvement>

   For each module above, please fetch the query profile JSON from:
   Databricks Job Run → Spark UI → SQL tab → click the query → download the profile JSON.

   Feature run profiles needed: <module_1>, <module_2>, ...
   Control run profiles needed: same modules

Would you like to provide these now, or skip this step?"
```

### Processing Temp Table Prefixes (SQL Workflows)

If temp table prefixes are provided:
1. Extract the execution prefix (e.g., `e12345` from `e12345__competition_look_back`)
2. Record in the track state:
   - Feature prefix: `e<feature_exec_prefix>`
   - Control prefix: `e<control_exec_prefix>`
3. Intermediate tables live in `client_view_catalog.temp_ccp_<client_id>` with naming pattern `<prefix>__<module_name>`
4. Use these to:
   - Run EXCEPT comparisons on **intermediate** module outputs (not just final output tables) when investigating unexpected differences
   - Query specific module outputs to understand where in the DAG a performance gain or data divergence originates
   - Verify that shared modules (used by other workflows) produce identical output
5. Note: these temp tables are ephemeral (~7 days) — query them promptly

### Processing Module-Level Latency Summary

If the module latency summary is provided:
1. Parse the per-module execution times for both feature and control runs
2. Build a comparison table:
   ```markdown
   | Module | Control (s) | Feature (s) | Delta (s) | Delta % |
   |---|---|---|---|---|
   | module_a | 120 | 45 | -75 | -62% |
   | module_b | 30 | 30 | 0 | 0% |
   | ... | ... | ... | ... | ... |
   | **Total** | **150** | **75** | **-75** | **-50%** |
   ```
3. Identify which modules account for the observed runtime improvement
4. Flag any modules that got **slower** — these may indicate regressions in shared modules
5. Use this to decide which module query profiles to request if not already provided

### Processing Query Profiles

If query profiles are provided:
1. Save them to `claude-analysis/<jira-id>/tracks/<track-id>/query-profiles/`
2. Invoke `/databricks-query-profile-analysis` on each profile
3. Compare the analysis results between feature and control for the same module:
   - Scan reduction (fewer table scans, smaller scan sizes)
   - Shuffle reduction (less data movement)
   - Spill elimination (no disk spill in feature vs spill in control)
   - Stage elimination (fewer execution stages)
4. Document specific physical plan improvements per module

### If Both Are Skipped

Note in the report that performance deep-dive was deferred. The runtime delta from Phase 3 still provides a top-level signal.

---

## Phase 5: Comparison Report

Generate `claude-analysis/<jira-id>/tracks/<track-id>/comparison-report.md`:

```markdown
# A/B Comparison Report — Track <track-id>

## Summary
- Recommendation: <description>
- Functional Equivalence: PASS / CONDITIONAL PASS / FAIL
- Performance Delta: X% faster (Y min saved)
- Hypothesis Validation: ALIGNED / PARTIALLY VALIDATED / REGRESSION

## Functional Equivalence Detail
| Output Table | EXCEPT (F-C) | EXCEPT (C-F) | Verdict |
|---|---|---|---|
| <table_1>    | 0 rows       | 0 rows       | PASS    |
| <table_2>    | 3 rows       | 0 rows       | CONDITIONAL PASS (tie-breaker ordering) |

## Aggregate Checksums
| Table     | Metric       | Feature    | Control    | Match |
|---|---|---|---|---|
| <table_1> | row_count    | 48230      | 48230      | YES   |
| <table_1> | revenue_sum  | 1234567.89 | 1234567.89 | YES   |

## Runtime Comparison
| Metric            | Feature | Control | Delta  | Delta % |
|---|---|---|---|---|
| Duration          | 12 min  | 18 min  | -6 min | -33%    |
| Est. DBU cost     | $2.10   | $3.15   | -$1.05 | -33%    |

Expected gain from recommendation: -35%
Observed gain: -33%
Assessment: ALIGNED (within ±25% threshold)

## Query Profile Analysis
[If profiles provided: detailed physical plan comparison]
[If skipped: "Profile analysis deferred — profiles not yet provided"]

## Verdict
[PROCEED / NEEDS_INVESTIGATION / FAIL]
- If PROCEED: Ready for PR and documentation
- If NEEDS_INVESTIGATION: [describe what needs further review]
- If FAIL: [describe the failure and recommended action]
```

---

## Key Gotchas

- EXCEPT queries can be slow on large tables — consider adding `LIMIT 100` to catch obvious differences without a full table scan
- Non-deterministic window functions (`ROW_NUMBER` without full tie-breaking) will cause false-positive EXCEPT differences — always investigate before declaring FAIL
- Table names must be **lowercase** for Unity Catalog
- The comparison tables in `temp_<client_id>` are ephemeral — run the comparison soon after the beta test
- Use `claude-analysis/` as the work directory (not `cursor-analysis/`)
