---
name: "praxis-audit-facets-blueprint"
title: "Audit Facets Blueprint"
description: "Review a Facets blueprint for hygiene issues — hardcoded values that should be expressions, override abuse, leaked secrets in base specs, and helm releases that deserve to be promoted into custom modules. Produces a prioritized action-items report. Use when user mentions audit blueprint, blueprint hygiene, review overrides, find hardcoded ARN, override abuse, module promotion candidate, blueprint cleanup, or pre-prod review."
triggers: ["blueprint hygiene", "audit blueprint", "review overrides", "hardcoded arn", "override abuse", "module promotion", "blueprint cleanup"]
version: "1.0"
category: "facets"
tags: ["facets", "blueprint", "audit", "review", "hygiene", "overrides", "modules", "raptor", "best-practices"]
icon: "🔍"
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

# Audit Facets Blueprint

You audit a Facets blueprint for hygiene issues — hardcoded values that should be expressions, override abuse, leaked secrets in base specs, and helm releases that deserve to be promoted into custom modules. The deliverable is a prioritized action-items report (HTML by default).

This skill is for **reviewing what exists**, not for designing or implementing new modules. Pair with `design-facets-module` / `build-facets-module` when the audit surfaces something that needs wrapping.

## When to run this skill

- Before a major prod env stand-up — surface base-spec gaps that would inherit silently into prod.
- After incident-driven migrations where overrides accumulated quickly.
- During renewal / customer-health reviews.
- When considering "should we make a custom module for X chart?"
- When the customer's blueprint has grown organically and nobody is sure what's still hand-tuned vs platform-managed.

## Inputs you need

- Project slug (e.g., `facets-signoz`)
- Environment to audit against (usually the `RUNNING` nonprod env — but any env with an active override set works)
- Raptor auth: `FACETS_PROFILE` set or `~/.facets/credentials` carrying the right profile
- A working directory for dumped specs and the report (e.g., `~/audit-<customer>/`)

## Step 1 — Inventory

Get the lay of the land before diving in.

```bash
raptor get projects
raptor get resources -p PROJECT -o wide
raptor get environments -p PROJECT -o wide
raptor get variables -p PROJECT -o wide
```

Note which resources are enabled in the target env (per-env `disabled: false` overrides), and which are stack-default disabled. Note the project type and the flavors used — heavy reliance on custom `*_<customer>_*` flavors signals a bespoke blueprint where audit value is highest.

## Step 2 — Dump base specs + overrides side-by-side

For every enabled resource, dump both the base blueprint spec and the env-level override into separate files. Reading them side-by-side is the core of the audit.

```bash
mkdir -p audit/raw audit/base
for r in $(raptor get resources -p PROJECT -o json | \
           jq -r '.[] | "\(.kind)/\(.metadata.name)"'); do
  safe=$(echo "$r" | tr / _)
  raptor get resource "$r" -p PROJECT -o yaml > "audit/base/base_${safe}.yaml"
  raptor get overrides "$r" -p PROJECT -e ENV -o yaml > "audit/raw/overrides_${safe}.yaml" 2>/dev/null
done
```

The **base spec** is where stack defaults live — including any plaintext credentials, placeholder ARNs, or stale hardcoded references that nonprod might have overridden but any other env would inherit blindly. This is usually where the worst findings hide.

## Step 3 — Discover available expressions

```bash
raptor describe expressions -p PROJECT
```

