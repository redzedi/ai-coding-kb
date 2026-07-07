---
name: databricks-warehouse-cost-optimization
description: >-
  End-to-end cost optimization analysis for a Databricks Serverless SQL Warehouse.
  Given a warehouse_id, produces a prioritized report with query-level cost attribution,
  root cause analysis, right-sizing recommendations, and application-layer savings.
  Use when asked to analyze warehouse cost, optimize Databricks spend, investigate
  a cost spike, or right-size a warehouse.
---

# Databricks Serverless SQL Warehouse Cost Optimization

## When to Use

Use this skill when given a Databricks warehouse_id and asked to:
- Investigate a cost spike or high spend
- Produce a cost optimization report
- Right-size warehouse configuration
- Identify expensive query patterns and recommend fixes

## Prerequisites

- Target `warehouse_id`
- Analysis window (default: trailing full calendar month)
- MCP server: **`user-dbx-dev`** for all Databricks SQL queries (system catalog is synced from prod; `admin_catalog` for rates/discounts is accessible here)
- MCP tool: `execute_sql` (use `poll_sql_result` for async results)
- Bitbucket MCP server: **`user-bitbucket4`** with workspace `commerceiq` for code search
- Prod workspace IDs: `6609267921842809`, `1086031994956170`, `2986176579409100`, `3311307628646430`

## Report Output Template

Create the report as `cursor-analysis/warehouse_<id>_cost_optimization.md`. Use this structure:

```markdown
# Warehouse <id> Cost Optimization Report

## Executive Summary
## 1. Warehouse Profile & Configuration History
## 2. Monthly Cost Trend (Baseline)
## 3. Non-SQL Workload Cost
## 4. Query Cost Attribution by Category
## 5. Top Expensive Query Patterns -- Root Cause Analysis
## 6. Application-Layer Ownership (Bitbucket Search)
## 7. Right-Sizing Analysis (from right_size_databricks_warehouse skill)
## 8. Prioritized Optimization Recommendations
```

---

## Step 1: Warehouse Profile & Configuration History

Retrieve current config and change history:

```sql
SELECT warehouse_id, warehouse_name, warehouse_size, min_clusters, max_clusters,
       auto_stop_mins, change_time, changed_by
FROM system.compute.warehouses
WHERE warehouse_id = '<WAREHOUSE_ID>'
ORDER BY change_time DESC
```

Note whether auto-stop is enabled or disabled. If auto-stop is disabled (warehouse always-on), idle-time savings are NOT applicable -- skip auto-stop analysis.

Determine the floor DBU rate from the warehouse size:

| Size | DBU/hr per cluster |
|------|--------------------|
| X-Small | 5 |
| Small | 10 |
| Medium | 20 |
| Large | 40 |
| X-Large | 80 |
| 2X-Large | 160 |
| 3X-Large | 320 |

---

## Step 2: Monthly Cost Baseline

Get the billing trend for the past 2-3 months to establish baseline and detect spikes:

```sql
SELECT DATE_TRUNC('month', usage_start_time) as month,
       ROUND(SUM(usage_quantity), 2) as total_dbus,
       ROUND(SUM(usage_quantity) * 0.399, 2) as est_cost_list_price
FROM system.billing.usage
WHERE usage_metadata.warehouse_id = '<WAREHOUSE_ID>'
  AND usage_start_time >= '2026-01-01'
GROUP BY 1 ORDER BY 1
```

If the warehouse was recently created, normalize to daily rates for fair comparison. A "14x spike" might just be 3 operational days vs a full month.

---

## Step 3: Non-SQL Workload Cost

Evaluate if the warehouse (or the same application) has significant non-SQL cost:

```sql
SELECT billing_origin_product, DATE_TRUNC('month', usage_start_time) as month,
       ROUND(SUM(usage_quantity), 2) as dbus,
       ROUND(SUM(usage_quantity) * 0.399, 2) as est_cost
FROM system.billing.usage
WHERE workspace_id IN (6609267921842809, 1086031994956170, 2986176579409100, 3311307628646430)
  AND usage_start_time >= '2026-01-01'
  AND (usage_metadata.warehouse_id = '<WAREHOUSE_ID>'
       OR custom_tags.application = '<APP_TAG_IF_KNOWN>')
GROUP BY 1, 2 ORDER BY 2, 1
```

