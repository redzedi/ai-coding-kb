---
name: dbx-job-compute-cost-completeness
description: Databricks job_compute cost analysis must include AWS infra cost, not just DBU list price
metadata:
  type: feedback
---

When estimating the cost of a Databricks Job Compute workflow, `system.billing.usage.usage_quantity * system.billing.list_prices` only gives the **DBU list-price cost**. It does not include the underlying **AWS infra cost** (EC2 instances, EBS, etc. that the job cluster runs on).

**Why:** Suman flagged that my DBU-only estimate (~$8,353 for May 2026) undershot the actual invoiced cost ($13,251) for `automation_resolve_wf` — the gap is the AWS infra layer sitting underneath job compute, which isn't captured by `list_prices` alone.

**How to apply:** For any Databricks job-compute cost investigation, pull AWS infra cost too and report DBU cost + infra cost together, not DBU cost alone as "the cost." `system.billing.cloud_infra_cost` is NOT populated in dbx-dev (0 rows) — use this query instead, which works in dbx-dev and is tagged per CCP workflow:

```sql
select start_date as ds, 'AWS Compute' as sku, tag_value as wf, sum(cost) as dbx_cost
from admin_catalog.account_usage.aws_cost_metrics_tags
where env='prod' and tag='ccp_workflow_name' and tag_value = '<workflow_name>'
and start_date between '<START_DATE>' and '<END_DATE>'
group by 1,2,3
```

Note: as of 2026-07, `admin_catalog.account_usage.aws_cost_metrics_tags` only has ~16-17 days of data per month populated (not full-month) — check `count(*)` per month before trusting a monthly total as complete.

**CIQ gets a 43% discount off Databricks list price.** Always apply `* 0.57` to any `system.billing.list_prices`-derived DBU cost before treating it as real spend, and before comparing/summing against actual invoiced numbers or AWS infra cost. This reconciled a ~$3,500 apparent gap on the `automation_resolve_wf` May 2026 cost-spike investigation (discounted DBU + AWS infra landed within ~1% of the actual invoiced total). See [[ccp-etl-wf]] and the `databricks-workflow-cost-optimization` skill, which should bake this in as a step.
