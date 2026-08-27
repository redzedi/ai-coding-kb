---
name: "praxis-cloud-waste-finder"
title: "Cloud Waste Finder"
description: "Find wasted cloud spend across AWS, GCP, and Azure using read-only CLI commands — idle databases, unattached disks and IPs, idle compute, idle load balancers and NAT gateways, and old snapshots. Reports a ranked table with approximate monthly savings. Report-only: it never deletes or modifies anything. Use when asked to find waste, cut cloud costs, find idle/unused resources, or run a cost cleanup."
triggers: ["waste", "wasted spend", "cloud cost", "cost cleanup", "idle resources", "unused", "save money", "rightsize", "finops", "orphaned", "cost optimization", "unattached", "unused databases"]
version: "1.0"
category: "cloud"
tags: ["cloud", "aws", "gcp", "azure", "finops", "cost", "waste", "read-only"]
icon: "🧹"
---

> **Execution context** — this was authored for in-process MCP
> in agent-factory. You're running it from a local AI host installed by
> `praxis login`, so MCP tools are NOT directly callable here.
> Whenever this references an MCP tool, shell out to `praxis`:
>
> ```
> # Says:          run_k8s_cli(integration_name="prod", command="get pods")
> # You run:       praxis mcp k8s_cli run_k8s_cli \
>                  --arg integration_name=prod --arg command='get pods'
> ```
>
> Rewrite rule: any `<mcp>.<fn>(args)` or bare `<fn>` reference becomes
> `praxis mcp <mcp> <fn> --arg k=v ...` (or `--body '<json>'` for nested
> args). The CLI authenticates as your Praxis user and runs the call
> server-side under your org's managed cloud / k8s credentials — your
> laptop never holds AWS / kube / terraform secrets.
>
> If `praxis mcp <mcp> <fn>` returns 404, that tool isn't yet exposed
> by the gateway; fall back to whatever non-MCP path the body suggests.
>
> **`raptor` is the exception — it is a LOCAL CLI, not a gateway tool.**
> Run `raptor …` commands directly in your shell; never route them
> through `praxis mcp` (there is no `raptor_cli` gateway tool). If
> `command -v raptor` finds nothing, ask the user to install it; if
> `raptor whoami` fails, ask the user to run `raptor login` first. In
> `praxis status --json`, `tools` is an ARRAY — find the entry whose
> `tool` is `raptor`; if that entry's `stale` is true, offer to run
> `raptor upgrade` (ask first — never auto-run it).
>
> Raptor's profile is NOT praxis's profile — check the `raptor` block in
> `praxis status --json`. If `pinned` is true, prefix EVERY raptor command
> with `FACETS_PROFILE=<profile>` (env vars don't persist across shell
> calls). If `matches_praxis_url` is false unexpectedly, raptor is aimed at a
> DIFFERENT control plane than praxis: ask the user before any write.
>
> **Discovering what's available** — to see every MCP and function the
> gateway exposes, run `praxis mcp --json` (live fetch). A snapshot
> from your last `praxis login` lives at `~/.praxis/mcp-tools.json` —
> grep that file when you need the tool list without making a network call.

# Cloud Waste Finder

Find wasted cloud spend by scanning for resources that cost money but do little
or no useful work. This skill is **report-only** — it uses exclusively read-only
commands and never deletes, stops, or modifies anything. Presenting the findings
and letting the user decide is the whole job; actually cleaning up is a separate,
future step.

## Prerequisites

This skill requires the `cloud_cli` MCP to be enabled on the agent. Available tools:

- `sync_facets_accounts` — Auto-link cloud accounts already connected in Facets (idempotent)
- `list_cloud_integrations` — Discover available cloud accounts
- `run_cloud_cli` — Execute read-only CLI commands

All commands are passed **without** the provider prefix (`ec2 describe-volumes`,
not `aws ec2 describe-volumes`). The system picks the CLI from the integration's
provider. Only read verbs are allowed (list/describe/get/show); every mutating
verb is blocked at the system level, which is exactly what this skill wants.

