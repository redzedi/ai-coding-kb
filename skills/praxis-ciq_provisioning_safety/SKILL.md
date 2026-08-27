---
name: "praxis-ciq_provisioning_safety"
description: Adds capability to detect resource naming conflicts and existence conflicts
  before provisioning resources in the ciq-apps Facets project. Checks across base
  and dependent environments to prevent duplicate resource errors, state conflicts,
  and naming collisions during releases or resource apply operations.
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

# CIQ Apps Provisioning Safety Check

Before provisioning **any** resource in the `ciq-apps` Facets project, this skill enforces a pre-flight conflict check across all base and dependent environments to prevent naming collisions, duplicate resource errors, and state conflicts.

## When to Load This Skill

Load this skill whenever:
- Creating or applying a new resource in `ciq-apps`
- Triggering a release or hotfix in `ciq-apps`
- Adding a resource to a dependent/child environment
- User asks to provision, create, apply, or deploy resources in `ciq-apps`

---

## Pre-Provisioning Conflict Check Workflow

### Step 1: Identify Target Environment and Resource

Before anything else, confirm:
- **Target environment**: Which environment is being provisioned into?
- **Resource(s)**: What is the `type/name` of the resource(s) being added?
- **Environment type**: Is this a base environment or a dependent (child) environment?

If unclear, use `AskUserQuestion` to confirm before proceeding.

---

### Step 2: Fetch All Environments in ciq-apps

Delegate to `raptor-operations` subagent:

```
raptor get environments -p ciq-apps
```

From the result, identify:
- The **base environment(s)** (typically the root/parent environment)
- All **dependent environments** (environments launched from a base)
- The relationship between them (which depends on which)

---

### Step 3: List Resources in Base Environment

Delegate to `raptor-operations`:

```
raptor get resources -p ciq-apps -e <BASE_ENV_NAME>
```

Collect the full list of resource identifiers in the format `type/name`.

---

### Step 4: List Resources in Target and Sibling Dependent Environments

For each dependent environment (including the target):

```
raptor get resources -p ciq-apps -e <DEPENDENT_ENV_NAME>
```

Build a map:
```
Environment → [resource_type/resource_name, ...]
```

---

### Step 5: Run Conflict Detection

Check for the following conflict types:

#### 5a. Naming Conflict (Same type/name exists in base)
- Does the resource `type/name` being provisioned already exist in the **base environment**?
- If YES → **BLOCK** — this will cause a state conflict when the dependent environment inherits or shares base resources.

#### 5b. Naming Conflict (Same type/name exists in another dependent env)
- Does the same `type/name` exist in a **sibling dependent environment**?
- If YES → **WARN** — may not be a hard block but flag for review. Could indicate misconfiguration or duplication.

#### 5c. Cross-environment Resource Reference Conflict
- Does the resource being provisioned reference another resource via `${type.name.out.attribute}` that exists ONLY in the base but is being overridden in the dependent?
- If YES → **WARN** — ensure the dependent's override is intentional.

#### 5d. Duplicate Resource in Same Environment
- Does the target environment already have a resource with the same `type/name`?
- If YES → **BLOCK** — cannot provision a duplicate. Either update the existing resource or choose a different name.

---

### Step 6: Config Resource Conflict Check

Config resources are a special class of resources in `ciq-apps` that act as the **source of truth for naming and dynamic values** used by other resources. They are referenced via:

```
${config.<name>.out.<attribute>}
```

This means names of other resources are often **derived from config outputs**, not hardcoded. This step checks for config-level conflicts that would cause downstream naming issues.

#### 6a. Identify All Config Resources Across Environments

Delegate to `raptor-operations` for each environment:

```
raptor get resources -p ciq-apps -e <ENV_NAME>
```

Filter results to extract all resources of type `config` (or equivalent config resource types used in the project). Build a per-environment config resource map:

```
Environment → [config/<name>, ...]
Config Name → Output Attributes
```

#### 6b. Check Config Resource Existence in Target Environment

For each resource being provisioned that has an `inputs` block referencing `${config.<name>.out.*}`:
- Does `config/<name>` exist in the **target environment**?
- If NO → **BLOCK** — the config resource must exist before any resource that derives its name or value from it can be provisioned.

#### 6c. Check Config Output Conflicts Across Environments

If the same `config/<name>` exists in both base and a dependent environment:
- Fetch both config resource definitions and compare their output values
- If the same output attribute resolves to **different values** across environments → **WARN** — resources in dependent env may get different names than in base, which could cause conflicts if they share state.

Use:
```
raptor get resource -p ciq-apps -e <ENV_NAME> -r config/<name>
```

#### 6d. Dynamic Name Derivation Conflict

