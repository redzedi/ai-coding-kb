---
name: automation-resolve-wf-cost-incident
description: automation_resolve_wf May 2026 $13.2k cost spike — root cause and cluster-sizing waste finding
metadata:
  type: project
---

`automation_resolve_wf` (CCP ETL workflow, resolves retail-media automation records per client) had a cost spike in May 2026: $13,251 vs. a normal <$1,000/month baseline (Mar $386→Apr $1,105→May $13,251→Jun ~$180, all DBU+AWS combined, 43% CIQ DBU discount applied).

**Location:** workflow/module config in `commerceiq/esm-ccp-edm` (`ccp-configs/workflows/automation_resolve.yaml`, `ccp-configs/pyspark/automation_resolve/automation_resolve.yaml`); actual pyspark code in `commerceiq/esm-ingestion-notebooks` (`ccp_autoresolve/automation_resolve/{ca_resolve,va_resolve,RDSUtils,DatabricksUtils}.py`). Databricks job_id `827678491059167`.

**Root cause (incident, May 6-15):** run duration and count both spiked (~100→200 runs/day, individual runs stretching to 30-60min ERROR states) then a batch of 15 runs all started at 2026-05-14T05:00 UTC were mass-CANCELLED ~22min later — signature of a stuck-run backlog being manually flushed. No code or config commit exists in either repo across the whole incident window (esm-ingestion-notebooks last commit repo-wide is Aug 2025; esm-ccp-edm last commit touching this workflow is Jul 2025) — so this was an operational event, not a shipped bug/fix. Likely cause: an external dependency (RDS/Postgres "MDS" store, or the classifier API) got slow/unreliable, and the module's retry-with-backoff logic (5 retries + exponential backoff in `DatabricksUtils`, plus a 5x/10s-sleep merge retry loop in `ca_resolve.py`/`va_resolve.py`) kept runs hanging and piling up.

**Deeper finding — this workload is misusing Databricks Job Compute:** `system.compute.node_timeline` for the ~500 ephemeral clusters spun up during the incident (autoscaling 1-5 workers, `md-fleet.xlarge` both driver+worker) shows driver and worker CPU utilization both flat at ~4-5% even at p90, with near-zero I/O-wait. This is not a Spark/data-lake compute pattern — it's consistent with the process spending nearly all wall-clock time in Python-level `time.sleep()`/blocking network calls to RDS Postgres and an external classifier API. The autoscaling multi-node Spark cluster is essentially decorative; workers do almost nothing.

**Follow-up worth raising:** (1) fix/harden the retry logic against a flaky RDS/classifier dependency (circuit breaker, cap on total retry time, alerting on stuck-run backlog) — this is the direct cost-spike trigger. (2) separately, right-size or migrate this workload off autoscaling Job Compute clusters — it's fundamentally a sequential per-client orchestration script, not a distributed Spark job, so most of its steady-state DBU+AWS spend is waste regardless of the May incident. See [[dbx-job-compute-cost-completeness]] for the cost-attribution methodology used (DBU list price × 0.57 discount + `admin_catalog.account_usage.aws_cost_metrics_tags` for AWS infra).
