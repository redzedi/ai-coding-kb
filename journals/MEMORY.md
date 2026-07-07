
## Workflow
- [wf-general](./wf-general.md) — CIQ branching/deploy conventions, jenv+Maven setup, test disabling policy
- [wf-java-stack](./wf-java-stack.md) — Maven multi-module version chain updates

## Coding
- [java-coding-best-practices](./java-coding-best-practices.md) — Mockito matchers, Redis error handling, Java API gotchas
- [sql-coding-best-practices](./sql-coding-best-practices.md) — MySQL index column order, online index creation
- [spark-perf-coding-best-practices](./spark-perf-coding-best-practices.md) — PySpark/Databricks SQL performance patterns

## Architecture & Domain
- [ciq-ccp](./ciq-ccp.md) — CCP platform: what it is, repo roles, execution model
- [automation-resolve-wf-cost-incident](./automation-resolve-wf-cost-incident.md) — automation_resolve_wf May 2026 $13.2k spike root cause + Job Compute cluster-sizing waste finding
- [ccp-etl-wf](./ccp-etl-wf.md) — CCP ETL wf structure: repo layout, 3 module types (sql/pyspark/spark), YAML manifests, VTL templates, CLI commands, operational tips
- [bi-workflow](./bi-workflow.md) — BI layer: dashboard-service, brands-service, omni-service-api

## Databricks Analysis
- [dbx-cost-analysis-tips](./dbx-cost-analysis-tips.md) — cost optimization tips for SQL warehouse and job compute
- [dbx-job-compute-cost-completeness](./dbx-job-compute-cost-completeness.md) — job_compute cost = DBU list price + AWS infra cost, not DBU alone
- [dbx-perf-analysis-tips](./dbx-perf-analysis-tips.md) — Spark/DB query performance debugging

