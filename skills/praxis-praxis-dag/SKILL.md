---
name: "praxis-praxis-dag"
title: "Praxis Task DAG"
description: "Use when the user describes a multi-step outcome that will take hours-to-weeks and has natural checkpoints (build -> review -> deploy, migrations, PRD -> feature -> PR -> rollout). Turns it into a durable, judge-gated task-DAG run in the Praxis control plane via `praxis mcp task_dag` functions. Also use when the user asks about progress of such work ('how's the migration going'), needs to approve or decline a pending step, wants to take a step themselves, or when this session owns a DAG node and must execute it and pass its self-judge loop."
triggers: ["task dag", "multi-step task", "start a migration run", "prd to deploy", "approve a step", "how is the migration going", "track this work", "judge-gated workflow", "dag run status", "take a node"]
category: "orchestration"
tags: ["task-dag", "orchestration", "judge", "workflow", "mcp"]
icon: "🕸️"
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

# Praxis Task DAG

A complex outcome becomes a durable DAG in the Praxis control plane: nodes are
units of work with briefs, success criteria, and typed results; edges are
handover contracts; an independent judge gates every handover. The server owns
all state — you talk to it exclusively through the MCP passthrough:

```bash
praxis mcp task_dag <fn> --body '<json-args>'     # or pipe: echo '<json>' | praxis mcp task_dag <fn> --body -
```

There are NO `dag` CLI verbs. Everything below is a `task_dag` function call.

## When to reach for a DAG (and when not)

- **Reach**: multi-step, gated, collaborative, or long-running outcomes —
  PRD -> feature -> PR -> deploy, cloud migrations, anything with human
  sign-off checkpoints or work split across people/sessions.
- **Don't**: single-session tasks. Just do those directly.

Templates come from the catalog. If no template fits the user's intent,
say so and stop — do not author or modify templates from a session.

## Starting: match intent to a template

1. `praxis mcp task_dag list_templates --body '{}'` — pick a template by name and
   params that matches the user's intent.
