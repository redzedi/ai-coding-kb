---
name: "praxis-slack-progress-tracker"
title: "Slack Progress Tracker"
description: "Use when reporting progress on a LONG-RUNNING task to a Slack channel (customer or internal) over time — instead of spamming new messages, post ONE tracker message and edit it IN PLACE as steps land. Posts as the org's Slack bot through the gateway (slack.post_message / slack.update_message) — no token on the laptop. Defines the converged format (code-block checklist + Last updated footer)."
triggers: ["slack progress", "progress tracker", "status message", "long-running task update", "in-place update", "post to slack"]
category: "communication"
tags: ["slack", "progress", "tracker", "customer-comms", "status"]
icon: "🚢"
version: "2.0"
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

# Slack in-place progress tracker (long-running tasks)

When a task spans many steps over time (migrations, multi-resource imports, cluster bring-ups,
multi-phase rollouts) and you're posting progress to Slack, **post a single tracker message and
update it in place** — don't post a new message per step (that buries the channel).

Messages are sent **as the org's Slack bot, server-side**, through the CLI gateway. There is no
Slack token on the laptop and nothing to fetch from a keychain — the server resolves the org's
Slack integration and posts. The bot can only post to channels it has been **invited to**, so add
the bot to the target channel first (`/invite @<bot>` in Slack) — that membership IS the guardrail.

## The format (converged on Snabbit + SaaS Labs customer channels)

The whole tracker is one Slack message. The checklist sits inside a Slack ```code block``` (shown
here as the inner three-backtick fence):

````text
:ship: *<Title> — tracker*

<one-line intro: what/why + scope. e.g. "Staging-only — production untouched.">

```
✅ <done step>            — <short detail>
✅ <done step>            — <short detail>
🔄 <in-progress step>     — in progress
⬜ <pending step>         — pending
```

*:rocket: Next: <the next concrete step>*

_Last updated: <DD Mon YYYY, HH:MM IST>_

- sent by Praxis
````

Format rules (learned the hard way):
- **Checklist goes in a Slack code block and uses UNICODE emoji** `✅ 🔄 ⬜` — NOT `:shortcodes:`
  (shortcodes render as literal text inside code blocks; unicode chars render fine). Outside the
  code block, `:shortcodes:` (`:ship:`, `:rocket:`) render normally.
- A bold **`:rocket: Next: …`** line states the next concrete step.
- A **`_Last updated: <DD Mon YYYY, HH:MM IST>_`** italic footer — get the timestamp with
  `TZ=Asia/Kolkata date '+%d %b %Y, %H:%M IST'`. Refresh it on EVERY in-place update.
- Customer-channel footer is **`- sent by Praxis`** (in the body).

## Mechanics (gateway — no token, no curl)

The tracker text is multi-line, so build the JSON body with `jq` and pass it via `--body` rather
than trying to cram newlines into a `--arg`. Use the channel **id** (`C…`) — right-click the
channel → Copy link, or open its details in Slack. The bot must be a member of the channel.

1. **First post** — `slack.post_message`, and CAPTURE the returned `ts` (you need it to edit):
   ```bash
   TS=$(printf '%s' "$TRACKER" | jq -Rs '{channel:"<CID>", text:., unfurl_links:false}' \
     | xargs -0 -I{} praxis mcp slack post_message --body '{}' \
     | jq -r 'try (.content[0].text | fromjson | .ts) // empty')
   # $TRACKER holds the full tracker message text (built per the format above).
   ```
   The response text is JSON: `{"ok":true,"channel":"<CID>","ts":"<TS>","integration_id":...}`.
   Keep `$TS` for the life of the task.

   For a **customer channel**, confirm the first post with the user before sending (unless it
   follows a pre-approved format). If the org has more than one Slack integration, add
   `--arg integration_name=<name>` (discover names with `praxis mcp integrations list_chat_integrations`).

2. **Update in place** — `slack.update_message` with the SAME `ts`, new text + refreshed
   `_Last updated_`:
   ```bash
   printf '%s' "$TRACKER_V2" | jq -Rs --arg cid "<CID>" --arg ts "$TS" \
     '{channel:$cid, message_ts:$ts, text:.}' \
     | xargs -0 -I{} praxis mcp slack update_message --body '{}'
   ```
   Only messages posted by this same bot can be edited (which is every message this tool posts).

3. **Persist the `ts`** across the task (note it, or stash it) so later updates can find the message.
   Flip `🔄`→`✅` as steps land; `⬜`→`🔄` when a step starts; update the `Next:` line.

## Guard & audit

- **Membership is the allowlist.** The bot posts only where it's a member — invite it to any new
  channel first. A `not_in_channel` error means the bot hasn't been added yet.
- **Own bot only.** You can only ever post through your own org's Slack integration; there is no
  path to another org's bot.
- **Every post/update is audit-logged** server-side with the channel and message text. Treat the
  text as visible in the audit trail — don't put secrets in a tracker message.

## When NOT to use
- One-shot announcements (single milestone, no further steps) — just post once, no tracker.
- Any channel the bot hasn't been invited to — add the bot first.
