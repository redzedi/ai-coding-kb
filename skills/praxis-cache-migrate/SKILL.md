---
name: "praxis-cache-migrate"
title: "Cache Migrate"
description: "Guided Redis/Valkey cache migration between clouds or instances (e.g. AWS ElastiCache -> GCP Memorystore). Elicits source/target/scope/mode, decides whether a copy is even needed, generates a RIOT-based migration command + runbook, and monitors key parity + replication lag to a cutover decision. Use when the user mentions migrating/replicating/mirroring a cache, ElastiCache to Memorystore, Redis migration, Valkey migration, copying redis keys, cache cutover, or warming a new cache. Orchestrates RIOT (does NOT reinvent the copy engine); keeps the source strictly read-only."
triggers: ["cache migration", "redis migration", "valkey migration", "elasticache to memorystore", "replicate cache", "copy redis keys", "cache cutover", "warm a cache", "mirror redis"]
category: "migration"
tags: ["cache", "redis", "valkey", "elasticache", "memorystore", "migration", "riot", "read-only"]
icon: "🧊"
version: "1.0"
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

# Cache Migrate

Guided migration of a Redis/Valkey cache from a source (AWS ElastiCache,
self-managed Redis, another Memorystore) to a target (usually GCP Memorystore
Valkey/Redis). This skill **orchestrates and verifies** — it generates the
right [RIOT](https://github.com/redis/riot) invocation, produces a runbook for
the host that can reach both endpoints, and monitors parity. It does **not**
hand-roll a copy engine, and it **never writes to the source**.

## Tools this skill uses (works on both hosts)

Cloud discovery goes through the `cloud_cli` MCP (read-only, credentials
resolved server-side from org integrations — the agent never sees secrets).
The **same** capability is called two ways depending on where this skill runs:

- **In the hosted Praxis agent** — call the MCP tool directly:
  `run_cloud_cli(integration_name="<acct>", command="elasticache describe-replication-groups --output json")`
  (also `list_cloud_integrations` / `sync_facets_accounts` to discover accounts).
- **Via the `praxis` CLI host** — shell the same call:
  `praxis mcp cloud_cli run_cloud_cli --arg integration_name=<acct> --arg command='elasticache describe-replication-groups --output json'`

Write the CLI command **without** the provider prefix (`elasticache ...`, not
`aws elasticache ...`) — the gateway selects the CLI from the integration's
provider. The RIOT copy and the `redis-cli` parity checks run locally (Bash) on
the reachability host from Step 1a — those are the same in both hosts.

## Philosophy / guardrails (do not skip)
- **Source is READ-ONLY.** Only `SCAN`/`DUMP`/`INFO`/`DBSIZE`/`RANDOMKEY`. Never `FLUSH`, `DEL`, `MIGRATE`, `CONFIG SET`, or `SLAVEOF` against the source.
- **Idempotent target writes** (RESTORE with REPLACE). Safe to re-run.
- **Dry-run / verify-first**, then run the copy **gated on user confirmation**.
- **Secrets never touch logs/disk** — auth tokens come from a secret store / env var, referenced by name.
- **Don't reinvent RIOT** — generate its command, don't replace it.

## Step 0 — Decide if a migration is even needed (gate)
Cache data is often ephemeral/rebuildable. Before copying anything, ask:
- Is the data **derived/rebuildable** from a database or upstream, or is it **authoritative** (sessions, tokens, dedupe sets, sequence counters)?
- Is there a **hot cross-service dependency** on specific keys during cutover (e.g. one service reads keys another writes across the cloud link)?
- What is the **downtime tolerance**?

Decision:
- Rebuildable + no hot cross-cloud key dependency → **cold-start the target** (no migration; let it re-warm from the DB). Recommend this; it's simpler and safer. Stop here.
- Authoritative data, or hot keys needed at cutover → proceed to a **copy** (snapshot) or **live mirror**.

## Step 1 — Elicit inputs
Collect (ask the user; pre-fill from discovery in Step 2). Build a JSON spec like `scripts/spec.example.json`:
- **source**: `kind` (aws-elasticache-redis | aws-elasticache-valkey | self-managed | gcp-memorystore), `host`/`port` or cluster id, `cluster_mode` (enabled/disabled), `tls` (bool), `auth_env` (name of an env var holding the token — NOT the value), `integration` (for discovery).
- **target**: `kind` (gcp-memorystore-valkey | gcp-memorystore-redis | redis-cluster), `host`/`port`, `tls`, `auth_env`, `cluster_mode`.
- **scope**: `key_patterns` (default `*`; e.g. `session:*`, `logs-*`), `databases` (default `[0]`), `exclude_patterns`, `include_ttl` (default true).
- **mode**: `snapshot` (one-shot copy) | `live` (continuous mirror until cutover) | `verify` (parity check only, no copy).
- **reachability**: `run_from` — the host/pod that can reach **both** endpoints (see Step 1a).
- **expected_keys**: rough count for a sanity check (from `CurrItems`).

### Step 1a — The reachability gate (the part people miss)
Source ElastiCache is usually **locked to specific security groups / a VPC** and is *not* reachable from a laptop or arbitrary tooling. The migration must run from a host that reaches **both** the source (its VPC/SG) and the target (the GCP side, typically over the cross-cloud link/Interconnect). Establish this explicitly:
- A bastion/jumpbox in the source VPC's SG, **or** a pod on a cluster with both-side connectivity, **or** a VM peered to both.
- If no single host reaches both, the migration can't run directly — surface this; the options are a relay host on the cross-cloud link, or a dump-to-file → transfer → restore (RIOT `file-export`/`file-import`).

## Step 2 — Discover the source (cloud_cli)
Fill in size/topology/encryption and a key-count baseline. Using the direct-tool
form (see the CLI equivalent in "Tools" above):
```
run_cloud_cli(integration_name="<acct>", command="elasticache describe-replication-groups --output json")
run_cloud_cli(integration_name="<acct>", command="elasticache describe-cache-clusters --show-cache-node-info --output json")
# CurrItems baseline (CloudWatch) for the parity sanity check:
run_cloud_cli(integration_name="<acct>", command="cloudwatch get-metric-statistics --namespace AWS/ElastiCache --metric-name CurrItems --dimensions Name=CacheClusterId,Value=<id> --start-time <t0> --end-time <t1> --period 300 --statistics Maximum --output json")
```
Confirm: cluster-mode (sharded?), TLS/AUTH, node type/size, and whether the target Memorystore is sized to hold it. Verify the target exists (`gcloud redis instances describe <name> --region <r>`, run from a host/pod with GCP reach).

## Step 3 — Generate the plan + RIOT command
```
python3 scripts/plan.py --spec spec.json
```
Emits: the exact RIOT `replicate` command (with TLS/auth/key-pattern/mode), the runbook for `run_from`, and the read-only/idempotency notes. Review before running.

## Step 4 — Run (gated)
Run the generated RIOT command **from `run_from`**, after explicit user confirmation. `snapshot` exits when done; `live` keeps mirroring until you stop it at cutover.

## Step 5 — Monitor parity + lag
```
python3 scripts/monitor.py --spec spec.json --interval 30          # key-count parity loop
python3 scripts/monitor.py --spec spec.json --verify --sample 200  # sampled key fidelity (type/TTL/value hash)
```
For an ongoing live mirror, hand off recurring parity checks to a schedule (e.g. every 30 min, alert on divergence > threshold).

## Step 6 — Cutover criteria
Cut over only when: key-count parity within tolerance, sampled-key verification clean, live-lag ≈ 0 (live mode), and the target is reachable by the consuming services. For `live` mode: freeze writers (or accept eventual), confirm final parity, repoint clients, stop RIOT.

## Notes
- Cluster-mode source → RIOT handles cluster URIs; verify slot coverage.
- Big keysets over a slow link → prefer `snapshot` in batches by `key_pattern`, or RIOT `file-export` → transfer → `file-import`.
- This skill pairs with: `cloud_cli` (discovery), `k8s_cli` (run RIOT from a pod near the data).
- **Validate against one non-prod cache before trusting on prod.** RIOT flag names vary by version; confirm with `riot replicate --help`.