If `billing_origin_product` shows JOBS alongside SQL, note the split. The JOBS cost may warrant a separate investigation.

---

## Step 4: Query Cost Attribution by Category

This is the core analysis. Use the **weighted cost attribution model** to attribute the warehouse's billed DBU cost to individual queries.

### 4a: Identify Query Patterns

First, get a sample of distinct query prefixes to define categories:

```sql
SELECT LEFT(statement_text, 200) as query_prefix, COUNT(*) as cnt,
       ROUND(SUM(total_duration_ms)/1000/3600, 2) as total_hours
FROM system.query.history
WHERE compute.warehouse_id = '<WAREHOUSE_ID>'
  AND start_time >= '<START_DATE>' AND start_time < '<END_DATE>'
GROUP BY 1 ORDER BY total_hours DESC LIMIT 30
```

From this, build a CASE statement mapping `statement_text` patterns to human-readable category names. Example:

```sql
CASE
  WHEN statement_text LIKE '%SUM(number) AS answer%' THEN 'health_check'
  WHEN statement_text LIKE '%retailersWithBadGathers%' THEN 'retailers_bad_gathers'
  WHEN statement_text LIKE '%client_products%retailer%' THEN 'product_basics'
  -- add more based on observed patterns
  ELSE 'other'
END as query_category
```

### 4b: Attributed Cost per Category

**CRITICAL**: The denominator subquery `s` must sum durations across ALL queries on the warehouse per hour, NOT just the category being analyzed. Scoping the denominator to a subset inflates that subset's cost (can exceed the total warehouse bill).

```sql
SELECT query_category,
       ROUND(SUM(cost_per_query), 2) as total_cost_usd,
       COUNT(*) as query_count,
       ROUND(AVG(cost_per_query), 6) as avg_cost_per_query
FROM (
  SELECT
    <CATEGORY_CASE_STATEMENT> as query_category,
    (
      u.usage_quantity * (
        h.total_task_duration_ms * 0.8 / NULLIF(s.a, 0)
        + h.execution_duration_ms * 0.15 / NULLIF(s.b, 0)
        + h.compilation_duration_ms * 0.05 / NULLIF(s.c, 0)
      )
    ) * lp.pricing.default AS cost_per_query
  FROM system.query.history h
  JOIN system.billing.usage u
    ON u.usage_metadata.warehouse_id = h.compute.warehouse_id
    AND h.start_time BETWEEN u.usage_start_time AND u.usage_end_time
    AND u.workspace_id = h.workspace_id
  JOIN system.billing.list_prices lp
    ON u.cloud = lp.cloud AND u.sku_name = lp.sku_name
    AND u.usage_start_time >= lp.price_start_time
    AND (u.usage_end_time <= lp.price_end_time OR lp.price_end_time IS NULL)
  JOIN (
    -- DENOMINATOR: ALL queries on warehouse per hour (NOT filtered by category)
    SELECT SUM(total_task_duration_ms) a, SUM(execution_duration_ms) b,
           SUM(compilation_duration_ms) c, compute.warehouse_id,
           DATE_TRUNC('hour', start_time) start_hour
    FROM system.query.history
    WHERE compute.warehouse_id = '<WAREHOUSE_ID>'
      AND date(start_time) BETWEEN '<START_DATE>' AND '<END_DATE>'
    GROUP BY compute.warehouse_id, DATE_TRUNC('hour', start_time)
  ) s ON s.warehouse_id = h.compute.warehouse_id
    AND s.start_hour = DATE_TRUNC('hour', h.start_time)
  WHERE h.compute.warehouse_id = '<WAREHOUSE_ID>'
    AND date(h.start_time) BETWEEN '<START_DATE>' AND '<END_DATE>'
) t
GROUP BY query_category
ORDER BY total_cost_usd DESC
```

**Weight interpretation**: 80% task (parallel compute), 15% execution (wall-clock occupancy), 5% compilation. The sum of all categories will exceed the billed total due to billing-boundary overlap; use **relative proportions** for prioritization.

---

## Step 5: Root Cause Analysis of Top Query Patterns

For each of the top 3-5 categories by attributed cost:

### 5a: Runtime Metrics Summary

