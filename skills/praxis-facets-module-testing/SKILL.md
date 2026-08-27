---
name: "praxis-facets-module-testing"
title: "Facets Module Testing"
description: "QA-test a Facets IaC module against the Control Plane end to end — populate ALL facets.yaml config (required + optional), run a --plan gate, do a REAL apply, verify live outputs + tags + naming against your org's tag/naming conventions, catch common module bugs, then fix and publish under a breaking-change gate. Use when asked to QA/test a Facets module, validate a module's facets.yaml/terraform, reproduce a module bug, apply a module for real in a sandbox, publish a module to the CP, verify a module's tags/naming, or wire/test network-dependent modules (EKS, RDS, Redis) against a spoke VPC."
triggers: ["qa module", "test facets module", "validate module", "module bug", "apply module sandbox", "publish module", "verify tags naming", "module qa lifecycle"]
version: "1.0"
category: "facets"
tags: ["facets", "module", "testing", "qa", "raptor", "terraform", "tags", "naming"]
icon: "🧪"
surface: "cli"
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

# Facets Module Testing

End-to-end methodology for QA-testing your org's Facets IaC modules:
full-config populate → plan → real apply → verify (outputs + tags + naming) →
teardown, finding and fixing bugs along the way, then publishing fixes. Built
from real QA runs against the sandbox Control Plane.

## Scope of one invocation (parametric — single module)

**This skill tests ONE module** (`<kind>/<flavor>/<version>`) end to end. It is
NOT an all-modules enumerator. An outer driver (a cloud session, or one spawned
session per module) loops it across the module set. This keeps it reusable:
when a new module ships tomorrow, point this skill at it and test in one shot.

Input contract per invocation: the module dir under
`<modules_root>/<kind>/<flavor>/<version>/` (authoritative
source — fixes land here), plus the target project/env (sandbox /
`<test_project>` / `dev`). For the current full-set run, the inventory and
per-module reconciliation live at
`<blueprints_repo>/<test_project>/_module-testing-inventory.md`.

## 0. Golden rules (read first)

- **Resolve `<module_source_repo>` from the CP, not by asking.** Run
  `raptor get modules-repo -o json` against the **prod org profile**: if a modules
  repo is linked, that repo IS `<module_source_repo>` (author fixes on a feature
  branch at `{pathPrefix}/modules/{intent}/{flavor}/{version}/`), and **publishing
  to prod = merging the PR** — CI publishes on merge (see /modules-repo-workflow);
  never `raptor publish` directly to a linked prod CP. Run the same check against
  the sandbox profile too: sandbox CPs are typically NOT linked, so sandbox
  publishes stay direct (`--publish`); if the sandbox is linked in WARN mode, a
  direct publish prints a provenance warning — expected during QA from a branch,
  don't chase it. Only when NO repo is linked anywhere does `<module_source_repo>`
  come from the user/task context.
- **Profiles are sacred.** `FACETS_PROFILE=<sandbox_profile>` = sandbox CP (do QA here).
  `FACETS_PROFILE=<prod_profile>` = **PRODUCTION** — only publish there once a fix is proven
  in sandbox, and only when explicitly asked. Never QA against prod. The repo's
  `.claude/settings.json` may force `<prod_profile>`, so set the profile **explicitly on
  every command**.
- **Scope:** project `<test_project>`, env `dev`, on `<cp_host>`.
- **AWS profiles** — match the account before any AWS CLI call
  (`aws sts get-caller-identity --profile <p> --query Account`). Sandbox test
  account is **`<aws_sandbox_profile>`** (`<account_id>`, us-west-2) — and `<aws_sandbox_profile>` can write S3,
  **`<aws_alt_profile>` cannot**. Wrong profile → `NotFound` errors that masquerade as bugs.
- **Never touch pre-existing infra.** Only tear down artifacts created during this
  QA run. Never destroy/delete anything you didn't create, or real data.
- **Sandbox fix policy is breaking-gated (see §7).** Sandbox is a pure testing env,
  so on a found bug you MAY fix the module in <module_source_repo> source + publish + retest in
  sandbox **without asking — IF the change is non-breaking.** A change is *breaking*
  if it could force-replace/destroy resources already created by other blueprints on
  this module version, removes/renames a spec field, changes the output schema, or
  changes a default that alters existing behavior. Breaking → STOP, flag it, plan a
  NEW module version, get explicit approval. When unsure whether a change is
  breaking, treat it as breaking.
