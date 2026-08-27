---
name: "praxis-zero-change-import"
title: "Facets Zero-Change Import"
description: "Adopt a pre-existing cloud estate (GCP/AWS/Azure, MongoDB Atlas, …) into Facets-managed Terraform at ZERO CHANGE — read-only import, hard-gated on a 0 replace / 0 destroy / 0 real-change plan. Use when adopting an existing production estate without mutating it. Teaches via real war-stories. Pairs with the module-authoring and per-resource import skills."
triggers: ["zero change import", "adopt estate", "import existing infrastructure", "zero drift", "bring under terraform", "read-only import", "import production"]
version: "1.0"
category: "infrastructure"
tags: ["terraform", "import", "zero-change", "gcp", "aws", "atlas", "infrastructure", "raptor"]
icon: "🧱"
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

# Facets — Zero-Change Import of Existing Infrastructure

Adopt a live production estate into Facets **without changing anything**. Proven on a
single ~1,000-resource GCP estate (hundreds of Pub/Sub topics + subscriptions, dozens of Redis,
GCS, Cloud SQL and Cloud Tasks resources + network + GKE & its node pools + one MongoDB Atlas
cluster), all read-only / 0-drift.

This is the *method, philosophy, and the traps*. For module-authoring CLI mechanics
(init, set-spec, output types, providers) use **praxis-build-facets-module**; for the
per-resource import-block mechanics (incremental imports.tf, `depends_on` removal, diff
reconciliation) use **praxis-terraform-import**.

> **The one invariant:** the import plan must be 0-change — `0 to change, 0 to destroy`,
> nothing `must be replaced`. The only benign diffs are `scratch_string.release_metadata`
> (Facets per-module metadata) and additive `Changes to Outputs`. If a plan wants to
> replace or destroy a real resource, **the module is wrong — fix the module, never
> loosen the gate.** The wall is the feature.

## Tools this skill uses

Cloud and cluster recon route through MCP tools that exist both in a normal Facets session
and via the praxis CLI gateway — reference them by name, no special wire syntax:

- `run_cloud_cli` — read-only recon against a cloud integration (`integration_name` + `command`
  with the provider prefix omitted; `jq_expression` to filter JSON). AWS/GCP/Azure.
- `run_k8s_cli` — read-only cluster scan (e.g. to find a connection string a workload uses).

Raptor commands (`raptor module …`, `raptor create iac-module`, `raptor apply resource`,
`raptor create release --plan`, `raptor create custom-release`, `raptor logs release`,
`raptor get …`) run directly as `raptor …` — the CLI is already installed and authenticated
(`raptor login`); RBAC + audit are enforced server-side.

## Philosophy (why each rule exists)

- **0-change is the whole discipline.** The gate once caught
  `~ enable_object_retention = true -> false # forces replacement` on live GCS buckets —
  dozens of buckets were one `apply` away from destroy+recreate of production data. The plan,
  not your model, is the authoritative read of live.
- **Read-only posture by default.** Assume viewer creds only; anything needing a write
  (labels, IAM) is `# TODO(write-creds)`. A read-only cred is a *safety net* — an
  accidental in-place update 403s instead of mutating — but don't lean on it: the gate
  must still require **0 in-place change**, not just 0 destroy.
- **Fix the module, never loosen the gate.** `--allow-destroy` / `--skip-validation` on
  shared prod are off the table (the latter is correctly classifier-blocked as a blind
  apply that could break provider wiring for every module on the CP).
- **Model from LIVE, not the customer's repo.** Their tfvars drift from reality
  (aspirational config never applied; resources created by hand). Repo = managed/unmanaged
  split + module *shape*; **live = source of truth for values**.
- **Input-driven over spec for structural deps.** project/region/credentials from the
  `cloud_account` input; VPC/subnet from `network_details`; cluster from
  `kubernetes_details`. Keeps modules reusable and the import 0-drift.
- **Blueprint env-agnostic, overrides env-specific.** Region, zones, names, IP allowlists,
  webhook URLs → env override (`x-ui-overrides-only`). Moving a value blueprint→override is
  provably 0-drift (resolved spec identical).
- **POC before batch.** Prove 1 simple + 1 of each tricky variant end-to-end, then fan out
  (~100/batch).
