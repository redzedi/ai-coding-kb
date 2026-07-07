---
name: databricks-workflow-cost-optimization
description: >-
  End-to-end cost optimization analysis for a Databricks Job Compute workflow (PySpark ETL).
  Given a CCP workflow name, builds context (repos, docs, architecture), profiles cost using
  system tables and billing data, identifies waste (failures, long-tail, stuck runs), and
  produces a structured analysis document with data-backed optimization hypotheses.
  Use when asked to analyze workflow cost, investigate a costly ETL pipeline, optimize
  Databricks job compute spend, or find runaway/stuck jobs.
---

# Databricks Job Compute Workflow Cost Optimization

## When to Use

Use this skill when given a CCP workflow name and asked to:
- Investigate why a Databricks job compute workflow is expensive
- Find and quantify wasted compute from failures, stuck runs, over-provisioning etc
- Produce a cost optimization analysis with actionable hypotheses
- Identify runaway jobs and propose timeout thresholds
- brainstorm to generate qualified ideas to reduce cost for the given wf

## Prerequisites

- Target CCP workflow name (e.g., `some_etl_wf`)
- Analysis window (default: trailing full calendar month)
- MCP servers:
  - **`user-dbx-dev`** for all Databricks SQL queries (system catalog synced from prod; `admin_catalog` accessible here)
  - **`user-dbx-prod`** as fallback for `system.billing.usage` and `system.lakeflow` queries
  - **`plugin-atlassian-atlassian`** for Jira/Confluence discovery
  - **`user-bitbucket4`** with workspace `commerceiq` for repo search
- Prod workspace IDs: `6609267921842809`, `1086031994956170`, `2986176579409100`

## Phase 0: Preparation

- create a work-dir for this analysis in `cursor-analysis`. The name pattern for that director is `<wf name>_cost-opt_<dd-MM-yyyy>`
- create a worktree from master for your analysis

## Phase 1: Context Discovery

Given only a workflow name, build understanding of what it does and where the code lives.

### Step 1: Find documentation
- Search Confluence via `searchConfluenceUsingCql` for the workflow name
- Search Jira via `searchJiraIssuesUsingJql` for related tickets (past optimizations, incidents)

### Step 2: Find code repos
- Search Bitbucket via `search_code` (server: `user-bitbucket4`, workspace: `commerceiq`) for the workflow name
- Look for two repos: a **code repo** and a **config repo** (CCP pattern)
- Clone locally with `--depth 1` for analysis

### Step 3: Read the code
- Identify the entry point (usually in `entrypoint/`)
- Understand the fan-out pattern: does an orchestrator spawn multiple generator/worker runs?
- Note: cluster config, parallelism settings, key libraries (Prophet, Spark ML, etc.)

### Step 4: Find out the upstream

- ccp etl wf are generally triggered by upstream data ingestion orchestrator  like airflow or azkaban, use bitbucket code search to figure out the repo and specific workflow that triggers this ccp wf.
- Analyze the grain trigger , are the triggers per client ? combination of retailer ,client , region etc

### Step 5: Find out the domain context

- Each ETL wf produces some data that is used to power one or more expereiences( metric pages) in ciq client facing products , identify these products by using code search with the output table names .

### Step 6: Create a dependency graph of modules in the workflow

- **Discover DAG for the current wf** -- CCP wf especially SQL wf are defined in terms of modules that  have dependency on other modules . Discover the DAG for the current wf. Check AGENTS.local.md if the DAG for this wf is already available

- **Discover the wf in the repo impacted** -- Find out all wf definitions in the repo that include any of the modules of the current wf . THese other wf are in the regression impact path
  
- **Add or Update the DAG details in AGENTS.local.md** -- for future reference

## Phase 2: Cost Profiling

### Step 1: Find the job_id

```sql
SELECT job_id, name, creator, description
FROM system.lakeflow.jobs
WHERE name LIKE '%<workflow_name>%'
```

### Step 2: Total cost using the CIQ cost query

This query combines discounted Databricks DBU cost (list price x 0.57) and AWS compute infra cost. **Must run on `user-dbx-dev`** (only environment with `admin_catalog` access).

