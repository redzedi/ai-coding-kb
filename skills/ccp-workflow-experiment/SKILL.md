---
name: ccp-workflow-experiment
description: Design, execute, and programmatically analyze offline testing experiments and physical execution profiles for Velocity Template Language (VTL) based SQL workflows on Databricks. Includes automated scan parsing, transitive DAG redundant scan mapping, and functional equivalence validation
---

# CCP Workflow Cost Optimization Experimentation Skill

This skill teaches agents how to design, compile, execute, and analyze offline testing experiments for Velocity Template Language (VTL) based SQL workflows (CCP) on Databricks SQL Warehouses, especially when operating under read-only permissions in production. NOTE: This validation has to be done on production data only.

---

## Prerequisites

1. (Optional) `is_vtl_file_changes_done` (True | False)
2. (Optional) Parameter values to run the SQL from the VTL file 

---

## Workflow Checklist

Copy and track progress with this checklist:

```markdown
Task Progress:
- [ ] Step 1: Analyze VTL templates for optimization opportunities (e.g., redundant joins, dual scans).
- [ ] Step 2: Implement the proposed refactoring changes directly on the `.vtl` template files.
- [ ] Step 3: Identify a live, valid historical execution run with necessary data volume.
- [ ] Step 4: Compile the VTL templates into raw SELECT statements using the compilation script.
- [ ] Step 5: Isolate variants for every optimization hypothesis (Control, Hypothesis A, Hypothesis B, Combined).
- [ ] Step 6: Execute all variants in production and verify functional equivalence (matching results).
- [ ] Step 7: Hand over Statement IDs to Suman to retrieve JSON query profiles.
- [ ] Step 8: Programmatically parse and critically analyze execution profiles and transitive DAG redundancies.
```

---

## Detailed Step-by-Step Instructions

### Step 1: Analyze VTL Templates
Review the target workflow's `*.vtl` files (specifically those containing `CREATE TABLE AS SELECT` queries) to detect cost bottlenecks:
- **Redundant lookback self-joins:** Left or inner joins calculating `MAX(scrape_date)` or `MAX(category_level1)` on lookup tables that are already deduplicated/filtered upstream (e.g., using `ROW_NUMBER() OVER (PARTITION BY comp_sku ... ORDER BY ... NULLS LAST) WHERE rn = 1`).
- **Dual table scans:** Subqueries executing group-by aggregates to find a latest date, then joining back to the same table to pull attributes. These should be replaced with a single-scan analytical window function.

### Step 2: Modify VTL Files
Directly update the `.vtl` files with the proposed refactorings. Maintain behavioral consistency and match existing code conventions exactly.

### Step 3: Identify Active Execution Parameters
CCP temporary tables created during workflows (e.g., inside schema `client_view_catalog.temp_ccp_<client_id>` with names like `e<execution_id>__<table_name>`) are ephemeral and expire after a few days. Before generating queries, you must find a valid, live run:
1. Run `SHOW TABLES IN client_view_catalog.temp_ccp_<client_id>` on Databricks.
2. Filter/parse the table names to locate live execution IDs (`eXXXXXX__competition_look_back`).
3. Query the Postgres metadata database to fetch parameters:
   ```sql
   SELECT execution_id, client_name, execution_status, execution_variables 
   FROM ccp_execute_schema.ccp_execution_request 
   WHERE execution_id = <execution_id>;
   ```
4. Extract the variables (e.g. `:client_id`, `:rundate`) to use for parameter substitution.

### Step 1, 2 & 3: *Alternate Path* when VTL changes and run parameters are given by caller

- **VTL file changes already done by caller** — Skip steps 1 and 2.
- **Identify control for the given parameter values** — For the given parameter values (e.g., client_id, start_date, end_date), find a run from production closest to these values to serve as control.

### Step 4 & 5: Compile VTL to Raw SQL & Isolate Hypotheses
Use the reusable compiler script located at `scripts/vtl_to_sql.py` (under the skill package directory) to generate raw read-only SQL queries. 

**When VTL changes and parameters are given:** There is only a single hypothesis being tested. The comparison is only between Hypothesis A and the control.

Generate separate SQL files to isolate each hypothesis:
1. **Control Query (Master):** Compiled from the original VTL code (retrieve from git history or `create_control.vtl`).
2. **Isolated Hypotheses:** One compiled query for each individual change (e.g., `query_optimized_phase2.sql` with redundant joins removed but dual scans kept).
3. **Combined Query:** A final query with all optimizations applied together.

Run the compiler script from the shell:
```bash
python3 scripts/vtl_to_sql.py <vtl_path> <output_path> <client_id> "'<rundate>'" <execution_id>
```