If a resource name in the provisioning request is dynamically derived from a config output (e.g., the resource `type/name` includes a variable segment pulled from config):
- Resolve what the actual name will be in both base and dependent environments
- Check if the **resolved name** already exists in either environment
- If YES → **BLOCK** — the derived name conflicts with an existing resource

#### 6e. Config Resource Naming Conflict (Same config name in base and dependent)

If a new `config/<name>` is being provisioned:
- Does a config resource with the same name already exist in the base?
- Does it exist in sibling dependent environments?
- Apply the same BLOCK/WARN rules as Step 5a and 5b

---

### Step 7: Report Findings Before Proceeding

Present a structured pre-flight report:

```
## Pre-Provisioning Conflict Report — ciq-apps

Target Environment : <env_name>
Resource(s)        : <type/name>

### Resource Conflicts

| Conflict Type           | Resource      | Environment  | Severity | Recommendation              |
|-------------------------|---------------|--------------|----------|-----------------------------|
| Duplicate in base       | postgres/db   | base-env     | BLOCK    | Rename or reuse existing    |
| Exists in sibling       | service/api   | dep-env-2    | WARN     | Confirm intentional         |

### Config Resource Conflicts

| Conflict Type               | Config Resource    | Environment  | Severity | Recommendation                          |
|-----------------------------|--------------------|--------------|----------|-----------------------------------------|
| Config missing in target    | config/app-config  | dep-env-1    | BLOCK    | Provision config resource first         |
| Output value mismatch       | config/db-config   | base vs dep  | WARN     | Derived names may differ across envs    |
| Derived name already exists | postgres/app-db-01 | base-env     | BLOCK    | Rename config output or use unique name |

### Safe to Proceed: YES / NO
```

- If **BLOCK** conflicts exist → **DO NOT proceed**. Present the conflict details and ask the user how to resolve.
- If only **WARN** conflicts exist → Inform user and ask for explicit confirmation before proceeding.
- If **no conflicts** → Proceed with provisioning and note "Pre-flight check passed."

---

## Resolution Guidance

### When a resource already exists in base:
- Consider using the **existing resource** via input reference: `${type.name.out.attribute}`
- Or provision with a **unique name** specific to the dependent environment (e.g., `postgres/main-db-dep1`)

### When a resource exists in a sibling dependent env:
- Confirm the resource is intentionally duplicated (different config per env)
- Ensure naming is distinct enough to avoid confusion in outputs/references

### When a duplicate exists in the same environment:
- Use `raptor get resource -p ciq-apps -e <env> -r <type/name>` to inspect the existing config
- Decide: update existing config or abandon the new provisioning

### When a config resource is missing in the target environment:
- Provision the config resource first before the dependent resource
- Ensure config outputs are set correctly for the target environment

### When config output values differ across environments:
- Check if the difference is intentional (env-specific config)
- If unintentional, align the config values or use environment-specific overrides explicitly

### When a derived name conflicts:
- Adjust the config output attribute value so the derived name is unique
- Or explicitly override the resource name in the dependent environment

---

## Tools Used

| Task                              | Tool/Command                                                        |
|-----------------------------------|---------------------------------------------------------------------|
| List environments                 | `raptor get environments -p ciq-apps` via raptor-operations         |
| List resources in env             | `raptor get resources -p ciq-apps -e <env>` via raptor-operations   |
| Inspect specific resource         | `raptor get resource -p ciq-apps -e <env> -r <type/name>` via raptor-operations |
| Inspect config resource           | `raptor get resource -p ciq-apps -e <env> -r config/<name>` via raptor-operations |
| Get resource outputs              | `raptor get resource-output-expressions -p ciq-apps` via raptor-operations |

---

## Key Principles

- **Never skip the pre-flight check** — even for "small" resources. Naming conflicts in Terraform state are hard to undo.
- **Base environment is authoritative** — dependent environments inherit from base. Always check base first.
- **Config resources drive naming** — always check config resources before provisioning anything that references them.
- **Resolve config before dependents** — if a config resource is missing in the target env, provision it first.
- **Block on hard conflicts, warn on soft** — BLOCK prevents state corruption; WARN gives user agency.
- **One check per provisioning operation** — if multiple resources are being provisioned in one release, check ALL of them before triggering.

---

## Common Pitfalls

- **Assuming dependent environments are isolated** — they share Terraform state ancestry with the base. A resource with the same name in base + dependent will collide.
- **Skipping sibling env checks** — a resource may look unique in base but already exist in another dependent, causing confusion in outputs.
- **Ignoring config-derived names** — the actual resource name after config interpolation may be different from what was specified. Always resolve dynamic names before checking.
- **Provisioning dependents before config** — if a resource relies on a config output for its name or value, the config resource must exist first.
- **Proceeding on WARN without confirmation** — always get explicit user sign-off before provisioning when soft conflicts exist.