- **Keep creds server-side; never pull secrets into context.** Facets injects the provider
  config from the account's output mapping — you never need the secret. (Extracting Atlas
  API keys from release logs was correctly denied; the apply worked anyway.)
- **Inform the customer, don't block them.** Per-type milestone updates (✅ + zero-drift +
  running total) and access asks go to the customer channel; framework gaps go to the
  eng/infra channel. Never mix blockers into the customer channel.

## Judgment calls that shaped this (operator decisions — with the concrete moment)

The human calls that bent the method the right way. Each is a real moment; the pattern
(the *when*) matters more than the instance.

- **Flag-pattern the echo, don't model it.** Cloud SQL echoed a disabled `psc_config` on
  12+ private-IP instances; modeling its computed sub-fields churned every plan. Call:
  emit nothing on import (a `dynamic "psc_config"` gated on a `psc_enabled` flag), so the
  disabled echo is a no-op; a *new* instance flips the flag to manage PSC cleanly.
  *When:* the thing you'd model is an API echo, not config you own.
- **Model the real one; ignore only the truly un-modelable.** Reversed an initial "keep
  modeling them" once shown the provider needs a `bucket`/`domain` to even declare
  `sql_server_audit_config`/`active_directory_config` — so those get `ignore_changes`,
  while `psc` (declarable) gets the flag pattern. *When:* separate "I can declare this"
  from "the provider literally won't let me."
- **"Env-specific values go in overrides — hope you didn't put it in blueprint?"** Caught
  `region`, redis `location_id`, mysql `zone`/`backup_location`/`authorized_networks_json`,
  GCS `bucket_name`/`location`, and pubsub `webhook_url` sitting in the blueprint; moved
  them to the prod override + marked `x-ui-overrides-only`. Re-plan proved 0-drift.
  *When:* any value that differs per env/region → override; blueprint stays portable.
- **"Cloud account should be an input to get region; the VPC is an input, not a spec
  field."** → `region = coalesce(var.inputs.cloud_account.attributes.region, "us-central1")`;
  network from a `@facets/gcp-network-details` input; cluster from `@facets/gke`. *When:*
  it's a dependency on another resource, not a tunable → input.
- **Reuse the standard module's output contract — and match it exactly.** GKE had to expose
  BOTH `@facets/gke` (default) AND `@facets/kubernetes-details` (attributes, carrying the
  kubernetes/helm providers via exec-auth); the network standard, conversely, declared only
  `@facets/gcp-network-details` — match what's there, no more, no fewer. *When:* check the
  canonical module's shape + outputs before authoring schema; don't assume the count.
- **Var-wire a shared `GCP_DEFAULT_ZONE`, override only the exceptions.** Set the project
  variable `GCP_DEFAULT_ZONE=us-central1-b`; the redis instances in `-b` inherit
  `${blueprint.self.variables.GCP_DEFAULT_ZONE}`, only those in `-a/-c/-f` get a per-
  instance override — and mysql `zone` reuses the *same* variable. Chosen over per-instance
  values and over a per-type variable. *When:* one common default + a few exceptions.
- **Region as an override-only field on `cloud_account/gcp`.** Set `spec.region=us-central1`
  once in the prod override; every module coalesces from `cloud_account.attributes.region`.
  *When:* a single env value many resources derive from.
- **"Still do a plan and check."** Refused "it should be fine" every time — e.g. after
  moving `webhook_url` to overrides, re-gated all subscriptions to confirm only
  `scratch_string` moved. *When:* always; assumption is the enemy of 0-change.
- **"Plan only."** Kept the entire Atlas effort read-only until explicitly choosing to
  apply. *When:* default to plan; apply is a separate, explicit decision.
- **The three Atlas pushes that cracked the provider gap:** (1) *"Are you doing a selective
  plan of **both**?"* — a targeted plan hit only the Atlas cluster module and dropped the
  Atlas *account* module (the provider supplier) from the graph; target both. (2) *"See the
  gcp cloud account code & its output type"* — diffing against the known-good
  `@facets/gcp_cloud_account` localized it. (3) *"This is not correct"* — refused a
  "framework can't do it" conclusion, which forced finding the real root cause: the ROOT
  tfmain lacks the non-hashicorp source, so the root-level `import{}` defaults to
  `hashicorp/mongodbatlas`. *When:* a "platform limitation" usually means an unfinished
  diagnosis — pressure-test before declaring defeat.