### Step 6: Execute & Verify Functional Equivalence
Execute each generated SELECT query in Databricks using read-only execution tools. 
- Ensure all queries return successfully.
- Compare their result sets row-by-row (or row counts/checksums) to guarantee **functional equivalence** (no regression risk).

### Step 7: Handoff Statement IDs
Share the Databricks Statement IDs generated by the executions with **Suman**. Ask him to retrieve the Query Profile JSON/text plan from the Databricks UI and save them in the `cursor-analysis` folder.

### Step 8: Programmatic Profile & DAG Analysis

#### A. Analyzing Transitive Scans across the Workflow DAG

**Option 1: Quick CLI-based scan detection** (preferred for identifying hot tables):
```bash
TABLE_NAME="ams.keywords"

# Find which modules scan this table (shows all references)
rg "$TABLE_NAME" ccp-configs/sql/ --files-with-matches --filename

# Count scans per module (shows hot tables)
rg "$TABLE_NAME" ccp-configs/sql/ --filename --count | sort -t: -k2 -rn

# Extract qualified table references across workflow (all schema.table patterns)
rg '\b([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\b' ccp-configs/sql/ -o | sort | uniq -c | sort -rn | head -20
```

**Option 2: Comprehensive transitive DAG analysis** (when full dependency mapping needed):
```bash
python3 scripts/analyze_wf_dag.py <workflow_yaml_path> <workspace_root_path>
```

Identify tables with high "Avoidable" counts. These are your top targets for converting to **Lazy Spark Temporary Views** or introducing **Materialization Checkpoints**.

#### B. Analyzing Individual Query Profiles

**Option 1: Quick CLI-based analysis** (preferred for simple checks):
```bash
# Extract physical scans from the profile
rg '(?:PhotonScan|Scan)\s+(?:parquet|delta)?\s*([a-zA-Z0-9_\.]+)' <query_profile_text_path> --only-matching

# Find redundant scans (same table appearing multiple times)
rg 'Scan.*([a-zA-Z0-9_\.]+)' <query_profile_text_path> -o | sort | uniq -c | sort -rn

# Count shuffles/exchanges
rg 'ShuffleExchange|ReusedExchange' <query_profile_text_path> | wc -l

# Find spill/memory pressure indicators
rg -i 'spill|memory pressure' <query_profile_text_path> --context 2
```

**Option 2: Comprehensive Python analysis** (when deep diagnostics needed):
```bash
python3 scripts/parse_query_profile.py <query_profile_text_path>
```

Review the results:
1. **Physical Scans:** Confirm that your target tables are scanned exactly **once** (Optimal status). If a table shows redundant scans, check for CTE branching or redundant subquery joins.
2. **Telemetry & Shuffles:** Check the ratio of shuffles. High numbers of reused exchanges confirm that Spark Catalyst is successfully reusing intermediate shuffles.
3. **Spills & Pressure:** Look at disk spill counts and byte metrics. Spills exceeding 100 MB indicate partition sizing or skew issues that require tuning via partition count modifications (e.g. `spark.sql.shuffle.partitions`).

---

## Reusable Companion Scripts

All utility and analysis scripts are checked into the `scripts/` subdirectory of this skill package.

### 1. VTL to SQL Compiler Script (`scripts/vtl_to_sql.py`)
Automates parameter substitution, qualified schema mapping, and raw `SELECT` query extraction.

#### Python Call Example:
```python
from scripts.vtl_to_sql import convert_vtl_to_sql

# Compiles VTL to raw read-only SQL
success = convert_vtl_to_sql(
    vtl_path="ccp-configs/sql/module/create.vtl",
    output_path="sandbox/compiled_query.sql",
    client_id=851,
    rundate="'2026-06-19'",
    execution_id=163453,
    extract_select=True
)
```

---

### 2. Query Profile & Scan Analyzer Script (`scripts/parse_query_profile.py`)
Programmatically parses a physical Spark physical plan or Databricks SQL execution profile to find redundant scans, shuffles, reused exchanges, and memory spills.

#### Python Call Example:
```python
from scripts.parse_query_profile import parse_query_profile

# Parses physical plan text file and prints diagnostic report
success = parse_query_profile(
    file_path="cursor-analysis/PROD-156316/keywords_performance_metric_data_run_4.txt"
)
```

---

### 3. Transitive DAG & Scan Analyzer Script (`scripts/analyze_wf_dag.py`)
Parses a CCP workflow definition YAML, builds its transitive dependency DAG, and crawls all constituting VTL SQL definitions to detect redundant scans across CTAS table boundaries.

#### Python Call Example:
```python
from scripts.analyze_wf_dag import analyze_transitive_scans

# Compiles workflow transitive dependency scans report
success = analyze_transitive_scans(
    workflow_path="ccp-configs/workflows/campaigns_workbench_wf.yaml",
    workspace_root="."
)
```