## Workflow

```
┌───────────────────────────────────────────────────────────────┐
│  0. AUTOLINK    sync_facets_accounts (idempotent)              │
│  1. DISCOVER    list_cloud_integrations → pick account(s)      │
│  2. SCAN        Run the detection playbook for the provider    │
│  3. MEASURE     Pull CloudWatch/monitoring metrics for the     │
│                 "is it idle?" checks (14-day window)           │
│  4. ESTIMATE    Attach an approximate $/mo to each finding     │
│  5. REPORT      Ranked table, grouped by confidence, with a    │
│                 total and clear "estimate" + safety caveats    │
└───────────────────────────────────────────────────────────────┘
```

### Step 1 — Discover

Always call `sync_facets_accounts` first (no args, idempotent), then
`list_cloud_integrations`. If more than one account exists and the user didn't
name one, ask which to scan (or offer to scan all and aggregate). Note each
integration's `provider` and default `region`.

### Step 2–3 — Run the detection playbook

Run the checks for the integration's provider below. Each check lists the
**exact read-only command(s)**, the **heuristic** that flags waste, and a
**confidence** level. For "idle" checks you must pull a metric over a window —
default to the **last 14 days**. Build the window as epoch milliseconds (AWS
CloudWatch wants ISO-8601 or epoch; use `--start-time` / `--end-time`).

---

## AWS detection playbook

### HIGH confidence (near-certain waste)

**1. Unattached EBS volumes** — you pay for every provisioned GB even when the
volume is attached to nothing.
```
ec2 describe-volumes --filters "Name=status,Values=available" --output json
```
Flag every volume with `State == "available"`. Cost ≈ `Size(GB) × price_per_gb`
(gp3 ≈ $0.08, gp2 ≈ $0.10, io1/io2 higher — see pricing note). Confidence: HIGH.

**2. Unassociated Elastic IPs** — an allocated EIP not attached to a running
instance is billed hourly.
```
ec2 describe-addresses --output json
```
Flag an address **only if it has no `AssociationId`** — allocated but attached
to nothing. Do NOT flag on a null `InstanceId` alone: an EIP fronting a NAT
gateway, NLB, or bare ENI legitimately has an `AssociationId` (and a
`NetworkInterfaceId`) but no `InstanceId`. Edge case: an EIP associated to a
*stopped* instance still bills — cross-check against the stopped-instance list.
Cost ≈ **$3.60/mo** each. Confidence: HIGH.

**3. Old / orphaned EBS snapshots** — snapshots whose source volume no longer
exists, or that are very old.
```
ec2 describe-snapshots --owner-ids self --output json
```
Flag snapshots older than **90 days**; mark as orphaned if `VolumeId` no longer
appears in `describe-volumes`. Cost ≈ `Size(GB) × $0.05`. Confidence: MEDIUM–HIGH.

### MEDIUM confidence (likely waste — confirm before acting)

**4. Idle RDS / Aurora databases** — a database nobody connects to.
```
rds describe-db-instances --output json
rds describe-db-clusters --output json
```
For each instance, check connections over 14 days:
```
cloudwatch get-metric-statistics --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=<db-id> \
  --start-time <ISO 14d ago> --end-time <ISO now> \
  --period 86400 --statistics Maximum Sum --output json
```
Flag if `Maximum` connections is **0** across the whole window (truly unused) —
or ≤1 (only monitoring/health-check traffic). Cost ≈ instance-class price ×
(×2 if Multi-AZ) + allocated storage. Confidence: MEDIUM–HIGH.
⚠️ Guard: a DB can be a warm standby or DR replica — see false-positive guards.