- **"Don't enable the callback now — use read-only access."** Disabled the `facets-callback`
  (cluster-admin write) once the read-only `run_k8s_cli` gateway proved enough to scan the
  cluster (found the Atlas connection in a workload's env). *When:* take the least-privilege
  path that does the job; a prod write is a separate, deliberate decision.
- **"Import the MongoDB VMs as plain self-managed VMs."** Chose ordinary
  `google_compute_instance` over a bespoke Mongo module for the self-hosted Mongo VMs since
  they're migrating to Atlas anyway. *When:* match modeling effort to the resource's
  future, not its current specialness.
- **Prove the fix on one, queue the rest as a tracked retrofit — don't stop the line.** When
  the blueprint-vs-override mistake surfaced mid-import, the call was *fix network now* (prove
  the override pattern, re-gate 0-drift) and *retrofit the earlier types in a follow-up task*
  (a tracked retrofit, handed to a background agent — re-plan only, no apply) — not halt to
  refactor, nor leave it unfixed. *When:* a structural mistake is found mid-stream — fix
  forward on the current unit, track the backfill.
- **Scope is the customer's call — ask, don't assume.** For the hand-created (clickops)
  Pub/Sub topics and the analytics layer (BigQuery/Datastream), posted the
  in-or-out-of-scope question to the customer channel instead of importing on a guess.
  *When:* "is this ours to manage?" is an ownership question, not a technical one — surface it.
- **Granted autonomy — but only inside the gate.** "Import after gating is confirmed without
  asking" + "post milestone updates without asking" — yet every apply still HARD-gates on
  0-change, and prod writes / non-clean plans stay human-gated. *When:* automate the safe,
  repeatable steps; keep the irreversible ones human.

## The flow (what mutates, what doesn't)

```
RECON   read-only recon, no local creds:
          run_cloud_cli(integration_name=<int>, command='storage buckets list --format=json',
                        jq_expression='[.[]|{…}]')
        + read the customer's TF for managed/unmanaged split + module shape.   MUTATES: nothing
MODEL   build/extend <intent>/<flavor> module (raptor module init/set-spec/create-output-type/
          set-output-provider), every attribute driven from live; raptor create iac-module
          --publish.                                                            MUTATES: module catalog
PREP    deploy cloud_account ONCE (targeted release) so its outputs (project_id, region,
          credentials…) populate — a no-op deploy (data sources + outputs only), ZERO cloud
          infra. Env must be LAUNCHED (a stopped env can't release).  MUTATES: Facets state (no cloud)
DOC     one JSON doc per live resource (kind/flavor/version/metadata.name/inputs/spec),
          values from live; raptor apply resource -p <project> -f <dir>. MUTATES: BLUEPRINT only (not cloud)
IMPORT  root-level import{} per resource (module address → provider-native id), base64-encoded
          and injected via a custom-release -c command. Already-imported = NO-OP.
GATE    plan-only custom release → poll → logs → grep verdict.                  MUTATES: nothing
APPLY   same recipe, terraform apply -auto-approve, only after a clean gate.    MUTATES: imports to state
SPLIT   move env-specific values to env override; mark x-ui-overrides-only; re-plan = 0-drift.
```

The GATE/APPLY custom-release recipe (the `-c` CSV parser chokes on bare quotes → **always
base64 the import.tf**):
```bash
raptor create custom-release -p <P> -e <E> --no-refresh \
  -c "echo '<b64-import.tf>' | base64 -d > imports.tf" \
  -c "terraform init -input=false" \
  -c "terraform plan -input=false -target=module.level2.module.<intent>_<resourcename>"
```

**Never `sleep`/`tail` to wait for the release** — poll its status, then fetch logs once and
grep the verdict:
```bash
while true; do
  STATUS=$(raptor get releases -p <P> -e <E> <release-id> -o json 2>/dev/null | grep -o '"status":"[^"]*"' | head -1)
  echo "$STATUS"
  if echo "$STATUS" | grep -qE 'COMPLETED|FAILED|SUCCESS'; then break; fi
  sleep 15
done
raptor logs release -p <P> -e <E> <release-id> --stream \
  | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -E 'Plan:|must be replaced|will be destroyed|Error:'
```
Capture the release id from `-o json`, never table output.

## Module-authoring rules (the import-friendly module)

- **Resolve every field with `lookup(local.spec, "x", <default>)` in `locals` — NOT
  `optional()` defaults.** Facets does **not** apply `variables.tf optional(…, default)` to
  the *deployed* spec; `local.spec` holds only keys the doc actually wrote. `lookup` defaults
  on a missing key; `try` is wrong here (it swallows *all* errors, hiding real bugs). The
  `optional()` in variables.tf is for type shape, not runtime defaults.
- **`ignore_changes` is legitimate ONLY for:** provider-managed labels
  (`labels`/`terraform_labels`/`effective_labels`), API **echo blocks** you can't declare,
  and **autoscaler/computed** fields. Never to hide a real config diff.
- **Echo blocks — two cases:**
  - *Modelable → flag pattern.* Cloud SQL echoes a disabled `psc_config` on private-IP
    instances. Don't emit it on import; `ignore_changes` the echo; expose a flag so a *new*
    resource can opt in:
    ```hcl
    dynamic "psc_config" { for_each = local.psc_enabled ? [1] : []; content { psc_enabled = true } }
    lifecycle { ignore_changes = [settings[0].ip_configuration[0].psc_config] }
    ```
  - *Un-modelable → ignore is the only option.* `sql_server_audit_config` /
    `active_directory_config` need a `bucket`/`domain` to even declare the block and live has
    neither → `ignore_changes`. Rule: model everything you *can*; ignore only what the
    provider literally won't let you declare empty.
- **ForceNew traps — set to the exact live value:** GCS `bucket_name`/`location`/
  `enable_object_retention`; VM image/zone/machine_type; `description` on some resources;
  pubsub sub `filter`/`name`.
- **…but DON'T set auto-assigned / input-only ForceNew fields.** Redis `reserved_ip_range`
  read back as `+ reserved_ip_range = "10.x/29" # forces replacement` — terraform import
  doesn't read input-only fields into state, so *any* value you set is an add on a ForceNew
  field. Leave it null; rely on the computed `effective_*`.
- **Cross-resource refs use the FULL live path via the *default* output's attributes.** A
  subscription's `.topic` must equal `projects/<p>/topics/<n>` (from the topic module's
  default output `attributes.topic_id`), not the bare name. Named `@facets/<x>_name` outputs
  are not surfaced as module outputs in this CP — ride the default output.
