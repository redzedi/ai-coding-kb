---
name: databricks-query-profile-analysis
description: Interpret Databricks SQL Warehouse execution profiles to find bottlenecks (scans, window spill, filter pushdown). Use when analyzing slow Databricks queries, query-profile JSON, execution plans, or optimizing BI/cubesdk-generated SQL.
---

# Databricks Query Profile Analysis

## When to use

Use this skill when you have a Databricks query execution profile (JSON) and need to identify why a query is slow, spilling to disk, or scanning too many rows.

## Key nodes in execution profiles

- **Scan nodes**: In metadata, check `SCAN_PARTITIONS` for partition columns and `FILTERS` for pushed-down predicates. If filters are missing, the optimizer did not push predicates below the scan.
- **Window / Sort nodes**: Check `Num uncompressed bytes spilled`, `Num bytes spilled to disk due to memory pressure`, and `Peak memory usage`. High spill or peak memory indicates the window is processing too much data before any filter.
- **Reused Exchange**: Indicates Databricks is reusing scan results across consumers; useful for understanding plan shape.

## Window functions and filter pushdown

Databricks (Spark) uses a `PushPredicateThroughWindow` rule. A filter on column X can be pushed **below** a window only if X appears in the window’s **PARTITION BY**. If X is not in PARTITION BY, the filter is applied **after** the window, so the window sees the full input.

**Implication:** In multi-tenant views, window functions must include the tenant key (e.g. `client_id`) in PARTITION BY so that `WHERE client_id = ?` can be pushed down and the window runs per-tenant instead of over all data.

## Row count interpretation

Scan node row counts can be much higher than the table’s logical row count (e.g. 4.3B scanned vs 354M logical) due to Delta Lake merge-on-read, file version amplification, or deletion vectors. Use scan metrics and spill to judge cost, not only logical rows.

## Workflow

1. Open the query profile JSON and locate the main scan and window/sort nodes.
2. For scans: confirm which filters (if any) appear in node metadata.
3. For windows: check spill and peak memory; if high, check whether tenant/filter columns are in PARTITION BY in the SQL.
4. Propose fixes (e.g. add tenant key to PARTITION BY, or use a parameterized UDF so the engine can push filters).