2. Confirm the params with the user in THEIR terms ("which customer? source
   and target cloud?") — never recite schema internals.
3. Start it (idempotency_key makes retries safe):

```bash
# body fields: template_id, params, display_name, idempotency_key, version (optional int)
praxis mcp task_dag create_run --body '{"template_id": "cloud-migration", "params": {"customer": "acme", "source": "aws", "target": "gcp"}, "display_name": "acme aws -> gcp", "idempotency_key": "acme-gcp-2026-07"}'
```

ALWAYS set `display_name` — a short label in the user's terms ("s3 module
write", "acme aws -> gcp") that distinguishes this run from other runs of
the same template in every list a human sees.

## Talking to the user

Report outcomes and progress conversationally. Never surface nodes, claims,
leases, or verdicts unless the user asks for detail. Say "two steps done, the
schema-review step is waiting on Priya" — not "node claim CAS succeeded".

## Progress questions

```bash
praxis mcp task_dag list_runs --body '{}'
praxis mcp task_dag get_dag --body '{"run_id": "<run-id>"}'
```

Summarize state in plain language. Failures come with judge feedback — relay
the *missing* items in the user's terms, not the verdict JSON.

## The monitoring UI (always share the link)

The control plane serves a live monitoring UI. When you start a run — and
whenever you report progress — give the user its link, formed on the SAME
base URL your praxis CLI talks to (never a hardcoded host or port):

- all runs: `<control-plane-base>/ui/ai/task-dag/`
- one run:  `<control-plane-base>/ui/ai/task-dag/runs/<run-id>`

That page is where humans approve gates, unblock start-gated nodes, and
copy per-node pickup prompts — so the link IS the human's control surface,
not a nicety.

When a node parks `needs_human`, don't just say "it needs approval" — send
the node's DEEP LINK so one click lands them on the Approve button:

- `<control-plane-base>/ui/ai/task-dag/runs/<run-id>?node=<node-id>`

## Approvals

When a step is waiting on a human and the user says yes/no:

```bash
praxis mcp task_dag approve --body '{"run_id": "<run-id>", "node_id": "<node-id>", "feedback": "LGTM"}'
praxis mcp task_dag reject --body '{"run_id": "<run-id>", "node_id": "<node-id>", "feedback": "plan shows a destructive change on users table"}'
```

Reject sends the node back for a fresh attempt with the feedback attached.

## Taking a step yourself (manual nodes)

When the user says "I'll take X" (or a node is `claim_mode: manual` and
assigned to them), claim it from this session:

```bash
praxis mcp task_dag own_node --body '{"run_id": "<run-id>", "node_id": "<node-id>", "mode": "manual", "session_id": "<this-session>"}'
```

The returned work packet is your contract: `brief`, validated
`input_payloads` from upstream nodes, `output_schema`, `success_criteria`,
judge config, and an `attempt_token`. To pick up ANY eligible ready node
instead, omit `node_id` (peek first with
`praxis mcp task_dag next_node --body '{}'` if you only want to look).

Offering capabilities (some nodes require them, e.g. raptor-equipped
steps): pass them as STRING values — `"capabilities": {"raptor": "true"}`.
Values match the template's worker_hints case-insensitively.

## Executing a node you own

Do the work however you choose — in this session, via a subagent, or as a
flow task. The packet's brief is the whole assignment; you do not need to
know anything about the wider graph. Non-negotiables:

- Produce a **result object that matches the packet's `output_schema`**
  exactly — it is validated server-side and downstream nodes receive only
  the contract-listed fields.
- Keep evidence as you go (PR URLs, test output, plan files) — the judge
  sees evidence, never your reasoning.
- Long work: extend the lease periodically with
  `praxis mcp task_dag heartbeat --body '{"run_id": "...", "node_id": "...", "attempt_token": "..."}'`
  — an expired lease re-opens the node for someone else.

## The self-judge loop

Before completing the node, converge against an independent judge:

1. Fetch the criteria packet:
   `praxis mcp task_dag judge_packet --body '{"run_id": "<run-id>", "node_id": "<node-id>"}'`.
2. Spawn a **FRESH subagent** (headless, empty context) whose ENTIRE input is
   the packet's criteria + your result + artifact evidence — **never your
   transcript, never your reasoning**. It returns a verdict:
   `{pass, checks[], missing[], confidence}`.
3. Verdict FAIL -> fix exactly what `missing[]` lists, then judge again with
   another fresh subagent — INCREMENTALLY, not from scratch:
   - Scope iteration 2+ to **only the checks that failed**, plus any
     previously-met check your fix could have disturbed (you know what you
     touched).
   - Its input: those criteria, the prior verdict, WHAT CHANGED since (the
     new artifact version + a one-line delta summary), and the fix's
     evidence. Do NOT re-feed the full evidence set for settled checks —
     that is where token bills explode.
   - Merge verdicts: carry previously-met checks into the new verdict with
     a note ("met at iteration 1"); the merged verdict is what you submit.
   Fresh subagent every iteration, always — incremental scopes the INPUT,
   never the judge's independence. Iterate up to `max_iterations`.

**Where the judge gets its facts:**

- Default: PASTE small, targeted excerpts into the judge's input — name
  the source (file path, artifact version). Cheapest and fastest, and the
  local judge is a convergence tool: the server's gates, raptor validate,
  and the human gates are the real authorities behind it.
- Whole files only when the check needs the whole file.
- The judge opens a real file or re-runs a command ONLY when a paste
  cannot prove the point: absence claims ("no provider blocks anywhere"),
  or when the pasted evidence looks inconsistent.
- Never re-do expensive or risky operations (applies, cloud calls) — the
  captured output is the evidence.

Blind means the judge never sees your reasoning. Pasted evidence is
fine; pasted reasoning never is.

4. Then submit once — pass or not — with the full trail:

```bash
praxis mcp task_dag complete_node --body '{"run_id": "<run-id>", "node_id": "<node-id>", "envelope": {"attempt_token": "...", "result": {...}, "summary": {"did": "...", "decisions": [], "deviations": []}, "artifacts": [...], "verdict": {...}, "iteration_trail": [...], "judge_prompt": "...", "prompt_digest": "...", "provenance": {...}}}'
```

The server re-validates everything (token, schemas, edge contracts) — a 422
tells you exactly which gate failed. Never skip the judge, never grade your
own work inline, never reuse a judge subagent between iterations.

## Writing success criteria (for template authors)

A criterion is healthy only if a fresh judge holding just the result and
evidence can settle it. Four failure classes to avoid:

- **Arithmetic proxies.** Counts and caps are blind to provenance — five
  invented fields pass a cap of five, and caps collide with criteria that
  require fields to exist. Ask for TRACEABILITY instead: "every X traces
  to <a named source> — nothing invented."
- **Process claims.** "The discussion ran until they agreed" judges a
  conversation the judge never saw. Demand the evidence instead: "the
  result carries their confirmation, QUOTED."
- **Unjudgeable vocabulary.** "small", "minimized", "reasonable",
  "agreed" — no evidence can settle them. Either name the threshold in a
  param (so it exists inside the run) or ask for the per-item reason:
  "every override-only field states why it varies per environment."
- **Briefs that pre-judge.** The brief assigns work; the judge judges it.
  A rule stated in the brief AND enforced by a criterion will drift —
  keep judgment in criteria only.

Crisp mechanical facts are fine as criteria ("CI green", "zero
destructive changes", "validate exits clean") — they are rules, not
proxies. Judgment calls are fine too ("configurable without reading
Terraform") — that is what judges are for.

## Rollback (explicit, human-decided only)

Only after the user explicitly decides to roll back:

```bash
praxis mcp task_dag rollback --body '{"run_id": "<run-id>", "target_node": "<node-id>"}'
```

## Unattended runs

If the user wants a run driven without babysitting, use the optional
`praxis-dag-runner` skill — a self-pacing loop over the same functions.

## Composing the envelope

Your work packet includes `envelope_schema` (the exact JSON Schema
`complete_node` validates against) and `defaults` (e.g. `lease_seconds`).
Compose your envelope against that schema directly — do not guess fields or
discover them through 422 rejections.

## Deliverables (document outputs)

When your work packet contains a `deliverables` map, those result fields must
be **artifact cross-links**, never inline content:

1. Produce the content (matching the declared `format`: markdown or html).
2. Publish it as an artifact using the artifacts functions (`emit_artifact` requires `name` — lowercase slug [a-z0-9_/-], ≤128 chars — plus `title`, `format`, `content`)
   (`praxis mcp artifacts <fn>`), using the packet's `title` for the artifact
   title and the declared format.
3. Compute the content's sha256 and set the result field to
   `{"artifact_id": "<id>", "sha256": "<hex>"}`.

The envelope's `artifacts[]` accepts EXACTLY two evidence shapes (anything
else is rejected):
- `{"type": "artifact", "artifact_id": "<id>", "label": "what it is"}` —
  internal artifacts (markdown or html), referenced by IDENTITY. Never invent
  URI schemes (`artifact://…`) or embed absolute URLs; consumers form links.
- `{"type": "link", "uri": "https://…", "label": "PR #482 / dashboard / …"}` —
  genuinely external references only.
Always set `label` — it is the display name humans see at gates.

**House style — deliverables are evidence, not essays.** Keep them SHORT
and scannable: lead with a table or an ASCII diagram, one line per fact,
no filler prose, no restating the brief. A reviewer at a gate should get
the picture in under a minute. If a section doesn't change a decision,
cut it.

**Iterations are versions:** when a judge fails you and you revise a
deliverable, re-emit the SAME artifact `name` — the store versions it
(v1, v2, …) so the document's evolution is one artifact's history, not a
trail of orphans. Your final ref's `sha256` pins exactly the version that
passed judgment.

The server verifies the artifact exists, matches the declared format, and
that the sha pins the exact stored content — then back-stamps the artifact
with this run/node so the document and the work reference each other. Never
paste document content into result payloads when a deliverable is declared;
the complete will be rejected.
