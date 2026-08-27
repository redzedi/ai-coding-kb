---
name: "praxis-facets-gcp-zero-change-import"
title: "Facets GCP Zero-Change Import"
description: "Use when adopting or owning an existing GCP estate (shared VPC, Cloud SQL, GKE, Pub/Sub, GCS, Memorystore, Cloud Tasks) into Facets-managed Terraform, doing a zero-change read-only import, or launching a new environment/region off an imported blueprint and validating each module type greenfield. Triggers on: import existing GCP into Facets, zero-change import, own existing infra in Facets, new region/environment launch, greenfield module validation, shared-VPC/shared-project import."
triggers: ["gcp import", "zero-change import", "own existing infra", "new region launch", "greenfield validation", "shared vpc import"]
category: "infrastructure"
tags: ["gcp", "import", "terraform", "zero-change", "greenfield", "migration", "shared-vpc"]
icon: "🌩️"
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

# Owning existing GCP infrastructure in Facets

## Overview

Three phases with hard gates between them:

```
  Phase A  ZERO-CHANGE IMPORT   adopt the live estate read-only; gate on a 0 destroy / 0 replace /
                                0 real-change plan before any apply.
  Phase B  GREENFIELD VALIDATE  enable ONE representative of EACH module type in a NEW env; deploy +
                                verify it matches the imported home env. Prove every module type works
                                greenfield before scaling.
  Phase C  SCALE OUT            bulk-enable the rest, by type, once each type is proven.
```

**Core principle — the cardinal rule.** When the new environment shares the home (prod) env's GCP
**project and/or VPC** (common, since a new region often reuses the existing project), **no change in
the new env may affect the home env.** Every shared-scope resource (CIDRs, VPC-scope CloudDNS domains,
GKE master ranges, firewall rules, peerings, project-global names) must be proven isolated *before*
apply. This rule overrides convenience.

## When to use

- Adopting a running GCP estate into Facets without mutating it (read-only import).
- Standing up a new region/environment off an already-imported blueprint.
- Validating that each blueprint module type provisions correctly greenfield.
- Any work where a new Facets env shares a project/VPC with a live one.

**Not for:** brand-new estates with no existing infra (no import phase needed — just build), or
non-GCP clouds (the method generalizes, but the nuances catalog is GCP-specific).

## Pairs with (don't duplicate these)

`praxis-zero-change-import` (cross-cloud umbrella) · `praxis-terraform-import` · `design-facets-module`
+ `build-facets-module` (when a module needs a greenfield-create path).

## The discipline (this is what makes it repeatable)

Every engagement MUST:
1. **Instantiate the SOP** — copy [sop-template.md](sop-template.md) into the customer's folder, fill
   the context block, enable order, and naming rules. This is the engagement's operating manual.
2. **Follow the playbook + catalog** — read [nuances-catalog.md](nuances-catalog.md) BEFORE Phase B;
   most non-obvious failures are already pre-documented there.
3. **Log every NEW nuance** inline in the engagement SOP as you hit it.
4. **Contribute novel nuances back** to [nuances-catalog.md](nuances-catalog.md) (PR to the central
   copy in `Facets-cloud/facets-assets`). The catalog grows; the next engagement is easier.

## Phase B — per-resource workflow (run for EVERY module type)

```
  a. READ the module main.tf + facets.yaml — note resource vs data blocks, which spec fields are
     env-specific (region/zone, names, CIDRs), and any ignore_changes (import-stability) that the
     greenfield path must tolerate. Confirm the DEPLOYED version (1.0 vs 1.1 differ).
  b. DIFF blueprint vs home-env-effective — single-env imports often parked env-specific values IN
     the blueprint. Anything env-specific in the blueprint must move to a per-env OVERRIDE.
  c. SET overrides for the new env (region/zone + any colliding name + greenfield-only fields).
  d. PLAN-GATE (--plan, targeted): expect ONLY the intended create (+ benign scratch_string).
     0 unexpected destroy/replace → STOP if violated. Plan errors on a missing field ⇒ that field is
     override-only and needs setting in (c).
  e. APPLY (drop --plan). Fire-and-poll, NOT -w (see catalog: the -w stall).
  f. VERIFY LIVE in GCP and diff against the home-env resource — identical except the intended
     region/zone/name.
```

## Quick reference

```bash
# Always prefix raptor with the profile + skip the update check:
RAPTOR_NO_UPDATE_CHECK=1 FACETS_PROFILE=<profile> raptor <cmd>

raptor get environments -p <PROJECT>
raptor get resources    -p <PROJECT> -e <ENV> -o json          # group by resourceType; filter disabled
raptor get resources KIND/NAME -p <PROJECT> -e <ENV> -o json   # .blueprint / .overrides / .effective
raptor apply override KIND/NAME -p <PROJECT> -e <ENV> --set spec.X=Y --enabled --yes -m "..."
raptor apply override KIND/NAME ... --spec-file FILE           # JSON-string (*_json) fields — NOT --set
raptor apply override KIND/NAME ... --unset spec.X             # revert an override
raptor create release   -p <PROJECT> -e <ENV> --plan --target KIND/NAME       # plan-gate: fire, then poll get releases
raptor create release   -p <PROJECT> -e <ENV> --target KIND/NAME              # apply: fire, then poll get releases

# Verify live in GCP via the gateway (read-only). Use the HOME-env integration for broad reads
# (the new-env deploy SA is often least-privilege and lacks read perms like machineTypes.get):
praxis mcp cloud_cli run_cloud_cli --arg integration_name=<integ> --arg command='<gcloud ... --format=json>'
```

## Safety gates (non-negotiable)

- Plan-gate before EVERY apply; 0 unexpected destroy/replace on any resource you didn't intend.
- One representative per type first; never bulk-enable until each type's module is proven greenfield.
- Shared project/VPC ⇒ run the **isolation audit** (catalog §Networking) before any shared-resource apply.
- Never destroy/recreate to "fix" a FAILED release — re-plan first (catalog §Release mechanics).
- Never send customer comms without the engagement owner's review.

## See also

- [nuances-catalog.md](nuances-catalog.md) — symptom → cause → fix for every non-obvious gotcha (READ before Phase B).
- [sop-template.md](sop-template.md) — the per-engagement SOP to instantiate.
