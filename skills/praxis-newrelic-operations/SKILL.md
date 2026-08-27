---
name: "praxis-newrelic-operations"
title: "New Relic Operations"
description: "Query and explore New Relic observability data (APM, logs, traces, NRQL, entities, alerts) through org-level New Relic integrations using the bundled CLI."
triggers: ["new relic", "newrelic", "nrql", "apm", "observability", "monitoring", "trace", "span", "incident", "alert", "synthetics"]
version: "1.0"
category: "observability"
tags: ["observability", "monitoring", "newrelic", "apm", "nrql", "cli"]
icon: "📈"
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

# New Relic Operations

Query and explore observability data in New Relic — APM applications, NRQL
queries, entities, logs, events, synthetics, alerts, and workflows — through
org-level integrations.

## Prerequisites

This skill requires the `newrelic_cli` MCP to be enabled on the agent. The
two available tools are:

- `list_newrelic_integrations` — Discover available New Relic accounts
- `run_newrelic_cli` — Execute `newrelic` CLI commands against a named integration

The integration's stored credentials (user key, account ID, region) are
injected as environment variables for the CLI process. You never see them.

## Workflow

```
┌──────────────────────────────────────────────────────────┐
│  1. DISCOVER          list_newrelic_integrations          │
│     ↓                 Returns: name, account_id, region   │
│  2. SELECT            Pick integration by name            │
│     ↓                                                     │
│  3. QUERY             run_newrelic_cli(integration, cmd)  │
│     ↓                                                     │
│  4. PRESENT           Parse JSON output, summarize        │
└──────────────────────────────────────────────────────────┘
```

### Step 1: Discover Integrations

Always start here. Call `list_newrelic_integrations` (no arguments) to see
what New Relic accounts are configured.

The response includes:
- `name` — Use this as `integration_name` in subsequent commands
- `account_id` — The New Relic account ID
- `region` — `US` or `EU`

### Step 2: Select Integration

If the user specifies an account/integration name, match it to the list.
If multiple integrations exist and the user hasn't specified, ask which to use.

### Step 3: Run Commands

Call `run_newrelic_cli` with:
- `integration_name` — The name from step 1 (required)
- `command` — CLI command WITHOUT the `newrelic` prefix (required)

**Do NOT include the `newrelic` prefix in the command.**
- Write `apm application list`, NOT `newrelic apm application list`
- Write `nrql query --query "..."`, NOT `newrelic nrql query --query "..."`

### Step 4: Present Results

Parse the JSON output and present in a structured form. Use tables for
lists; surface key fields (name, status, severity); summarize counts.

## Command Reference

All commands omit the `newrelic` prefix.

### APM applications

```
apm application list
apm application get --applicationId 12345
apm application search --name "checkout-service"
```

### NRQL queries

NRQL is the primary query language. Use it for metrics, logs, events, traces.

```
nrql query --query "SELECT count(*) FROM Transaction SINCE 1 hour ago"

nrql query --query "SELECT average(duration) FROM Transaction WHERE appName = 'checkout-service' SINCE 30 minutes ago FACET name"

nrql query --query "SELECT count(*) FROM Log WHERE level = 'ERROR' SINCE 1 hour ago FACET service.name"

nrql query --query "SELECT count(*) FROM TransactionError SINCE 1 day ago FACET error.class LIMIT 20"
```

### Entities (services, hosts, dashboards, alerts, etc.)

```
entity search --name "my-service"
entity search --type APPLICATION --domain APM
entity get --guid "..."
```

### Workloads

```
workload list
workload get --guid "..."
```

### Alerts & workflows

```
alerts policy list
alerts policy get --id 12345
alerts condition list --policy-id 12345
workflows list
```

### Synthetics

```
synthetics monitor list
synthetics monitor get --id "..."
```

### Logs (via NRQL)

```
nrql query --query "SELECT message, hostname, service.name FROM Log WHERE level IN ('ERROR','FATAL') SINCE 30 minutes ago LIMIT 100"
```

### Events (via NRQL)

```
nrql query --query "SELECT * FROM PageView SINCE 1 hour ago LIMIT 100"
```

## Post-Processing

The MCP supports an inline post-processing pipeline so you don't need shell
pipes (which are blocked):

- `jq_expression` — transform JSON output
  (e.g. `.[] | {name: .name, language: .language}`)
- `grep_pattern` — filter output lines (e.g. `error`)
- `output_file` — save final output to the working directory.
  Allowed extensions: `.json`, `.txt`, `.csv`, `.yaml`, `.yml`, `.log`

Pipeline order: command stdout → jq → grep → file save.

Example:

```
run_newrelic_cli(
  integration_name="prod",
  command="apm application list",
  jq_expression=".[] | {id: .id, name: .name, language: .language}"
)
```

## Security Constraints

- Shell metacharacters (`;`, `|`, `` ` ``, `<`, `>`, `&`, newline) are blocked.
  For filtering, use `jq_expression` / `grep_pattern` instead of shell pipes.
- Commands are parsed via `shlex.split()` and executed with `shell=False`.
- Credentials are injected as env vars per call; they never appear in tool
  input, output, or logs.

The MCP does **not** restrict subcommands — both read and mutating CLI verbs
are passed through. Make sure your prompt reflects the user's intent and you
have permission to mutate before running destructive operations.

## Common Patterns

### Incident investigation

1. List APM apps to find the affected service
2. NRQL: error rate over time for that service
3. NRQL: top error classes for the same time window
4. Cross-reference with Logs (via NRQL on `Log` event)

### Cross-source analysis (with `cloud_cli`)

When investigating incidents that span observability + cloud:

1. `list_newrelic_integrations` → pick a New Relic account
2. `nrql query ...` → find services with elevated error rates
3. `list_cloud_integrations` → pick the cloud account hosting those services
4. `run_cloud_cli` → describe related resources (EC2 instances, RDS, EKS
   nodes) to correlate infrastructure state with observability signals.

### Service inventory

1. `apm application list` to list all APM-monitored apps
2. `entity search --type APPLICATION --domain APM` for a broader view
3. Summarize by language, environment, throughput