This is the canonical list of `${...}` references the blueprint can resolve. Every hardcoded value found in Step 4 should be checked against this list — if an expression exists for it, the hardcoded value is provably an anti-pattern (the right reference is available; the override author didn't use it).

Key expression families to know:

- `${aws_iam_role.X.out.attributes.iam_role_arn}` / `irsa_iam_role_arn` — for IRSA role ARNs
- `${iam_policy.X.out.attributes.arn}` — for policy ARNs
- `${s3.X.out.attributes.bucket_name}` / `bucket_regional_domain_name` / `bucket_arn` — for S3
- `${kafka.X.out.attributes.bootstrap_servers}` / `cluster_name` — for Kafka
- `${kafka_topic.X.out.interfaces.topics.topic_name}` — for topic names
- `${kubernetes_cluster.X.out.attributes.cluster_name}` — for EKS/GKE cluster name
- `${blueprint.self.secrets.X}` — for secrets
- `${blueprint.self.variables.X}` — for project variables
- `${cloud_account.X.out.attributes.aws_iam_role}` / `aws_region` — for cloud account
- `${RESOURCE_TYPE.NAME.out.attributes.namespace}` — for any helm-release-style resource

## Step 4 — Sweep for anti-patterns

Run these greps against the dumped files. Each category maps to a finding type.

### Plaintext secrets in base values_yaml (CRITICAL)

```bash
grep -nE '(password:|api_key:|apiKey:|token:|jwt|signozApiKey:|access_key)' \
  audit/base/*.yaml | grep -vE '\$\{|secretRef|secret_name|secretKeyRef'
```

A base spec containing a real-looking credential is critical — the value leaks via blueprint history, and any env without override inherits it. Always rotate the leaked secret before fixing the blueprint.

### Hardcoded ARNs (HIGH)

```bash
grep -nE 'arn:aws:[a-z0-9-]+:[a-z0-9-]*:[0-9]{12}' audit/base/*.yaml audit/raw/*.yaml | \
  grep -vE '\$\{|arn: \"\$|123456789012'
```

Any ARN string in a values_yaml or spec field is suspect. Should be one of:
- `${aws_iam_role.X.out.attributes.iam_role_arn}` (or `irsa_iam_role_arn`)
- `${iam_policy.X.out.attributes.arn}`
- `${s3.X.out.attributes.bucket_arn}`

Special call-out: **placeholder ARNs with fake account `123456789012`** in base specs are a separate critical finding — they don't break nonprod (which overrides them) but silently break any env that inherits the base.

### Hardcoded AWS account IDs (HIGH)

```bash
grep -nE '[^0-9][0-9]{12}[^0-9]' audit/base/*.yaml audit/raw/*.yaml | grep -vE '#|//'
```

A bare 12-digit number in a spec is usually an AWS account ID. Should never be hardcoded — comes via the cloud_account resource when needed.

### Hardcoded service DNS names (HIGH)

```bash
grep -nE '(kafka.*:9092|.*-brokers\.|.*\.kafka:|.*-bootstrap\.|.*:4317)' \
  audit/base/*.yaml audit/raw/*.yaml | grep -vE '\$\{|0\.0\.0\.0|endpoint: 0'
```

Service endpoints should reference the resource that exposes them. The exception is `0.0.0.0:N` (server-side bind addresses) which are fine.

### Hardcoded S3 endpoints (HIGH)

```bash
grep -nE 's3\.amazonaws\.com|s3\.[a-z0-9-]+\.amazonaws\.com|s3://' \
  audit/base/*.yaml audit/raw/*.yaml | grep -v '\$\{'
```

Should be `${s3.X.out.attributes.bucket_regional_domain_name}` or computed from the bucket resource's outputs.

### Per-env name suffixes baked in (MEDIUM)

```bash
# Adjust ENV_SUFFIX to your project's env-naming convention
ENV_SUFFIX="(nonprod|prod|dev|stg|staging|np|qa|qat|uat)"
grep -nE "$ENV_SUFFIX" audit/raw/*.yaml | grep -vE '#|//|stream:' | head -30
```

For each hit, ask: would a different env need a different value here? If yes, this should be a project variable, a derived expression, or templated by a module. Count how many places the same suffix is repeated — if it's 5+, that's a strong "make it a variable" signal.

### Overrides that duplicate base defaults (LOW)

```bash
for o in audit/raw/overrides_*.yaml; do
  base="audit/base/base_${o#audit/raw/overrides_}"
  [ -f "$base" ] || continue
  # Identify overrides that only set disabled or have minimal content
  bytes=$(wc -c < "$o")
  [ "$bytes" -lt 200 ] && echo "minimal: $o ($bytes bytes)"
done
```

Overrides whose content is `overrides: {}` or only sets `disabled: false` are typically harmless but worth surfacing as dead config that could be cleaned up.

### Internal inconsistencies (MEDIUM)

Look for fields whose values contradict each other within the same resource:
- `clusterName: telemetry-prod` inside a chart whose top-level `clusterName: telemetry-signoz-np` (subchart drift)
- A `kafka_topic` with `replicas: 2` against a `kafka` cluster with `replica_count: 1` (impossible replication-factor)
- A `signoz.persistence.existingClaim: query-svc-claim` referencing a PVC that doesn't exist in the live cluster
- Base resource `metadata.name` that doesn't match the chart name being deployed (left over from earlier conventions)

These require reading whole files, not just greps. Always read the heavyweight overrides (helm_release values_yaml in particular) at least once end-to-end.

## Step 5 — Score findings

Use this rubric. Be conservative — calling everything "critical" devalues the label.

- **CRITICAL** — credentials or secrets leaked in base values_yaml; placeholder ARN with fake account ID that would silently break a prod launch; any leaked value worth rotating before cleanup.
- **HIGH** — hardcoded resource references (Kafka brokers, S3 endpoints, IRSA ARNs) that have an available `${...}` expression; coherence bugs that produce wrong runtime behavior; naming mismatches between base and override.
- **MEDIUM** — env-baked strings repeated 5+ times in one resource; stale config blocks (referring to resources that no longer exist); internal inconsistencies; per-env divergence that should be project variables.
- **LOW** — typos in secret/variable names (works but pollutes search surface); empty no-op overrides; comments referring to obsolete patterns.

## Step 6 — Identify module-promotion candidates

A bare `helm_release` is a candidate for promotion into a custom Facets module when **any of**:

1. **Operator surface is unwieldy** — `values_yaml` > 100 lines, or fields the user has to find by reading upstream chart docs every time.
2. **Embeds customer-specific operational knowledge** — service-name regex lists, cluster-name transforms, log-group bucketing rules. These belong as typed module inputs, not raw values_yaml strings.
3. **Has cross-resource wiring that's currently hardcoded** — IAM roles, S3 buckets, Kafka clusters whose ARN/endpoint is baked in instead of input-wired.
4. **Will be replicated across envs with mechanical changes** — same chart stood up in dev/staging/prod with same shape but different sizing/secrets/cluster-names.

For each candidate, document:

- **Spec fields to expose** — what the module's user would set (typed, not values_yaml strings). Examples: `signoz.version`, `clickhouse.shards`, `source_clusters: [{name, log_group}]`.
- **Inputs to wire** — resources the module depends on (`s3_bucket`, `kafka`, `kafka_topic`, `aws_iam_role`, `kubernetes_cluster`, etc.).
- **Secret references** — what credentials become typed secret refs instead of inline strings.
- **Effort estimate** — small (3–5 days), medium (1–2 weeks), large (2+ weeks).

### Skip wrapping when

- The chart is a thin upstream wrapper (metrics-server, node-exporter, KEDA, cluster-autoscaler) with no customer-specific customization.
- The release is transitional / under evaluation — don't invest in module-ing something likely to be retired in 3 months.
- The chart already wraps a custom module at a different flavor — confirm via `raptor describe module KIND/FLAVOR/VERSION`.

### Recommendation taxonomy

Label each candidate with one of:

- **DO** — strong recommendation, clear value, candidate meets ≥ 2 criteria
- **CONDITIONAL** — value depends on a separate decision (e.g., "if customer keeps tool X as a permanent stack")
- **MAYBE** — low-leverage; suggest only if the customer asks specifically
- **SKIP** — thin wrapper, no value in adding a typed surface
- **ALREADY DONE** — already a custom module; surface the level of typed coverage and where it could be tightened

## Step 7 — Produce the report

Write a single HTML file at `audit/blueprint-hygiene.html` with these sections:

1. **Critical base-spec findings** — top of report, color-coded by severity (red border for critical, amber for high, blue for medium, gray for low).
2. **Override anti-patterns** — table mapping each abuse to the right answer (expression / input / secret ref).
3. **Module-promotion candidates** — one card per candidate with recommendation tag, spec fields, inputs, effort, and rationale.
4. **Suggested sequence** — what to fix first. Always lead with:
   1. Rotate any leaked credentials immediately.
   2. Replace base-spec plaintext with secret refs (small edits, zero new modules).
   3. Add input wiring to existing `helm_release` resources to replace hardcoded `${...}` opportunities.
   4. Promote the highest-leverage helm_release into a custom module.
   5. Proceed down the rest of the module-promotion list as priorities warrant.
5. **Open questions / verifications** — anything observed but not confirmed (e.g., "does the kafka_topic with replicas=2 actually create on a 1-broker cluster?"). Items the user should validate in cluster or with the customer before acting.

### Report style

- Concise. The audit reader is usually an internal advisor, not the customer. Cherry-pick the items that matter.
- Print-friendly (page breaks on cards/findings).
- Use real values from the spec, not generic placeholders — `arn:aws:iam::108177350548:role/...` is more useful than `<account-id>`.
- For each finding, include the **fix** as a separate line — the exact expression or pattern to replace it with.

### Optional output formats

- **Markdown** for chat-pasteable summary
- **HTML** for sharing or print-to-PDF
- **Inline summary** if the user just wants the top 3–5 items called out in chat without writing files

Default to HTML unless the user specifies otherwise.

## Anti-patterns of this audit

- **Don't critique architectural choices** the customer made — the design (two-tier collectors, Kafka buffering, ClickHouse shard count, multi-stack coexistence) is theirs. Surface operational findings (hardcoded values, leaked secrets, dead config), not design opinions. The user feedback memory captures this rule: "don't question their arch choice thats theirs unless something is horrible."
- **Don't volunteer module-promotion as a sales pitch.** The customer either already wants to make custom modules or doesn't. State the case neutrally; let them decide.
- **Don't treat the audit as a punch list to dump on the customer.** It's internal reference material for the platform-side advisor. For customer-facing artifacts, distill the 2–3 items that actually need their attention; drop the rest.
- **Don't skip the expression-discovery step.** A "hardcoded ARN" is only an anti-pattern if there's an expression that could replace it. Always cross-check against `raptor describe expressions` before scoring.
- **Don't infer secrets are still active without verifying.** A leaked token might already be rotated; flag the rotation as the action and confirm with the customer rather than assuming.
- **Don't propose surgery on the base spec without coordinating** — modules that other projects/envs depend on can't be edited in isolation. If the resource flavor is shared (e.g., `fourkites/aws_iam_role/0.2`), check who else uses it first via the module registry.
- **Don't conflate "module exists" with "module is well-designed".** A `fourkites_chronocollector/1.1` that exposes only raw values is technically a custom module but operationally no better than a bare helm_release. Tighten existing modules where the surface still leaks.

## When NOT to use this skill

- The customer is asking a focused operational question (e.g. "why is my release failing?") — use `release-debugging` instead.
- The customer wants to design a new module from scratch — use `design-facets-module`.
- The customer is implementing a module that's already designed — use `build-facets-module`.
- The customer wants to inventory resources for billing/sizing purposes — `facets-blueprint` covers `raptor get resources` with the effective-enabled-state logic.

## Related skills

- `facets-blueprint` — general blueprint operations, including the effective-enabled-state logic this audit depends on
- `design-facets-module` — natural follow-on when this audit identifies promotion candidates
- `build-facets-module` — implementation of the chosen module
- `release-debugging` — for operational incidents discovered during the audit (use it, then come back)
