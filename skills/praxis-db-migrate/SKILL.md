---
name: "praxis-db-migrate"
title: "DB Migrate"
description: "Guided relational DB migration between clouds — AWS RDS/Aurora (PostgreSQL/MySQL) -> GCP Cloud SQL or AlloyDB. Elicits source/target/scope/strategy, gates on the (non-obvious) replication prerequisites + network reachability, generates the migration commands (GCP Database Migration Service for continuous/low-downtime, or pg_dump/mysqldump for one-shot) + a cutover runbook, and VERIFIES with per-table row-count + checksum parity. Use when the user mentions migrating a relational database between clouds, RDS/Aurora to Cloud SQL/AlloyDB, Postgres/MySQL cross-cloud migration, database migration service, logical replication, CDC, or db cutover. Orchestrates DMS/dump tools (does NOT reinvent them); source DATA stays read-only."
triggers: ["cross-cloud database migration", "rds to cloud sql", "aurora to alloydb", "postgres migration", "mysql migration", "database migration service", "logical replication", "cdc migration", "db cutover", "pg_dump migrate"]
category: "migration"
tags: ["database", "postgres", "mysql", "rds", "aurora", "cloud-sql", "alloydb", "migration", "cdc", "read-only"]
icon: "🗄️"
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

# DB Migrate

Guided migration of a relational database from AWS RDS/Aurora (PostgreSQL or
MySQL) to GCP **Cloud SQL** or **AlloyDB**. This skill **orchestrates and
verifies** — it picks the strategy, surfaces the prerequisites people forget,
generates the exact commands, and proves correctness with row-count + checksum
parity. It does **not** reinvent a replication engine, and it **never mutates
source data**.

> This is a **guided runbook** for a data-plane move between clouds. It is
> distinct from any product "migration" feature — it drives the cloud-native
> migration service + dump tools and verifies the result; it does not import
> infrastructure into Terraform state (for that, see the terraform-import /
> zero-change-import skills).

## Tools this skill uses (works on both hosts)

Cloud discovery goes through the `cloud_cli` MCP (read-only, credentials
resolved server-side — the agent never sees secrets). Same capability, two
call styles depending on where this skill runs:

- **In the hosted Praxis agent** — call the MCP tool directly:
  `run_cloud_cli(integration_name="<acct>", command="rds describe-db-instances --output json")`.
- **Via the `praxis` CLI host** — shell the same call:
  `praxis mcp cloud_cli run_cloud_cli --arg integration_name=<acct> --arg command='rds describe-db-instances --output json'`.

Write commands **without** the provider prefix (`rds ...`, not `aws rds ...`).
The `gcloud database-migration` / `pg_dump` / `mysqldump` / `psql` / `mysql`
steps run locally (Bash) on the reachability host — identical in both hosts.

## Guardrails (verify + guard + reuse)
- **Source DATA is READ-ONLY.** Migration reads via dump or logical replication only — never `UPDATE`/`DELETE`/`TRUNCATE` on the source.
- **Enabling replication is a CHANGE — propose, don't auto-run.** Turning on logical replication / binlog, creating the replication user, and editing parameter groups are *printed for the user to run*; the skill never applies them.
- **Verify deterministically.** Don't eyeball "looks migrated" — run `verify.py` (per-table row count + checksum). Row count is necessary, not sufficient.
- **Idempotent target setup**; re-runnable. Secrets via env vars (referenced by name), never in the spec/logs.