- **Real applies that create/destroy infra** run freely in sandbox (env `dev`,
  cloud_account enabled). Publishing to **prod** (`FACETS_PROFILE=<prod_profile>`) always
  needs explicit approval. Confirm git-push target vs CP-publish target **per task**
  ("publish" ≠ "commit to <module_source_repo>").
- **Always seed a resource spec from the module's facets.yaml `sample:` block** —
  never create with an empty spec (empty spec crashes on missing required fields).
- **Defaults live in `facets.yaml`, not hardcoded in terraform.** A `try()`-less read
  of an optional/override-only field with no facets.yaml default is the #1 crash.
- **UI is for verification only.** Drive every blueprint/override/release *mutation*
  through `raptor`. Use the **agent-browser** agent for form checks — not claude-in-chrome.
- **Don't touch terraform `ignore_changes` without asking.**
- **Run raptor commands standalone**, not as compound `cd …; raptor …` (the
  permission classifier denies compound commands).

## 1. The QA lifecycle (per module)

The full ladder the resource goes through. Stop and report at the first real bug.

0. **Resolve dependencies first.** Build the dependency tree (output-type → producer),
   topo-sort, create/reuse dependencies before dependents. Wire each input to its
   producer resource (don't leave inputs dangling).
1. **Create seeded from `sample:`, then populate ALL config (L1 — core).** Create the
   resource via raptor using the facets.yaml `sample:` spec as the seed (never empty),
   THEN populate **every** spec field the facets.yaml exposes — required AND optional,
   blueprint AND `x-ui-overrides-only` (the latter into the env override) — with valid
   values. The point of this skill's config test is that terraform handles the *whole*
   config surface, not just the `sample:` subset. Build the full spec from the
   facets.yaml `properties` tree (mechanics in **§2.5**). Optional fields with no
   facets.yaml default are exactly where `try()`-less reads crash, so they must be
   exercised, not skipped.
2. **Form-clickability verify (L2 — only for complex x-ui).** Run the agent-browser
   form check (full mechanics in **§2**) ONLY for modules whose facets.yaml has
   array-of-object fields or `patternProperties` maps — the field types where UI-render
   bugs actually occur. Skip the browser pass for plain string/boolean/integer/object
   modules; L1 already proves their config. Pre-scan flags candidates (§2 pre-scan).
3. **Plan (blast-radius gate).** `raptor create release ... --plan` first — always
   see what would be created/destroyed before any real apply.
4. **Real apply.** `raptor create release ...` (no `--plan`). Sandbox env `dev` has
   cloud_account enabled → this provisions real AWS. Defaults, IAM perms, and provider
   quirks surface here.
5. **Verify outputs + per-key creation.** Confirm the resource is actually healthy,
   not just "apply ok": (a) Facets live outputs via
   `raptor get resource-outputs <kind>/<name> -p <proj> -e <env> -o json` — every
   declared output must be populated; (b) per-config-key creation in the cloud via
   AWS CLI. Record EACH config key set and whether it materialized (a per-field
   results table — see §8). Use `aws ... --output text`; `--output json` may render
   schema not values in some shells.
6. **Verify tags + naming (§6).** Assert the composed tag set against the R1-R18 tag
   rules — load the `<org>-tag-rules` skill if it is installed; the checklist is also
   inlined in §6 (Layer hardcoded, OwnerTeam/SubEnv from registry, config+team singleton
   FinOps tags, Tenancy/Name) — and confirm config/team singleton wiring. Check the
   rendered terraform name per the `<org>-module-rules` convention if that skill is
   installed — **record, do not fail on naming** (convention unconfirmed).
7. **Teardown.** Disable the resource (`--disabled`), release with `--allow-destroy`
   to destroy it, then delete the resource. That way existing infra is never touched.

A clean plan ≠ a clean apply; a failing plan is a hard stop. Track results in a
running progress doc (module | L1-config | L2-form | plan | real-apply | tags |
naming | bugs | fix-status) and note which modules hit live infra vs plan-only.

## 1.5 Phase 0 — CP prerequisites (publish-first, idempotent)

A module can only be released after it is PUBLISHED on the target CP, with its
intent registered, its input/output types existing, and an aws resource-type
mapping. Mapping ≠ published; published-in-source ≠ published-on-sandbox. Run
this before the lifecycle for any module not already published. Every step is
idempotent — safe to rerun.

1. **ALWAYS (re)publish from <module_source_repo> SOURCE before testing — even if already published.**
   A release uses the PUBLISHED module, not your local source; a pre-published version
   can be STALE vs source, so testing it validates the wrong code (real example:
   kinesis_stream pre-published copy lacked the source's stream_name→name fix and crashed
   "Missing required argument" despite a correct effective spec). So the publish step is
   NOT conditional on "is it published" — `raptor create iac-module -f <source-dir> --publish`
   (idempotent) every time. Only the output/input-type + intent prerequisites below are
   conditional. If a module already-tested-as-PASS turns out to have been on a stale
   published version, re-verify it after the source republish.
2. **Register input AND output types.** Dry-run surfaces missing types:
   `raptor create iac-module -f <dir> --dry-run`. For each
   `references non-existent output type '<T>'` (these come from BOTH the
   module's `outputs:` and its `inputs:` — check both), pull the schema from
   prod and create on sandbox:
   - `FACETS_PROFILE=<org> raptor get output-type '<T>' -o yaml > /tmp/<n>.yaml` (read-only on prod)
   - `FACETS_PROFILE=<sandbox_profile> raptor create output-type '<T>' -f /tmp/<n>.yaml`
   Types already present on sandbox (e.g. `@facets/mysql`, `@facets/postgres`,
   `@facets/<org>_config`) are reused — only create the missing ones. Re-run
   the dry-run until it reports "ready to upload".
3. **Publish with intent auto-create.** New intents (a `kind` never seen on this
   CP) are NOT created by `resource-type-mapping` — it rejects them
   ("Invalid intent names"). Use the `--auto-create` flag, which registers the
   intent if absent, and `--publish` to promote in one shot:
   `raptor create iac-module -f <dir> --auto-create --publish`.
   (Without `--auto-create`, a brand-new intent 404s "Intent not found".)
4. **Map the resource type to the aws project type** (needed before creating a
   resource instance): `raptor get resource-type-mappings aws | grep <kind>/<flavor>`
   or `raptor create resource-type-mapping aws --resource-type <kind>/<flavor>`.

**Determinism inputs (so reruns produce identical specs):**
- Standing base resources kept enabled: `cloud_account`, `config` (+ shared
  producers like the spoke VPC / EKS cluster once stood up).
- Valid tag-registry values come from `config/<flavor>/<version>` outputs.tf:
  `OwnerTeam ∈ team_entry` (the values your config/team singleton outputs.tf allows),
  `SubEnv ∈ sub_env_entry` (the values your config singleton outputs.tf allows). Pick from these — never
  invent. The config singleton already emits Product/SubProduct/EngineeringEnv/SubEnv.

## 1.6 Release strategy — per-dependency-level batched

Drive releases **per dependency level**, not per single module: enable all
ready modules at one level (e.g. all storage/messaging leaves), then one
selective release targeting that whole level
(`raptor create release ... --target <a> --target <b> … --target cloud_account --target config`).
raptor serializes releases per env, so batching cuts overhead (one terraform
init per level, not per module) without losing attribution — terraform plan is
per-resource, so read the plan gate per module. If a module errors at apply,
drop it from the level's target set, fix it (§7 gate), and re-release the level.
Known-risky modules may get their own single-target release. Levels:
1. base (cloud_account, config) → 2. producers (kms, iam_policy, network) →
3. storage/messaging leaves → 4. network-dependent (redis/rds/aurora/docdb/es/lb)
→ 5. eks-cluster-dependent (helm/k8s_resource/namespace/node_pool/eks_addons/karpenter)
→ 6. standalone (apigateway/ses/step_functions).

## 2. How to test the UI (form verification)

Two surfaces must pass: the **blueprint** form and the **per-env Resource Center
override** form. Use the **agent-browser** agent (not claude-in-chrome). UI is
verification-only — **discard every test edit** at the end; never mutate through it.

### Routing (sandbox CP)

Host `https://<cp_host>`. Project `<test_project>`, env `dev`.

| Screen | URL |
|---|---|
| Project overview / blueprint graph | `/v2/projects/<test_project>/overview` |
| Env settings | `/v2/projects/<test_project>/environments/<envId>/settings` |
| Env Resource Center (override forms) | `/v2/projects/<test_project>/environments/<envId>/resources` |

`<envId>` is the opaque CP id (e.g. `6a326782b2d5c75bfa90c9df`) — **read it from the
URL after selecting the env, don't guess.**

**(a) Blueprint resource form:**
1. Open `/v2/projects/<test_project>/overview` → the Blueprint Resources graph (canvas of nodes).
2. Find the node. Search **highlights but does NOT filter** — if off-screen, pan the canvas (click-drag) to reach it.
3. Click node → context menu → **Configure**. Form opens with a **Form/JSON toggle** (top) and a **field-nav list on the right** enumerating every section.

**(b) Per-env override form (Resource Center):**
1. Select env `dev`; note `<envId>` from the URL.
2. Open `/v2/projects/<test_project>/environments/<envId>/resources` → target resource → its override form.
3. This surface shows the `x-ui-overrides-only: true` fields (invisible in the blueprint form).

### Driving the browser (per field)

Loop per screen: **navigate → screenshot → read page (interactive) → act → screenshot to confirm.**
Login: host → email `<your-sso-login>` → SSO/Google; session persists; **never type passwords**. For parallel per-module checks, run a subagent in **its own tab**.

Exercise **every** field (rule: *"verify each and every field is clickable and added via form"*):
- **Text** → type a value → it lands + Save enables.
- **Boolean** → click → state flips.
- **Dropdown** (e.g. Flavour) → open → options render.
- **Array** → click `[+]` / "+ Add Items" → confirm an editable row/sub-form actually appears.
- **Editor field** (Yaml/Json) → editor renders.

When a control is ambiguous (array `[+]` collapses), cross-check via the **JSON view**
(what the click wrote to spec) and a **DOM/page read** of the section — ground truth.

### Pass / fail criteria

**PASS** = control appears AND is editable (text accepts input + Save enables; toggle flips;
dropdown opens; array-of-string shows editable repeatable rows; map shows key/value editor;
nested object shows a sub-section; editor field shows the code editor).

**FAIL (array-of-object)** = expanding the section shows the literal
**`Array type "object" not yet supported`** and **zero** editable sub-fields. Tell-tales:
the field's right-nav entry is **greyed-out**; clicking `[+]` writes an empty item (triggers
the unsaved-changes prompt) but **no sub-form persists** — it collapses to header + `[+]`.
Don't conclude "works" from the modal alone.

| facets.yaml type | Form behavior |
|---|---|
| `array` items=**object** | **BROKEN** — `Array type "object" not yet supported` |
| `array` items=**string** | Works — "+ Add Items" → editable rows + delete + item counter |
| `object` + `patternProperties` (map) | Works — key/value editor |
| `object` (nested) | Works — sub-section |
| string / boolean / integer | Works |
| editor-enabled (Yaml/Json) | Works — the only acceptable carrier for complex/array data |

**Pre-scan complement:** before opening the UI, grep every module's facets.yaml for
`items:` blocks with `type: object` to flag array-of-object form-breakers up front.

### Confirming `x-ui-overrides-only`

Two-surface contrast: a field is override-only when it is **absent from the blueprint
form but present in the env-override form.** Example (spoke VPC): blueprint form shows
only DNS/Appliance under the TGW section (the IDs correctly absent); env-override form
renders Primary VPC CIDR, Availability Zones, and Transit Gateway ID.

### Gotchas

- Graph search highlights, doesn't filter — pan to off-screen nodes.
- Array `[+]` is deceptive — verify via expand + DOM/JSON, not the modal.
- JSON-view toggle may need a retry to switch.
- Some menus need **hover, not click**.
- **Discard all test edits** at the end — bottom bar must read greyed **"Saved"** (no pending changes). Never leave a QA artifact.
- Subagent per module = its own tab; returns per-field PASS/FAIL + the exact UI string + the state it left behind.

## 2.5 Full-config population (L1 — the core config test)

The `sample:` block is a *minimal* spec. This skill's config test requires the
**whole** config surface to plan/apply cleanly, so build a full spec covering
every field, then release.

1. **Enumerate the field set.** Read facets.yaml `spec.properties` (and any
   nested `properties` / `patternProperties` / array `items`). List required +
   optional + `x-ui-overrides-only` fields. Note each field's type, `enum`,
   `default`, `minimum`/`maximum`, and whether it's override-only.
1b. **NEVER set resource-name override fields** (stream_name, topic_name, table_name,
   override_name, name_override, function_name, bucket_name, lb_name, etc.). Names must
   AUTO-GENERATE via the canonical convention; name overrides exist only for brownfield
   import. Omit them from test specs. (This also exercises the autogen path — see the
   try/coalesce bug class below: `try(local.spec.X_name, <autogen>)` is BROKEN when X_name
   is `optional()` in variables.tf, because `try` passes null through instead of falling to
   the autogen fallback → "Missing required argument". Fix in source to
   `coalesce(try(...,null), <autogen>)`. The plan-gate surfaces this.) This is the
   QA-testing rule — production brownfield imports DO set resource-name overrides, per the
   design skill's dual-mode naming section; the two are different paths, not a contradiction.
2. **Author values for every field.** Start from `sample:`, then add each
   missing field with a valid value: pick a legal `enum` member, satisfy
   `minimum`, use a real dependency ref for ID-typed fields (VPC/subnet/SG/role
   ARNs come from wired producers, not invented).
   Blueprint-visible fields go in the resource spec; `x-ui-overrides-only` fields
   go in the **dev override**.
3. **Apply the full spec, not `--set` field-by-field.** Use `--spec-file f.json`
   (blueprint) and `--spec-file` on the override — `--set` booleans can fail
   structural validation, and a JSON file is the only reliable carrier for
   nested/array/map data.
4. **Release + plan.** A field the module reads `try()`-less with no default
   crashes here when populated in an unexpected combination — that's the bug
   this layer is built to catch.
5. **Record coverage.** Note any field you could NOT populate (e.g. needs a real
   external credential, or an array-of-object the form/schema can't carry) and
   why — that gap is itself a finding (§5 classes).

Do NOT invent IDs/ARNs/account values to fill a field — wire from a real
producer resource or leave it and record the gap. Inventing values produces
false passes.

## 3. raptor CLI cheat-sheet

```bash
# --- create / wire a resource (seed spec from facets.yaml sample:) ---
raptor apply resource <intent>/<flavor>/<ver> -p <test_project> -n <name> \
  --input <inputname>=<producer-intent>/<producer-name> \
  [--set KEY=VALUE | --spec-file f.json] --yes
#   enable/disable in blueprint: --enabled / --disabled

# --- env overrides (layered on blueprint, per-env) ---
raptor apply override <intent>/<name> -p <project> -e <env> --set KEY=VALUE -y
raptor apply override <intent>/<name> ... --disabled -y          # disable in this env
raptor apply override <intent>/<name> ... --spec-file f.json -y  # REPLACES whole spec
#   --set merges (preserves other fields). Booleans via --set can fail structural
#   validation -> use --spec-file with a real JSON boolean.

# --- releases ---
raptor create release -p <project> -e <env> --plan              # plan-only gate
raptor create release -p <project> -e <env>                     # real apply, all
raptor create release -p <project> -e <env> --target <intent>/<name>  # selective (repeatable)
raptor create release -p <project> -e <env> --allow-destroy     # permit destroys
raptor create release ... -w                                    # wait + tail logs
#   Selective releases MUST include cloud_account + config (they populate provider
#   config) — else post-destroy applies fail with "object with no attributes".

# --- prerequisites ---
raptor create resource-type-mapping <project-type> --resource-type <intent>/<flavor>
#   else: "not available in project type 'aws'". Map first.
raptor create output-type @facets/<name> -f /tmp/<name>.yaml
#   register output-types BEFORE publishing modules that emit them. (Pull the schema
#   read-only from prod <org> CP, then create on sandbox.)

# --- module publish: exactly as in the `build-facets-module` skill's Development
#   Workflow (create → PREVIEW → publish). Its validation covers: facets.yaml schema,
#   required vars (instance/instance_name/environment/inputs), terraform fmt -check,
#   init, validate, trivy (if installed).

# --- env lifecycle / inspect ---
raptor launch environment <env> -p <project> -w
raptor destroy environment <env> -p <project> --yes -w
raptor get iac-module -o wide | grep <flavor>                   # stage PREVIEW/PUBLISHED
raptor get release -p <project> -e <env> -o wide                # release history/status
raptor get resource <intent>/<name> -p <project> -e <env> -o json
```

When bulk-republishing: **output-types before modules.** For intent class, try
without `-a`; on "Intent not found"/404, retry with `-a` (built-in intents reject `-a`).

## 4. Publish workflow (after a fix is approved)

1. Publish to **sandbox** exactly as in the `build-facets-module` skill's Development
   Workflow (create → PREVIEW → publish). The `--dry-run` must pass clean — the
   `required_providers` warning is pre-existing/benign in these modules.
2. Re-plan/apply on sandbox to prove the fix.
3. Only then ship to **prod**, if asked. **Linked modules repo (the usual case):
   commit → push branch → PR → merge, and CI publishes to prod — merge ⇒ publish.**
   Direct `raptor publish` to prod only when NO modules repo is linked (and it
   still needs explicit approval either way).
4. Commit to the module git repo if asked (confirm target — sometimes "don't push
   to <module_source_repo> this time"). Note: `main` may be **protected** (no force-push) — don't
   squash already-pushed commits; add a follow-up commit instead.
5. CP publish ≠ git commit ≠ deployed behavior — except on a linked repo, where
   merging to the default branch IS the prod publish. A comment-only change needs
   no sandbox republish but will still republish on merge (harmless).

## 5. Common module bugs (what to actually look for)

- **array-of-object spec fields are UI-uneditable** — "Array type 'object' not yet
  supported." Fix: map + patternProperties (or an editor-enabled field). array-of-string
  and maps render fine.
- **empty-spec crash** — creating with no spec set crashes on a missing required field
  (e.g. dynamodb `hash_key`). Always seed from the facets.yaml `sample:`.
- **`try()`-less optional reads** — module reads an optional / `x-ui-overrides-only`
  field directly → plan crashes when unset (e.g. config `EngineeringEnv`/`SubEnv`).
  Fix: `try(...)` + a facets.yaml default.
- **default hardcoded in terraform, not facets.yaml** — value invisible/uneditable;
  or the reverse, a facets.yaml default silently fills a field the user thought was off.
- **field missing from the OVERRIDES schema** — a field marked `x-ui-overrides-only`
  but absent from the OVERRIDES schema can't be set via override at all. Also watch
  `minimum`/`required` that make a value impossible to zero/disable (e.g. eks
  `create_default_node_pool` missing; `desired_size` `minimum: 1`).
- **booleans via `--set`** — can fail structural validation; fall back to `--spec-file`
  with a real JSON boolean.
- **required-but-marked-optional** — a field "optional" in schema but actually needed
  for a usable resource (e.g. firehose `s3_configuration` bucket_arn+role_arn).
- **missing IAM auto-create** — module demands an externally-supplied `role_arn`;
  better to have the module create the role itself (mind the ≤64-char name limit).
- **no portable placeholder artifact** — lambda / lambda_layer crash on initial create
  when the S3 code object doesn't exist; fix = bundle a `placeholder.zip` in the module
  with a `filename = "${path.module}/placeholder.zip"` fallback.
- **missing variables.tf / outputs.tf** — a module shipped without them while
  main.tf/locals reference `var.instance/instance_name/environment/inputs`; tf init
  fails. Fix: copy from a sibling flavor.
- **wrong output_name wiring** — wire an input to the typed sub-output
  (`output_name: attributes`), not `default`, when the schema demands it.
- **output gated on a failed submodule** — e.g. an EKS `kubernetes-details` output
  gated on the whole eks submodule; a failed node group leaves it unresolved →
  downstream helm/k8s_resource silently skipped.
- **IAM gaps on the release runner** — real applies fail `AccessDenied` on perms the
  runner lacks (`athena:CreateWorkGroup`, `glue:CreateJob`, `kinesis:AddTagsToStream`).
  Not a module bug — get the perm granted, re-apply.
- **NOT module bugs** (classify explicitly): lambda_layer's s3_bucket/s3_key source is
  by-design; `sns_platform_application` needs real APNS/GCM creds (not sandbox-applyable).

## 6. Tag & naming verification

After a real apply, assert tags and naming. **If an `<org>-tag-rules` skill is
installed, load it first** — it owns R1-R18 (config singleton wiring, spec.tags
shape, hardcoded Layer, registry-driven OwnerTeam/SubEnv). Either way this section
is the assertion checklist, so you can proceed from it directly when that skill is
absent.

**Tags (must all hold):**
- **Layer** present and **hardcoded** in the module (not user-supplied).
- **OwnerTeam** and **SubEnv** resolved from the registry (config/team singleton
  via `x-ui-output-type`), not free-typed literals.
- **config + team singleton FinOps tags** present on the resource: Product /
  SubProduct / EngineeringEnv / SubEnv from the `@facets/config` singleton, and
  the team tags from the `@facets/team` singleton. Confirm the module actually
  WIRES these singletons as inputs and merges them — a module that declares the
  inputs but never merges them emits empty tags (silent failure).
- **Tenancy** and **Name** correct per-resource.
- Verify the **rendered** tag set, not just the plan intent: read it back
  (`raptor get resource ... -o json` for the planned tags, or the AWS resource's
  actual tags post-apply via the cloud CLI).

**Config/team singleton wiring check:** the module's facets.yaml inputs must use
`@facets/config` / `@facets/team` (not `@outputs/...`), and main.tf/locals must
merge the singleton outputs into the resource tag map. Grep the module:
inputs declared → singleton outputs referenced → merged into tags. A break
anywhere = empty/missing FinOps tags.

**Naming:** compute the expected terraform resource name using the `<org>-module-rules` convention if that skill is installed
(formula: `lower(join("-", compact([unique_name, SubEnv, instance_name])))`), compare to
the rendered name, and **record the result — do NOT fail the module on naming.**
The convention is unconfirmed and will change; flag mismatches for review only.

## 7. Fix gate — breaking vs non-breaking

When testing finds a real module bug (TF crash, tag-wiring break, missing
default, etc.), decide before editing:

**Non-breaking → fix freely in sandbox (no approval needed).** The change does
NOT alter existing resources created on this module version by other blueprints.
Typical non-breaking: adding a `try()` + facets.yaml default, adding a missing
optional field, fixing tag-merge wiring, bundling a placeholder artifact, adding
missing variables.tf/outputs.tf. Procedure: fix in
`<modules_root>/...`, `terraform fmt`, publish to sandbox
(§4 steps 1-3), re-plan/apply to prove the fix, record.

**Breaking → STOP, flag, plan a NEW version, get approval.** A change is breaking
if it could:
- force-replace or destroy resources already created on this version,
- remove or rename a spec field (existing blueprints reference it),
- change the output schema (downstream wiring breaks),
- change a default in a way that alters existing resource behavior.

Procedure: do NOT edit the published version in place. Record the bug + the
proposed fix, propose it as a new module version (e.g. `1.0` → `1.1`), and get
explicit approval before authoring/publishing. Other blueprints pin the current
version, so they migrate deliberately.

**When unsure whether a change is breaking, treat it as breaking** and ask.

## 8. Reporting

Produce a concise findings doc per module: what was tested, what passed, each bug with
(a) the exact error string, (b) root cause, (c) recommended fix, (d) any sandbox
workaround applied. **Separate "module bug" from "environment/permission/credential
issue"** — different owners. Keep account numbers out of anything customer-facing;
concise, neutral tone, commands over prose.

Per-module result row: `module | L1-config (all fields applied?) | L2-form (n/a
unless complex x-ui) | plan | real-apply | tags (R1-R18 pass/fail) | naming
(recorded, non-failing) | bugs | fix-status (none / fixed-nonbreaking-published /
flagged-breaking-needs-new-version)`. For any fix, note the breaking
classification and, if breaking, the proposed new version. For the current
full-set run, keep the running table alongside
`<blueprints_repo>/<test_project>/_module-testing-inventory.md`.

**Keep a running SOP / improvements log** (e.g.
`<blueprints_repo>/<test_project>/_module-testing-sop.md`): whenever you hit a
process gap, a missing-prereq surprise, a raptor quirk, or a recurring module-bug
class, append it with a fix/automation idea + status. Append-only. These get folded
back into THIS skill so each rerun is more automated and reproducible.
