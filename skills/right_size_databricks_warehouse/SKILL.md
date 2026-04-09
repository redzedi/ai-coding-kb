# Skill: Right-Size Databricks Serverless SQL Warehouses

## Context
Databricks Serverless SQL Warehouses auto-scale based on concurrency (default ~10 queries per cluster). Inefficient configuration of `min_clusters`, `max_clusters`, and `auto_stop_minutes` can lead to massive compute waste, especially on lumpy workloads. This skill provides the methodology and exact SQL queries to analyze query history and scientifically project cost savings from configuration changes.

## Prerequisites
- Access to Databricks system tables: `system.query.history` and `system.compute.warehouse_events`.
- Access to Databricks system tables: `system.compute.warehouses` - this contains current configuration state of the warehouse.
- A specific Target `warehouse_id`.
- An analysis window (e.g., Trailing 7 days).
- Databricks rate specific to the serverless cluster type(e,g for MEDIUM cluster the current rate is $16.8/hr or $0.28/min)

## Step 1: Workload Profiling (Online vs Offline)
First, determine if the warehouse is serving real-time user traffic (needs low latency) or programmatic background jobs (needs high throughput). 

```sql
SELECT 
  CASE WHEN executed_as LIKE 'ciq_sp_read%' THEN 'Real-time UI' ELSE 'Offline/Programmatic' END as workload_type,
  COUNT(*) as total_queries
FROM system.query.history 
WHERE compute.warehouse_id = '<WAREHOUSE_ID>' 
  AND start_time >= current_timestamp() - INTERVAL 7 DAYS
GROUP BY 1;
```
*Note: Adapt the `executed_as` matching logic based on the specific org's service principal naming conventions.*

## Step 2: Concurrency Profiling
Understand the lumpiness of the workload. How often is it idle? How large are the spikes?

**Calculate Concurrency Distribution:**
```sql
WITH events AS (
  SELECT start_time AS event_time, 1 AS delta FROM system.query.history WHERE compute.warehouse_id = '<WAREHOUSE_ID>' AND start_time >= current_timestamp() - INTERVAL 7 DAYS
  UNION ALL
  SELECT end_time AS event_time, -1 AS delta FROM system.query.history WHERE compute.warehouse_id = '<WAREHOUSE_ID>' AND start_time >= current_timestamp() - INTERVAL 7 DAYS AND end_time IS NOT NULL
),
running_concurrency AS (
  SELECT event_time, SUM(delta) OVER (ORDER BY event_time ASC, delta DESC) AS concurrent_queries, LEAD(event_time) OVER (ORDER BY event_time ASC, delta DESC) AS next_event_time FROM events
)
SELECT 
  CASE 
    WHEN concurrent_queries = 0 THEN '0 (Idle)'
    WHEN concurrent_queries BETWEEN 1 AND 10 THEN '1-10'
    WHEN concurrent_queries BETWEEN 11 AND 20 THEN '11-20'
    ELSE '>20' 
  END as concurrency_bucket,
  SUM((unix_timestamp(next_event_time) - unix_timestamp(event_time)) / 60.0) as minutes_in_state
FROM running_concurrency
WHERE next_event_time IS NOT NULL
GROUP BY 1 ORDER BY 1;
```

## Step 3: Auto-Stop Savings Projection (e.g., 5m down to 1m)
Calculate the exact cluster-minutes wasted during the shutdown grace period. 

**The Math Logic ("Cost Rectangle"):**
Savings = (Time Saved) * (Current Min Clusters).

