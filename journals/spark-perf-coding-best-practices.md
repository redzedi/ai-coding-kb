## Databricks/Spark (Pyspark / Dbx SQL / java) Coding Best Practices for Perf


### General Guidelines


-
- **Arrow serialization OOM**: `toPandas()` with Arrow optimization can OOM even when JVM heap graphs show low utilization. Root cause: `ByteArrayOutputStream.toByteArray()` creates a transient copy, doubling memory for the duration of the copy. A 2 GB Arrow batch needs 4 GB transiently. Heap monitoring captures steady-state, not instantaneous spikes. Spark falls back to non-Arrow `toPandas()` after retries, but this is slower.


- **Wasted Ephemeral Compute / Multi-Client Airflow Loops**: Watch out for DAG loops that trigger a Databricks job for all clients (e.g. via `getE2EActiveClients()`). If parent-child collapsing (via views like `AVC_CLIENT_PARENT_CHILD_MAPPING`) merges children under a parent client ID, or if certain clients have no data, this spawns hundreds of dedicated ephemeral clusters daily that do nothing but query empty views. Always audit the row volume in source tables (e.g., `catalog_listing_view`) across client IDs to quantify and eliminate empty runs via lightweight Airflow-level preflight queries or whitelists.



### UNION & deduplication

- **Bare `UNION` in Spark SQL forces full global hash shuffle**: Even for mutually exclusive datasets (SP/SB/SD, keywords/targets), `UNION` triggers 200-partition expansion + autoscaler scale-out. Always use `UNION ALL` when datasets cannot have duplicates by definition. Also applies inside subqueries feeding downstream joins (common in dimension builds). Verified: 50–70% runtime reduction; prevents disk spill on large tenants.
- **`UNION` before `ROW_NUMBER()` is redundant dedup**: If a downstream window already deduplicates (`ROW_NUMBER() ... WHERE rn = 1`), the upstream bare `UNION` shuffle is wasted. Use `UNION ALL` and let the window handle dedup in one pass.

### CTEs, scans & history-table patterns

- **CTEs are inlined — repeated references = repeated physical scans**: Spark Catalyst inlines CTE definitions. Referencing the same CTE (or base table across multiple CTE branches) compiles to independent Parquet scans. Mitigations: (1) one-pass window refactor, (2) `spark.sql.optimizer.cte.materialization.threshold=2` to auto-materialize CTEs referenced 2+ times, (3) lazy temp views at orchestration level (see below).
- **Self-join CTE pattern causes double full scan**: `WITH max_dates AS (SELECT MAX(...))` + join back = two independent scans. Fix: `MAX(...) OVER (PARTITION BY ...)`.
- **Double-scan self-join on history tables**: Replace `MAX(feed_date)` subquery + rejoin with `ROW_NUMBER() OVER (PARTITION BY keys ORDER BY feed_date DESC) WHERE rn=1` — compresses I/O by ~50% on tables like `search_data_archive` (9.6 TB). Also: if upstream already deduped via `ROW_NUMBER() WHERE rn=1`, downstream `MAX(scrape_date)` self-joins are redundant.
- **One-pass window pattern for multi-step history logic**: Collapse 3–4 separate CTE scans of the same table into one scan using `ROW_NUMBER()` (latest state), `LAG()` (bid-change detection), and `MAX(CASE WHEN ...)` (run-start date) in a linear pipeline. Verified: 11 scans → 5 (theoretical minimum) on `keywords_performance_metric_data`; 103 min → 42 min.
- **Branching CTE references defeat scan reduction**: Even after window refactoring, if CTE `A` is referenced by both `B` and `C`, Catalyst inlines and duplicates the scan. Fix: **linear chain** — each CTE referenced exactly once (`A → B → C → D`). No branching.
- **`FIRST_VALUE` for state inheritance in single scan**: Instead of a separate scan to find active/latest state, use `FIRST_VALUE(state) OVER (PARTITION BY keys ORDER BY report_date DESC)` on every history row, then filter inline. Avoids a second scan for active-record isolation.
- **In-memory metric conditioning eliminates re-join**: When metrics (e.g. clicks) live in the same table as history, carry metric columns through the linear window pipeline and aggregate with `SUM(CASE WHEN report_date >= bid_change_date THEN clicks ELSE 0 END)`. Eliminates the expensive final left-join back to the raw metrics table (often the 3rd–4th physical scan).
- **Inner join on active IDs acts as a filter**: Inner joining history to an active-keyword CTE limits processing to currently active entities only — significant win on archived-heavy tables.

### Window functions

- **Window functions block filter pushdown**: If `client_id` is NOT in `PARTITION BY`, Databricks cannot push `WHERE client_id = X` below the window — forces full table scan. Fix: add tenant key to PARTITION BY. Verified: 128s → 16s, all spill eliminated.
- **Align `PARTITION BY` keys across consecutive window operators**: Matching keys (e.g. `keyword_id, campaign_id, profile_id, adgroup_id`) on sequential windows lets Spark pipeline without re-shuffle or re-sort.
- **Prefer sorted window functions over high-cardinality hash joins for history**: `LAG`/`ROW_NUMBER` on sorted partitions buffer one key-group at a time (~30–90 rows). Shuffled hash joins build massive in-memory tables that spill. Use windows for chronological state/bid history; reserve joins for dimension lookups.