## Step 0 — Strategy decision (gate)
Pick by downtime tolerance + engine + size:
- **Continuous / near-zero downtime** -> **GCP Database Migration Service (DMS)**: full load + CDC from the external RDS/Aurora into Cloud SQL/AlloyDB, then *promote*. Default for homogeneous Postgres->Postgres / MySQL->MySQL. (AWS DMS only if heterogeneous or GCP DMS can't reach/support the source.)
- **One-shot with a maintenance window** -> **`pg_dump`/`pg_restore`** or **`mysqldump`** -> import. Simpler; fine for small DBs or where a window is acceptable.
- **Huge DB + tight window** -> dump the schema first, load data with CDC to catch up, cut over at lag ~0.

State the choice and why; confirm the downtime tolerance with the user.

## Step 1 — Elicit inputs (spec)
Build a JSON spec like `scripts/spec.example.json`:
- **source**: `engine` (postgres|mysql|aurora-postgres|aurora-mysql), `version`, `host`, `port`, `databases[]`, `user`, `auth_env`, `tls`, `rds_id`/`cluster_id` (for discovery), `integration` (AWS account).
- **target**: `kind` (cloud-sql-postgres|cloud-sql-mysql|alloydb-postgres), `instance`, `version`, `host`, `port`, `user`, `auth_env`, `connection` (private-IP / Auth Proxy / connector).
- **scope**: `schemas[]`, `tables_include[]`/`tables_exclude[]`, `include_sequences` (default true), `include_large_objects`.
- **strategy**: `gcp-dms` | `dump-restore` | `aws-dms`.
- **downtime_tolerance**, **reachability.run_from** (host that reaches both, or the DMS connectivity method).

## Step 1a — Prerequisites + reachability gate (the part people miss)
Surface these to the user (they are CHANGES — propose, don't apply):
- **Postgres CDC prereqs:** `rds.logical_replication=1` in the RDS parameter group (reboot), `wal_level=logical`, a replication role with `REPLICATION` + `SELECT`, and `max_replication_slots`/`max_wal_senders` headroom. GCP DMS uses `pgoutput`/`pglogical`.
- **MySQL CDC prereqs:** `binlog_format=ROW`, `binlog_row_image=FULL`, sufficient `binlog retention hours`, a user with `REPLICATION SLAVE`/`REPLICATION CLIENT`.
- **Extensions/features:** every Postgres extension used must exist on the target (Cloud SQL/AlloyDB have a *supported* list); unsupported types/extensions must be remediated first.
- **Network path:** the source RDS SG must admit the migration connection (GCP DMS connection profile via VPN/Interconnect/peering, or RDS publicly-accessible + IP allowlist). Same reachability gate as any cross-cloud move — name the host/path.

## Step 2 — Discover source (cloud_cli)
Using the direct-tool form (CLI equivalent in "Tools" above):
```
run_cloud_cli(integration_name="<acct>", command="rds describe-db-instances --output json")          # or describe-db-clusters for Aurora
run_cloud_cli(integration_name="<acct>", command="rds describe-db-parameters --db-parameter-group-name <pg> --output json")   # check logical_replication / binlog
```
Confirm engine/version, size, Multi-AZ, parameter group (CDC readiness), encryption, endpoint. Verify the target Cloud SQL/AlloyDB exists and the version is compatible (`gcloud sql instances describe` / `gcloud alloydb clusters describe`).

## Step 3 — Generate plan + commands
```
python3 scripts/plan.py --spec spec.json
```
Emits, per strategy: the **prereq SQL/param changes** (clearly flagged *user runs these*), the **GCP DMS** connection-profile + migration-job commands (or the `pg_dump`/`pg_restore` / `mysqldump` pair), and a cutover runbook. Review before running.

## Step 4 — Run (gated)
Run from `run_from` after explicit user confirmation. GCP DMS: create connection profile -> create + start migration job (full load + CDC). Dump-restore: dump (read-only) -> restore into target.

## Step 5 — Verify parity (the centerpiece)
```
python3 scripts/verify.py --spec spec.json                 # row counts, all in-scope tables
python3 scripts/verify.py --spec spec.json --checksum      # + per-table content checksum
```
Read-only on both ends (whitelisted SELECT/SHOW/CHECKSUM only). Reports per-table row-count delta and checksum mismatches. Postgres: count + ordered-row md5 aggregate; MySQL: count + `CHECKSUM TABLE`.

## Step 6 — Cutover
Cut over only when: CDC lag ~ 0, `verify.py` row counts match, checksums clean. Then: **stop writers on the source**, drain CDC, run a **final `verify.py`**, **reset sequences / AUTO_INCREMENT on the target** (CDC does NOT advance them — classic post-migration footgun: new inserts collide with existing PKs), repoint apps, and *promote* the target (GCP DMS promote = stop replication, make it standalone). Keep the source read-only until the target is confirmed healthy.

## Notes
- `verify.py` ordered-checksum needs a stable key (PK) per table; keyless tables report `no-pk(skip)` for the checksum column — fall back to row-count parity there and accept it as probabilistic.
- AlloyDB target: same Postgres prereqs; columnar/extensions differences are target-side, not migration-blocking.
- Reset sequences (PG: `setval` from `max(id)`; MySQL: `ALTER TABLE ... AUTO_INCREMENT=`) is the #1 post-cutover bug — the runbook makes it explicit.
- **Validate against one non-prod DB pair before prod**; confirm `gcloud database-migration` flag names for your tooling version.
