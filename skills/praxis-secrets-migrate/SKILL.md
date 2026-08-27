---
name: "praxis-secrets-migrate"
title: "Secrets Migrate"
description: "Replicate a workload's secrets from AWS Secrets Manager -> GCP Secret Manager so External Secrets Operator (ESO) reconstructs a byte-identical Kubernetes Secret on GKE. Elicits which secret keys the workload actually needs, builds the AWS->GCP mapping, and replicates values with byte-identical read-back verification. Use when the user mentions migrating secrets, AWS Secrets Manager to GCP Secret Manager, replicating/copying secrets to GCP, External Secrets / ESO, or making a k8s secret match after a cloud move. NEVER creates secrets (an IaC secret_manager module does); values are held in memory only."
triggers: ["secrets migration", "aws secrets manager to gcp", "replicate secrets", "copy secrets to gcp", "external secrets", "eso secret sync", "match k8s secret after cloud move", "secret manager migration"]
category: "migration"
tags: ["secrets", "secrets-manager", "gcp-secret-manager", "eso", "external-secrets", "kubernetes", "migration", "operator-run"]
icon: "🔐"
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

# Secrets Migrate

Replicate the secret **values** a workload depends on from AWS Secrets Manager
to GCP Secret Manager, so that ESO's `dataFrom.extract` unpacks the same JSON
into the `<workload>-secret` Kubernetes Secret on GKE — an identical contract to
what it had on EKS. This skill **orchestrates `aws`/`gcloud` and verifies
byte-for-byte**; it does not create secrets and never touches source data
destructively.

## Who runs this, and on both hosts

Reading secret **values** requires AWS `secretsmanager:GetSecretValue` on the
in-scope secrets — a permission the read-only discovery/federation role
deliberately lacks. So **this is operator-run in every context**: an operator
whose shell has AWS creds with `GetSecretValue` **and** `gcloud` authenticated
as a principal with `roles/secretmanager.secretVersionAdder` runs
`scripts/replicate.py` locally.

- **In the hosted Praxis agent** — the agent plans the mapping and
  reviews output, but hands `scripts/replicate.py` to a human to run (it can't
  read secret values through the read-only gateway). Discovery of *which*
  secrets a workload needs can use the `k8s_cli` MCP (read the workload's ESO
  specs) — the agent never reads the secret values themselves.
- **Via the `praxis` CLI host** — the operator already has a shell; they run
  `scripts/replicate.py` directly with their own AWS/`gcloud` creds. Use
  `kubectl` locally for the ESO discovery in Step 0.

## Guardrails (verify + guard + reuse)
- **NEVER creates secrets.** The target GCP secret must already exist — created by an IaC `secret_manager` module (e.g. a Facets blueprint). This script only **adds a value version** to an existing secret; a missing target is an ERROR, not an auto-create. (Keeps secret *existence/policy* in IaC, values out of git.)
- **Values in memory only.** Secret material is read into memory and piped to `gcloud` via **stdin** — never written to disk, never logged, never passed as an argv. Output shows only a short **sha digest**, never the value.
- **Byte-identical verification.** After adding a version, it reads the value back and compares sha — proves the GCP value equals the AWS value. Row-count-style eyeballing is not enough.
- **Idempotent.** `--skip-unchanged` (default) avoids version churn; `--dry-run` reads + classifies + writes nothing.

## Step 0 — Scope: which secrets does the workload actually need?
Don't copy a whole account. Derive the in-scope set from the workload's **ESO `ExternalSecret`** specs (the `remoteRef`/`dataFrom` keys) and its Helm `envFrom`/`secretKeyRef` usage. That list = the AWS secret names to replicate.

## Step 1 — Build the mapping
A CSV `aws_secret_name,gcp_secret_id` (one row per secret) — see `scripts/mapping.example.csv`. The GCP id is the secret the `secret_manager` IaC module created for that workload.

## Step 1a — Prerequisites (gates)
- **Target secrets exist** — the `secret_manager` IaC module has been applied so every `gcp_secret_id` in the mapping already exists (empty is fine; the script adds the value version).
- **Operator creds** — AWS `GetSecretValue` + `gcloud` `secretVersionAdder` in the running shell.
- **GCP residency policy** — if an org policy restricts secret replication locations (`constraints/gcp.resourceLocations`), the IaC module must create secrets with **user-managed replication** in an allowed region; automatic/global replication will be rejected.

## Step 2 — Dry-run (classify + confirm targets)
```
python3 scripts/replicate.py --mapping mapping.csv --gcp-project <proj> \
    --aws-profile <profile> --aws-region <region> --dry-run
```
Each secret is classified:
- **ok** — flat JSON object of string values → safe to auto-copy (ESO-extractable).
- **nonflat** — JSON object with non-string values → auto-copy works, but ESO extraction is shape-sensitive → verify in a non-prod env first.
- **NEEDS-MANUAL** — binary, non-JSON plaintext, or a top-level JSON scalar/array → **not** `dataFrom.extract`-able → copy by hand with the right k8s wiring (a `data:` key mapping or a volume mount). The skill LOGS these; it does not silently skip them.

## Step 3 — Replicate + verify
```
python3 scripts/replicate.py --mapping mapping.csv --gcp-project <proj> \
    --aws-profile <profile> --aws-region <region>
```
Reads each AWS value, adds it verbatim as a new GCP version, reads it back, and reports `OK` (sha match) / `VERIFY-FAIL` / `NO-CHANGE`. Non-zero exit if any ERROR / VERIFY-FAIL / NEEDS-MANUAL remains — so it's safe in a gate.

## Step 4 — Handle NEEDS-MANUAL
Copy binary / non-JSON secrets by hand into the target with the correct k8s wiring, then re-run to confirm the rest.

## Step 5 — Verify the resulting k8s Secret
Once ESO syncs on GKE, confirm the `<workload>-secret` Secret has the same keys as on the source (compare `kubectl get secret ... -o jsonpath='{.data}'` key sets — compare KEYS, not values). The per-value byte-identity is already proven in Step 3.

## Notes
- ESO `dataFrom.extract` needs the secret to be a **flat JSON object** of string values — that's why `classify` flags anything else as manual.
- The read-only discovery role deliberately lacks `GetSecretValue`; this is why the flow reads no values as the agent and hands the run to an operator.
- **Validate against one non-prod workload's secret set before prod.**
