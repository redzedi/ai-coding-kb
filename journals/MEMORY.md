
# How to Use This Index

Each memory below lists **Triggers** — keywords/patterns that should prompt Claude to load that memory proactively during task orientation. When reviewing a task, Claude should scan for these keywords and load relevant memories WITHOUT waiting for you to point them out.

**Cross-links** show related memories that should be loaded together. Load all of them as a unit if any trigger fires.

---

## Behavioral
- [behavioral-verify-before-concluding](./behavioral-verify-before-concluding.md) — verify causal claims against exact config/full-population data before presenting as confirmed
  - **Triggers**: root cause analysis, cost investigation, debugging, "why is this happening", sizing/estimating impact, proposing a mechanism
  - **Scope**: Any investigation where a proposed explanation needs to be checked before being stated as settled — applies across all projects, not just CIQ-specific work

## Workflow
- [wf-general](./wf-general.md) — CIQ branching/deploy conventions, jenv+Maven setup, test disabling policy
  - **Triggers**: pom.xml, Maven, branching strategy, pre-commit hooks, test disabling, release
  - **Scope**: All CIQ Java project setup, build conventions, and testing policy

- [wf-java-stack](./wf-java-stack.md) — Maven multi-module version chain updates
  - **Triggers**: version bump, pom.xml, dependency management, multi-module, release prep, parent-pom
  - **Scope**: Any version chain coordination work across pom.xml files

## Coding
- [java-coding-best-practices](./java-coding-best-practices.md) — Mockito matchers, Redis error handling, Java API gotchas
  - **Triggers**: unit test, Mockito, Redis client, Java 11+, concurrency, test setup, mocking
  - **Scope**: Java unit testing patterns, Redis integration, common pitfalls in JVM code

- [sql-coding-best-practices](./sql-coding-best-practices.md) — MySQL index column order, online index creation
  - **Triggers**: schema migration, CREATE INDEX, ALTER TABLE, query perf, index design, DDL
  - **Scope**: MySQL schema changes, index strategy, migration safety

- [spark-perf-coding-best-practices](./spark-perf-coding-best-practices.md) — PySpark/Databricks SQL performance patterns
  - **Triggers**: PySpark slow, Databricks job tuning, shuffle, broadcast, partition pruning, query plan
  - **Scope**: PySpark ETL performance, Databricks cluster tuning, query optimization

## Architecture & Domain
- [ciq-ccp](./ciq-ccp.md) — CCP platform: what it is, repo roles, execution model
  - **Triggers**: CCP, ccp-configs, workflow module, campaign execution, CCP architecture
  - **Scope**: CCP platform design, responsibilities, and module layout
  - **Cross-links**: [[ccp-etl-wf]], [[ccp-execution-audit-log]]

- [ccp-execution-audit-log](./ccp-execution-audit-log.md) — CCP execution audit trail in RDS Postgres
  - **Triggers**: CCP execution debug, ccp_execution_request, RDS Postgres, audit trail, ccp-prod-metadata-db
  - **Scope**: Where/how CCP executions are logged, metadata queries
  - **Cross-links**: [[ciq-ccp]]

- [ccp-etl-wf](./ccp-etl-wf.md) — CCP ETL workflow structure: repo layout, modules, YAML, VTL, CLI
  - **Triggers**: ccp-sql-modules, ccp-pyspark-modules, VTL template, YAML manifest, ccp-run, workflow CLI
  - **Scope**: CCP ETL module structure, configuration, and operation
  - **Cross-links**: [[ciq-ccp]]

- [bi-workflow](./bi-workflow.md) — BI layer: dashboard-service, brands-service, omni-service-api
  - **Triggers**: dashboard, BI service, customer-facing reporting, brand analytics, omni-service
  - **Scope**: BI platform architecture and data flow

## Databricks Analysis
- [dbx-cost-analysis-tips](./dbx-cost-analysis-tips.md) — cost optimization for SQL warehouse and job compute
  - **Triggers**: cost optimization, warehouse spend, job cost, DBU, billing, cost-per-query, waste
  - **Scope**: Databricks cost analysis and reduction strategies
  - **Cross-links**: [[dbx-job-compute-cost-completeness]], [[spark-perf-coding-best-practices]]

- [dbx-job-compute-cost-completeness](./dbx-job-compute-cost-completeness.md) — job_compute cost = DBU list + AWS infra
  - **Triggers**: job cost model, DBU pricing, AWS compute, infrastructure cost, total cost calculation
  - **Scope**: Understanding Databricks job compute billing components
  - **Cross-links**: [[dbx-cost-analysis-tips]]

- [dbx-dev-vs-prod-env](./dbx-dev-vs-prod-env.md) — dbx-dev is local testing; use dbx-prod for real data
  - **Triggers**: dbx-dev, dbx-prod, environment selection, catalog, DESCRIBE HISTORY, table metadata
  - **Scope**: Choosing correct Databricks environment for queries, data availability
  - **Cross-links**: [[dbx-perf-analysis-tips]]

- [dbx-perf-analysis-tips](./dbx-perf-analysis-tips.md) — Spark/Databricks query performance debugging
  - **Triggers**: slow query, Spark DAG, shuffle, partitioning, scan size, query plan, job execution
  - **Scope**: Performance profiling and optimization for Spark/Databricks workloads
  - **Cross-links**: [[dbx-cost-analysis-tips]], [[spark-perf-coding-best-practices]]