```sql
SELECT COUNT(*) as query_count,
       ROUND(AVG(total_duration_ms/1000.0), 2) as avg_total_secs,
       ROUND(AVG(execution_duration_ms/1000.0), 2) as avg_exec_secs,
       ROUND(AVG(read_bytes/1024/1024/1024.0), 2) as avg_read_gb,
       ROUND(AVG(CASE WHEN execution_duration_ms > 0 THEN total_task_duration_ms*1.0/execution_duration_ms END), 2) as avg_parallelization_factor,
       ROUND(SUM(CASE WHEN spilled_local_bytes > 0 THEN 1 ELSE 0 END)*100.0/COUNT(*), 2) as pct_spilling,
       ROUND(AVG(CASE WHEN spilled_local_bytes > 0 THEN spilled_local_bytes/1024/1024/1024.0 END), 2) as avg_spill_gb
FROM system.query.history
WHERE compute.warehouse_id = '<WAREHOUSE_ID>'
  AND start_time >= '<START_DATE>' AND start_time < '<END_DATE>'
  AND <CATEGORY_FILTER>
```

### 5b: Extreme Examples (include statement_id)

Always include `statement_id` for the most extreme examples so Suman can pull query profiles:

```sql
SELECT statement_id, start_time,
       ROUND(total_duration_ms/1000.0, 2) as total_secs,
       ROUND(execution_duration_ms/1000.0, 2) as exec_secs,
       ROUND(read_bytes/1024/1024/1024.0, 2) as read_gb,
       ROUND(total_task_duration_ms*1.0/NULLIF(execution_duration_ms,0), 2) as parallelization_factor,
       ROUND(spilled_local_bytes/1024/1024/1024.0, 2) as spill_gb
FROM system.query.history
WHERE compute.warehouse_id = '<WAREHOUSE_ID>'
  AND start_time >= '<START_DATE>' AND start_time < '<END_DATE>'
  AND <CATEGORY_FILTER>
ORDER BY total_task_duration_ms DESC
LIMIT 5
```

### 5c: Parallelization Factor Interpretation

PF = `total_task_duration_ms / execution_duration_ms`. **PF of 10 ≈ 1 worker node.**

| Size | Workers | PF Capacity |
|------|---------|-------------|
| Medium | 8 | ~80 |
| Large | 16 | ~160 |
| X-Large | 32 | ~320 |

If a query has PF > the cluster's capacity, it is fully utilizing the cluster and would benefit from a larger size (or query optimization to reduce parallelism needs).

### 5d: Ask Suman for Query Profiles

After identifying the top optimizable queries, tell Suman:

> "I've identified the top N most expensive query patterns. For deeper optimization, I need query profiles for these statement_ids: [list]. You can get these from the Databricks SQL UI > Query History > click on the query > Profile tab. Please share the profile JSON."

Then use the `databricks-query-profile-analysis` skill to analyze the profiles.

---

## Step 6: Application-Layer Ownership (Bitbucket Search)

For each top query category, search Bitbucket to find which service/repo generates these queries:

```
MCP server: user-bitbucket4
Tool: search_code
Args: { "query": "<distinctive_keyword_from_sql>", "workspace": "commerceiq" }
```

Search for distinctive fragments from the SQL: table names, CTE names, SQL file names (e.g., `retailersWithBadGathers`, `availabilityByRetailer.sql`), or column patterns.

Also identify the service principal and client application:

```sql
SELECT executed_as, client_application, COUNT(*) as cnt
FROM system.query.history
WHERE compute.warehouse_id = '<WAREHOUSE_ID>'
  AND start_time >= '<START_DATE>' AND start_time < '<END_DATE>'
GROUP BY 1, 2 ORDER BY cnt DESC LIMIT 10
```

Do first-level analysis only. Ask Suman if he wants to go deeper on any specific query's codebase origin.

---

## Step 7: Right-Sizing Analysis

Read and follow the `right_size_databricks_warehouse` skill (at `~/ai-coding-kb/skills/right_size_databricks_warehouse/SKILL.md`) to produce:

1. Workload profiling (online vs offline)
2. Concurrency distribution
3. Auto-stop savings projection (skip if auto-stop is disabled)
4. min_clusters savings projection
5. max_clusters cap recommendation
6. T-shirt size evaluation using parallelization factor analysis

### T-Shirt Sizing via PF Distribution

