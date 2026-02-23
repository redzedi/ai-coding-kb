---
title: "3P Common Filter View Performance & Architecture"
date: 2026-02-18
milestone: "BIPLATFORM-580 - Fix common_filter_view window partition"
tags: [databricks, performance, query-optimization, 3p, seller-cubes, common-filter, window-functions]
project: athena_brands-modulus-service
related_tickets: [BIPLATFORM-580]
---

# Journal: 3P Common Filter View - Performance, Architecture & Lessons

## CIQ BI Layer Architecture

The reporting data flow is:
```
UI Layer --> dashboard-service (V1: /entity/metrics/data, V2: /data) --> brands-service (/cube/execute, uses cubesdk for SQL gen) --> Databricks SQL Warehouse
```

- dashboard-service is the API gateway; it transforms UI requests and forwards to brands-service
- brands-service loads cube JSON definitions and uses cubesdk library to generate SQL
- The generated SQL runs on Databricks SQL Warehouses (sizes: X_SMALL to 4X_LARGE)

## Common Filter View - 1P vs 3P

The common filter is a mechanism to join a filter/dimension table with the cube's source table, enabling cross-cube dimension filtering (e.g., filter by brand, campaign name, custom dimensions).

### 1P (Amazon seller central / vendor central)
- Uses a **parameterized UDF**: `brands_cubes.common_filter_udf(#CLIENT_ID_PARAM)`
- cubesdk substitutes `#CLIENT_ID_PARAM` with the actual client_id at SQL generation time
- The UDF receives client_id as a parameter, guaranteeing filter pushdown

### 3P (Amazon 3P seller)
- Uses a **plain VIEW**: `seller_cubes.common_filter_view`
- No `#CLIENT_ID_PARAM` substitution; client_id is added as a WHERE clause
- Filter pushdown depends entirely on the Databricks optimizer

### Key code locations
- View selection: `BasicQueryGeneratorImpl.getCommonFilterQuery()` line 472-474
- Constants: `Constants.java` - `AMAZON_3P_COMMON_FILTER_CUBE_VIEW` (view) vs `COMMON_FILTER_CUBE_VIEW` (UDF)
- FROM clause template: `commonFromClause = "( SELECT %s FROM (%s) filter left join %s source ON %s)"`

## The seller_cubes.common_filter_view Structure

The view has 4 CTEs joined together:

1. **common_filter_fact_table** (alias `a`) - small dimension table (~5K rows per client)
2. **client_internal_catalog** (alias `b`) - custom dimensions (dimension1..dimension100), ~1K rows per client
3. **brands_common_filter_fact_table** (alias `c`) - 1P data for unified accounts
4. **campaigns_asin_workbench** (alias `d`) - campaign metadata CTE with FIRST_VALUE window functions

The final SELECT joins: `a LEFT JOIN b ON (asin, client_id) LEFT JOIN c ON (asin, client_id) LEFT JOIN d ON (asin, client_id)`

### Critical: Window functions in CTE `d` block filter pushdown

The `campaigns_asin_workbench` CTE uses:
```sql
FIRST_VALUE(portfolio_id) OVER (PARTITION BY campaign_id ORDER BY report_date DESC NULLS FIRST)
```

If `client_id` is NOT in the PARTITION BY, the optimizer CANNOT push `WHERE CLIENT_ID = X` below the window. This forces a full scan of the entire campaigns_asin_workbench table (4.3B rows across all clients).

### Fix: Add client_id to PARTITION BY
Adding `client_id` to `PARTITION BY client_id, campaign_id` enables pushdown. Verified on prod: 128s -> 16s, all spill eliminated.

## View Resolution Chain (Databricks catalogs)

- `client_catalog.seller_cubes.common_filter_view` - the actual view definition
- `client_view_catalog.seller_cubes.common_filter_view` - row-level security wrapper that adds `WHERE CLIENT_ID IN (SELECT ... FROM access_control_table)`

