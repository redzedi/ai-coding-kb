---
name: "praxis-praxis-dag-runner"
title: "Praxis Task DAG Runner"
description: "OPTIONAL unattended-loop pattern for driving a Praxis task-DAG run without a human babysitting it. Host it however you like (a flow owner task is one good way): each tick claims eligible ready nodes via `praxis mcp task_dag`, executes them per the praxis-dag skill, runs the self-judge loop, completes, nudges humans for pending gates, self-paces, and journals. Use when the user asks to 'keep the run moving', 'drive this migration unattended', or when setting up a recurring owner for an active DAG run."
triggers: ["dag runner", "unattended dag run", "keep the run moving", "drive the migration", "dag owner tick", "run the dag in the background"]
category: "orchestration"
tags: ["task-dag", "runner", "unattended", "orchestration", "mcp"]
icon: "🔁"
version: "1.0"
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

# Praxis Task DAG Runner (optional unattended pattern)

This is an OPTIONAL pattern, not a required component: any laptop session can
drive a run entirely by hand with the `praxis-dag` skill. Use this loop when
nobody wants to babysit. A flow owner task is one good way to host the tick
(recurring, self-pacing, journaled); a scheduled session works too. All state
lives server-side, so ticks are stateless and safe to re-run — and everything
goes through the MCP passthrough (`praxis mcp task_dag <fn> --body '<json>'`; there
are no `dag` CLI verbs).

## Each tick

1. **Peek, then claim, up to capacity.** Repeat until `next_node` returns
   nothing or you hit your parallelism budget:

   ```bash
   praxis mcp task_dag next_node --body '{"run_id": "<run-id>", "capabilities": {...}}'
   praxis mcp task_dag own_node --body '{"run_id": "<run-id>", "node_id": "<node-id>", "session_id": "<tick-session>"}'
   ```

   `next_node` only ever surfaces auto-claimable nodes you are eligible for;
   it never claims. `own_node` may still lose the race (packet=null) — that
   is fine, move on.

2. **Execute each owned node per the main `praxis-dag` skill** ("Executing a
   node you own" + "The self-judge loop"): do the work (subagent or flow
   task), heartbeat long work, judge with fresh subagents against
   `judge_packet` criteria, then submit exactly once:

   ```bash
   praxis mcp task_dag complete_node --body '{"run_id": "...", "node_id": "...", "envelope": {...}}'
   ```

3. **Check the board:** `praxis mcp task_dag get_dag --body '{"run_id": "<run-id>"}'`.
   - Nodes in `needs_human`: make sure the initiator has been asked
     (question task / ask-mac) — once per node, not per tick.
   - `manual`-mode nodes that are ready: nudge the assignee once per node —
     they can take it themselves, or hit **Unblock for AI** in the Praxis UI
     (which releases the node to auto; after that `next_node` surfaces it to
     this loop naturally). NEVER claim manual nodes from this loop — a
     manual node that is still manual belongs to a person's decision.

4. **Self-pace:** nodes in flight -> next tick in ~10m; only waiting on
   humans -> ~45m; run completed/aborted -> retire this loop.

5. **Journal:** one note per tick — claimed, completed, waiting-on,
   next check.

## Never

- Never claim `claim_mode: manual` nodes or approve/reject on a human's
  behalf.
- Never re-claim a node the DAG shows as claimed/executing by someone else.
- Never skip the self-judge loop or submit a second time after a 409/422 —
  read the error, fix, or leave it for the next tick.
