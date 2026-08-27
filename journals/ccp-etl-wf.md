---
name: ccp-etl-wf
description: CCP ETL workflow structure — repo layout, 3 module types (sql/pyspark/spark), YAML manifests, VTL templates, CCP CLI commands, and operational debugging tips
metadata:
  type: project
---

## CCP Workflow Structure

CCP orchestrates Databricks ETL via a **project → workflow → module** hierarchy. Three module types: **sql** (VTL templates + manifest in same repo), **pyspark** and **spark** (manifest-only — code lives in separate repos). Workflows define a DAG of modules with `dependsOn` for parallel execution. Each repo has `ccp-configs/` containing `project.yaml`, `workflows/*.yaml`, and `sql|pyspark|spark/<module>/<module>.yaml`. SQL modules also contain `create.vtl` (DDL), `postProcess.vtl` (DML/transforms), and `select.vtl` (query). Variables (`:client_id`, `:rundate`) are injected at runtime.

### Repo layout
```
ccp-configs/
  project.yaml              # name, projectPdKey
  workflows/
    my_wf.yaml               # outputModules, dependsOn, variables, warehouseConfig
  sql/<module>/
    <module>.yaml             # name, variables, dependsOn
    create.vtl                # CREATE TABLE ...
    postProcess.vtl           # INSERT/MERGE/DELETE with :var params
    select.vtl                # SELECT (often empty)
  pyspark/<module>/
    <module>.yaml             # + pysparkExecutableConfig {version, packageName, entryPoint}
  spark/<module>/
    <module>.yaml             # + executableConfig {type: java, packageName, version, entryPoint}
```

### Key YAML shapes

**Workflow** (`workflows/*.yaml`):
```yaml
name: "my_wf"
outputModules:
- name: "module_a"
  schema: "ams_cubes"
  outputTable: "target_table"
  updateType: "truncate_and_append"   # or append, merge
dependsOn: ["module_a"]
variables:
- {name: "client_id", type: "NUMBER", defaultValue: "0"}
warehouseConfig:
  tag: "DEMO_WH"
  size: "X_SMALL"
  databaseName: "ciq_catalog"
```

**PySpark module**:
```yaml
name: "my_pyspark_module"
dependsOn: []
pysparkExecutableConfig:
  version: "0.1.0"
  packageName: "my_package"
  entryPoint: "main"
```

**Spark (Java) module**:
```yaml
name: "my_spark_module"
dependsOn: []
executableConfig:
  type: java
  packageName: ams-cubes-spark-source
  version: 1.0.0-SNAPSHOT
  entryPoint: ai.commerceiq.package.ClassName
```

### CCP CLI commands
```shell
ccp --env beta configure      # set environment (beta/prod/qa)
ccp config                    # verify current config
ccp pyspark publish           # upload wheel to S3
ccp link                      # link branch to CCP
ccp status --job_id <ID>      # check link status
ccp trigger --file_name ./ccp-configs/payload.json   # execute workflow
ccp status --execution_id <ID>                       # monitor run
```

### Trigger payload (`payload.json`):
```json
{
  "clientName": "brand-name",
  "executionEntityInfo": {
    "branch": "feature-branch",
    "name": "my_wf",
    "project": "CUSTOM_AMS_CUBES"
  },
  "sqlConfig": {"size": "SMALL"},
  "executionVariables": [
    {"name": "client_id", "value": "1019"}
  ]
}
```

---

## Operational Tips

### CCP intermediate tables
Live under `client_view_catalog.temp_ccp_<client_id>` with prefix `e<execution_id>__<table_name>`. Table names must be **lowercase** — uppercase causes Unity Catalog resolution errors.

### Execution duration from system tables
`system.lakeflow.job_task_run_timeline` `execution_duration_seconds` is 0 on intermediate rows. Use `MAX(period_end_time) - MIN(period_start_time)` grouped by `run_id` for actual duration.

### Workflow discovery guardrails
- Check for `*lean_wf.yaml` variants before proposing new workflows — trimmed-down versions may already exist.
- Trace downstream dependencies before removing modules (e.g. `ams_performance_metrics` feeds the Lockout Service in the bidding engine).
- Cross-reference `rmm_utilize.client_specifics` RDS feature flags to detect dual-triggering.

### Deterministic window functions
Always add tie-breaker columns to `ORDER BY` in `ROW_NUMBER()` — e.g. `ORDER BY feed_date DESC NULLS LAST, comp_sku ASC`. Without tie-breakers, Spark chooses rows arbitrarily.

### Functional equivalence validation
Use bidirectional `EXCEPT` to prove query rewrites are equivalent:
```sql
(SELECT cols FROM original) EXCEPT (SELECT cols FROM optimized)
(SELECT cols FROM optimized) EXCEPT (SELECT cols FROM original)
```

### Getting exact per-module timing from Groundcover (not CCP's own APIs)
`ccp status --execution_id` only gives aggregate `totalTasks`/`finishedTasks`/`failedTasks` counts, no
per-module breakdown. `ccp get-execution-logs --execution_id` is frequently broken/empty (returns
malformed non-JSON, throws `JSONDecodeError` in the CLI). For real per-module timing, query Groundcover
(cluster `ciq-apps-beta` for beta) for `CcpExecuteObservabilityHelper` log lines — these emit the exact
duration CCP itself measured per task, no reconstruction needed:

```
cluster:ciq-apps-beta <execution_id> SUCCEEDED | fields _time, content | sort by (_time asc) | limit 150
```

Look for lines shaped like:
`Task <task_id> in execution <execution_id> reached terminal state SUCCEEDED (prev=RUNNING, duration=<N>s, client=<name>, task=<module_name>)`

and, for the whole workflow:
`Workflow execution <execution_id> reached terminal state SUCCEEDED (prev=RUNNING, duration=<N>s, ..., workflow=<wf_name>)`

This is the fastest, most reliable way to get a full module-by-module timing table for an A/B comparison —
far better than trying to pair `DatabricksSQLQueryExecutor` "Submitting query"/`JobStatus(state=...)` log
lines by statement ID (that works but is much more manual and error-prone). Bare-keyword searches
(`SUCCEEDED`, `Completed`) work as expected in gcQL for logs; `state=SUCCEEDED` with the `=` inline did NOT
match — use the bare keyword form instead.

Also useful: CCP job-compute executions (`dbxExecutionMode=SQL_JOBCOMPUTE_NO_SPARK`) show up in Groundcover
as a `DatabricksWorkflowRunnable` polling a wrapper Databricks Job (`pollJobStatus`, `jobId`/`runId`) before
any module-level `DatabricksSQLQueryExecutor` SQL submission appears — a `RUNNING` state with 0 finished
tasks for several minutes right after trigger is normal cluster/job startup, not a stuck run. The trigger's
`jarParams` JSON (visible in the `DatabricksWorkflowRunnable:224 Triggering databricks job` log line) is also
the definitive way to confirm which `executionVariables` (e.g. `rundate`) actually made it into the run,
independent of what the trigger payload file said.
