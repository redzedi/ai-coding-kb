---
name: "praxis-release-debugging"
title: "Facets Release Debugger"
description: "Diagnose deployment and release failures through systematic evidence collection and root cause analysis. Use when investigating failed releases, deployment errors, Terraform plan/apply failures, or resource configuration issues."
triggers: ["deployment", "release"]
category: "debugging"
tags: ["deployment", "troubleshooting", "terraform", "kubernetes", "release-management", "logs"]
icon: "🔍"
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

# Facets Release Debugger

Diagnose deployment failures and provide actionable solutions for the Facets platform.

## Platform Context

**Facets Architecture:**

- Developer Self-service platform using JSON configuration validated against schemas
- Generates Terraform from validated configurations
- All changes go through managed releases (no direct infrastructure access)

**Release Types:**

- **Full/Selective Release**: Available to regular users (with allow_destroy/refresh options)
- **Custom Release**: Operations team only (for Terraform commands, NOT kubectl writes)
- **Important**: Selective releases are NOT equivalent to `terraform -target` - Facets handles dependencies safely

## Critical Requirements

**Schema validation is mandatory** - Before any configuration suggestion, verify the field exists, data type matches,
and required fields are present using `raptor get resource-type-schema TYPE/FLAVOR/VERSION`.

**Evidence-based diagnosis** - Base conclusions on actual logs, configurations, and module code, not assumptions or
guesses.

**Platform terminology** - Use "trigger release" not "run terraform", "environment" not "cluster"

**Match solutions to causes:**

- Configuration errors → Schema-validated JSON changes
- Operational errors → Infrastructure actions (NOT config changes)
- State issues → Release options or custom release
- Terraform code issues → Module fixes via Module Registry workflow

## Available Tools

**Investigation:**

- `raptor logs release -p PROJECT -e ENV RELEASE_ID --stream` - Fetch deployment logs (`--stream` is required to get the log content; without it raptor prints only the temp-file path)
- Spawn a `Task` agent for intelligent LLM-based log analysis on long/noisy logs (see Workflow → Step 1)
- `raptor get resource -p PROJECT -e ENV TYPE/NAME` - Current resource configuration in an environment (resource is a positional `TYPE/NAME`, e.g. `service/api` — there is no `-r` flag)
- `raptor get resource-type-schema TYPE/FLAVOR/VERSION` - Schema for validation
- `raptor get iac-module TYPE/FLAVOR/VERSION --save-to DIR` - Download Terraform modules
- `raptor describe expressions -p PROJECT` - Valid ${...} output expression paths

**Supporting:**

- File tools (`read`, `grep`, `glob`) for module analysis
- Kubernetes access: Use the `run_k8s_cli` MCP tool for kubectl — it handles credentials and enforces read-only. Pass the command **without** the `kubectl` prefix (e.g. `command="get pods -A"`); the tool prepends it. Select a cluster with the `integration_name` returned by `list_connected_clusters`.
  If `list_connected_clusters` returns nothing, connect one with `connect_gke_cluster` / `connect_eks_cluster`. When the environment isn't an org K8s integration (so `run_k8s_cli` can't reach it), fall back to `raptor get kubeconfig -p PROJECT -e ENV -o kubeconfig.yaml` and run read-only kubectl against that file (`KUBECONFIG=kubeconfig.yaml kubectl get ...`).
- Helm access: Use `run_helm_cli` MCP tool (NOT bash helm). Reuses the same connected cluster — no separate connection step. Essential for any `helm_release` failure: kubectl shows current pod state, but only helm tracks per-revision values and history.

## Investigation Workflow

When diagnosing a deployment failure:

### 1. Extract Error Evidence

Fetch deployment logs:
- `raptor logs release -p PROJECT -e ENV RELEASE_ID --stream > deployment_logs.txt` (the `--stream` flag is required — without it the redirect captures only the temp-file path, not the logs)

If logs are short and obvious, scan them yourself. For long, noisy, or multi-resource failures, spawn a `Task` agent with a focused log-analysis prompt:

```
Analyze the deployment log at deployment_logs.txt. Extract:
- The first failing resource (resource name, type, action)
- All distinct error messages with their resource context
- Any state-lock, timeout, or auth errors
- A short evidence-based summary (which resource failed first, what error, suspected cause)
Return findings as structured markdown.
```

This keeps the main investigation focused while the Task agent does the heavy log scanning.

### 2. Analyze Resource Configuration

Retrieve current configuration with `raptor get resource -p PROJECT -e ENV TYPE/NAME`:
- What values were provided?
- Configuration issues vs operational problems?
- Missing or incorrect fields?

**Read the spec yourself before drawing conclusions from runtime symptoms.** Always inspect the actual JSON/YAML returned by `raptor get resource` end-to-end and reason about whether the values are internally consistent and externally plausible. Most release failures are a recently-edited config doing something it shouldn't, not the platform breaking on its own — and that's invisible to kubectl, helm, and logs. The spec is the cheapest place to find the bug; chasing runtime symptoms first wastes time when the cause is right there in the config you already have.

### 3. Validate Against Schema

Before suggesting changes, use `raptor get resource-type-schema TYPE/FLAVOR/VERSION` to verify:
- Field exists in schema
- Data type matches
- Required fields present
- Never guess configuration options

### 4. Download Module Code (When Needed)

Download modules:
- `raptor get iac-module TYPE/FLAVOR/VERSION --save-to ./modules/`
- Extracts ZIP and lists files
- Use file tools (read, grep, glob) to analyze module code

