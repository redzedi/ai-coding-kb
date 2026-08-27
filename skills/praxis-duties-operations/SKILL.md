---
name: "praxis-duties-operations"
title: "Duties Operations"
description: "Manage recurring agent duties (schedules) — list, create, update, pause, resume, delete, and run them on demand, then inspect run history and findings. Works from the praxis CLI and the in-app chat agent. Use when the user says duty, duties, schedule, recurring task, cron job, run now, trigger a duty, pause/resume a duty, or asks what a duty found."
triggers: ["duty", "duties", "schedule", "recurring task", "cron job", "run now", "trigger duty", "pause duty", "resume duty", "duty runs", "duty findings"]
category: "operations"
tags: ["duties", "schedules", "cron", "automation"]
icon: "🗓️"
version: "1.0"
surface: both
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

# Duties Operations

A **duty** is a recurring, self-improving agent task — an objective the agent
checks/monitors/audits on a cron schedule, accumulating findings and learnings
across runs. The tools run server-side under your org's credentials; you never
touch a local database.

When the user doesn't name an agent, duties belong to the **`praxis`** agent by
default. Pass an agent name (see param table) to target a different custom agent.

## Tool names depend on where you're running

The exact same operations are exposed under **two different tool namespaces**,
one per surface. **Use whichever set actually exists in your environment** — on
the praxis CLI it's the `duties` namespace; in the in-app chat agent it's the
`agent_ops` namespace. They are 1:1 equivalent:

| Operation | praxis CLI (`duties`) | in-app chat agent (`agent_ops`) |
| --- | --- | --- |
| List duties | `mcp__duties__list_duties` | `mcp__agent_ops__list_agent_schedules` |
| Create a duty | `mcp__duties__create_duty` | `mcp__agent_ops__create_agent_schedule` |
| Update a duty | `mcp__duties__update_duty` | `mcp__agent_ops__update_agent_schedule` |
| Delete a duty | `mcp__duties__delete_duty` | `mcp__agent_ops__delete_agent_schedule` |
| Pause a duty | `mcp__duties__pause_duty` | `mcp__agent_ops__pause_agent_schedule` |
| Resume a duty | `mcp__duties__resume_duty` | `mcp__agent_ops__resume_agent_schedule` |
| Run it now | `mcp__duties__trigger_duty` | `mcp__agent_ops__trigger_agent_schedule` |
| List runs | `mcp__duties__list_duty_runs` | `mcp__agent_ops__list_schedule_runs` |
| Get one run | `mcp__duties__get_duty_run` | `mcp__agent_ops__get_schedule_run` |
| List findings | `mcp__duties__list_duty_findings` | `mcp__agent_ops__list_schedule_findings` |

Below, tool references use the CLI (`duties`) names for brevity — if you're the
in-app chat agent, use the matching `agent_ops` name from the row above.

In-app only: after working a finding, mark it done with
`resolve_finding(finding_key=…)` (`schedule_ops` MCP — not exposed on the CLI).

## Arguments (same on both surfaces)

- **create**: `name` (URL-safe slug, e.g. `daily-cost-check`), `cron_expression`
  (e.g. `0 9 * * *`), `objective`; optional `agent_name` (defaults to `praxis`),
  `display_name`, `timezone` (IANA, default `UTC`), `enabled` (default true).
  Advanced (optional): `targets` (infrastructure targets to scan), `slack_config`
  and `git_config` (per-duty overrides of the agent's defaults).
- **update**: `schedule_id` + only the fields to change. Editing
  `cron_expression`/`timezone` re-registers the cron; `enabled=false` stops it
  firing without deleting it.
- **list**: optional `agent_name` (defaults to `praxis`).
- **pause / resume / delete**: `schedule_id`. `resume` also clears the error counter.
- **trigger**: `schedule_id`; optional `instructions` — a one-shot note for this
  run only (max 4000 chars, appended to the run prompt, NOT saved as a learning).
- **list runs**: `schedule_id`, optional `limit`.
- **get run**: `run_id`.
- **list findings**: `schedule_id`, optional `status` (`open` (default) /
  `resolved` / `all`) and `limit`.

## Triggering a run is asynchronous

`trigger_duty` starts the run in the background and returns a `run_id`
immediately — it does **not** wait for the duty to finish. It runs even if the
duty is **paused**. To see the outcome, poll `list_duty_runs(schedule_id)` or
`get_duty_run(run_id)` until the run's status is `success` or `failed`, then read
its findings/actions.

## Common flows

- **"Run the daily cost check now, focus on the new cluster"** →
  `trigger_duty(schedule_id, instructions="Focus on the new GKE cluster today")`,
  then poll `get_duty_run(run_id)`.
- **"What's this duty been finding?"** → `list_duty_findings(schedule_id)` for
  the open rollup; drill into a specific run with `get_duty_run(run_id)`.
- **"Set up a duty to audit IAM every morning"** →
  `create_duty(name="iam-audit", cron_expression="0 6 * * *", objective="...")`.

Always show the user the duty's `id` (and `run_id` after a trigger) so they can
refer back to it.