```sql
WITH idle_blocks AS (
  SELECT event_time as idle_start, next_event_time as idle_end, (unix_timestamp(next_event_time) - unix_timestamp(event_time)) / 60.0 as idle_minutes FROM (SELECT event_time, LEAD(event_time) OVER (ORDER BY event_time) as next_event_time, concurrent_queries FROM (SELECT event_time, SUM(delta) OVER (ORDER BY event_time ASC, delta DESC) AS concurrent_queries FROM (SELECT start_time AS event_time, 1 AS delta FROM system.query.history WHERE compute.warehouse_id = '<WAREHOUSE_ID>' AND start_time >= current_timestamp() - INTERVAL 7 DAYS UNION ALL SELECT end_time AS event_time, -1 AS delta FROM system.query.history WHERE compute.warehouse_id = '<WAREHOUSE_ID>' AND start_time >= current_timestamp() - INTERVAL 7 DAYS AND end_time IS NOT NULL)) WHERE concurrent_queries = 0 AND next_event_time IS NOT NULL AND (unix_timestamp(next_event_time) - unix_timestamp(event_time)) > 0)
)
SELECT
  SUM(CASE WHEN idle_minutes > <CURRENT_AUTO_STOP> THEN <CURRENT_AUTO_STOP> ELSE idle_minutes END) * <CURRENT_MIN_CLUSTERS> as billed_idle_mins_current,
  SUM(CASE WHEN idle_minutes > <PROPOSED_AUTO_STOP> THEN <PROPOSED_AUTO_STOP> ELSE idle_minutes END) * <CURRENT_MIN_CLUSTERS> as billed_idle_mins_proposed,
  (SUM(CASE WHEN idle_minutes > <CURRENT_AUTO_STOP> THEN <CURRENT_AUTO_STOP> ELSE idle_minutes END) - SUM(CASE WHEN idle_minutes > <PROPOSED_AUTO_STOP> THEN <PROPOSED_AUTO_STOP> ELSE idle_minutes END)) * <CURRENT_MIN_CLUSTERS> as savings_cluster_mins
FROM idle_blocks;
```

## Step 4: Min Clusters Savings Projection (e.g., 3 down to 1)
If `min_clusters` > 1, the warehouse wastes compute when traffic is low (Active Waste) AND when shutting down (Compounding Shutdown Waste).

**Query to calculate Active Waste:**
*(Assumes `min_clusters` is currently 3. Adjust math if different).*
```sql
WITH events AS (
  SELECT start_time AS event_time, 1 AS delta FROM system.query.history WHERE compute.warehouse_id = '<WAREHOUSE_ID>' AND start_time >= current_timestamp() - INTERVAL 7 DAYS
  UNION ALL
  SELECT end_time AS event_time, -1 AS delta FROM system.query.history WHERE compute.warehouse_id = '<WAREHOUSE_ID>' AND start_time >= current_timestamp() - INTERVAL 7 DAYS AND end_time IS NOT NULL
),
running_concurrency AS (
  SELECT event_time, SUM(delta) OVER (ORDER BY event_time ASC, delta DESC) AS concurrent_queries, LEAD(event_time) OVER (ORDER BY event_time ASC, delta DESC) AS next_event_time FROM events
)
SELECT
  SUM(CASE WHEN concurrent_queries BETWEEN 1 AND 10 THEN (unix_timestamp(next_event_time) - unix_timestamp(event_time))/60.0 ELSE 0 END) * 2 +  -- 1 needed, 3 billed = 2 wasted
  SUM(CASE WHEN concurrent_queries BETWEEN 11 AND 20 THEN (unix_timestamp(next_event_time) - unix_timestamp(event_time))/60.0 ELSE 0 END) * 1     -- 2 needed, 3 billed = 1 wasted
  as active_waste_cluster_mins_saved
FROM running_concurrency WHERE next_event_time IS NOT NULL;
```

**Calculate Compounding Shutdown Waste:**
*(Calculates the remaining shutdown footprint after the auto-stop change, and determines savings from lowering cluster height).*
```sql
-- Use the same `idle_blocks` CTE from Step 3
SELECT
  SUM(CASE WHEN idle_minutes > <PROPOSED_AUTO_STOP> THEN <PROPOSED_AUTO_STOP> ELSE idle_minutes END) * (<CURRENT_MIN_CLUSTERS> - <PROPOSED_MIN_CLUSTERS>) as compounding_shutdown_cluster_mins_saved
FROM idle_blocks;
```

## Step 5: Synthesize Final Report
1. Sum the cluster-minutes saved across all buckets.
2. Multiply by the retail cost per minute of the specific warehouse type (e.g., Serverless Medium = ~$0.28/min).
3. Contrast against the historical bill, accounting for any corporate Databricks discounts.
4. Issue final recommendations for `min_clusters`, `max_clusters`, and `auto_stop_minutes`, prioritizing throughput/cost for offline batch, and latency/P95 for real-time.

## General Guidance:
1. For more accuracy and flexibility of calculations, download the raw data over the timeperiod locally . THen write python script to massage , aggregate the data to get the required result.