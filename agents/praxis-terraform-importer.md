---
name: "praxis-terraform-importer"
description: "Imports multiple cloud resources (AWS/GCP/Azure) into Facets-managed Terraform state in one go. Derives region, import IDs, and release strategy automatically from kind/name pairs, project, and env"
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

# Batch Terraform Import

Import multiple cloud resources into Facets-managed Terraform state with zero drift.

**Success criteria:** Every resource reaches `Plan: 0 to add, 0 to change, 0 to destroy.`

**Key optimization:** Custom releases are the bottleneck (only 1 at a time). Selective releases support multiple `--target` flags and CAN run in parallel. This skill uses multi-target selective releases for planning and verification, and combined custom releases for import — reducing from N × (3 + K) sequential releases to ~4 + K total.

## Raptor Multi-Target Syntax

Raptor supports multiple `--target` flags in a single selective release:
```bash
raptor create release -p myproject -e dev --plan \
  --target dynamodb/my-table \
  --target sqs/my-queue \
  --target s3/my-bucket
```

This produces a single plan covering all targeted resources.

## Module Resolution

Modules live in the `terraform-modules/` repo (always checked out in agent session — hardcoded dir name). Skill resolves module location per-resource:

1. **Check local repo first:**
   ```bash
   ls terraform-modules/<kind>/<flavor>/<version>/main.tf
   ```
   - Exists → `module_path = terraform-modules/<kind>/<flavor>/<version>/`, `module_source = "local"`
2. **Fallback to raptor download:**
   ```bash
   raptor get iac-module <kind>/<flavor>/<version> --save-to <batch-dir>/modules/<kind>/<flavor>/<version>/
   ```
   - Set `module_path = <batch-dir>/modules/<kind>/<flavor>/<version>/`, `module_source = "raptor"`

Strict rule: if local copy exists in `terraform-modules/`, MUST use it — never re-download.

All module reads, greps, and edits use the resolved `module_path`. Fixes edit that path in place. Commit/push + publish gated by user approval (see Approval Gates).

## Repository Layout

```
terraform-modules/
├── <kind>/<flavor>/<version>/                    ← module source (local-first for imports)
└── facets_modules/utility-scripts/*.sh           ← helper scripts for the import skill
```

Path roots:
- **Scripts**: `terraform-modules/facets_modules/utility-scripts/` (co-located with module repo).
- **Working files** (logs, state, validation, downloaded modules + blueprints, results.json): written to `batch-<timestamp>/` under the current working directory. Ephemeral.

## Critical Rules

- **NEVER run `poll-release.sh` or custom releases in the background.** Always synchronous.
- **Run all scripts synchronously** unless explicitly stated otherwise.
- **Everything on disk.** The orchestrator NEVER holds plan diffs, log contents, or validation details in context. Subagents write results to disk. Orchestrator reads summaries from disk.
- **Subagent return messages must be minimal** — one line status + diff path, no verbose output.
- **Prefer `terraform-modules/` local copy** over raptor download whenever the flavor/version exists there.
- **Every platform mutation requires user approval** — see Approval Gates below.

## Approval Gates

This is a production system. No autonomous writes. Skill computes all proposed changes first, then presents batched summaries for approval.

**Auto-run (no approval):**
- `raptor get` / `raptor logs` / `raptor get resource-spec` / `raptor get overrides`
- Plan-only releases (`--plan`, `terraform plan` via custom-release)
- Cloud CLI reads (`describe`, `show`, `list`, `get`)
- Reads/writes inside `<batch-dir>/`
- Reads + `git diff` / `git status` in `terraform-modules/`
- `jq` / shell script transformations

**Require approval (batched where noted):**

| Phase | Operations | Batching |
|---|---|---|
| 0 | Pre-flight fixes: register missing resource, enable disabled, delete env override, fork import flavor, switch flavor | **BATCHED** — one approval before queue present (Step 5) |
| 2 | `forces_replacement` blueprint edits, unmanaged-field blueprint edits | **BATCHED** with drift iteration approval (or standalone if no further drifts) |
| 3 | Blueprint applies + module commits/pushes/publishes from drift fix subagents | **BATCHED per iteration** — all proposed diffs shown together; ONE master approval, then per-module commit/push/publish sub-approvals |
| 4 | Combined import apply (`terraform apply` via custom-release) | **PER-OP** — always ask |
| 5 | Selective apply (Facets output population) | **PER-OP** — always ask |

**Module commit/push/publish — per-module flow (3 approvals):**
1. If `module_source == "local"` (module in `terraform-modules/`):
   - Show `git diff` of changes
   - Ask: `Commit to terraform-modules with "DEVOPS-532: <auto-generated description>"? [y/n]`
   - On yes → `git add <files>` + `git commit -m "DEVOPS-532: ..."`
   - Ask separately: `Push to remote? [y/n]`
   - On yes → `git push`
2. If `module_source == "raptor"` (downloaded copy): skip commit/push steps.
3. Ask: `Publish to raptor: raptor create iac-module -f <module_path> --publish --skip-validation? [y/n]`
4. On yes → publish.

**On rejection (any step):**
- STOP that module fix
- Eject affected resources — set `status: "rejected"` in `resources.json`
- Record in `<batch-dir>/rejections.json`: `{resource, operation, step_rejected}`
- Continue batch with remaining resources
- Final `results.json` must include `rejected: [...]` list

## Inputs Required

Gather from the user:
- **Resource list** — one of:
  - Inline list of `kind/name` pairs (e.g. `sqs/my-queue, dynamodb/my-table, s3/my-bucket`) — no cloud IDs required, derived from plan
  - A kind filter (e.g., "all dynamodb resources in this project/env")
- **Project** — Facets project name
- **Environment** — Facets environment name
- **Batch size** — optional, default 10. How many resources per batch. Recommendations (by complexity):
  - Simple (10–15): AWS sqs/dynamodb/s3; GCP pubsub/storage_bucket/bigquery_dataset; Azure storage_account/key_vault
  - Medium (3–5): AWS rds/elasticache; GCP cloud_sql/memorystore; Azure postgresql/mysql
  - Complex (2–3): AWS eks; GCP gke (container_cluster); Azure aks (kubernetes_cluster) — many sub-resources