**5. Idle EC2 instances** — running but doing nothing.
```
ec2 describe-instances --filters "Name=instance-state-name,Values=running" --output json
cloudwatch get-metric-statistics --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=<instance-id> \
  --start-time <ISO 14d ago> --end-time <ISO now> \
  --period 86400 --statistics Average Maximum --output json
```
Flag if `Maximum` CPU < **5%** for the whole window. Cost ≈ on-demand price for
the instance type. Confidence: MEDIUM.

**6. Stopped EC2 instances** — compute is free while stopped, but attached EBS
still bills.
```
ec2 describe-instances --filters "Name=instance-state-name,Values=stopped" --output json
```
Flag instances stopped a long time (check `StateTransitionReason` date). Report
the cost of their attached volumes, not the instance. Confidence: MEDIUM.

**7. Idle load balancers** — an ALB/NLB with no targets or no traffic.
```
elbv2 describe-load-balancers --output json
elbv2 describe-target-groups --output json
elbv2 describe-target-health --target-group-arn <arn> --output json
cloudwatch get-metric-statistics --namespace AWS/ApplicationELB \
  --metric-name RequestCount --dimensions Name=LoadBalancer,Value=<lb-name> \
  --start-time <ISO 14d ago> --end-time <ISO now> \
  --period 86400 --statistics Sum --output json
```
Flag LBs with **no healthy targets** or `RequestCount` Sum == 0 over 14 days.
Cost ≈ **$16–22/mo** base (+ LCU). Confidence: MEDIUM.

**8. Idle NAT gateways** — expensive even when unused.
```
ec2 describe-nat-gateways --output json
cloudwatch get-metric-statistics --namespace AWS/NATGateway \
  --metric-name BytesOutToDestination --dimensions Name=NatGatewayId,Value=<id> \
  --start-time <ISO 14d ago> --end-time <ISO now> \
  --period 86400 --statistics Sum --output json
```
Flag NAT gateways with ~0 bytes over 14 days. Cost ≈ **$32/mo** base + data.
Confidence: MEDIUM.

### Optimization (not waste, but easy savings — report separately)

**9. gp2 → gp3 volumes** — from the `describe-volumes` output, any `gp2` volume
can usually move to `gp3` for ~20% less. Report as an optimization, not waste.

---

## GCP detection playbook (commands without `gcloud` prefix)

- **Unattached persistent disks** — `compute disks list --format=json`; flag
  disks with no `users` field. Cost ≈ `sizeGb × ~$0.04` (pd-standard) to
  `~$0.17` (pd-ssd). HIGH.
- **Reserved-but-unused static IPs** — `compute addresses list --format=json`;
  flag `status == "RESERVED"` (not `IN_USE`). Cost ≈ **$7.20/mo**. HIGH.
- **Old snapshots** — `compute snapshots list --format=json`; flag > 90 days. MEDIUM.
- **Idle Cloud SQL** — `sql instances list --format=json`; flag `RUNNABLE`/stopped
  instances, and any you can confirm idle. (Connection metrics via CLI are
  limited; state the confidence honestly.) MEDIUM.
- **Idle Compute Engine VMs** — `compute instances list --format=json` +
  monitoring where available; flag by low utilization if metrics accessible. MEDIUM.

## Azure detection playbook (commands without `az` prefix)

- **Unattached managed disks** — `disk list --output json`; flag
  `diskState == "Unattached"`. Cost ≈ tier/size dependent. HIGH.
- **Unassociated public IPs** — `network public-ip list --output json`; flag any
  with no `ipConfiguration`. Cost ≈ **$3–4/mo**. HIGH.
- **Old snapshots** — `snapshot list --output json`; flag > 90 days. MEDIUM.
- **Deallocated VMs with retained disks** — `vm list -d --output json`; flag
  long-deallocated VMs (disks still bill). MEDIUM.

---

## Step 4 — Estimating cost (be honest that it's approximate)