```sql
SELECT
  CASE
    WHEN total_task_duration_ms*1.0/execution_duration_ms < 80 THEN 'fits_medium'
    WHEN total_task_duration_ms*1.0/execution_duration_ms < 160 THEN 'needs_large'
    ELSE 'needs_xlarge'
  END as size_bucket,
  COUNT(*) as query_count,
  ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (), 2) as pct_of_queries,
  ROUND(SUM(total_task_duration_ms)/1000.0/3600, 2) as total_task_hours
FROM system.query.history
WHERE compute.warehouse_id = '<WAREHOUSE_ID>'
  AND start_time >= '<START_DATE>' AND start_time < '<END_DATE>'
  AND statement_type = 'SELECT' AND execution_duration_ms > 500
GROUP BY 1 ORDER BY 1
```

Key decision framework:
- If >95% of queries fit in a smaller size AND the overflowing queries are not latency-sensitive --> downsizing is viable
- If the overflowing queries carry >30% of total task hours --> downsizing will cause cascading slowdowns (longer queries = more concurrency = more clusters)
- Always check spill data for memory-bound constraints separately from PF

---

## Step 8: Prioritized Recommendations

Build a summary table with:

| # | Recommendation | March Attributed Cost | Mechanism | Est. Savings $/month | Effort |
|---|---|---|---|---|---|
| 1 | ... | $X,XXX | ... | ... | Low/Medium/High |

Include the previous month's attributed cost as a baseline column. Prioritize by estimated savings descending. Group into tiers:
- **Tier 1: Quick Wins** (config changes, cache additions)
- **Tier 2: Query Optimization** (SQL changes, materialized views)
- **Tier 3: Infrastructure** (warehouse sizing, splitting workloads)


---

## Important Gotchas

1. **Cost attribution denominator**: ALWAYS scope the denominator (`s` subquery) to ALL queries on the warehouse per hour. Scoping to a subset inflates that subset's cost beyond the total warehouse bill.

2. **Auto-stop disabled warehouses**: If auto-stop is disabled, the warehouse is always-on. Health-check/warm-keeping cost analysis is irrelevant. Floor cost = `hours_in_month × DBU_per_hour × $0.399`. Focus on query optimization and max_clusters capping.

3. **Column name differences across system tables**:
   - `system.billing.usage`: warehouse_id is at `usage_metadata.warehouse_id`
   - `system.query.history`: warehouse_id is at `compute.warehouse_id`
   - `system.compute.warehouses`: size column is `warehouse_size` (not `cluster_size`)
   - `system.query.history`: use `statement_id` (not `query_id`)



5. **New warehouse "spike" framing**: Always normalize to daily rates when a warehouse was created mid-period. A 14x month-over-month increase might just be 3 days vs 31 days.

6. **dbt vs application workloads**: Check `client_application` to distinguish. dbt pipelines (`PyDatabricksSqlConnector`) have different optimization patterns (incremental models, OPTIMIZE tuning) vs application queries (`Databricks SQL Driver for Node.js`).

7. **Failed query waste**: Always check for failed/canceled queries -- they still consume compute:
   ```sql
   SELECT status, COUNT(*), ROUND(SUM(total_task_duration_ms)/1000/3600, 2) as wasted_hours
   FROM system.query.history
   WHERE compute.warehouse_id = '<WAREHOUSE_ID>'
     AND start_time >= '<START_DATE>' AND start_time < '<END_DATE>'
     AND status != 'FINISHED'
   GROUP BY 1
   ```

--

## Guidelines

- **Parallelization Factor (PF) 10 ≈ 1 Databricks worker node**: PF < 80 → Medium (8 workers); PF 80–160 → Large; PF > 160 → X-Large.
- **max_clusters cap**: `max_clusters=40` on always-on warehouse = worst case 40 × 40 DBU/hr = 1,600 DBU/hr ($638/hr). Cap at 5–8 for Large. Saves $1K–3K/month with no functional impact.
- **X-Large → Large downsize**: $10K–12K/month savings, zero code change. Medium sizing blocked until high-PF queries are optimized first.
- **5.8% of queries can carry 56% of compute work**: Optimize the heaviest queries before downsizing cluster — wrong order causes P95 regression 1.3–2x.
- **`total_task_duration_ms / execution_duration_ms < 2`** is an effective heuristic for detecting queries that don't benefit from distributed compute — good candidates for RDS/cache offload.
