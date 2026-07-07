
## Databricks cost optimization analysis tips - for both batch/Job Compute and realtime/SQL warehouse workloads


### Foundational info

- CIQ is on *Enterprise* plan , thus sku s for databricks products like compute are always prefixed by the plan type e.g *ENTERPRISE_JOBS_COMPUTE_(PHOTON)*
- With most compute types , there is option to enable Photon acceleration engine underneath . Photon engine provides dynamic optimization and thus an extra speed up to existing queries . Photon is additional cost over the the base compute type
- In databricks compute types are -- *SQL Serverless Compute* , *Job Compute*  and *All Purpose Compute*

- *SQL Serverless Compute* -- As this is serverless ,  the underlying cluster is maintained in databricks environment and query is sent to dbx env and is executed there , users do not have any other footprint for running these queries . Callers do not get to know the instance types or number of instances actually running . The pricing is in units  a DBU/hr or $/hr basis. The rate depends on the cluster size  . The cluster size options are ( in ascending order of instances in cluster) -- *2x-small* , *x-small* *small* , *medium* , *large* , *x-large* , *2x-large* ... upto *5x-large*. 

sku name is *ENTERPRISE_SERVERLESS_SQL_COMPUTE_US_WEST_OREGON*. Catalog rate for this sku is $ 0.70/DBU .
The indicative rates are as follows --

| Instance size | DBU/hr rate | $/hr rate |
|---------------|-------------|-----------|
| 2X-Small | 4.000DBU/hr | $2.8/hr |
| X-Small | 6.000DBU/hr | $4.2/hr|
| Small | 12.000DBU/hr | $8.4/hr|
| Medium | 24.000DBU/hr | $16.8/hr|
| Large | 40.000DBU/hr | $28/hr|
| X-Large | 80.000DBU/hr | $56/hr|
| 2X-Large | 144.000DBU/hr | $100.8/hr|
| 3X-Large | 272.000DBU/hr | $190.4/hr|
| 4X-Large | 528.000DBU/hr | $369.6/hr|
| 5X-Large | 1042.000DBU/hr | $729.4/h|

- *Job Compute* -- Here databricks sets up cluster in the client's vpc and the queries are run completely in client's infrastructure . Client pays for infrastructre cost for the instances these clusters are running on . Also clients are billed by databricks for the software that is running per usage . There is a dedicated ephemeral cluster that is provisioned for each job request , using the nodes ( e.g ec2 instances in AWS cloud) provisioned by the client . 
	- Here there is base rate ( cost per DBU ) set on the compute type ( Jobs_compute ) level what is $ 0.15/DBU.
	- But the amount of compute in DBU terms here is actually tied to the instance type . A larger instance has more compute thus can consume or burn through more of databricks underlying compute capacity ( remember this is just licensing fee for the code used ) . By that logic the dbu burn rate ( DBU/hr ) is published for each instance type for a cloud provider .
      
