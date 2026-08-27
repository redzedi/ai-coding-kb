---
name: "praxis-cloud-operations"
title: "Cloud Infrastructure Explorer"
description: "Query and explore cloud infrastructure (AWS, GCP, Azure) through org-level integrations using read-only CLI commands. Use when listing, describing, or inspecting cloud resources like EC2, S3, VPC, RDS, EKS, Lambda, or IAM configurations."
triggers: ["cloud", "aws", "gcp", "azure", "infrastructure", "ec2", "s3", "vpc", "rds", "eks", "lambda", "iam"]
version: "1.0"
category: "cloud"
tags: ["cloud", "aws", "gcp", "azure", "infrastructure", "read-only", "cli"]
icon: "☁️"
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

# Cloud Infrastructure Explorer

Query and explore cloud infrastructure through org-level integrations using read-only CLI commands.

## Prerequisites

This skill requires the `cloud_cli` MCP to be enabled on the agent. The available tools are:

- `sync_facets_accounts` — Auto-link cloud accounts already connected in Facets (idempotent)
- `list_cloud_integrations` — Discover available cloud accounts
- `run_cloud_cli` — Execute read-only CLI commands

## Workflow

```
┌──────────────────────────────────────────────────────────┐
│  0. AUTOLINK          sync_facets_accounts (idempotent)   │
│     ↓                 Inherit Facets-linked accounts      │
│  1. DISCOVER          list_cloud_integrations             │
│     ↓                 Returns: name, provider, region     │
│  2. SELECT            Pick integration by name            │
│     ↓                 (user may specify or you choose)    │
│  3. QUERY             run_cloud_cli(integration, command) │
│     ↓                 Read-only commands only              │
│  4. PRESENT           Parse JSON output, summarize        │
└──────────────────────────────────────────────────────────┘
```

### Step 1: Discover Integrations

**Always start here.** First call `sync_facets_accounts` (no arguments) to
auto-link any cloud accounts already connected in Facets — idempotent, and a
no-op if nothing new is linked. Then call `list_cloud_integrations` (no
arguments) to see what cloud accounts are available.

The response includes:
- `name` — Use this as `integration_name` in subsequent commands
- `provider` — aws, gcp, or azure
- `region` — Default region configured for the integration
- `metadata` — Additional details (account ID, project, etc.)

### Step 2: Select Integration

If the user specifies an account/integration name, match it to the list. If multiple integrations exist and the user hasn't specified, ask which one to use.

### Step 3: Run Commands

Call `run_cloud_cli` with:
- `integration_name` — The name from step 1 (required)
- `command` — CLI command WITHOUT the provider prefix (required)
- `region` — Optional region override

**CRITICAL: Do NOT include the provider prefix in the command.**
- Write `ec2 describe-instances`, NOT `aws ec2 describe-instances`
- Write `compute instances list`, NOT `gcloud compute instances list`
- Write `network vnet list`, NOT `az network vnet list`

The system automatically selects the correct CLI tool based on the integration's provider.

### Step 4: Present Results

Parse the JSON output and present it in a structured, readable format. Use tables for lists, highlight important fields, and summarize counts.

## Command Reference

### AWS Commands (without `aws` prefix)

**Compute:**
```
ec2 describe-instances --output json
ec2 describe-instances --filters "Name=instance-state-name,Values=running" --output json
ec2 describe-security-groups --output json
ec2 describe-vpcs --output json
ec2 describe-subnets --output json
ec2 describe-volumes --output json
```

**Networking:**
```
ec2 describe-vpcs --output json
ec2 describe-subnets --vpc-id vpc-xxx --output json
ec2 describe-route-tables --output json
ec2 describe-nat-gateways --output json
ec2 describe-internet-gateways --output json
ec2 describe-network-interfaces --output json
elbv2 describe-load-balancers --output json
elbv2 describe-target-groups --output json
```

**Storage:**
```
s3api list-buckets --output json
s3api list-objects-v2 --bucket my-bucket --output json
```