Derive automatically (do NOT ask the user):
- **Cloud provider + credentials profile** — determined by the `cloud_account` resource `kind`:
  - `cloud_account` with AWS provider → use `aws` CLI. Use ambient profile (env var `AWS_PROFILE` or default credentials).
  - `cloud_account` with GCP provider → use `gcloud` CLI. Project from `cloud_account` spec; credentials from ambient `gcloud auth`.
  - `cloud_account` with Azure provider → use `az` CLI. Subscription from `cloud_account` spec; credentials from ambient `az login`.
  Store under `cloud_profile` in `batch-config.json` with fields `{provider: aws|gcp|azure, profile|project|subscription: "..."}`.
- **Region / location** — derive from the cloud_account resource via raptor:
  1. `raptor get resources -p <project> --type cloud_account` to find the cloud_account name + provider
  2. `raptor get overrides cloud_account/<name> -p <project> -e <environment> -o json` to check for environment-level region/location override
  3. If no override, read the resource spec: `raptor get resource-spec cloud_account/<name> -p <project> -o json`
  The region/location from the override or spec is used for all cloud CLI calls (AWS `--region`, GCP `--region` / `--zone` / `--location`, Azure `--location`).

## Batch Directory Structure

```
batch-<timestamp>/
├── batch-config.json                    ← {id, project, environment, region, cloud_profile: {provider, profile|project|subscription}, batch_size, max_drift_iterations, facets_profile}
├── resources.json                       ← [{kind, name, status: active|error|ejected|rejected|already_imported, error?}]
├── targets.txt                          ← active terraform targets (rebuilt on ejection)
├── pre-flight-mutations.json            ← Phase 0: batched mutations pending approval
├── proposed-changes.json                ← Phase 3 per-iteration: blueprint + module changes pending approval
├── rejections.json                      ← appended on any user rejection {resource, operation, step_rejected, iteration, timestamp}
├── module-diffs/<kind>-<flavor>-<version>.diff   ← module fix subagent output
├── merged-plan-addresses.json           ← concatenated from active resources
├── merged-import-ids.json               ← concatenated from active resources
├── merged-imports.tf                    ← built from merged files
├── selective-plan-logs.txt              ← from multi-target selective release
├── combined-plan-logs.txt               ← from combined custom release
├── combined-validation.json             ← from validate.sh
├── drift-summary.json                   ← from split-validation.sh
├── drift-loop.json                      ← {iteration, max_iterations, status}
├── modules/<kind>/<flavor>/<version>/   ← only when module_source == "raptor"
├── <kind>/<name>/
│   ├── plan-addresses.json              ← extracted from resource-validation.json
│   ├── import-ids.json                  ← from cloud CLI lookups (aws/gcloud/az)
│   ├── blueprint.json                   ← downloaded live spec (edited in-place during drift loop)
│   ├── blueprint-diff.json              ← per-iteration proposed blueprint edits
│   ├── state.json                       ← {kind, name, project, env, region, module_path, module_source, blueprint_path, ...}
│   └── resource-validation.json         ← from split-validation.sh (per-resource drifts)
├── apply-logs.txt                       ← from combined apply
├── <kind>/<name>/verify-result.json     ← from verification
└── results.json                         ← final batch summary (imported / ejected / rejected / failed + stats)
```

---

**Universal:** `UNDERSTAND → PLAN → EXECUTE → VERIFY`
Use `TodoWrite` for all batch operations. Keep exactly one task `in_progress` at a time. Mark tasks `completed` immediately — never batch completions.

## Phase 0: Build the Queue

### Step 1: Parse the resource list

From the user's input, build the initial `resources.json`:
```json
[
  {"kind": "sqs", "name": "my-queue", "status": "active"},
  {"kind": "dynamodb", "name": "my-table", "status": "active"}
]
```

ARN is NOT required upfront — it will be derived from the plan output and blueprint in Phase 1.

### Step 2: Check already-imported resources (optional)

If the user wants to skip already-imported resources, run a state list:

```bash
terraform-modules/facets_modules/utility-scripts/terraform-state-list.sh \
  --project <project> \
  --environment <environment>
```

Run the generated script, poll, fetch logs, then parse:

```bash
terraform-modules/facets_modules/utility-scripts/parse-state-list.sh \
  --log-file <state-list-logs-path> \
  > batch-dir/state-list.json
```

For each resource in resources.json, check if any address in the state list starts with `module.level2.module.<kind>_<name>.`. If found, set `status: "already_imported"`.

**Do NOT rely solely on `imported_resources` from parse-state-list.sh** — its regex breaks for compound kinds (e.g., `ecs_cluster`). Instead, do a substring match against the raw `addresses` array.

### Step 3: Create batch directory and config

```bash
mkdir -p batch-<timestamp>
```

**Derive region** from the cloud_account resource via raptor before proceeding:
1. `raptor get resources -p <project> --type cloud_account` — find the cloud_account name
2. `raptor get overrides cloud_account/<name> -p <project> -e <environment> -o json` — check for environment-level region override
3. If no override, `raptor get resource-spec cloud_account/<name> -p <project> -o json` — read region from spec

Write `batch-config.json`:
```json
{
  "id": "batch-<timestamp>",
  "project": "<project>",
  "environment": "<environment>",
  "region": "<derived region / location>",
  "cloud_profile": {
    "provider": "aws | gcp | azure",
    "profile": "<aws profile or null>",
    "project": "<gcp project or null>",
    "subscription": "<azure subscription id or null>"
  },
  "batch_size": 10,
  "max_drift_iterations": 10,
  "facets_profile": "<FACETS_PROFILE value>"
}
```

If total active resources > batch_size, split into sub-batches. Process each sub-batch through the full pipeline (Phase 1–6) sequentially. Each sub-batch gets its own batch directory.

### Step 4: Pre-flight checks (per resource, no releases)

For each active resource, gather state and record any needed mutations in `<batch-dir>/pre-flight-mutations.json`. **Do NOT apply any mutations during the per-resource loop** — collect, then batch-approve at Step 4.7.