- **Non-hashicorp providers** (e.g. `mongodb/mongodbatlas`): see the Atlas war-story — the
  child module needs `required_providers { x = { source = "ns/x" } }` (source only, no
  version), and the **root** needs the same source injected (framework gap).

## The gate — trust the plan, not the list API

```
  CLEAN (proceed):                          BLOCK (fix the module, do NOT apply):
   • scratch_string.release_metadata add      • "<n> must be replaced"
   • additive "Changes to Outputs"            • "will be destroyed"
   • Plan: X to import, Y to add, 0 change,   • ~ on a real google_*/mongodbatlas_* attr
            0 destroy                            you didn't intend
```
The cloud `list`/`describe` API **lies by omission** — it hid `enable_object_retention=true`,
and uses snake_case keys you must discover (`default_storage_class`, not `storageClass`).
`list` + `jq_expression` is the workhorse for recon, but the cloud read API is not the
authority: the terraform **plan/refresh** is the real read of live, and when it disagrees with
`list`/`describe`, **the plan is right.**

## War-stories (read these — they're the point)

### MongoDB Atlas — non-hashicorp provider (framework gap; being fixed in-platform)
Importing the Atlas cluster took many failed plans for one root cause: a non-hashicorp
provider (`mongodb/mongodbatlas`). The level2 *child* module resolved it fine, but the
Facets-generated **root tfmain** had no `mongodbatlas` in its root `required_providers`, so
the root-level `import{}` block defaulted to `hashicorp/mongodbatlas` (doesn't exist) →
`Failed to query providers` / lock inconsistency. Temporary workaround: declare the `source`
(no version) in both the account and cluster modules, inject
`required_providers { mongodbatlas = { source = "mongodb/mongodbatlas" } }` into the **ROOT**
versions.tf at deploy, and use plain `terraform init` (NOT `-upgrade` — it upgrades
everything and breaks unrelated modules). A final `zone_name = "Zone 1"` closed the last
drift → `1 to import, 0 to change, 0 to destroy`. **This is being fixed in the platform**
(root generation should propagate the exposed provider's source) — don't carry the
workaround as the answer. *Diagnostic lesson:* a targeted plan must include the
provider-supplying account module, or the provider drops out of the graph.

### The bucket near-miss (the gate's finest hour)
`list` omitted `enable_object_retention`; the module assumed `false`; on a live `true` bucket
that's `forces replacement` = data loss. The gate flagged it on a handful, with dozens at
risk. Fix: read the value the **plan/refresh** reveals, set spec to match, re-plan. Lesson:
never apply a plan with `must be replaced`/`to destroy` on a stateful resource.

### Cloud SQL echo blocks
12+ instances wanted to *remove* empty `psc_config`/`sql_server_audit_config`/
`active_directory_config` the API echoes. Modeled the real one (psc, flag pattern), ignored the
two truly un-modelable echoes. (See the echo-block rule above.)

### cloud_tasks drift (blueprint ≠ live)
The customer tfvars set a task queue's `max_attempts=2`, but the live queue was `6` — the
blueprint inherited a stale value the cloud never had. Re-applied the doc from live and
re-gated. Lesson: the blueprint, not just the cloud, must match live — drive values
from the live read, not the customer's (drifted) tfvars.

## Operational mechanics (gotchas that waste hours)

- Capture release IDs from `-o json`, never table output.
- Keep each `-c` body **< ~25KB / ~100 imports** — raptor silently truncates → `FAILED` with
  `cat: write error`. Batch larger sets.
- Build `-target` from the exact `module.level2.module.<intent>_<resourcename>` token; a loose
  `grep` matches substrings (`pubsub_topic` ⊂ another name) and wrongly drops legit targets.
- Custom releases **serialize per env** ("deployment already in progress" = a concurrent one).
- **Sub-agents** can do recon + docs + plan/gate in parallel; **prod APPLY is classifier-gated
  from sub-agents** — the parent runs apply after explicit user authorization.
- When reading logs, grep for the verdict/errors — **never** for secret values (it's blocked,
  and you don't need them: Facets injects the provider config).

## Scoping — what to import

Reconcile three counts: **live** (cloud) vs **TF-defined** (their repo) vs **Facets-state**.
Classify and exclude system/managed-service noise (appspot, gcf/run upload buckets, logging
sinks); defer ops/pipeline resources. Import the resources that represent real, owned infra.

## Customer comms / routing

- Per-resource-type milestone update: ✅ + what's now managed + zero-drift + running total +
  the project's sign-off footer.
- Access requests (e.g. a viewer IAM role) → the customer channel.
- Framework gaps / platform bugs (e.g. the root-provider gap) → the eng/infra channel, cc the
  owner. Never put blockers in the customer channel.

## Anti-patterns

```
  ✗ Loosening the gate (--allow-destroy / ignore a replace) to "make it apply" → data-loss path
  ✗ optional() defaults expected in the deployed spec            → lookup() in locals
  ✗ ignore_changes on a real attribute to hide drift             → model it (ignore only echo/computed/labels)
  ✗ terraform init -upgrade as a lock fix                        → upgrades everything; patch root source + plain init
  ✗ trusting the list API for stateful values                   → trust the plan/refresh
  ✗ pulling secret values into context to "use the API"          → blocked; let Facets inject the provider
  ✗ a targeted plan that drops the account/provider module       → target the provider supplier too
  ✗ --skip-validation publish to a shared prod catalog           → blind apply, blocked
  ✗ setting auto-assigned ForceNew fields (reserved_ip_range)    → leave null, rely on effective_*
```

## Sensitive Values in Raptor Commands

This workflow rarely needs a secret value at all — a read-only import doesn't put
provider credentials in the command (Facets injects the provider config
server-side). When a command genuinely does need one, follow the "Sensitive Values in
Raptor Commands" section of the `terraform-import` skill — **NEVER ask the user to type
a secret in the chat.**