```sql
SELECT date_trunc('month', ds) AS month, wf, SUM(total_daily_cost) AS total_monthly_cost
FROM (
  SELECT ds, wf, SUM(dbx_cost) AS total_daily_cost
  FROM (
    SELECT ds, sku,
      COALESCE(custom_tags['ccp_workflow_name'], 'wf') AS wf,
      CAST(SUM(cost_at_list_price) AS DECIMAL(32,2)) AS dbx_cost
    FROM (
      SELECT u.workspace_id,
        CASE
          WHEN u.workspace_id = 5482606822854295 THEN 'qa'
          WHEN u.workspace_id = 8144498481388127 THEN 'sbx'
          WHEN u.workspace_id IN (6609267921842809, 1086031994956170, 2986176579409100) THEN 'prod'
          WHEN u.workspace_id = 4563007571506375 THEN 'beta'
        END AS workspace_name,
        u.usage_metadata['cluster_id'] AS cluster_id,
        u.usage_date AS ds,
        u.sku_name AS sku,
        u.custom_tags,
        CAST(u.usage_quantity AS DOUBLE) AS dbus,
        CAST((lp.pricing.default * 0.57) * usage_quantity AS DOUBLE) AS cost_at_list_price
      FROM system.billing.usage u
      INNER JOIN system.billing.list_prices lp
        ON u.cloud = lp.cloud
        AND u.sku_name = lp.sku_name
        AND u.usage_start_time >= lp.price_start_time
        AND (u.usage_end_time <= lp.price_end_time OR lp.price_end_time IS NULL)
      WHERE u.usage_unit = 'DBU'
    )
    WHERE workspace_name IN ('prod')
      AND ds BETWEEN '<start_date>' AND '<end_date>'
    GROUP BY 1, 2, 3

    UNION ALL

    SELECT start_date AS ds, 'AWS Compute' AS sku, tag_value AS wf, SUM(cost) AS dbx_cost
    FROM admin_catalog.account_usage.aws_cost_metrics_tags
    WHERE env = 'prod'
      AND tag = 'ccp_workflow_name'
      AND start_date BETWEEN '<start_date>' AND '<end_date>'
    GROUP BY 1, 2, 3
  )
  WHERE wf != 'wf'
  GROUP BY 1, 2
)
GROUP BY 1, 2
ORDER BY total_monthly_cost DESC
```

Filter by workflow: add `WHERE wf = '<workflow_name>'` or `WHERE wf LIKE '%<partial>%'` to the outer query.

**Cost structure**: Total cost = DBU cost ($0.0855/DBU after discount) + AWS infra cost. The AWS cost table may have data gaps — treat as lower bound.

### Step 3: Run volume and duration distribution

```sql
SELECT
  CASE
    WHEN execution_duration_seconds <= 300 THEN '0-5 min'
    WHEN execution_duration_seconds <= 600 THEN '5-10 min'
    WHEN execution_duration_seconds <= 1800 THEN '10-30 min'
    WHEN execution_duration_seconds <= 3600 THEN '30-60 min'
    WHEN execution_duration_seconds <= 7200 THEN '1-2 hours'
    WHEN execution_duration_seconds <= 14400 THEN '2-4 hours'
    WHEN execution_duration_seconds <= 28800 THEN '4-8 hours'
    ELSE '8+ hours'
  END AS duration_bucket,
  COUNT(*) AS runs,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct_runs
FROM system.lakeflow.job_task_run_timeline
WHERE job_id = '<job_id>'
  AND period_start_time >= '<start_date>' AND period_start_time < '<end_date>'
  AND result_state IS NOT NULL
GROUP BY 1
ORDER BY MIN(execution_duration_seconds)
```

**Important**: In `job_task_run_timeline`, `execution_duration_seconds` is only meaningful on terminal rows (where `result_state IS NOT NULL`). Intermediate hourly segments have `execution_duration_seconds = 0`.

### Step 4: Failure profile

```sql
SELECT
  result_state,
  termination_code,
  COUNT(DISTINCT job_run_id) AS runs,
  ROUND(AVG(execution_duration_seconds) / 3600, 2) AS avg_hours,
  ROUND(MAX(execution_duration_seconds) / 3600, 2) AS max_hours
FROM system.lakeflow.job_task_run_timeline
WHERE job_id = '<job_id>'
  AND period_start_time >= '<start_date>' AND period_start_time < '<end_date>'
  AND result_state IS NOT NULL
GROUP BY 1, 2
ORDER BY runs DESC
```

### Step 5: Per-run DBU cost for sample runs

