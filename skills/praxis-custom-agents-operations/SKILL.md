---
name: "praxis-custom-agents-operations"
title: "Custom Agents Operations"
description: "Manage the organization's custom agents — list, inspect, create, update, and delete them. Works from the praxis CLI and the in-app chat agent. Use when the user says custom agent, create an agent, update an agent, delete an agent, list agents, change an agent's model or system prompt, or edit an agent's enabled MCPs."
triggers: ["custom agent", "create agent", "update agent", "edit agent", "delete agent", "list agents", "agent model", "agent system prompt", "agent mcps", "manage agents", "new agent", "we need an agent", "hire an agent"]
category: "operations"
tags: ["agents", "custom-agents", "agent-management", "crud"]
icon: "🤖"
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

# Custom Agents Operations

A **custom agent** is an organization-scoped agent definition: a name, a model
(`intelligent` or `fast`), a system prompt, a set of enabled system MCPs, and
optional repository/database attachments. These are the same agents the settings
UI (Settings → Agents) manages. The tools run server-side under your org's
credentials; you never touch a local database.

These operations live in the **`agent_ops`** MCP namespace — the same names on
the praxis CLI and in the in-app chat agent (no per-surface renaming). On the
praxis CLI a bare `create_custom_agent(...)` reference below becomes
`praxis mcp agent_ops create_custom_agent --arg …`.

## Before you create an agent

Every new agent is a permanent addition — a new name in the list, a new prompt to
maintain. **Your default is not to create one.** Walk through these in order:

1. **An existing agent already fits.** Call `list_custom_agents` and read
   descriptions, not just names. If the fit is reasonable, delegate to it.
2. **An existing agent almost fits.** Extending one — a tool, an MCP, a prompt
   section, a new duty under its remit — beats spawning a sibling with
   overlapping turf. When you extend, update its `description` and
   `system_prompt` so the wider scope is visible.
3. **You can do it yourself.** Simple, one-shot, cross-domain, or still-exploratory
   work (morning digests, first-run audits) is often best run directly rather
   than shaped into a specialist prematurely.
4. **Only then create — and create for breadth.** One "Cost Optimizer" covering
   AWS/GCP/Azure cost reviews, idle resources, and anomalies is a good agent;
   four narrow siblings are sprawl. The test: if two agents would share 60%+ of
   their tools, MCPs, and domain knowledge, they should be one agent with a
   broader charter. Name the agent after the domain it owns ("Kubernetes
   Health"), not a single duty ("Pod Crash Investigator").

Before calling `create_custom_agent`, state in one or two sentences what
recurring work the agent exists to do and why no existing agent can absorb it,
then ask the user for the green light. Never silently create an agent, and never
create one per duty — a duty is a task, not an identity.

## Operations

| Operation | Tool | Key arguments |
| --- | --- | --- |
| List agents | `list_custom_agents` | (none) |
| Get one agent | `get_custom_agent` | `agent_id`, optional `include_full_prompt` |
| Create an agent | `create_custom_agent` | `name`, `display_name`, `description`, `system_prompt`, … |
| Update an agent | `update_custom_agent` | `agent_id` + only the fields to change |
| Delete an agent | `delete_custom_agent` | `agent_id` |

## Arguments

- **create**: `name` (URL-safe slug, 3–50 chars, `[a-z0-9-]`), `display_name`
  (≤100 chars), `description` (10–500 chars), `system_prompt` (50–100,000 chars).
  Optional: `model` (`intelligent` default / `fast`), `icon` (default `bot`),
  `goal` (≤1000 chars), `triggers` (list), `enabled_system_mcps` (list of MCP
  slugs, e.g. `["agent_ops","cloud_cli"]` — unknown values are dropped; defaults
  to `["agent_ops"]`), `attached_custom_mcp_ids` (list), `enable_reasoning_output`
  (default true). New agents are always **organization**-scoped and owned by you.
- **update**: `agent_id` + only the fields to change. `name` and `scope` cannot be
  changed. Lists (`triggers`, `enabled_system_mcps`, `attached_custom_mcp_ids`)
  replace the existing set.
- **get**: `agent_id`; pass `include_full_prompt: true` to see the entire system
  prompt (omitted by default because prompts can be long).
- **delete**: `agent_id`. Soft delete — the agent is deactivated, not purged.

## Ownership & permissions

You can update or delete only agents **you own**. GLOBAL platform agents (e.g.
the built-in `praxis` agent) are read-only and cannot be modified or deleted.
To find valid enabled_system_mcps slugs, list what the gateway exposes with
`praxis mcp --json` (or read `~/.praxis/mcp-tools.json`).

## Common flows

- **"What agents do we have?"** → `list_custom_agents()`, then
  `get_custom_agent(agent_id, include_full_prompt=true)` to inspect one.
- **"Create a code-review agent"** →
  `create_custom_agent(name="code-reviewer", display_name="Code Reviewer",
  description="Reviews PRs for correctness and style.", system_prompt="…",
  model="intelligent", enabled_system_mcps=["agent_ops"])`.
- **"Switch the code-reviewer to the fast model"** → look up its id with
  `list_custom_agents()`, then `update_custom_agent(agent_id=…, model="fast")`.
- **"Delete the old triage agent"** → `list_custom_agents()` for the id, then
  `delete_custom_agent(agent_id=…)`.

Always surface the agent's `id` to the user after a list/create so they can refer
back to it in a follow-up update or delete.
