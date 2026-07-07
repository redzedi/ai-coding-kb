## DB, Datalake perf analysis tips

- **Databricks 1,000-query queue per warehouse limit**: services connected via jdbc can saturate this under peak load with no connection pooling.

- **DB query is fast (4–14ms); 250ms latency is network + Hibernate overhead**: EXPLAIN ANALYZE with PRIMARY key range scan at 4–14ms means DB is optimal. Network (~150ms) + JPA entity hydration (~100ms) is the bottleneck. Use native queries or DTO projections for hot paths.
- **Databricks A/B query profile comparisons are confounded by cache state**: Cache hit rate changing 46%→20% between runs can make a faster query appear slower. Always note cache state when comparing profiles.

- **Databricks query profile analysis**: Check `SCAN_PARTITIONS` for partition columns, `FILTERS` for pushed predicates, spill metrics on Window/Sort nodes, `Reused Exchange` for shared scans. High scan row count vs logical rows → Delta Lake merge-on-read / deletion vectors.

- **Physical plan audit — count `PhotonScan` nodes per base table**: After query optimization, grep the physical plan for `PhotonScan parquet <table>` to count actual scans per table. Compare against theoretical minimum (1 per base table). If scans exceed 1, CTE branching or non-linear references are causing inline expansion.

- **`ReusedExchange` confirms Catalyst sharing shuffle exchanges**: When Spark displays `ReusedExchange (N)` reusing an earlier `ShuffleQueryStage`, it proves the optimizer successfully shared a single shuffle across multiple branches (e.g. `ciq_actions` grouped once, reused across SP/SB/SD branches). This is a key victory indicator in union-based query plans.

- **Delta Time Travel for baseline vs optimized comparison**: Use `DESCRIBE HISTORY <table>` to locate version numbers corresponding to specific workflow runs. Query both versions (`VERSION AS OF <n>`) and compare `row_count`, `SUM(clicks)`, `SUM(impressions)`, `SUM(cost)` for 100% bit-perfect equivalence proof.

- **`system.compute.instance_events` for infrastructure anomalies**: Check instance event logs when investigating unexpected performance or duration anomalies in ephemeral Databricks jobs — reveals Spot reclamation events, node additions/removals, and their exact timestamps.

- **Dynamic execution-to-cluster traceability**: Map CCP execution IDs to physical Databricks cluster IDs via `SELECT DISTINCT compute.cluster_id FROM system.query.history WHERE query_text LIKE '%e<execution_id>__%'`. Essential for correlating query-level and cluster-level metrics.