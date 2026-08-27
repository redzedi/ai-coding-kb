---
name: "praxis-build-web-component"
title: Build a Facets Web Component
description: >-
  Build, style, register and deploy a custom web component for the Facets
  control plane — scoped to a project or an environment, in the Facets
  design language, reading control-plane data with the viewer's own session. Use
  when the user wants to create or build a web component, a custom UI element, a
  sidebar app, a NAV_APP, a panel or a page inside the platform — for example a
  DORA panel, a cost breakdown, an audit viewer, or a release summary. Every
  component is built with React and the Facets theme, so it matches the rest
  of the product.
surface: both
category: development
icon: 🧩
tags:
  - web-component
  - frontend
  - ui
  - control-plane
  - design-language
triggers:
  - web component
  - custom ui element
  - nav app
  - sidebar app
  - build a web component
  - facets web component
  - add a panel
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

# Build a Facets Web Component

A web component here is **one JavaScript file**. The platform serves it and mounts
it inside its own page, in a drawer or on an overview page. Your component receives
the viewer's session, the page's context, and the tenant's theme.

## One way to build

Every component is **React + Ant Design on the Facets theme**, built from
`assets/template/`. Do not hand-write a component in plain JavaScript, and do not
style one by hand: it will not follow the tenant's theme, it will not follow dark
mode, and it will read as a bolt-on beside first-party pages.

The template already carries the parts that are easy to get wrong — the shadow-DOM
shell, the theme, the build settings, and the control-plane transport.

## Read these

| Doc | When |
|---|---|
| `references/design-language.md` | **before writing UI** — libraries, tokens, the five states, the panel pattern, build traps |
| `references/cp-api.md` | **always** — the platform contract, endpoints, registration, deployment |
| `assets/template/` | the scaffold. Copy it; do not invent one |

## Preflight

Confirm the local toolchain before you start. Stop and name the failing step.

```bash
raptor whoami                # must be logged in — this is where the component registers
command -v node && node -v   # 18 or newer — required, the component is built
command -v npm               # required
command -v gh                # only if you will host the file yourself in URL mode
```

## Flow

```
① REQUIREMENTS  what should it show? which data? which scope?
                AND: where will the built file live? -> source mode
② SCOPE         one environment, one project, or org-wide? -> registration type
③ SCAFFOLD      copy assets/template, install, build, open index.html,
                confirm the placeholder renders
④ BUILD         one panel at a time; five states each
⑤ REGISTER      create the component with the chosen source mode, then deploy
⑥ VERIFY        open it the way the customer will; check all five states
```

Do not skip step ③. A build that renders the placeholder proves the toolchain, the
shadow root and the theme all work together. Skip it and the first blank panel has
three possible causes instead of one. `index.html` in the template loads the built
bundle against a light and a dark host — serve it over HTTP, never `file://`.

## Where the built file lives — ask, do not assume

Two source modes work today. **This is the user's choice, so ask in step ①** unless
they have already said. Do not pick silently; the answer changes what you build into
the repository and what you hand to the platform.

| If the user… | Mode | What you need |
|---|---|---|
| wants the code in a git repository, or has one | **`GIT`** | repository URL, a VCS account **already registered in the platform**, the branch, and the path to the built file inside the repo |
| already hosts the file, or wants to publish it themselves | **`URL`** | the address of the hosted file. It must be reachable without a login |
| has no preference | **suggest `GIT`** | nothing to host, and the asset route requires a login, so a private repository is fine |

A third mode, a direct upload, is not available yet. Do not plan around it.

Set **exactly one** source — the server rejects a request carrying more than one.

> **Tell the user this when you choose `GIT`.** A push to the tracked branch is
> **not** picked up on its own. The platform clones when the component is created or
> updated, then keeps serving that commit. It fails silently — the file returns
> success and a working, older bundle — so re-apply the registration after every push.
> Identical values are enough.
>
> *Verified 2026-08-14, while `control-plane#2819` was open. If that has merged, this
> warning is obsolete: checkouts then refresh on a poll, and you should drop the
> re-apply step rather than repeat it.* See `cp-api.md`.

`references/cp-api.md` has the payload fields, the exact commands, and the rules for
the file path that otherwise fail quietly.

## Scoping — and no pickers when scoped

| Ask | `type` | `scopeDetails` |
|---|---|---|
| one environment | `ENVIRONMENT` | `blueprintName` + `environmentId` |
| every environment of a project | `ENVIRONMENT` | `blueprintName` |
| a project overview | `BLUEPRINT` | `blueprintName` |
| org-wide, in the sidebar | `NAV_APP` | — |

A scoped component receives `project-name` and `environment-id` as attributes.
**Absent levels are omitted, not empty strings** — test for presence, not for `''`.

Read them. **Do not render project or environment pickers.** Only `NAV_APP` needs
pickers, because only it has no injected context. A scoped component that asks which
environment you meant is asking a question it was already given the answer to.

`TAB_APP` is deprecated and renders nowhere. Do not use it.

## Non-negotiables

**Never query `document`.** Query `this.shadowRoot`. A component that reaches into
the host page will break when the host changes.

**Relative URLs only.** `fetch('/cc-ui/v1/...')`. The viewer's session cookie is
attached by the browser. Never put a token or an absolute host in component code.

**Five states per panel.** `loading` · `error` · `no-config` · `empty` · `data`.
`no-config` is the one everyone forgets, and it is what stops "this environment has
no X" from looking like a bug.

**Absent is not zero.** Missing data renders as `not collected`, never as `0`. A gap
that looks like health is a statement the user will act on. Where you know the
remedy, name it.

**One required call per panel.** Everything else degrades. One missing value must not
blank a whole panel.

**The product design language.** Use `assets/template/src/theme/`. It carries about
117 token overrides plus component overrides. Read every colour, radius, size and
font from the theme. Never write a hex value.

**The built file must be a classic script.** The host loads it with
`type="text/javascript"`, so the output may contain no `import`, no `export` and no
top-level `await`. Your source uses imports freely — the bundler resolves them. Keep
`formats: ['iife']`; **never switch to `umd`**, which fails silently on any page
where a code editor has mounted. See `design-language.md`.

**Say what you built and what you skipped.** Which endpoints, which scope, what is
missing and why.

## Transport rules

| Call | Rule |
|---|---|
| any tunnel URL | use `baseClusterId \|\| clusterId` — dependent environments route through their base cluster |
| any tunnel call | hard timeout of about 15 seconds. A dead tunnel *hangs*, and it starves the browser's connection pool for the whole page |
| `/cc-ui/v1/.../k8s-explorer/*` | **single-slot queue.** Three of four calls fail in parallel; twelve of twelve succeed in series |
| other `/cc-ui/v1/...` reads | parallel is fine |

`assets/template/src/transport/cp.js` implements all four. Use it.

## Related skills

For a dashboard that reads Prometheus, also load
**facets-observability-dashboard**. It adds metrics discovery, the transports that
reach a metrics backend, and gap detection on top of everything here.

**If that skill is not available, do not improvise the metrics half.** Everything in
this skill still applies, so build the component and wire it to control-plane data.
But say plainly that finding the metrics backend, reaching it from the browser, and
telling a missing metric from a zero are not covered here, and that a dashboard built
without them will read an empty panel as healthy. Offer to continue once the skill is
installed.

To write or change **alert rules**, do not hand-roll a manifest. Alert Doctor owns
that. Reading alerts for display is fine — see `cp-api.md`.
