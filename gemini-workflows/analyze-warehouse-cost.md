---
description: Automated analysis of Databricks SQL Warehouse performance and cost optimization opportunities.
variables:
  warehouse_id: The ID of the warehouse to analyze (e.g., de174e171ce90e15)
---

This workflow guides you through a comprehensive cost and performance analysis of a Databricks SQL Warehouse.

1.  **Verify MCP Connection**: Ensure the `dbx-dev` MCP server is active and you can run SQL queries.

2.  **Get Warehouse Configuration**:
    Run the following query to understand the current sizing and scaling settings:
    ```sql
    SELECT * FROM system.compute.warehouses WHERE warehouse_id = '{warehouse_id}'
    ```
    *Note: warehouse_id is often nested in specific tables, so check schema if needed.*

3.  **Analyze Baseline Metrics (30 Days)**:
    Run this query to get the high-level performance snapshot:
    ```sql
    SELECT 
      count(*) as total_queries,
      avg(total_duration_ms) as avg_duration_ms,
      approx_percentile(total_duration_ms, 0.95) as p95_duration_ms,
      sum(case when spilled_local_bytes > 0 then 1 else 0 end) as spilling_queries,
      avg(case when spilled_local_bytes > 0 then total_duration_ms end) as avg_spill_duration_ms
    FROM system.query.history
    WHERE compute.warehouse_id = '{warehouse_id}'
    AND start_time > current_date() - 30
    ```

4.  **Analyze Queueing & Concurrency**:
    Run this query to identify if and when queueing is happening (5-minute windows):
    ```sql
    SELECT
      date_format(from_unixtime(floor(unix_timestamp(start_time)/300)*300), 'yyyy-MM-dd HH:mm:ss') as time_window_utc,
      count(*) as total_queries,
      sum(case when waiting_at_capacity_duration_ms > 0 then 1 else 0 end) as queued_queries,
      cast(avg(total_duration_ms) as int) as avg_latency_ms,
      cast(max(waiting_at_capacity_duration_ms)/1000 as decimal(10,1)) as max_wait_sec
    FROM system.query.history
    WHERE compute.warehouse_id = '{warehouse_id}'
      AND start_time >= current_date() - 30
    GROUP BY 1
    HAVING max_wait_sec > 1
    ORDER BY max_wait_sec DESC
    LIMIT 20
    ```

5.  **Identify Spill Patterns**:
    Run this query to find the specific queries causing spills (the "heavy hitters"):
    ```sql
    SELECT 
      substr(statement_text, 1, 100) as query_snippet,
      count(*) as frequency,
      avg(total_duration_ms) as avg_duration_ms,
      avg(spilled_local_bytes)/1024/1024/1024 as avg_spill_gb,
      max(spilled_local_bytes)/1024/1024/1024 as max_spill_gb
    FROM system.query.history
    WHERE compute.warehouse_id = '{warehouse_id}'
    AND start_time > current_date() - 30
    AND spilled_local_bytes > 0
    GROUP BY 1
    ORDER BY avg_spill_gb DESC
    LIMIT 10
    ```

6.  **Calculate Optimization Opportunity**:
    - **Rightsizing**: If P95 duration is low (<5s) and only a small % of queries spill, propose downsizing (e.g. LARGE -> MEDIUM).
    - **Savings**: 
        - MEDIUM is ~50% cheaper than LARGE.
        - 2x MEDIUM clusters costs the same as 1x LARGE cluster but provides 2x concurrency.
    - **Strategy**: Fix the top spill queries identified in Step 5, then downsize.

7.  **Generate Report**:
    Create a markdown report `warehouse_{warehouse_id}_cost_analysis.md` with:
    - **Executive Summary**: Potential savings % and root cause.
    - **Baseline Metrics**: Table from Step 3.
    - **Queueing Analysis**: Insights from Step 4 (include a Mermaid chart if useful).
    - **Spill Analysis**: Top patterns from Step 5 with recommendations (partition pruning, materialized views, etc.).
    - **Action Plan**: Immediate fix (increase max clusters) vs Long-term fix (refactor & downsize).