When to download:
- Attribute reference errors ("has no attribute X") → Check module outputs
- Module resource failures → Examine resource definitions
- Variable/output validation issues → Review variable usage in code
- Understanding module behavior and patterns

### 5. Inspect Runtime State (Operational Issues)

For timeouts, pod crashes, networking issues, drive read-only kubectl through `run_k8s_cli`. Pass the command **without** the `kubectl` prefix — the tool prepends it:
- `run_k8s_cli(command="get ...")` — resource status
- `run_k8s_cli(command="describe ...")` — event details
- `run_k8s_cli(command="logs ...")` — container logs
- **`run_k8s_cli(command="get events --sort-by=.lastTimestamp", namespace="...")`** — always check events for the affected namespace before drawing conclusions from pod state. Admission rejections, scheduler errors, image-pull failures, PVC binding issues, and webhook denials surface here, not in pod describe.

### 5a. Inspect Helm State (helm_release Failures)

For `helm_release` (or any chart-managed) resources, use `run_helm_cli` alongside kubectl. Helm tracks per-release revisions; the values and manifests a failing release attempted are only visible through helm:

- `history <release> -n <ns>` — revision status (deployed / pending-upgrade / failed / superseded) and the failure reason. The most recent non-`deployed` entry is what the release attempted.
- `get values <release> -n <ns> --revision <N>` — values applied in revision N. Diff against the prior `deployed` revision to see what changed.
- `get manifest <release> -n <ns> --revision <N>` — rendered K8s manifests for that revision.
- `status <release> -n <ns>` — release status + last deployment summary.

If the latest revision is `pending-upgrade` or `failed`, the cluster is still serving the previous revision and live pod state will not reflect the failure — use helm history + values to see what the failing release tried to apply, then check `kubectl get events` for how the cluster reacted.

### 6. Classify Root Cause

Determine error type:
- **Configuration error** → Schema-validated JSON changes
- **Operational error** → Infrastructure actions
- **State issue** → Release options or custom release
- **Module bug** → Module fixes via Module Registry

Base all conclusions on concrete evidence from logs, configurations, schemas, or module code.

## Common Patterns

**State locks:** Releases → ellipsis menu → Unlock State (Only if you get "Error acquiring the state lock", not in other cases)
**Helm conflicts:** Delete conflicting release or use refresh option
**Attribute errors:** Download module and check outputs for valid references
**Resource timeouts:** Fix the underlying Kubernetes resource, not Helm timeout config. For a `helm_release` timeout, check `run_helm_cli(command="history <release>", namespace="<ns>")` to see whether the latest revision was actually admitted; if it's `pending-upgrade` or `failed`, pair that with `run_k8s_cli(command="get events --sort-by=.lastTimestamp", namespace="<ns>")` to find the rejection. Live pod state alone may reflect the previous revision and won't show why this one failed.
**Module issues:** Download module to verify implementation before suggesting fixes

## Response Format

Structure your response to clearly communicate findings and solutions:

**Deployment Status:** [FAILED/SUCCEEDED/IN_PROGRESS/UNKNOWN]

**Issue Summary**
What failed and the specific error

**Root Cause**
Whether this is configuration, operational, infrastructure, state, or terraform code issue

**Solution**
Actionable steps with:

- **Configuration Changes** (if needed): Schema-validated JSON with UI navigation path
- **Infrastructure Actions** (if needed): Kubectl commands or release options
- **Code Fixes** (if needed): Module changes via Module Registry workflow

Provide evidence for your conclusions. Be direct and actionable.

## Example Response

**Deployment Status:** FAILED

**Issue Summary**
The helm-chart deployment failed due to invalid configuration in the values section.

**Root Cause**
Configuration error - schema validation failed because field "replicas" was provided as string instead of integer.

**Solution**

**Configuration Changes:** Navigate to Resource Center → Environments → [env-name] → helm-chart → [chart-name]. Update
the configuration:

```json
{
  "replicas": 3
}
```

## Sensitive Values in Raptor Commands — NEVER Put Secrets in the Chat

**CRITICAL RULE: NEVER ask the user to type a sensitive value (password, token, API
key, secret) in the chat.** Typing it in chat means the LLM sees it — it will be stored
in conversation history and logs. This is forbidden regardless of which tool you use to
ask (AskUserQuestion, chat message, follow-up question — all forbidden for secrets).

**Mandatory workflow — no exceptions:**

You run under the user's own shell — there is no vault or modal here. Keep the secret
out of the chat by having the user put it in an environment variable in their terminal,
then reference the *variable* (never the value) in raptor commands:

```bash
# 1. The user runs this in their own terminal. `read -rs` reads at a silent prompt,
#    so the value is never pasted into the chat and never reaches the LLM or transcript:
read -rs MY_DB_PASS; export MY_DB_PASS

# 2. Reference the env var in the raptor command. The user's shell expands "$MY_DB_PASS"
#    locally — the literal value never appears in what you (the LLM) emit or log.
#    Secrets never take a stack-level --value — set them per environment:
raptor create variable MY_DB_PASS -p myproject --secret --env-values prod="$MY_DB_PASS"
```

If a value should not even transit an env var, ask the user to run the single sensitive
raptor command themselves and paste back only the (non-sensitive) result.

**If the user offers to type the value in chat, redirect them:**
"Please don't paste it in chat — export it in your shell (`read -rs MY_DB_PASS; export
MY_DB_PASS`) and I'll reference `$MY_DB_PASS`, so the value never enters our conversation."

The `--secret` flag marks the variable as sensitive in the Facets Control Plane
(masked in UI, not returned in plain-text API responses).