|  instance type     |  # cpus|  # mem |  DBU/hr rate |  $/hr rate | 
| -------------------| -------| -------| -------------| -----------| 
| m5d.large (Photon) |  2CPUs |  8GB |  0.986DBU/hr |  $0.1479/hr| 
| m5d.xlarge (Photon) |  4CPUs |  16GB |  2.001DBU/hr |  $0.30015/hr| 
| m5d.2xlarge (Photon) |  8CPUs |  32GB |  3.973DBU/hr |  $0.59595/hr| 
| m5d.4xlarge (Photon) |  16CPUs |  64GB |  7.946DBU/hr |  $1.1919/hr| 
| m5d.8xlarge (Photon) |  32CPUs |  128GB |  15.892DBU/hr |  $2.3838/hr| 
| m5d.12xlarge (Photon) |  48CPUs |  192GB |  23.867DBU/hr |  $3.58005/hr| 
| m5d.16xlarge (Photon) |  64CPUs |  256GB |  31.784DBU/hr |  $4.7676/hr| 
| m5d.24xlarge (Photon) |  96CPUs |  384GB |  47.734DBU/hr |  $7.1601/hr| 
| m5dn.large (Photon) |  2CPUs |  8GB |  1.189DBU/hr |  $0.17835/hr| 
| m5dn.xlarge (Photon) |  4CPUs |  16GB |  2.378DBU/hr |  $0.3567/hr| 
| m5dn.2xlarge (Photon) |  8CPUs |  32GB |  4.727DBU/hr |  $0.70905/hr| 
| m5dn.4xlarge (Photon) |  16CPUs |  64GB |  9.454DBU/hr |  $1.4181/hr| 
| m5dn.8xlarge (Photon) |  32CPUs |  128GB |  18.937DBU/hr |  $2.84055/hr| 
| m5dn.12xlarge (Photon) |  48CPUs |  192GB |  28.391DBU/hr |  $4.25865/hr| 
| m5dn.16xlarge (Photon) |  64CPUs |  256GB |  37.874DBU/hr |  $5.6811/hr| 
| m5dn.24xlarge (Photon) |  96CPUs |  384GB |  56.782DBU/hr |  $8.5173/hr| 
| m6gd.large (Photon) |  2CPUs |  8GB |  1.13DBU/hr |  $0.1695/hr| 
| m6gd.xlarge (Photon)  |  4CPUs |  16GB |  2.23DBU/hr |  $0.3345/hr| 
| m6gd.2xlarge (Photon)  |  8CPUs |  32GB |  4.47DBU/hr |  $0.6705/hr| 
| m6gd.4xlarge (Photon)  |  16CPUs |  64GB |  8.9DBU/hr |  $1.335/hr| 
| m6gd.8xlarge (Photon)  |  32CPUs |  128GB |  17.78DBU/hr |  $2.667/hr| 
| m6gd.12xlarge (Photon) |  48CPUs |  192GB |  26.71DBU/hr |  $4.0065/hr| 
| m6gd.16xlarge (Photon) |  64CPUs |  256GB |  35.61DBU/hr |  $5.3415/hr| 

See the full list at [[./dbx-jobs-compute-ec2-rate.md]]

- In databricks , Compute type are priced by *$/DBU* . The compute price catalog is in the table `system.billing.list_prices`. This is the base conversion rate .
-  The actual cost to client is depends on the the actual instances types used or the cluster size configured .  For different configurations there is a *DBU/hr* rate , there is a separate catalog for that rate . Above we snapshot the DBU/hr rate for various configurations . Note -- unlike $/DBU prices that are real-time , the above rates are just snapshotted.


### Key System Tables Reference

| Table | What It Tells You | Key Columns |
|---|---|---|
| `system.lakeflow.jobs` | Job definitions | `job_id`, `name` |
| `system.lakeflow.job_run_timeline` | Run-level timeline | `job_run_id`, `period_start_time`, `result_state` |
| `system.lakeflow.job_task_run_timeline` | Task-level detail | `execution_duration_seconds`, `result_state`, `termination_code`, `task_parameters` |
| `system.billing.usage` | Hourly DBU consumption | `usage_quantity`, `usage_metadata` (job_id, job_run_id, cluster_id) |
| `system.billing.list_prices` | SKU list prices | `pricing.default`, `sku_name` |
| `system.compute.clusters` | Cluster lifecycle | `create_time`, `delete_time`, `cluster_name`, node types |
| `admin_catalog.account_usage.aws_cost_metrics_tags` | AWS infra cost by workflow tag | `tag_value`, `cost`, `start_date` (dbx-dev only) |

### Query to calculate monthly ccp wf cost