**Databases:**
```
rds describe-db-instances --output json
rds describe-db-clusters --output json
dynamodb list-tables --output json
dynamodb describe-table --table-name my-table --output json
elasticache describe-cache-clusters --output json
```

**Containers:**
```
eks list-clusters --output json
eks describe-cluster --name my-cluster --output json
ecs list-clusters --output json
ecs list-services --cluster my-cluster --output json
ecr describe-repositories --output json
```

**Serverless:**
```
lambda list-functions --output json
lambda get-function --function-name my-func --output json
```

**IAM:**
```
iam list-roles --output json
iam list-users --output json
iam list-policies --scope Local --output json
iam get-role --role-name my-role --output json
```

**Monitoring:**
```
logs describe-log-groups --output json
logs filter-log-events --log-group-name /aws/lambda/my-func --start-time 1700000000000 --output json
cloudwatch describe-alarms --output json
```

**Other:**
```
sts get-caller-identity --output json
route53 list-hosted-zones --output json
sns list-topics --output json
sqs list-queues --output json
secretsmanager list-secrets --output json
kms list-keys --output json
```

### GCP Commands (without `gcloud` prefix)

**Compute:**
```
compute instances list --format=json
compute instances describe INSTANCE --zone=ZONE --format=json
compute disks list --format=json
compute firewall-rules list --format=json
```

**Networking:**
```
compute networks list --format=json
compute networks subnets list --format=json
compute addresses list --format=json
compute forwarding-rules list --format=json
```

**Containers:**
```
container clusters list --format=json
container clusters describe CLUSTER --zone=ZONE --format=json
container node-pools list --cluster=CLUSTER --zone=ZONE --format=json
```

**Storage & Databases:**
```
sql instances list --format=json
storage buckets list --format=json
redis instances list --region=REGION --format=json
```

**IAM:**
```
iam roles list --format=json
iam service-accounts list --format=json
```

### Azure Commands (without `az` prefix)

**Compute:**
```
vm list --output json
vmss list --output json
```

**Networking:**
```
network vnet list --output json
network nsg list --output json
network public-ip list --output json
network lb list --output json
network application-gateway list --output json
```

**Containers:**
```
aks list --output json
aks show --name CLUSTER --resource-group RG --output json
```

**Storage & Databases:**
```
storage account list --output json
sql server list --output json
cosmosdb list --output json
redis list --output json
```

## Security Constraints

**Read-only enforcement** is applied at the system level. The following rules are enforced:

| Provider | Allowed operations | Blocked operations |
|----------|-------------------|-------------------|
| AWS      | list, describe, get, show, filter-log-events, tail | create, delete, update, put, modify, terminate, remove, start, stop, reboot, run, invoke |
| GCP      | list, describe, get, read, tail | All others |
| Azure    | list, show, get, query | All others |

Additionally:
- Shell metacharacters (`;`, `|`, `` ` ``, `$`, `(`, `)`, `{`, `}`, `<`, `>`, `&`) are blocked
- Commands are parsed safely via `shlex.split()` to prevent injection

**You cannot:**
- Create, modify, or delete any resources
- Execute arbitrary shell commands
- Access credentials directly (they are resolved server-side)

## Multi-Region Queries

To query a different region than the integration's default:

```
run_cloud_cli(
    integration_name="my-aws-account",
    command="ec2 describe-instances --output json",
    region="eu-west-1"
)
```

For comprehensive multi-region inventory, query each region separately and aggregate results.

## Common Patterns

### Infrastructure Inventory

1. List VPCs across all integrations
2. For each VPC, list subnets, security groups, route tables
3. Summarize with counts and CIDR ranges

### Resource Cost Analysis

1. List all running EC2 instances with instance types
2. List RDS instances with engine types and sizes
3. List EKS clusters with node counts
4. Present a summary table

### Security Audit

1. Check security groups for overly permissive rules (0.0.0.0/0)
2. List IAM roles and their attached policies
3. Check for unencrypted S3 buckets or RDS instances
4. Report findings with severity

### Troubleshooting

1. Describe the specific resource in question
2. Check related resources (security groups, subnets, route tables)
3. Look at CloudWatch logs or events
4. Correlate findings across services