```sql
SELECT
  usage_metadata['job_run_id'] AS job_run_id,
  SUM(CAST(usage_quantity AS DOUBLE)) AS total_dbus,
  SUM(CAST((lp.pricing.default * 0.57) * u.usage_quantity AS DOUBLE)) AS dbu_cost
FROM system.billing.usage u
INNER JOIN system.billing.list_prices lp
  ON u.cloud = lp.cloud AND u.sku_name = lp.sku_name
  AND u.usage_start_time >= lp.price_start_time
  AND (u.usage_end_time <= lp.price_end_time OR lp.price_end_time IS NULL)
WHERE u.usage_unit = 'DBU'
  AND u.usage_metadata['job_id'] = '<job_id>'
  AND u.usage_metadata['job_run_id'] IN ('<run_id_1>', '<run_id_2>', ...)
  AND u.usage_date BETWEEN '<start_date>' AND '<end_date>'
GROUP BY 1
ORDER BY total_dbus DESC
```

### Step 6: Cluster lifecycle verification

Verify that billing matches cluster uptime for sample runs:

```sql
SELECT
  cluster_id, cluster_name, cluster_source,
  create_time, delete_time,
  driver_node_type, worker_node_type,
  min_autoscale_workers, max_autoscale_workers
FROM system.compute.clusters
WHERE cluster_id = '<cluster_id_from_billing>'
```

The `cluster_id` is in `usage_metadata['cluster_id']` from `system.billing.usage`. For ephemeral job clusters, the cluster name includes the `job_run_id`.

To verify continuous billing, query hourly usage entries for a specific run:

```sql
SELECT usage_start_time, usage_end_time, ROUND(CAST(usage_quantity AS DOUBLE), 4) AS dbus
FROM system.billing.usage
WHERE usage_metadata['cluster_id'] = '<cluster_id>'
  AND usage_unit = 'DBU'
ORDER BY usage_start_time
```

Multiple entries per hour = multiple nodes (driver + workers). Continuous hourly entries with no gaps = cluster stayed fully provisioned.

### Step 7: Find the distribution of wf runtimes by tenant

- Find out median , p95, p99 , max runtimes by client_id . Find the top 10 clients by median and p95 values.
- If there is a time window provided and the timewindows are variable , then find the same distribution for the combination of client_id + time_window.

## Phase 3: Analysis Patterns

This is where you brainstorm for ways to reduce cost . Each recommendation is a hypothesis derived from some evidence observed in the context collected so far . 

*Each hypothesis should be verifiable* . With each hypothesis propose a plan to test it , with quantitative threshold that proves or disproves the hypotheses. 

*The following list of patterns is not exhuastive, it is just the usual set of analysis that were done in other cases* . Remember each wf is unique so which analysis applies for a particular case depends on the specific context .

Here being creative, thinking out of the box helps .

create an intermediate document `temp_recommendations_<version number starting from 1>.md`, withe following details at the end of this Phase to document the findings -

```
  | reccomendation | reccomendation type(code | config | architecture) | why this helps ? | expected saving in $/month |

```
### Pattern A: Timeout Analysis

When failures consume significant cost:

1. **Profile SUCCEEDED durations** — compute p50, p90, p95, p99, p99.9, max
2. **Choose timeout threshold** — should be above the max SUCCEEDED (or p99.9 if max is an outlier), with buffer
3. **Quantify savings** — count non-SUCCEEDED runs above threshold, sum their DBUs
4. **Verify billing behavior** — confirm stuck jobs are billed continuously (hourly usage records with no gaps)
5. **Check for manual intervention** — `USER_CANCELLED` runs indicate ops is already killing stuck jobs manually

### Pattern B: Long-Tail Optimization

When a small % of runs consume disproportionate cost:

1. **Identify the threshold** — typically >1 hour runs in a workflow where median is minutes
2. **Quantify the cost share** — what % of total cost comes from these runs?
3. **Examine the code** — what determines run duration? (combination count, data volume, model complexity)
4. **Propose code-level fixes** — lighter models, better batching, early-exit for low-value work
5. **Lead with Hypothesis** -- for each code level fix recommendation , quantify the expected benefit in terms of total execution time saving and the hypothesis statement of what is causing the perf gain . This provides a grounding to objectively validate these recommendations later.

### Pattern C: Volume Reduction

When run count seems excessive:

1. **Understand the fan-out** — how does the orchestrator decide how many runs to trigger?
2. **Check for combinatorial explosion** — are pairwise combinations, cartesian products involved?
3. **Assess incremental processing** — can runs be skipped when input data hasn't changed?

### Pattern D: Architectural Mismatch Detection