### Filters & predicate pushdown

- **Always apply client_id/date filters immediately after `spark.read.table()`**: Predicate pushdown only fires if filters appear before transformations. Pre-calculate `allowed_ids_list` once in source schema module setup. 20–40% I/O reduction.
- **No-date-filter trap (T-1 lean run paradox)**: Modules that ignore `:minreportdate`/`:maxreportdate` scan full client history even on 1-day runs. Common when computing "clicks since last bid change" — developers omit date bounds because bid changes can be months old. Fixes: (1) safe lookback ceiling (e.g. 60 days, coordinate with downstream consumers), (2) stateful incremental aggregation (see below).
- **Lookback padding inflates short runs**: `DATEADD(day, -14, :minreportdate)` forces a 1-day run to recalculate 15 days. Audit padding in foundational modules before optimizing daily lean runs.
- **Runtime-computed predicates block partition pruning**: `scorecard_date = (subquery)` cannot be pushed into partition pruning — requires static/literal predicates.
- **Large IN-list defeats partition pruning**: 300+ client_ids in single IN-list. Fix: batch or cache.
- **SQL UDF guarantees filter pushdown over plain VIEW**: Parameterized UDF e.g. `brands_cubes.common_filter_udf(#CLIENT_ID_PARAM)` — client_id substituted at SQL gen time. Plain VIEW e.g. `seller_cubes.common_filter_view` — pushdown depends entirely on optimizer.
- **SQL push-down as memory enabler**: Consolidating multiple `spark.sql().toPandas()` calls into a single server-side query reduces not just I/O time but the in-memory DataFrame size (often 99%+ reduction). This can be the prerequisite for instance downsizing — evaluate push-down for both time AND memory impact.

### DAG orchestration & CTAS boundaries

- **CTAS boundaries cut Catalyst lineage**: Each `CREATE TABLE AS SELECT` in a multi-module workflow is a hard execution boundary — optimizer cannot push filters, prune columns, or fuse operators across modules. Intermediate tables get rescanned independently (observed: 68 intermediate rescans, 217 base-table rescans in a 119-module DAG). Fix: register intermediate modules as **lazy temp views** (`CREATE OR REPLACE TEMP VIEW`), write only terminal/output modules physically.
- **Temp views require pinned JDBC session**: Temp views are session-scoped. In JDBC-pooled orchestrators, pin one connection for the entire workflow run (all view registrations + final CTAS on same connection).
- **State-aware module classification for CTAS vs temp view**: Modules with `MERGE`/`INSERT`/`DELETE` or self-referential historical lookups must remain physical tables (materialization checkpoints). Pure stateless transforms can be temp views. ~65/119 modules convertible in practice.
- **Materialization checkpoints for deep plans**: Chaining 100+ temp views can freeze the driver during planning. Keep 3–4 heaviest junction nodes (high fan-out intermediates) as physical CTAS; rest as views. Or use `.localCheckpoint()` in PySpark to truncate lineage on worker SSD.
- **Audit wide columns at CTAS boundaries**: `SELECT *` carrying 50+ unused columns across module boundaries multiplies memory and spill. Project only keys + columns used downstream in Tier-1 modules.

### Stateful incremental aggregation (daily runs)

- **Stateful incremental aggregation for T-1 runs**: Instead of re-scanning full keyword/bid history daily, read only T-1 raw data + yesterday's output state. If bid unchanged, accumulate clicks; if bid changed, reset counter and date. 100% accurate, scales infinitely. Verified target: T-1 lean run 28 min → <5 min.

### PySpark & Delta patterns

- **PySpark parallel prep + serial write**: `ThreadPoolExecutor` for `prepare_dataframe()` across aggregators, then serial Delta writes to prevent concurrent-append conflicts. 40–60% latency reduction for multi-aggregator workflows.
- **Materialize broadcast DataFrames before joining**: Call `.cache()` then `.count()` on small lookup tables before `broadcast()` to force materialization and avoid repeated scans during join.
- **Exponential backoff for Delta ConcurrentAppendException**: `max_retries=8`, `wait = initial_backoff_sec * 2^(attempt-1)`. Reduces parallel-aggregator workflow failures 80%+.
- **Delta Lake merge-on-read amplification**: Tables with heavy UPDATE/DELETE can read 10–30x physical rows vs logical. Fix: `OPTIMIZE + VACUUM`.
- **SQL push-down reduces both runtime AND memory**: Consolidating multiple `toPandas()` calls into one server-side query reduces runtime AND memory simultaneously — evaluate both dimensions, as memory reduction often enables aggressive instance downsizing.

### Analysis discipline

- **Cluster size masks inefficiency**: Larger cluster (X_SMALL→LARGE) throws parallelism at a bad plan. Always fix the plan, not just resize.
- **LIKE pattern cost attribution**: A single LIKE can match both cheap lookups and expensive analytical CTEs. Always inspect actual query text before attributing cost.
- **Verify optimizations with aggregate checksums, not row samples**: Compare `COUNT(*)`, `SUM(clicks)`, `SUM(impressions)`, `AVG(days)` across control vs refactored queries. Guarantees bit-perfect equivalence at scale without pulling raw data.
- **Databricks A/B profile comparisons are confounded by cache state**: Note cache hit rate when comparing query profiles between runs.