The `client_view_catalog` version is for production use (access-controlled). The `client_catalog` version is direct access. When investigating, always query `client_catalog` as `client_view_catalog` may return 0 rows depending on credentials.

## Bundle Request Processing

The brands-service request has `bundleCubeExecutionRequest` which is a map:
- Key: bundle group identifier (e.g., `ams_campaigns_asin_workbench_v2`) - NOT the cube name
- Value: a `CubeExecutionRequest` with its own `cubeName`, `metricsList`, `filterEntities`, `commonFilterEnabled`, etc.

Important: the `cubeName` inside the value is the actual cube JSON file name (e.g., `ams_campaigns_asin_workbench`), not the map key.

### Filter entities
- `filterEntities: ["asin", "asin", "campaign_id"]` means:
  - [0] = filter entity (column from common filter view for SELECT)
  - [1] = source entity (column from cube source table for JOIN ON)
  - [2] = additional join column (optional)
- These are pre-populated by the caller (dashboard-service), not always from cube's `defaultFilterEntityHook`

### commonFilterEnabled
- Can be set at top-level AND per-bundle
- Per-bundle `commonFilterEnabled: true` overrides top-level `false`
- The cube JSON's `enableCommonFilter` field can also be overridden by the request

## Databricks Query Profile Analysis Techniques

### Key nodes to look for in execution profiles
- **Scan nodes**: Check `SCAN_PARTITIONS` metadata for partition columns, `FILTERS` for pushed-down predicates
- **Window/Sort nodes**: Check for `Num uncompressed bytes spilled`, `Num bytes spilled to disk due to memory pressure`, `Peak memory usage`
- **Reused Exchange**: Databricks can share scan results across multiple consumers; look for `Reused Exchange` nodes

### Window function filter pushdown rule
Databricks (Spark) has a `PushPredicateThroughWindow` optimizer rule. A filter on column X can be pushed below a window function ONLY if X is in the PARTITION BY clause. If X is not in PARTITION BY, the filter must happen after the window completes.

### Row count discrepancy
The scan node row count may be much higher than the actual table row count (e.g., 4.3B scanned vs 354M logical rows). This is due to Delta Lake merge-on-read behavior, file version amplification, or deletion vectors.

## Schema Management (DDL Changes)

- Repo: `databricks-schema-management` (Bitbucket, commerceiq workspace)
- DDL files go in: `resources/db_migration/ESM/CLIENT_CATALOG/<SCHEMA_NAME>/`
- File naming: `YYYY_MM_DD__<action_description>.yaml`
- Format:
```yaml
DDLType: create_view
changeSets:
  - id: 1
    viewStatement:
      CREATE OR REPLACE VIEW ...
```
- Branch naming: use JIRA ticket ID (e.g., `BIPLATFORM-580-description`)
- Pipeline validates the branch via `validate_branch.sh` which calls a schema management API

## Lessons Learned

1. **Always verify data assumptions with actual queries before stating them as fact.** I initially stated "campaign_ids are unique per client" based on a query that returned 0 overlaps, but Suman confirmed from prod that overlaps exist. The query may have been against a different data snapshot or environment.

2. **Window function PARTITION BY is a common performance trap in multi-tenant views.** When a view is designed for multi-tenant access but its window functions don't include the tenant key in PARTITION BY, every query pays the cost of processing all tenants' data.

3. **The fix can be both a performance optimization AND a correctness fix.** Adding client_id to PARTITION BY not only enables filter pushdown but also prevents cross-tenant data leakage where shared campaign_ids could mix portfolio metadata.

4. **Cluster size masks inefficiency.** The same query took 18 min on X_SMALL and 128s on LARGE - the LARGE cluster just throws more parallelism at the same inefficient plan. The fix brought it to 16s on LARGE (and would be ~30s on X_SMALL).

5. **For JIRA updates via API v3**, pass markdown directly as a string for the description field. The Atlassian MCP tool handles the markdown-to-ADF conversion internally. Don't try to pass raw ADF objects or Jira wiki markup.