When DBU:AWS cost ratio is unusually low (< 0.5) or CPU utilization is near zero:

The workload may not belong on Spark at all. Spark clusters are sometimes used as
expensive container runtimes for non-distributed work (pandas, asyncio HTTP, ML inference).

**Detection signals:**
1. **`toPandas()` in the hot path** — converting Spark DataFrames to pandas means
   all subsequent work is single-node, negating Spark's distributed compute
2. **`asyncio` / `httpx` / `requests` imports** — HTTP I/O-bound work doesn't benefit
   from Spark; a lightweight pod or container is 10-50× cheaper
3. **Near-zero CPU with high wall-clock** — cluster is waiting on external API calls
4. **Workers idle most of runtime** — memory graphs show brief spikes during data load
   then zero activity for hours
5. **Low DBU relative to infra** — healthy Spark jobs show DBU:AWS ratio ~1:1; I/O-bound
   jobs on over-provisioned clusters show ratios like 1:2 or 1:3

**Evidence collection:**
- Correlate **driver logs** (phase timing), **cluster CPU graphs** (utilization %),
  **worker memory graphs** (active vs idle time), and **JVM heap graphs** (OOM patterns)
- If CPU < 5% during the dominant phase and workers show 0 B memory utilization after
  initial data load, the workload is I/O-dominated and architecturally mismatched

**Recommendation framework:**
- If the workload is I/O-bound HTTP (API calls, web scraping): K8s pod or Fargate
- If the workload is pandas-only (no distributed compute): Airflow PythonOperator or K8s pod
- If the workload needs only Delta I/O: Databricks SQL Serverless (query-based pricing, not provisioned-cluster pricing)
- If the workload mixes SQL + I/O: hybrid (SQL Serverless for reads/writes, K8s pod for I/O)

### Pattern E: Progressive Optimization Strategy

When proposing changes to another team, structure as independently shippable phases:

1. **Config-only wins** (1 day, zero risk) — spot instances, disable broken configs, reduce autoscale
2. **DAG-level changes** (1-2 days, low risk) — preflight skip queries, schedule optimization
3. **Code changes** (days-weeks, medium risk) — SQL push-down, batch consolidation, write pattern changes
4. **Code-dependent config** (1 day, low risk) — instance downsizing enabled by code changes
5. **Architectural redesign** (weeks, higher risk) — platform migration, compute model change

For each phase, document:
- **Effort** and **risk** level
- **Standalone cost savings** (not dependent on later phases)
- **Cumulative running cost** (shows the staircase of savings)
- **Dependencies** on prior phases (e.g., instance downgrade requires memory reduction first)

This lets the receiving team ship quick wins immediately while evaluating larger changes.
The phased approach also builds credibility — if Phase 1 savings materialize as predicted,
the team gains confidence to proceed with riskier phases.

### Pattern F: Tiered Compute Profiling

Include upstream(triggering side) information for this too , the recommendation might be batching or some pre-trigger work in upstream.
However , these recommendations will have high complexity now because of the sensitive nature of the data ingestion orchestrators.
When a workflow serves heterogeneous clients with 10-100× variation in data volume:

1. **Identify the volume dimension** — what input characteristic drives runtime? (row count, combination count, model count)
2. **Define 2-3 tiers** from observed data (e.g., Large >4M rows, Medium 1-4M, Small <1M)
3. **Map clients to tiers** using data from input tables or `mle_run_stats`
4. **Define cluster profiles per tier** via CCP's per-workflow client-to-cluster mapping
5. **Estimate cost per tier** — hours × (DBU_rate × 0.57 + estimated_EC2_rate)

This right-sizes compute for 80%+ of runs (typically small) while maintaining headroom
for heavy-hitter clients. Often saves 30-50% vs flat sizing for the worst case.

### Pattern G: Multi-module analysis

Workflows might consist of multiple intermediate modules. Look a across modules for cross cutting patterns. Remember security concerns are paramount .

- **Same source tables scanned multiple times in various modules** -- Look for opportunities of merging modules , using temp views in SQL workflows . Be mindful of hte high complexity though

- **Data shape by upstream modules** -- An intermediate module might be able to leverage the data shpae ( e.g distinct rows) of the data emitted by upstream and forego those expensive checks in its own code.

- **Intermediate modules might be shared, AVOID REGRESSION AT ALL COST** -- a recommendation for an intermediate module might cause a regression when used from another workflow . Find out   all workflows that use any of the modules that are impacted by our proposed changes so far . Analyse the impact on each of those wf of the change . Only include a recommendation if it is absolutely safe . The recommendations that are categorized as non-safe should be documented separately 