```sql

  select date_trunc('month', ds), wf , sum(total_daily_cost) as total_monthly_cost
 from
 ( 
    select  ds ,wf,sum(dbx_cost) as total_daily_cost from 
    (select ds, sku, coalesce(custom_tags['ccp_workflow_name'], 'wf') as wf,cast(sum(cost_at_list_price) as decimal(32,2)) as dbx_cost 
    from (
      select u.workspace_id, 
        case when u.workspace_id = 5482606822854295 then 'qa'
            when u.workspace_id = 8144498481388127 then 'sbx'
            when u.workspace_id IN (6609267921842809, 1086031994956170, 2986176579409100) then 'prod'
            when u.workspace_id = 4563007571506375 then 'beta'
        end as workspace_name,
        u.usage_metadata['cluster_id'] as cluster_id,
        u.usage_date as ds, 
        u.sku_name as sku,
        u.custom_tags, 
        cast(u.usage_quantity as double) as dbus, 
        cast((lp.pricing.default * 0.57) * usage_quantity as double) as cost_at_list_price 
      from system.billing.usage u 
      inner join system.billing.list_prices lp 
        on u.cloud = lp.cloud 
        and u.sku_name = lp.sku_name 
        and u.usage_start_time >= lp.price_start_time 
        and (u.usage_end_time <= lp.price_end_time or lp.price_end_time is null)
      where u.usage_unit = 'DBU' 
      
    ) where workspace_name in ('prod')
    and  ds between '<START_DATE>' and '<END_DATE>'


    group by 1,2,3
    union
    select start_date as ds, 'AWS Compute' as sku, tag_value as wf, sum(cost) as dbx_cost
    from admin_catalog.account_usage.aws_cost_metrics_tags where env='prod' and tag='ccp_workflow_name'  and start_date between '<START_DATE>' and '<END_DATE>'
    group by 1,2,3
    )
    where wf != 'wf' 
    group by 1,2

 )
 group by 1,2


```


### Tips
-**Always report proposed savings for ccp wf or optimized query in $/month unit** -- Use the table `system.billing.list_prices` and the DBU/hr rate for the common compute type as noted above , always report the expected cost saving both in terms of DBU s saved and most importantly in $ saved , wherever possible extrapolate it to $/month in saving . Call out any assumptions needed to be made in such a process.
- **Verify data assumptions with actual queries**: Don't state data facts without verifying against prod data.

- **Parallel/migrated workflows double-billing**: After migration, old + new workspace may run concurrently for months. Always compare daily run timelines across both workspace IDs in `system.lakeflow.job_run_timeline` to detect double-billing.

- **System table column names are inconsistent**: `system.billing.usage` uses `usage_metadata.warehouse_id`; `system.query.history` uses `compute.warehouse_id` and `statement_id` (not `query_id`); `system.compute.warehouses` uses `warehouse_size`.

- **Month-over-month cost "spike" normalization**: Always normalize to daily DBU rate before alarming — a 14x MoM spike was only ~13% daily increase because the prior month had 3 days of data vs 31 days.
- **Auto-stop disabled = always-on**: Health-check warm-keeping cost analysis is irrelevant for always-on warehouses; health checks cost only their direct query attribution, not a warm-keeping floor.
- **Consistent daily query counts (<5% variance) signal scheduled batch jobs**: Not interactive traffic — don't attribute them to user-facing latency budgets. This applies for SQL warehouses serving realtime UI/BI query.

- **Stuck Databricks job keeps full ephemeral cluster billed continuously**: Autoscaler does NOT scale to zero while a Spark job is "active" — timeouts are the most effective cost control lever.

- **OPTIMIZE without partition filter is catastrophically expensive**: Bare `OPTIMIZE <table>` on listing tables caused 4,590h waste/month; one run timed out burning 1,657h for nothing. Always scope with `WHERE date >= current_date - INTERVAL N DAYS`.

- **Cost attribution denominator must cover ALL warehouse queries**: Scoping the denominator to a filtered subset grossly inflates that subset's attributed cost. Use relative proportions, not absolute dollar figures, for prioritization.

- **Ephemeral cluster autoscale over-provisioning**: Short 10–30 min jobs have high boot-up overhead (3–5 min). Autoscaling to 10 workers is wasteful — limit `max_autoscale_workers` to 2–4 to cap scaling before the short job finishes. Saves up to 40% compute with negligible performance impact.

- **Autoscaling thrashing in sequential-module workflows**: When a DAG runs 20+ modules sequentially, each module's `spark.sql.shuffle.partitions=200` floods the task queue, scaling to max workers. After the stage completes, cooldown shrinks the cluster. Next module repeats. Fix: consider fixed-size cluster (e.g. stable pool of 4 workers) instead of wide elastic ranges (1–10) for sequential pipelines.

- **Super-linear cost scaling for large tenants (power-law skew)**: Cost per row is exponential, not linear. Small tenants (<1M rows) complete in-memory on 1–2 workers before autoscaler boots. Large tenants (50M–100M+ rows) spill to disk AND run on 5–10x larger clusters for longer. Top-10 tenants can account for 90%+ of total workload while representing <10% of client count. Optimization ROI is highest when targeting these standout tenants first.