1. **Check resource is registered and enabled (READ ONLY):**
   ```bash
   raptor get resources -p <project> --type <kind> --name <name>
   ```
   - If not found → record mutation: `{type: "register", kind, name, blueprint_path}`. Download the live spec for later apply:
     ```bash
     raptor get resource-spec <kind>/<name> -p <project> -o json > <batch-dir>/<kind>/<name>/blueprint.json
     ```
     If `get resource-spec` also fails (resource doesn't exist at all), mark `status: "error"` (reason: "resource not found in control plane").
   - If disabled → record mutation: `{type: "enable", kind, name, blueprint_path}`. Download spec (if not already) and prepare an edited copy with `"disabled": false`.
   - Check env override: `raptor get overrides <kind>/<name> -p <project> -e <environment> -o json`. If `overrides.disabled == true`, record mutation: `{type: "delete_override", kind, name}`.

2. **Resolve module location (local-first, fallback to raptor):**
   Get flavor + version:
   ```bash
   raptor get resources -p <project> --type <kind> --name <name> -o json
   ```
   Check local repo first:
   ```bash
   if [ -f terraform-modules/<kind>/<flavor>/<version>/main.tf ]; then
     module_path=terraform-modules/<kind>/<flavor>/<version>/
     module_source=local
   else
     raptor get iac-module <kind>/<flavor>/<version> --save-to <batch-dir>/modules/<kind>/<flavor>/<version>/
     module_path=<batch-dir>/modules/<kind>/<flavor>/<version>/
     module_source=raptor
   fi
   ```
   Verify `$module_path/main.tf` exists. If still missing → mark `status: "error"` (reason: "module not available locally or from raptor").

3. **Audit module for `depends_on` conflicts (READ ONLY):**
   ```bash
   grep -n 'depends_on' <module_path>/*.tf
   ```
   If `depends_on` blocks reference resources that will also be imported in this batch, record mutation: `{type: "fork_import_flavor", kind, name, original_flavor, original_version}`. Option A (import flavor fork) is preferred. Option B (eject dependent) is a non-mutation alternative — if chosen, just set `status: "deferred"` in resources.json.

4. **Download live blueprint from raptor** (READ from control plane, WRITE to batch-dir — not a platform mutation):
   ```bash
   raptor get resource-spec <kind>/<name> -p <project> -o json > <batch-dir>/<kind>/<name>/blueprint.json
   ```

5. **Write initial state.json:**
   ```json
   {
     "kind": "<kind>", "name": "<name>",
     "project": "<project>", "environment": "<environment>",
     "region": "<from batch-config.json>",
     "cloud_profile": "<from batch-config.json>",
     "facets_profile": "<FACETS_PROFILE value>",
     "blueprint_path": "<batch-dir>/<kind>/<name>/blueprint.json",
     "module_path": "<resolved module_path>",
     "module_source": "local | raptor"
   }
   ```

If any resource fails pre-flight (non-fixable), set `status: "error"` in resources.json with the reason.

6. **Write `<batch-dir>/pre-flight-mutations.json`** — accumulated list of all mutations needed across resources:
   ```json
   [
     {"type": "register", "resource": "sqs/foo", "blueprint_path": "<path>"},
     {"type": "enable", "resource": "dynamodb/bar", "blueprint_path": "<path>"},
     {"type": "delete_override", "resource": "s3/baz"},
     {"type": "fork_import_flavor", "resource": "rds/qux", "original_flavor": "default", "original_version": "1.0"}
   ]
   ```

7. **Batch-approve pre-flight mutations (APPROVAL GATE):**
   If `pre-flight-mutations.json` is non-empty, present to user:
   ```
   Pre-flight fixes needed (N resources):
   - register: sqs/foo (create resource from downloaded spec)
   - enable: dynamodb/bar (set disabled: false)
   - delete_override: s3/baz (remove disabled=true env override)
   - fork_import_flavor: rds/qux (fork rds/default/1.0 → rds/default-import/1.0, remove depends_on, switch blueprint)
   
   Approve all? [y=all / n=skip all & eject affected / s=selective]
   ```
   On `y`: execute all mutations sequentially (`raptor apply` / `raptor delete override` / flavor-fork workflow).
   On `n`: mark all affected resources `status: "rejected"`, log to `<batch-dir>/rejections.json`.
   On `s`: prompt per-mutation; rejected items → resource marked `rejected`.

   Rejected resources are reported in Phase 6 results under `rejected`.

### Step 5: Present queue to user

```
Batch Import Plan:
- Total in list: N
- Already imported: M (list them)
- Pre-flight failed: P (list with reasons)
- To import: K (list them)
- Batch size: B (K resources in ceil(K/B) batches)

Proceed?
```

Wait for user confirmation.

---

## Phase 1: Multi-Target Selective Plan

Run ONE selective release targeting all active resources in this batch. No subagents needed.

### Step 1: Run multi-target selective plan

Build the target list from active resources, then run:

```bash
raptor create release -p <project> -e <environment> --plan \
  --target <kind1>/<name1> \
  --target <kind2>/<name2> \
  --target <kind3>/<name3> \
  ...
```

Extract release ID, then:

```bash
terraform-modules/facets_modules/utility-scripts/poll-release.sh --project <project> --environment <environment> --release-id <release-id>
terraform-modules/facets_modules/utility-scripts/fetch-logs.sh --project <project> --environment <environment> --release-id <release-id> --output-file <batch-dir>/selective-plan-logs.txt
```

### Step 2: Validate and split per resource

```bash
terraform-modules/facets_modules/utility-scripts/validate.sh \
  --log-file <batch-dir>/selective-plan-logs.txt \
  > <batch-dir>/selective-validation.json
```

```bash
terraform-modules/facets_modules/utility-scripts/split-validation.sh \
  --validation-file <batch-dir>/selective-validation.json \
  --resources-file <batch-dir>/resources.json \
  --output-dir <batch-dir>
```

### Step 3: Extract plan-addresses per resource

For each active resource, extract plan-addresses from its resource-validation.json:

```bash
jq '[.all_diffs[].resource]' <batch-dir>/<kind>/<name>/resource-validation.json \
  > <batch-dir>/<kind>/<name>/plan-addresses.json
```

### Step 4: Handle selective plan errors

If the selective release FAILS (status `FAILED`):
1. Fetch and read the logs to identify which module/resource caused the error
2. Try to attribute the error to a specific resource by checking for module paths in the error message
3. If attributable: eject that resource (`status: "error"` in resources.json), re-run the selective plan without it
4. If not attributable: **STOP**, show full error, ask user

### Step 5: Derive import IDs from plan + blueprint + Cloud CLI

The user does NOT provide full cloud identifiers (ARNs / resource paths). Instead, derive the terraform import ID for each resource from the plan output, blueprint spec, and cloud CLI lookups (`aws`, `gcloud`, or `az` depending on provider).

**How to derive import IDs for each terraform address in plan-addresses.json:**

1. **Read the plan diff** (primary source) from `resource-validation.json` — for `"will be created"` resources, the plan shows proposed attribute values, which usually include cloud resource identifiers (table name, queue name, bucket name, project/location, etc.).

2. **If the plan diff doesn't show the identifier** (some attributes are `(known after apply)`), read the downloaded blueprint at `<batch-dir>/<kind>/<name>/blueprint.json` — the spec contains the cloud resource name/identifier.

3. **Use the appropriate cloud CLI** to convert the identifier into the format terraform expects for import:
   - **AWS:** `aws ... --region <region> --profile <aws_profile>` (if profile set)
   - **GCP:** `gcloud ... --project <project> --format json` (project typically from `cloud_account` spec)
   - **Azure:** `az ... --subscription <subscription-id>` (subscription typically from `cloud_account` spec)

**Import ID Reference — each terraform resource type → what terraform expects on import. Provider docs are authoritative; this is a quick-lookup only.**

**AWS** (most resources use name, ARN, or URL; see provider docs for each):
- `aws_sqs_queue` → queue URL (`aws sqs get-queue-url --queue-name <name>`)
- `aws_dynamodb_table` → table name
- `aws_s3_bucket` → bucket name
- `aws_s3_bucket_versioning` / `_server_side_encryption_configuration` / `_public_access_block` / `_lifecycle_configuration` / `_cors_configuration` → bucket name (sub-resources share parent ID)
- `aws_iam_policy` → policy ARN (`aws iam list-policies --query ...`)
- `aws_iam_role` → role name
- `aws_rds_cluster` → cluster identifier
- `aws_db_instance` → instance identifier
- `aws_db_subnet_group` / `aws_db_parameter_group` → name
- `aws_lambda_function` → function name
- `aws_kinesis_firehose_delivery_stream` → ARN (`aws firehose describe-delivery-stream`)
- `aws_kinesis_stream` → stream name

**GCP** (most resources use structured path `projects/<project>/.../<name>`; see provider docs):
- `google_storage_bucket` → bucket name (or `<project>/<bucket>`)
- `google_compute_instance` → `projects/<project>/zones/<zone>/instances/<name>`
- `google_compute_disk` → `projects/<project>/zones/<zone>/disks/<name>`
- `google_compute_network` → `projects/<project>/global/networks/<name>`
- `google_compute_subnetwork` → `projects/<project>/regions/<region>/subnetworks/<name>`
- `google_container_cluster` → `projects/<project>/locations/<location>/clusters/<name>`
- `google_container_node_pool` → `projects/<project>/locations/<location>/clusters/<cluster>/nodePools/<name>`
- `google_sql_database_instance` → `projects/<project>/instances/<name>` (or just `<name>`)
- `google_bigquery_dataset` → `projects/<project>/datasets/<dataset_id>`
- `google_bigquery_table` → `projects/<project>/datasets/<dataset_id>/tables/<table_id>`
- `google_pubsub_topic` → `projects/<project>/topics/<name>`
- `google_pubsub_subscription` → `projects/<project>/subscriptions/<name>`
- `google_service_account` → `projects/<project>/serviceAccounts/<email>`
- `google_project_iam_member` / `_iam_binding` → `<project> <role> <member>` (space-separated, see docs)
- `google_cloud_run_service` → `locations/<location>/namespaces/<project>/services/<name>`

**Azure** (nearly every resource uses the full Azure Resource ID; `az resource show` returns it):
- Generic: `/subscriptions/<sub>/resourceGroups/<rg>/providers/<namespace>/<type>/<name>`
- `azurerm_resource_group` → `/subscriptions/<sub>/resourceGroups/<rg>`
- `azurerm_storage_account` → `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<name>`
- `azurerm_virtual_network` → `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<name>`
- `azurerm_subnet` → `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<name>`
- `azurerm_kubernetes_cluster` → `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ContainerService/managedClusters/<name>`
- `azurerm_postgresql_flexible_server` → `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.DBforPostgreSQL/flexibleServers/<name>`
- `azurerm_key_vault` → `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<name>`
- `azurerm_role_assignment` → `<scope>|<role-assignment-id>` (see docs; scope-dependent)
- For any other type: `az resource show --ids <full-id>` or `az <service> <subcmd> show ...` returns the `id` field → use that

**Sub-resource rule (all clouds):** for module sub-resources (`aws_s3_bucket_versioning`, `aws_sqs_queue_policy`, `google_storage_bucket_iam_member`, Azure child resources), the import ID is typically the parent's ID or the parent's ID + child name. Check provider docs.

**Fallback:** if resource type not listed above, look up the terraform provider documentation for that resource — every provider documents its import ID format in the "Import" section.

4. **Write to `<batch-dir>/<kind>/<name>/import-ids.json`:**
```json
[
  {"tf_pattern": "aws_dynamodb_table", "id": "my-table"},
  {"tf_pattern": "aws_appautoscaling_target.read", "id": "service/dynamodb/table/my-table/dynamodb:table:ReadCapacityUnits"}
]
```

### Step 6: Write state.json per resource

For each active resource, update `<batch-dir>/<kind>/<name>/state.json` (enriching what was written in Phase 0):
```json
{
  "kind": "<kind>",
  "name": "<name>",
  "project": "<project>",
  "environment": "<environment>",
  "region": "<from batch-config.json>",
  "cloud_profile": "<from batch-config.json>",
  "facets_profile": "<FACETS_PROFILE value>",
  "blueprint_path": "<batch-dir>/<kind>/<name>/blueprint.json",
  "module_path": "<resolved module_path from Phase 0>",
  "module_source": "local | raptor"
}
```

Report to user:
```
Selective plan complete:
- Resources planned: N
- Total terraform addresses: M
- Import IDs derived: M

Proceeding to combined import plan...
```

---

## Phase 2: Combined Import Plan (1 custom release)

This phase uses **1 custom release** to test all imports together with the `imports.tf` injected.

### Step 1: Merge per-resource files

```bash
terraform-modules/facets_modules/utility-scripts/merge-batch-files.sh \
  --batch-dir <batch-dir> \
  --resources-file <batch-dir>/resources.json
```

**Output:** Creates `merged-plan-addresses.json`, `merged-import-ids.json`, `targets.txt`.

### Step 2: Build combined imports.tf

```bash
terraform-modules/facets_modules/utility-scripts/build-imports.sh \
  --plan-addresses-file <batch-dir>/merged-plan-addresses.json \
  --import-ids-file <batch-dir>/merged-import-ids.json \
  --output-file <batch-dir>/merged-imports.tf
```

### Step 3: Run combined custom plan

```bash
terraform-modules/facets_modules/utility-scripts/encode-imports.sh \
  --imports-file <batch-dir>/merged-imports.tf \
  --project <project> \
  --environment <environment> \
  --action plan \
  --targets-file <batch-dir>/targets.txt \
  --resources-file <batch-dir>/resources.json
```

Run the generated `run_script`. Extract release ID, then:

```bash
terraform-modules/facets_modules/utility-scripts/poll-release.sh --project <project> --environment <environment> --release-id <release-id>
terraform-modules/facets_modules/utility-scripts/fetch-logs.sh --project <project> --environment <environment> --release-id <release-id> --output-file <batch-dir>/combined-plan-logs.txt
```

### Step 4: Validate and split

```bash
terraform-modules/facets_modules/utility-scripts/validate.sh \
  --log-file <batch-dir>/combined-plan-logs.txt \
  > <batch-dir>/combined-validation.json
```

```bash
terraform-modules/facets_modules/utility-scripts/split-validation.sh \
  --validation-file <batch-dir>/combined-validation.json \
  --resources-file <batch-dir>/resources.json \
  --output-dir <batch-dir>
```

**Output:** Per-resource `resource-validation.json` files + `drift-summary.json`.

### Step 5: Classify Drifts (Deterministic)

**DO NOT rely on `unexpected_drifts` / `expected_drifts` from validate.sh.** Classify every resource in `resource_diffs` yourself using this rule:

| Action in plan | Classification | What to do |
|---|---|---|
| `will be imported` | **OK** — expected | Nothing |
| Any action on `scratch_string.*` or `cloud_account_*` | **Facets internal** — always safe | Ignore |
| `will be updated in-place` | **DRIFT** — must fix | Phase 3 loop |
| `will be created` (non-import resource) | **DRIFT** — must fix | Phase 3 loop |
| `will be destroyed` / `must be replaced` | **DANGEROUS** — propose fix for approval (Step 7); eject immediately if action is `destroyed` | Step 7 |
| `errors` non-empty | **BLOCKING** — stop | **STOP**, show errors |

Build your own per-resource `drifts` list by filtering `resource_diffs` with this rule. Use this list (not `unexpected_drifts`) as input to the drift resolution loop and all subsequent steps.

### Step 6: Read Drift Summary

Read `<batch-dir>/drift-summary.json`. Report to user:

```
Combined import plan results:
- Clean (import-only): N resources
- Has drifts: M resources (list with drift counts)
- Dangerous: P resources (list)

Total drifts to resolve: X
```

### Step 7: Handle Dangerous Resources

**`forces_replacement` — propose fix for approval before ejecting:**

The fix is NOT applied autonomously. Skill computes proposed blueprint edits and routes them through the drift-iteration approval pass (Phase 3). If no other drifts exist, skill presents a standalone approval for these edits.

1. Read the `forces_replacement` entries to identify which fields are wrong
2. Fetch actual live resource state using the appropriate cloud CLI:
   - **AWS — dynamodb**: `aws dynamodb describe-table` → check `KeySchema`, `BillingModeSummary`
   - **AWS — sqs**: `aws sqs get-queue-attributes` → check `FifoQueue`, `ContentBasedDeduplication`
   - **AWS — rds**: `aws rds describe-db-clusters` / `describe-db-instances` → check `Engine`, `EngineVersion`, `StorageType`
   - **AWS — s3**: `aws s3api get-bucket-location` → check region
   - **GCP — GKE cluster**: `gcloud container clusters describe <name> --location <location> --project <project> --format json` → check `locations`, `releaseChannel`, `privateClusterConfig`
   - **GCP — Cloud SQL**: `gcloud sql instances describe <name> --project <project> --format json` → check `databaseVersion`, `region`, `settings.tier`
   - **GCP — GCS bucket**: `gcloud storage buckets describe gs://<name> --format json` → check `location`, `storageClass`
   - **GCP — Compute VM**: `gcloud compute instances describe <name> --zone <zone> --project <project> --format json` → check `machineType`, `zone`, `networkInterfaces`
   - **Azure — AKS**: `az aks show -g <rg> -n <name>` → check `kubernetesVersion`, `dnsPrefix`, `networkProfile`
   - **Azure — Storage**: `az storage account show -g <rg> -n <name>` → check `kind`, `sku.name`, `location`
   - **Azure — PostgreSQL**: `az postgres flexible-server show -g <rg> -n <name>` → check `version`, `sku`, `storage`
   - **Generic fallback — AWS**: `aws <service> describe-<resource>` / `get-<resource>`
   - **Generic fallback — GCP**: `gcloud <service> <subcmd> describe <name> --project <project> --format json`
   - **Generic fallback — Azure**: `az resource show --ids <full-id>` or `az <service> show ...`
3. Edit the blueprint JSON in-place at `<blueprint_path>` with correct values from the cloud response. **Do NOT call `raptor apply` here** — blueprint mutations are approved + applied via the drift iteration approval pass (Phase 3).
4. Record proposed change to `<batch-dir>/proposed-changes.json` (type: `blueprint_apply`, resource, blueprint_path, diff_summary).
5. Continue through Phase 3 drift loop. The user will approve the batched changes there. If after approval + re-plan:
   - `forces_replacement` resolved AND no new drifts → continue normally
   - `forces_replacement` resolved BUT new drifts → another drift iteration
   - `forces_replacement` persists → eject the resource (`status: "ejected"` in resources.json), show details

**`destroys` — eject immediately** (set `status: "ejected"` in resources.json). Do not propose fix.

### Step 8: Unmanaged Fields Check (per clean resource, BLOCKING)

**Why:** `Optional + Computed` attributes set to `null` in the module mean "don't manage." After import, the value sits in state silently — no drift visible in the plan, but if the resource is ever destroyed and recreated, the value is lost. Run this check on every resource classified as clean (import-only + internals, zero drifts) before proceeding to the apply gate.

For each clean resource:

**Step 8a:** Grep the module for null patterns (module already downloaded in Phase 0):
```bash
grep -n 'null' <batch-dir>/modules/<kind>/<flavor>/<version>/*.tf
```

**Step 8b:** For each null pattern found, fetch the actual live cloud value via CLI (the plan diff will NOT show values for fields set to `null` — terraform doesn't track them):
- Use the same cloud CLI commands as Step 7 (AWS `describe-*` / GCP `gcloud ... describe` / Azure `az ... show`)
- Check if the field has a non-default value on the live cloud resource

Classify using this table:

| Module has null | Cloud has non-default value | Blueprint sets it | Classification |
|---|---|---|---|
| Yes | Yes | No | **UNMANAGED — fix** |
| Yes | Yes | Yes | OK — managed |
| Yes | No / default | No | OK — nothing to manage |
| Yes | No / default | Yes | OK — explicitly declared |

**Step 8c:** For each UNMANAGED field — propose fix for approval (NOT autonomous):
1. Read actual cloud value from the cloud CLI output (NOT the plan diff)
2. Edit blueprint JSON in-place with the field under the corresponding `spec` field
3. Record proposed change to `<batch-dir>/proposed-changes.json` (type: `blueprint_apply`, resource, blueprint_path, diff_summary, reason: "unmanaged field")
4. Route through drift-iteration approval pass (Phase 3). If unmanaged fixes are the only proposed changes, present standalone approval.
5. On approval + apply → re-run Steps 1–5 from Phase 2 → re-classify:
   - Still clean → write `<batch-dir>/<kind>/<name>/unmanaged-check.json`: `{"checked": true, "unmanaged_fields": [], "status": "PASS"}` and continue
   - New drifts appeared → another drift iteration
   - Still unmanaged fields → repeat Step 8 (counts toward Phase 3 iteration limit)
6. On rejection → mark resource `status: "rejected"` with operation `unmanaged_fix`, record in `rejections.json`

**Step 8d:** If zero unmanaged fields found, write:
```json
{"checked": true, "unmanaged_fields": [], "status": "PASS"}
```

If zero drifts across all resources AND all unmanaged checks pass → skip to Phase 4 (Apply Gate).

---

## Phase 3: Drift Resolution Loop (max 10 iterations)

Each iteration has **three passes**: PLAN (compute proposed changes), APPROVE (single batched approval), EXECUTE (apply approved changes).

Write `drift-loop.json`:
```json
{"iteration": 0, "max_iterations": 10, "status": "running"}
```

### Loop Procedure

1. **Read** `<batch-dir>/drift-summary.json` (from disk)
2. If zero drifts AND no `forces_replacement` / unmanaged fixes pending → update drift-loop status to `"clean"`, proceed to Phase 4
3. If `iteration >= max_iterations` → update status to `"max_iterations_reached"`, **STOP**, show remaining drifts

4. **PLAN PASS (no platform writes):**
   - Group drifts by fix type (module vs blueprint, grouping module fixes by shared `module_path`)
   - Dispatch fix subagents in parallel. **Subagents do NOT apply or publish anything** — they only:
     - Edit files in-place: blueprint JSON at `<blueprint_path>`, module files at `<module_path>`
     - Return one-line status + diff file path
   - Orchestrator collects all proposed changes into `<batch-dir>/proposed-changes.json`:
     ```json
     [
       {"type": "blueprint_apply", "resource": "sqs/foo", "blueprint_path": "<path>", "diff_summary": "+spec.fifo_queue=true"},
       {"type": "module_fix", "module_path": "terraform-modules/sqs/default/1.0/", "module_source": "local", "affected_resources": ["sqs/foo", "sqs/bar"], "changed_files": ["main.tf", "facets.yaml"], "diff_path": "<batch-dir>/module-diffs/sqs-default-1.0.diff"}
     ]
     ```

5. **APPROVE PASS (batched):**
   Present to user:
   ```
   Iteration <N> proposed changes:
   
   Blueprint edits (<count>):
   - sqs/foo: +spec.fifo_queue=true
   - dynamodb/bar: +spec.point_in_time_recovery=true, ~spec.billing_mode=PAY_PER_REQUEST
   ...
   
   Module edits (<count>):
   - terraform-modules/sqs/default/1.0/ [local]: affects sqs/foo, sqs/bar
     <diff summary, first ~20 lines>
   - <batch-dir>/modules/rds/default/2.0/ [raptor]: affects rds/qux
     <diff summary>
   
   Approve all? [y=all / n=reject all / s=selective]
   ```

6. **EXECUTE PASS (with per-module sub-approvals for commit/push/publish):**
   - For each **approved blueprint** edit: `raptor apply -f <blueprint_path> -p <project>`
   - For each **approved module** edit, run the 3-step module flow (see Approval Gates):
     - If `module_source == "local"`: show `git diff`, ask commit (with `DEVOPS-532: <desc>`), ask push (separate), ask publish
     - If `module_source == "raptor"`: ask publish only
     - On any sub-rejection: eject affected resources (`status: "rejected"`), log to `rejections.json`, skip publish
   - Rejected items in APPROVE pass → mark resource `status: "rejected"`, log to `rejections.json`

7. After EXECUTE complete:
   - Run `merge-batch-files.sh` (in case resources ejected)
   - Re-run Steps 1–5 from Phase 2 (merge → build → plan → validate → split → re-classify)
   - Increment iteration in `drift-loop.json`
   - Read updated `drift-summary.json`
   - Report: `"Iteration N: M drifts remaining across K resources. Rejected this iteration: P."`
8. Loop back to step 1

### Grouping Drifts by Fix Type

Read each resource's `resource-validation.json` from disk. For each drift, classify:

**Module fix needed:** The drifting field is not in `facets.yaml` spec schema, or a hardcoded default doesn't match the live cloud resource. Requires editing the module .tf files.

**Blueprint fix needed:** The field exists in spec schema but the blueprint has wrong/missing value. Requires editing the blueprint JSON.

**Critical grouping for module fixes:**
Multiple resources may share the same module (e.g., 5 SQS queues all using `sqs/default/1.0`). If they have the same drift pattern, it's ONE module fix that resolves all of them.

Group module fixes by `module_path` (from each resource's `state.json`). One fix subagent per unique module, not per resource.

Blueprint fixes are per-resource and safe to parallelize.

### Module Fix Subagent Prompt

```
You are proposing module edits for a batch terraform import (PLAN PASS only — do NOT apply or publish).

## Module to Fix
- Module path: <module_path> (may be terraform-modules/... [local] or <batch-dir>/modules/... [raptor])
- Module source: <local | raptor>
- FACETS_PROFILE: <facets_profile>

## Drifts (from multiple resources sharing this module)
<For each resource using this module, list the drifts:>

Resource: <kind>/<name>
  Drift 1: <resource_address> — <action>
    <diff text from resource-validation.json>
  Drift 2: ...

Resource: <kind2>/<name2>
  <same pattern drifts>

## How to Fix

For each unique drift pattern:
1. Read the module source files at the module path
2. Read facets.yaml to check if the field is in spec schema
3. If NOT in spec schema → add the field using the module development skill (edit in-place)
4. If in spec schema but hardcoded default wrong → fix the default in main.tf

## Rules
- Fix all drift patterns for this module in one pass
- Edit files in-place at <module_path>
- **DO NOT run `git commit`, `git push`, or `raptor create iac-module --publish`** — orchestrator handles those with user approval
- Produce a unified diff: `git diff > <batch-dir>/module-diffs/<kind>-<flavor>-<version>.diff` (for local) or a `diff -u` against the original raptor download (for raptor source)
- Return ONE LINE: "proposed: <N> patterns, diff at <path>" or "error: <reason>"
```

### Blueprint Fix Subagent Prompt

```
You are proposing blueprint edits for a batch terraform import (PLAN PASS only — do NOT apply).

## Resource
- Kind: <kind>
- Name: <name>
- Blueprint path: <blueprint_path> (from state.json)
- Project: <project>
- FACETS_PROFILE: <facets_profile>

## Drifts
Read <batch-dir>/<kind>/<name>/resource-validation.json for the full drift list.

For each drift:
1. Read the diff text to determine the actual cloud value (confirm with cloud CLI `describe`/`show` if diff is ambiguous)
2. Read the blueprint JSON
3. Update the blueprint in-place at <blueprint_path> with the correct value under the corresponding spec field
4. **DO NOT run `raptor apply`** — orchestrator applies with user approval

## Drift Category Reference
| Drift category | Action |
|---|---|
| Tag drift (tags, tags_all) | Promote to blueprint spec |
| Metadata (description, labels) | Promote to spec |
| Additive set/list widening | Promote to spec |
| Identifier rewrite (*_arn, *_id) | STOP — write error to resource status |
| Network/security topology | STOP — write error |
| Engine/version fields | STOP — write error |

## Rules
- Edit blueprint file in-place; do not apply
- Write diff summary to `<batch-dir>/<kind>/<name>/blueprint-diff.json`: {fields_changed: [...], summary: "..."}
- Return ONE LINE: "proposed: N fields, diff at <path>" or "error: <reason>"
```

### After fix subagents complete

1. Run `merge-batch-files.sh` (in case any resources were ejected during fixes)
2. Run Steps 1–5 from Phase 2 (merge → build → plan → validate → split → re-classify using deterministic matrix)
3. Read updated `drift-summary.json`
4. Continue loop

---

## Phase 4: Apply Gate

### Present per-resource summary

Read `drift-summary.json` from disk. For each active resource, show:

```
Batch Import Summary:
┌─────────────────────────────────────────────┐
│ Resource                  │ Imports │ Drifts │
├───────────────────────────┼─────────┼────────┤
│ sqs/my-queue              │ 1       │ 0      │
│ s3/my-bucket              │ 3       │ 0      │
│ dynamodb/my-table         │ 1       │ 0      │
└─────────────────────────────────────────────┘

Total: N resources, M import blocks
Drift iterations used: K
Plan summary: <from combined-validation.json>

Options:
- Apply all
- Eject specific resources first (list them), then apply rest
- Abort
```

**Wait for explicit user approval.** Never auto-apply.

### On eject request

If user wants to eject resources before apply:
1. Set `status: "ejected"` in resources.json for those resources
2. Run `merge-batch-files.sh` to rebuild merged files
3. Run `build-imports.sh` + `encode-imports.sh` with the reduced set
4. Run a quick combined plan to confirm
5. Re-present the summary

### On apply approval

```bash
terraform-modules/facets_modules/utility-scripts/encode-imports.sh \
  --imports-file <batch-dir>/merged-imports.tf \
  --project <project> \
  --environment <environment> \
  --action apply \
  --targets-file <batch-dir>/targets.txt \
  --resources-file <batch-dir>/resources.json
```

Run the generated `run_script`. Poll and fetch logs:

```bash
terraform-modules/facets_modules/utility-scripts/poll-release.sh --project <project> --environment <environment> --release-id <release-id>
terraform-modules/facets_modules/utility-scripts/fetch-logs.sh --project <project> --environment <environment> --release-id <release-id> --output-file <batch-dir>/apply-logs.txt
```

Check release status:
- `SUCCEEDED` → proceed to Phase 5
- `FAILED` → **STOP**, show error from logs, ask user how to proceed

---

## Phase 5: Multi-Target Verification + Selective Apply

After the custom import apply, Facets outputs (interfaces, attributes) are NOT yet populated. A selective apply is required to write them. This phase runs a selective plan to verify zero drift, then a selective apply to populate outputs.

### Step 1: Run verification selective plan

```bash
raptor create release -p <project> -e <environment> --plan \
  --target <kind1>/<name1> \
  --target <kind2>/<name2> \
  ...
```

Poll and fetch logs:

```bash
terraform-modules/facets_modules/utility-scripts/poll-release.sh --project <project> --environment <environment> --release-id <release-id>
terraform-modules/facets_modules/utility-scripts/fetch-logs.sh --project <project> --environment <environment> --release-id <release-id> --output-file <batch-dir>/verify-plan-logs.txt
```

### Step 2: Validate and split

```bash
terraform-modules/facets_modules/utility-scripts/validate.sh \
  --log-file <batch-dir>/verify-plan-logs.txt \
  > <batch-dir>/verify-validation.json
```

```bash
terraform-modules/facets_modules/utility-scripts/split-validation.sh \
  --validation-file <batch-dir>/verify-validation.json \
  --resources-file <batch-dir>/resources.json \
  --output-dir <batch-dir>
```

### Step 3: Check per-resource results

Read `drift-summary.json`. For each resource:
- `status: "clean"` and zero drifts → write `verify-result.json`: `{"status": "clean", "plan_summary": "Plan: 0 to add, 0 to change, 0 to destroy."}`
- Any drifts → write `verify-result.json`: `{"status": "drift", "drift_count": N}`

Expected: `Plan: 0 to add, 0 to change, 0 to destroy.` for every resource.
If any resource has non-zero drifts → **STOP**, show which ones and their diffs.

### Step 4: Selective apply (APPROVAL GATE — required for Facets output population)

After confirming zero drift, a selective apply populates the `scratch_string.release_metadata` outputs that Facets uses to serve resource interfaces and attributes to dependent resources.

**Present to user:**
```
Verification plan clean (0/0/0) for all <N> imported resources.

Run selective apply to populate Facets outputs (interfaces/attributes)?
This is a real release — will run terraform apply on all targets.

Approve? [y/n]
```

On `n` → STOP. Write `results.json` with `selective_apply_skipped: true`. Resources are imported but Facets outputs remain unpopulated until selective apply runs.

On `y`:
```bash
raptor create release -p <project> -e <environment> \
  --target <kind1>/<name1> \
  --target <kind2>/<name2> \
  ...
```

Poll and fetch logs:

```bash
terraform-modules/facets_modules/utility-scripts/poll-release.sh --project <project> --environment <environment> --release-id <release-id>
terraform-modules/facets_modules/utility-scripts/fetch-logs.sh --project <project> --environment <environment> --release-id <release-id> --output-file <batch-dir>/verify-apply-logs.txt
```

Check release status:
- `SUCCEEDED` → proceed to Phase 6
- `FAILED` → **STOP**, show error from `verify-apply-logs.txt`, ask user how to proceed

---

## Phase 6: Report

Write `<batch-dir>/results.json`:
```json
{
  "batch_id": "<timestamp>",
  "project": "<project>",
  "environment": "<environment>",
  "completed_at": "<ISO timestamp>",
  "selective_apply_skipped": false,
  "results": {
    "imported": ["sqs/my-queue", "s3/my-bucket"],
    "verified_clean": ["sqs/my-queue", "s3/my-bucket"],
    "verified_drift": [],
    "ejected": ["rds/problem-cluster"],
    "failed": ["dynamodb/bad-table"],
    "rejected": [
      {"resource": "sqs/foo", "operation": "blueprint_apply", "step_rejected": "approve_pass", "iteration": 1},
      {"resource": "rds/qux", "operation": "module_publish", "step_rejected": "publish", "iteration": 2}
    ],
    "not_attempted": []
  },
  "stats": {
    "total": 10,
    "imported": 7,
    "ejected": 1,
    "failed": 1,
    "rejected": 1,
    "drift_iterations": 2,
    "custom_releases_used": 5,
    "user_rejections": 2
  }
}
```

Present to user:
```
Batch Import Complete:
- Imported & verified (0/0/0): N (list)
- Imported with remaining drift: M (list with summaries)
- Ejected (autonomous): P (list with reasons)
- Rejected (user declined approval): R (list with operation + step)
- Failed: Q (list with errors)
- Selective apply: <done | skipped by user>

User rejections total: U
Custom releases used: X (vs. ~Y if done sequentially)
```

---

## Autonomy Rules (Quick Reference)

| Situation | Action |
|---|---|
| Pre-flight check fails for a resource (unfixable) | Mark as error, continue with remaining |
| Pre-flight fixes needed (register/enable/override/flavor-fork) | **BATCHED APPROVAL** before queue present (Step 4.7) |
| `depends_on` conflict found in pre-flight | Record fork_import_flavor mutation → batched approval; if rejected, eject or defer per user |
| Selective plan succeeds | Continue — split and extract per-resource data |
| Selective plan FAILS | Read logs, try to attribute error to a resource, eject it, retry |
| Combined import plan shows only imports + internals | Run unmanaged fields check (Step 8) — proposed edits route to drift-iteration approval |
| Combined import plan shows drifts | Apply deterministic classification (Step 5), then enter Phase 3 drift loop |
| Combined import plan shows `forces_replacement` | Propose fix (Step 7): edit blueprint in-place, record in `proposed-changes.json` → Phase 3 drift-iteration approval |
| Combined import plan shows `destroys` | Eject immediately, continue with rest |
| Combined import plan has `errors` non-empty | **STOP** — show errors |
| Unmanaged fields found for clean resource | Propose fix (Step 8c): edit blueprint, route through drift-iteration approval |
| Phase 3 iteration | **BATCHED APPROVAL** of all proposed blueprint + module changes; per-module commit/push/publish sub-approvals follow |
| User rejects a proposed change | Eject affected resources (`status: "rejected"`), log to `rejections.json`, continue |
| Max drift iterations reached | **STOP** — show remaining, ask user |
| Combined import apply (Phase 4) | **PER-OP APPROVAL** — always ask, never auto |
| Apply succeeds | Proceed to Phase 5 verification |
| Apply fails | **STOP** — show error |
| Verification plan clean (0/0/0) | **APPROVAL** before selective apply (Phase 5 Step 4) |
| Selective apply succeeds | Complete — write results with `rejected` + `user_rejections` populated |
| Verification plan shows drift | **STOP** — report which ones and diffs |
| Selective apply fails | **STOP** — show error from verify-apply-logs.txt |
| Selective apply skipped by user | Write results with `selective_apply_skipped: true` |
| Module fix needed for shared module | ONE subagent per module, not per resource |
| Module source `local` (terraform-modules/) | Commit/push (with `DEVOPS-532:` prefix) before publish — 3 separate approvals |
| Module source `raptor` (downloaded) | Publish approval only, no commit/push |
| Context getting large | Read from disk, not from prior messages |

## Scripts Reference

| Script | Purpose | Batch-specific? |
|---|---|---|
| `split-validation.sh` | Split combined validation into per-resource files + drift-summary.json | **Yes — new** |
| `merge-batch-files.sh` | Merge per-resource plan-addresses + import-ids, build targets.txt | **Yes — new** |
| `encode-imports.sh` | Encode imports.tf for custom release with TF regeneration in hotfix mode (requires `--resources-file`) | Updated |
| `regenerate-tf.sh` | Cleanup generated TF + re-run generate.py with hotfix mode so non-targeted modules are skipped | **Yes — new** |
| `build-hotfix-json.sh` | Convert batch resources.json to /configs/hotfix.json format for generate.py | **Yes — new** |
| `build-imports.sh` | Build imports.tf from plan-addresses + import-ids | Existing |
| `validate.sh` | Classify plan output into resource_diffs | Existing |
| `analyze-plan.sh` | Extract terraform addresses from plan logs | Existing |
| `poll-release.sh` | Poll release until terminal status | Existing |
| `fetch-logs.sh` | Fetch release logs to file | Existing |
| `terraform-state-list.sh` | Run terraform state list via custom release | Existing |
| `parse-state-list.sh` | Parse state list logs into JSON | Existing |


{{include:agent_operating_principles.md}}
{{include:facets_domain_knowledge.md}}