## Phase 4: Low level design for the SQL optimization recommendations

Create a document `temp_sql_lld.md`

- **For each SQL optimization reccomendation from the previous Phase** --
  - - **Generate and document the low level design** -- Create a section in the lld document. Add real code snippets such that an agent can directly implement these with minimum effort and no ambiguity reading this document.



## Phase 5: Validate SQL optimization recommendations

Applies for SQL wf only .

- **For each unvalidated SQL optimization reccomendation** --
  - **Create new worktree from master**
  - **Do the changes in the .vtl files**
  - **invoke 'ccp-workflow-experiment'** -- with arguments `is_vtl_file_changes_done`=F and map of parameters needed to run the resultant query . use the top client_id by p95 runtime as detected above and other parameter values for corresponding run from prod
  - **Compare experiment observations with expected gain**. -- if the actual observed execution time improvement is lesser than expected gain by more than 20-25% , the hypothesis and recommendation stands invalidated.
  - **Create New SQL recommendations from the clues uncovered in the observed query profile** - The analysed query profile might uncover newer possibilities that were not considered before , those ideas should be analyzed and captured to the list of unvalidated reccomendations to be validated. Add the corresponding lld in the `temp_sql_lld.md` ( see ## [Phase 4](./##Phase ) above)

## Phase 6: Output

### Analysis Document

Create in the work-dir with this structure:

```
# <Workflow Name> — Cost Optimization Plan

## Executive Summary
[1-2 sentences: monthly cost, key waste finding, savings potential]

## Workflow Overview
- Purpose, architecture, run volume, cluster config
- Code repos

## Cost Breakdown
- DBU cost vs AWS EC2 cost (separate line items)
- DBU:AWS ratio (healthy ~1:1; I/O-bound mismatches show 1:2+)
- Cost per run by duration bucket

## Runtime Characterization
[Duration bucket table with runs, %, DBUs, cost]
[Architectural mismatch check: is Spark doing real distributed work?]

## Failure Analysis
[By result_state x termination_code: count, cost, avg/max duration]

## Per-Run Cost Evidence
[Sample runs with DBU and dollar cost from billing tables]
[Cluster billing verification showing continuous charges]
[If available: CPU/memory graphs correlated with log timeline]

## Optimization Roadmap
Structure as independently shippable phases (see Pattern E):

### Phase 1: Config & Quick Wins
[Config-only changes: spot, autoscale, disable broken configs]
[Each with effort, risk, savings, cumulative cost]

### Phase 2: Code Changes
[SQL push-down, write pattern changes, batch consolidation]

### Phase 3: Architecture Changes (if Pattern D applies)
[Platform migration, compute model change]

### Phase Summary Table
| Phase | Change Type | Effort | Savings/month | Cumulative Cost | Dependencies |

## Input/Output Data Profile (if heterogeneous clients)
[Client volumes, tier definitions for Pattern F]

## Other Optimizations considered

| Name | Description | Effort level | Savings/month | why not recommending ? |

## Sample Run IDs for Investigation
[Organized by failure type and duration bucket]

## Reference: Cost Query
[The CIQ cost query for future agents]
```

### Jira Ticket

Create in the relevant project. Keep concise and data-driven:
- Problem: monthly cost, waste amount and %
- Evidence: failure profile summary, sample runs with costs
- Hypothesis: proposed fix, expected savings
- Next steps: what to investigate further

Add labels: `cost-optimization`, `databricks`

### Discovered Data

THere should one consolidated document called `misc_<ddMMYYYY>.md` in the workdir , containing all important context data discovered in the process of this investigation . THese data will be useful in the next phases of the uber workflow . 
The document is expected to contain the following ( but not limited to these only ) --
 
 - runtime distribution by client and other input parameter combinations
 - run volume and duration distribution
 - failure profile 

### Consolidated LLD document for the valid SQL code change reccomendations

copy over from `temp_sql_lld.md` document created in Phase 4.



## Important Notes

- **Parent-Child View Collapsing**: Always inspect underlying source views (e.g., `catalog_listing_view`) for joins with parent-child metadata tables (like `ARAMUS.AVC_CLIENT_PARENT_CHILD_MAPPING`). These views may resolve all child client rows under a parent client ID, meaning many of the child runs triggered separately will result in zero-row data operations.