- **Spot instance reclamation mid-run penalties**: Spot node terminations cause aborted tasks, JVM restarts, and NVMe shuffle file regeneration overhead. When reporting performance, always separate code-level execution efficiency (query plan changes) from infrastructure-level variance (Spot reclamation, cluster boot time) to avoid confounding analysis.

- **`system.compute.clusters` for Spot vs On-Demand detection**: Contains cluster configs, driver/worker node types, and `aws_attributes.availability` field to determine Spot vs On-Demand pricing mix.


- **Cost attribution query**: `system.billing.usage` — group by `usage_metadata.warehouse_id`, filter `record_type = 'ORIGINAL'`. Include failed/canceled queries separately — they represent real DBU spend. (databricks-warehouse-cost-optimization-analysis, omni-api-service_warehouse_f15f1d4fa5e32ffc_analysis.md)
- **`system.query.history` doesn't log Spark job cluster queries**: Only SQL Warehouse queries appear there. For CCP/Spark job cost analysis, use `system.billing.usage` filtered by `usage_metadata['job_id']` and correlate with `system.lakeflow.job_task_run_timeline`.
- **DBU cost bucketing query**: Most effective way to identify "looping idle" compute patterns — bucket runs by cost range using `system.billing.usage` joined with `system.billing.list_prices`.
- **`system.billing.account_prices` may be empty in CIQ environment**: Cannot get contracted rates from system tables; use `admin_catalog.account_usage.aws_cost_metrics_tags` (dbx-dev only) for AWS infra costs. `admin_catalog.account_usage.dbx_discounts` has discount rates.
- **VTL-to-SQL playback testing**: Replace `:param` placeholders, map table names to fully-qualified ephemeral `client_view_catalog.temp_ccp_<id>.e<run_id>__<table>` paths, strip `CREATE TABLE AS` wrappers → safe read-only `SELECT` runnable against production.

- **Databricks total cost = discounted DBU + AWS EC2**: EC2 billed separately (~2× discounted DBU, ~67% of total) and does NOT benefit from Databricks discount. Formula: `discounted_dbu = list_price × 0.57`; check `admin_catalog.account_usage.dbx_discounts` via `user-dbx-dev` MCP for contracted rates.

 **Discount factor**: 0.57 on Databricks list price is the CIQ contracted rate. Verify if this changes.

- **DBU ≠ total cost**: Databricks catalog prices (e.g., r5d.8xlarge = $1.44/hr) are **DBU-only**. AWS EC2 cost is billed separately and is typically ~2× the discounted DBU cost. Total hourly cost ≈ (DBU_list × 0.57) + EC2 ≈ DBU_list × 0.57 × 3. When proposing instance changes, always estimate both components. The EC2 portion (~67% of total) does not benefit from the Databricks enterprise discount.

- **AWS cost gaps**: The `aws_cost_metrics_tags` table may have missing dates. Treat as lower bound.
- 
- **Ephemeral clusters**: CCP job compute workflows use per-run ephemeral clusters. Each run = one dedicated cluster. Stuck jobs keep the full cluster (driver + all workers) provisioned and billed continuously.

- **`job_task_run_timeline` gotcha**: `execution_duration_seconds` is 0 on intermediate hourly rows. Only terminal rows (`result_state IS NOT NULL`) have the full duration.

- **Databricks Serverless ≠ cheap for I/O-bound work**: Serverless job compute bills for allocated driver resources × wall-clock time, not CPU utilization. For workloads that are 95% idle on CPU (waiting on API calls), you pay full provisioned-driver price for hours of HTTP wait. SQL Serverless is different — it bills per query, making it efficient for actual SQL work.

- **`system.query.history` limitation**: `system.query.history` only logs queries run on SQL Warehouses (DBSQL). It does NOT log SQL queries executed on classic ephemeral Spark job clusters. To profile classic compute Spark queries, inspect Spark UI logs or perform manual timing. Do not assume zero query activity from a classic job just because `system.query.history` is empty for its job_id.

- - **MCP server selection**: Use `user-dbx-dev` for queries involving `admin_catalog`. Use either for `system.*` tables.