The cloud CLIs **do not return prices**. Estimate with the approximate
`us-east-1`-ish on-demand reference below, and **always label totals as
estimates**. Prices vary by region, commitment (Savings Plans / CUDs / Reserved),
and tier — so present a *range* or an "approx" figure, never a false-precision number.

| Resource | Approx cost |
|---|---|
| EBS gp3 / gp2 | $0.08 / $0.10 per GB-month |
| EBS snapshot | $0.05 per GB-month |
| Unassociated Elastic IP (AWS) | ~$3.60/mo |
| GCP reserved static IP | ~$7.20/mo |
| Azure unassociated public IP | ~$3–4/mo |
| ALB/NLB base | ~$16–22/mo |
| NAT gateway base | ~$32/mo + data |
| EC2 (varies wildly) | look up the instance type; e.g. m5.large ≈ $70/mo |
| GCP pd-standard / pd-ssd | ~$0.04 / ~$0.17 per GB-month |

**Optional cross-check with actuals** (AWS): `ce get-cost-and-usage` (Cost
Explorer) is read-only and can confirm real service-level spend. Per-resource
cost needs resource-level granularity enabled; if it isn't, stick to the
reference estimates and say so.

## Step 5 — Report format

Present findings as a ranked table, **grouped by confidence** (HIGH first), with
a total. Sort within a group by estimated $/mo descending.

```
## 🧹 Cloud waste found in <account> (<region(s)>, last 14 days)

Estimated potential savings: **~$X–Y/month** (approximate — see notes)

### High confidence — safe to clean up
| Resource | Type | Why it's waste | Approx $/mo |
|----------|------|----------------|-------------|
| vol-0abc… | Unattached EBS (100 GB gp3) | Not attached to anything | ~$8 |
| eipalloc-… | Unassociated Elastic IP | Allocated, attached to nothing | ~$3.60 |

### Medium confidence — confirm before removing
| Resource | Type | Why it's flagged | Approx $/mo |
|----------|------|------------------|-------------|
| payments-old | RDS db.t3.medium | 0 connections in 14 days | ~$50 |
| my-alb | ALB | 0 requests in 14 days, no targets | ~$18 |

### Notes & caveats
- Costs are **estimates** (region/commitment pricing varies).
- Medium-confidence items may be warm standbys, DR, or seasonal — verify first.
- This scan is read-only. Removing anything is a separate, deliberate step.
```

If nothing is found, say so plainly and note what was checked — a clean bill of
health is a valid, useful result.

## False-positive guards (state these; don't silently assume)

Before calling something "waste," consider — and flag in the report — these
legitimate reasons a resource can look idle:

- **Warm standby / DR** — a zero-connection DB or idle instance may be a
  deliberate failover target.
- **Recently created** — anything younger than the metric window (14 days) has
  incomplete data; note "insufficient history."
- **Batch / seasonal** — month-end jobs, quarterly reports. A 14-day window can
  miss them; mention longer windows if the user cares.
- **Snapshots as backups** — old snapshots may be intentional retention. Flag
  orphaned ones (source volume gone) with higher confidence than merely-old ones.
- **Cross-account / shared** — an EIP or LB may front something in another
  account you can't see.

When in doubt, put the item in MEDIUM (or lower) confidence and say why.

## Hard rules

- **Read-only, always.** Never run create/delete/modify/stop/terminate. The
  system blocks these anyway; do not try to work around it.
- **Never claim exact savings.** Approximate ranges only, clearly labeled.
- **Never auto-remove.** Recommending is fine; the user (or a future cleanup
  step) does the acting.
- **Query each region you care about** — most `list`/`describe` calls are
  regional. For a full picture, iterate regions and aggregate.
- **An auth/credential error is NOT a clean result.** If a command returns a
  login/credential failure (e.g. Azure `AADSTS7000215`/`AADSTS7000222` expired
  or invalid client secret, AWS `ExpiredToken`, GCP auth error), report that
  account as **"not scanned — credential issue"** and continue with the others.
  Never present an un-scannable account as having zero waste.
