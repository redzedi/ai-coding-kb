---
name: praxis
description: Praxis CLI is installed locally. Use whenever the user asks about Praxis, Facets infrastructure, or wants infra/cloud/release operations done. Run praxis commands directly — don't ask the user to run them.
---

# Praxis CLI

You are the operator of the praxis CLI on this machine. The user types
intent ("debug my release", "show my AWS resources"); you shell out to
`praxis` and bring the results back. The user is NOT going to type praxis
commands themselves.

## Setup is two steps

```
brew install praxis    ← happens once, by the user
praxis login           ← AI runs this on first contact (or when token expires)
```

That's the entire setup. Login does everything: installs this
meta-skill into your AI host's skill directory, authenticates (reusing
the control-plane token raptor already holds, else opening the control
plane's personal-access-token page for the user to paste one), fetches
this org's skill catalog, and writes the MCP tool manifest snapshot to
~/.praxis/mcp-tools.json.

## First thing to do every conversation

```bash
praxis status --json
```

Returns a small JSON snapshot:

  - `profile`, `profile_source` — which profile is active and where it came from
  - `url` — Praxis deployment the active profile points at
  - `logged_in` — whether there's a usable token for that profile
  - `username` — context
  - `skills_installed`, `agents_installed` — installed names only
    (deduped); add `--full` for per-harness paths, or use
    `praxis agents --json` / `praxis list-skills --json`
  - `raptor` — the raptor CLI's auth state and whether it targets the
    same control plane as this praxis profile (see "Raptor profile ≠
    praxis profile" below)
  - `tools` — praxis/raptor version freshness (array of per-tool
    objects with a `stale` flag)

Branch on `logged_in`.

## When `logged_in: false`

**Run `praxis login` yourself.** The CLI opens the user's browser; the
user clicks "Create Key" once; the CLI exits 0 with a fresh token saved,
this profile's skill catalog installed, and the MCP manifest snapshot
refreshed. Then retry the original task.

```bash
praxis login                                          # default profile
praxis login --url https://acme.console.facets.cloud  # different deployment
praxis login --profile bigcorp --url https://...      # named profile
```

Re-running login is also how you refresh stale skills or pick up new
ones the org has published. Login is idempotent.

## Switching between Praxis deployments

If the user has multiple deployments (e.g. internal support engineers),
each one is its own profile. Switch by re-running login with --profile X.
Login wipes the previous profile's org skills (praxis-* prefix) before
installing the new one's, so there's never a mixed state on disk.

```bash
praxis login --profile acme        # active profile becomes acme
praxis login --profile bigcorp     # wipes acme skills, installs bigcorp
```

This meta-skill survives every switch. Only the catalog skills cycle.

## Per-directory profiles (local mode)

For users working several orgs at once (one directory per customer), a
profile can be pinned to a directory tree instead of switching global
state:

```bash
cd ~/work/acme
praxis login --profile acme --local     # pins acme to this tree
praxis refresh-skills --project         # same scope, no re-auth
```

  - Writes a pointer at `<dir>/.praxis/config.json`; discovery is
    git-style, walking up from cwd (bounded to `$HOME`).
  - Skills/agents install project-scoped (`<dir>/.claude/skills`, …),
    so several orgs' skills coexist on one machine without wiping each
    other. Credentials always stay global in `~/.praxis/credentials`.
  - `praxis status` inside the tree shows
    `profile_source: "project"` plus `project_root`; outside
    it, the global profile applies as usual.

## Output convention

Every AI-callable command supports `--json` and auto-emits JSON when
stdout is not a terminal. **Always pass `--json`** from a tool loop —
the output is stable and machine-parseable.

## Exit codes (act on these)

  - `0` ok — proceed
  - `1` generic failure — read stderr
  - `2` bad command-line args — your invocation was wrong
  - `3` auth missing/expired → run `praxis login` and retry
  - `4` no config / no profile → run `praxis login --profile <name>`
  - `5` network unreachable

## The full command surface

AI-callable (always pass --json):

  - `praxis status [--refresh] [--full]` — local snapshot. `--refresh`
    adds a live /auth/me call to verify the token isn't revoked.
    `--full` expands skills/agents to per-harness install detail.
  - `praxis mcp` — list available MCP tools (no args) or invoke one
    (`praxis mcp <mcp> <fn> --arg k=v ...`). See "Discovering MCP tools"
    below.
  - `praxis agents [--json]` — list every agent file the CLI has
    installed on this host (custom agents from /ai-api/custom-agents,
    prefixed `praxis-`). Read-only, no network call.
  - `praxis list-skills [--json]` — list every skill file the CLI
    has installed on this host, with per-harness paths. Read-only,
    no network call.
  - `praxis refresh-skills` — re-fetch this profile's catalog and
    rewrite skill files + MCP snapshot, without re-authenticating. Use
    when the org has published new skills or after `brew upgrade praxis`.
  - `praxis logout` — drop creds + org skills for active profile.
    `--all` wipes everything except this meta-skill.
  - `praxis profiles` — list every profile with URL, username, active
    marker, and login state (no tokens printed). `--refresh` live-verifies
    each stored token.
  - `praxis profiles rename OLD NEW` / `praxis profiles rm NAME` —
    credentials-only profile management; no browser, no skill changes.
    `rm` refuses the active profile (that's `praxis logout`).
  - `praxis login --dry-run` — SAFE probe: reports what login would do
    (profile, URL reachability, browser vs token reuse, skill effect) and
    changes nothing. Use before any profile switch you're unsure about.
  - `praxis update` — self-update binary. `--json` implies `--yes`.
  - `praxis version` — build metadata.

Human-only (don't try to script these):

  - `praxis login` — opens the user's browser; you (the AI) RUN this on
    the user's behalf when status shows logged_out, but the user has to
    click "Create Key" once. Wait for exit 0 before retrying the task.
    (`--dry-run` is the exception — it's AI-safe, see above.)

## Facets control plane = the local raptor CLI

Facets control-plane objects — **projects, resources, environments,
releases, cloud accounts** — are NOT gateway MCP tools. They are managed
by the `raptor` CLI, which runs **locally on this machine**, directly in
the shell. Never route raptor through `praxis mcp` (there is no
`raptor_cli` gateway tool).

```bash
raptor get projects -o json                    # list Facets projects
raptor get accounts -o json                    # linked cloud accounts
raptor get releases -p <project> -e <env> -o json
```

Preflight — once per session, before the first raptor command:

  - **Installed?** `command -v raptor` — if missing, install it for
    the user with the `raptor.install_hint.commands` from
    `praxis status --json` (already resolved for this OS/arch; no
    sudo). See "Raptor profile ≠ praxis profile" below.
  - **Logged in?** `raptor whoami` — if it errors, RUN
    `raptor login` for the user. It opens their browser and they
    complete the sign-in; it stores a PAT in
    `~/.facets/credentials`. Wait for exit 0. Never ask for a token
    in chat or write credentials yourself.
  - **Up to date?** `praxis status --json` reports `tools` as an
    ARRAY, one object per tool with its `current`/`latest` version
    and a `stale` flag. Find the entry whose `tool` is
    `raptor` (or `praxis`); if its `stale` is true, tell
    the user and offer to run `raptor upgrade` — ask first, never auto-run
    it. praxis surfaces the versions; you and the user decide.

So when the user asks about projects / resources / environments /
releases / cloud accounts, reach for `raptor`, not `praxis mcp`.

## Raptor profile ≠ praxis profile

praxis and raptor keep SEPARATE credential stores; switching a praxis
profile never moves raptor:

  - praxis: `~/.praxis/credentials`, switched by `praxis login --profile X`
  - raptor: `~/.facets/credentials`, selected ONLY by the
    `FACETS_PROFILE` env var (no flag, no pointer file; unset = its
    `[default]` section)

`praxis status --json` cross-checks them in the `raptor` block.
Act on it:

  - `pinned: true` — this praxis profile is paired to a raptor profile
    (set via `praxis login --raptor-profile <name>`). Prefix EVERY
    raptor command: `FACETS_PROFILE=<profile> raptor …`. Per-command
    prefix, never `export` — each shell call starts fresh.
  - `matches_praxis_url: false` — raptor targets a different control
    plane than this praxis profile. Say which two hosts you see and ask the
    user which is intended BEFORE any raptor write;
    read-only exploration may proceed with a note.
  - `installed: false` — raptor isn't on this machine at all, so every
    control-plane command will fail. The block carries an
    `install_hint`. Point the user at `install_hint.docs`
    FIRST — that's raptor's own README and the maintained source of truth
    (its steps end in `sudo mv … /usr/local/bin`). If the user
    can't run those, or asks you to do it, use
    `install_hint.no_sudo_commands`: already resolved for this
    OS/arch and free of sudo, which you can't answer a password prompt
    for. It installs to `~/.local/bin`, so check that's on PATH
    afterwards. When `asset_url` is absent raptor publishes no
    build for this platform — docs only, don't improvise. Then continue
    to `raptor login` below.
  - `found: false` — raptor has no usable profile. RUN
    `raptor login` on the user's behalf, exactly as you do for
    `praxis login`: it opens their browser and they complete the
    sign-in themselves. Wait for exit 0. Never ask for a token in chat,
    and never write `~/.facets/credentials` yourself.
  - `setup_complete` (top level, not inside the raptor block) — true
    only when praxis is logged in AND raptor is installed and resolved.
    Check it first; the two bullets above say what to do when it's false.

## Discovering MCP tools

The server gateway exposes tools grouped by MCP namespace
(`cloud_cli`, `k8s_cli`, `catalog_ops`, …). Each tool runs
server-side under the org's managed credentials — your laptop never
holds AWS / kube secrets.

  - **List (live)**: `praxis mcp --json` → fresh fetch of every MCP +
    function + arg shape. Best when you need accuracy.
  - **Snapshot (cached)**: `~/.praxis/mcp-tools.json` is rewritten on
    every `praxis login` and `praxis refresh-skills`. Grep when you
    need tool names without going to the network.
  - **Call**: `praxis mcp <mcp> <fn> --arg k=v ... --json` (or
    `--body '<json>'` for nested args). Output is the tool's JSON
    result directly — the CLI unwraps the MCP envelope when the payload
    is a single JSON text item. On tool error (exit 1) or non-JSON
    payloads you get the raw envelope
    (`{content: [...], isError?: bool}`). Pass `--envelope` to
    always get the raw envelope.

Example flow:
```bash
praxis mcp --json | jq '.mcps.k8s_cli'         # what's in k8s_cli?
praxis mcp k8s_cli list_connected_clusters --json
praxis mcp k8s_cli run_k8s_cli \
  --arg integration_name=prod-cluster \
  --arg command='get pods -n default' --json
```

## Agents

`praxis login` also installs custom agent files into the supported
hosts' subagent directories:

  - Claude Code:  `~/.claude/agents/praxis-<name>.md` (via the `Task` tool)
  - Gemini CLI:   `~/.gemini/agents/praxis-<name>.md` (via `@<name>` invocation or `/agents`)

Each file's frontmatter describes when to invoke it; pick based on
the user's intent.

Codex is intentionally not targeted in v1: its documented loader
path (`~/.codex/agents/*.toml`) matches what the renderer produces,
but its runtime did not surface the installed files in smoke
testing. The renderer keeps the TOML path; Codex enable is a
one-line flip in `supportsAgentInstall` once the loader consumes
what's documented.

Agents shell out to `praxis mcp` for any infrastructure access — same
rewrite rule as skills. No new credentials live on the laptop.

`praxis agents [--json]` lists what's currently installed.

## Don'ts

  - **Don't** tell the user to "open a browser and paste a token" — that's
    not how it works. `praxis login` handles the browser+callback.
  - **Don't** ask the user to run praxis commands. Run them yourself.
  - **Don't** parse human-readable text output. Always use `--json`.
