---
name: "praxis-onboard-ig"
title: "Onboard to ig"
description: "Use when a user wants to onboard, set up, or bootstrap a Facets project into ig (infragraphify) — pick a Facets project, choose environments, associate source repos to the project's artifact-bearing services, write the ig manifest, and build the catalog. Triggers on 'onboard to ig', 'set up ig for <project>', 'create an ig manifest', 'ig onboarding', 'map my repos to Facets services'."
triggers: ["onboard to ig", "set up ig for project", "create an ig manifest", "ig onboarding", "map my repos to facets services", "bootstrap facets project into ig", "build ig catalog"]
category: "infragraph"
tags: ["ig", "infragraph", "onboarding", "catalog", "facets", "raptor", "graphify", "builder"]
icon: "🗺️"
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

# Onboard a Facets project to ig

## Overview

Turn a Facets **project** into a built **ig catalog** through a guided interview. The
job is to produce a `<project>.ig.yaml` manifest (Facets project + envs + repos mapped
to services) and run `ig build`. You gather the Facets side from `raptor` (via the
bundled `scripts/facets.py`) and the repo side from `gh` + the user.

> **Installed?** Check all three; ask the user to install any that are missing, don't
> install them yourself:
> - `command -v ig` → [ig releases](https://github.com/Facets-cloud/ig-releases/releases)
> - `command -v raptor` → [raptor releases](https://github.com/Facets-cloud/raptor-releases/releases) (this BUILDER flow needs it)
> - `command -v praxis` → [praxis-cli releases](https://github.com/Facets-cloud/praxis-cli/releases) — Step 0 and publishing (Step 7) go through it. Confirm it's authenticated: `praxis ig list` should return (an empty list is fine); if it errors, the user runs `praxis login`.

**Profiles.** Every `praxis ig …` command targets the **active** praxis profile (the org's
catalog server). If the user works across multiple orgs/servers, pass `--profile <name>` on
each praxis call — otherwise you silently hit the default. `praxis profiles` lists them.
The catalog name equals the Facets **project** name, so Step 0's `praxis ig list` check
matches on the project you picked in Step 1.

**Builder vs reader.** This skill is the BUILDER flow — it needs source checkouts,
graphify, and raptor. Most org members are READERS: catalogs are built once and
published through **Praxis** (`praxis ig publish`), and a reader just installs one with
`praxis ig sync <project>` (see step 0). Don't rebuild what the org already publishes.

**Core principle:** the user makes every real choice through `AskUserQuestion` — never a
prose question. You supply labeled candidates (recency-sorted projects, envs with
cloud/status, LLM-matched repos); they click. Do NOT raise a modal the user can't
meaningfully answer (see the no-candidate and collision rules in step 4).

`SKILL_DIR` below = the directory this SKILL.md lives in. Call the helper as
`python3 "$SKILL_DIR/scripts/facets.py" <subcommand>`. Every subcommand prints JSON.

## Step 0 — does the org already have this catalog? (check before building)

`praxis ig list` — if the target project is **not** listed, it's a new catalog: skip
to Prerequisites and build. If it **is** listed the catalog exists, but "exists" has
two very different shapes — check which before choosing a path:

```bash
praxis ig sync <project>              # installs bundle → ~/.ig/projects/<project>, writes .sync.json
ig status -p <project>                # members + health; note kinds (infra vs code)
```

**Is it infra-only?** A catalog created by the "Create catalog" UI CTA (or an
infra-only manifest) has **just its infra member and no code members** — the infra
graph is there, but no repos are mapped yet. `ig status` shows a single member of
`kind=infra`. This is *not* a finished catalog; it's a seed waiting for the code side.

- **Infra-only → offer to ENRICH, not read.** Use `AskUserQuestion` (header: "This
  catalog is infra-only"): "Add source repos now" vs "Just read it". On "Add repos",
  **continue to step 1 below** — you'll map repos to services and publish; the existing
  infra member persists (it's a stored member) and your code members join onto it, so
  the result is a full catalog. Do NOT rebuild the infra member; it stays fresh via
  Praxis on every Facets deploy.
- **Already has code members (fully built) → READER path.** Nothing to add:

  ```bash
  ig validate -p <project> && ig status # portable ✓ + health
  ig workspace scan <their code roots>  # bind answers to THEIR local clones
  ```

  Then stop — onboarding done.

Continue below for a NEW project, to ENRICH an infra-only catalog with repos, or when
the user explicitly wants a local rebuild.

## Prerequisites (check first, fail fast)

- `ig doctor` — graphify + raptor present. (Its `✓` lines echo each tool's first help
  line, e.g. `✓ graphify: Usage: graphify <command>` — that's cosmetic, not an error.)
  If graphify is missing: `uv tool install graphifyy` — the PyPI dist is `graphifyy`
  (double y); the installed binary is `graphify`. `uv tool install graphify` fails.
- `python3 "$SKILL_DIR/scripts/facets.py" projects` returns a non-empty list — raptor is
  authenticated. If it errors/empty, the user needs `FACETS_PROFILE` set or a raptor login.
- `gh auth status` — needed for repo matching. If unauthenticated, continue but skip the
  gh candidate step (the user can still type local paths).

## The flow

### 1. Pick the Facets project
`python3 "$SKILL_DIR/scripts/facets.py" projects` → JSON `[{name, projectType, test,
lastModified, description}]`, **already sorted most-recently-modified first**.
`AskUserQuestion` (header: "Project") — present the top ~4 recent as options (label =
name, description = `projectType` plus the `description` when non-empty — omit the `·`
separator if the description is blank; mark `test:true` ones). The built-in "Other"
free-text covers the rest of the list. The chosen name is both the manifest
`name` and `facets.project`.

### 2. Choose environments to map
`python3 "$SKILL_DIR/scripts/facets.py" envs <project>` → JSON `[{name, cloud, status,
lastRelease, clusterState}]`, sorted most-recently-released first (dead/never-released
last). `AskUserQuestion` with **`multiSelect: true`** (header: "Environments"); label
each option `name` with description `cloud · last release <date> · <status>` so the user
can tell live envs from stale junk. These become `facets.envs`; at least one required.

### 3. Enumerate artifact-bearing services
`python3 "$SKILL_DIR/scripts/facets.py" services <project>` → JSON array of
`{service, artifact, resourceType}` — only the deployable resources that have an artifact
attached (these need a source repo). It also prints a stderr note of resource types it
did NOT scan; if the user expects a deployable that's missing, that note tells you which
type to add to the helper's `DEPLOYABLE_TYPES`.

**Group the rows by `artifact`** — two services can share one artifact/repo (e.g.
`control-plane-service` and `control-plane-mt` both build `control-plane`), so you ask for
that repo **once** per artifact.

If the array is empty, tell the user no artifact-bearing services were found and offer to
write an infra-only manifest (no `repos:`), then jump to step 5.

### 4. Associate a repo per artifact (repeat per artifact group)

First build ONE candidate pool, then loop the artifacts.

**Candidate pool (once):** list repos from BOTH the org and the user's own account. A
hardcoded `--limit` silently truncates a growing org (Facets-cloud is already ~580 repos)
and gh sorts by most-recently-pushed, so a too-low limit drops the *oldest* repos — usually
fine, but not guaranteed. So size the limit to the org first:

```bash
LIM=$(( $(gh api orgs/<org> --jq '.public_repos + .total_private_repos') + 50 ))
gh repo list <org> --limit "$LIM" --json name,description,url          # org
gh repo list       --limit 300  --json name,description,url,owner       # personal
```

The best match often lives in the personal account, so never search only the org. Infer
the org from the user's existing repos.

For each distinct `artifact` group:

a. **Rank (the "LLM match").** Score the pool against the `artifact` and `service` names
   (token overlap on repo `name`/`description`). Keep the best 2–3.

b. **No good candidate → don't ask.** If nothing scores a plausible match, auto-record the
   artifact as *skipped* and move on — do NOT raise a modal whose only real option is
   "Skip". Collect skipped artifacts for the step-5 summary.

c. **Generic-name collision guard.** The project's OWN builds are prefixed with
   `<project>-` (e.g. `saas-cp-cross-control-plane`). A **bare, project-unprefixed generic
   name** (e.g. `control-plane`, `billing-service`, `tenant-mgmt`) that exact- or
   near-matches an org-wide repo is risky — it may silently bind a shared/global backend
   into this project. Treat ANY such bare-generic match as LOW confidence — **this holds
   even for real, non-test projects** (saas-cp's `billing-service`/`tenant-mgmt` are the
   trap). Surface it, but do NOT pre-select it; default to "Skip / type my own". A prefixed
   artifact (`<project>-foo`) is specific and safe to pre-select.

d. **Ask (only when ≥1 real candidate).** `AskUserQuestion` (header: "Repo for <artifact>")
   with the top matches as options (label = repo name, description = owner/name · repo
   description), plus "Skip this service". "Other" lets the user type their own — a local
   path, an `owner/repo`, or a git URL.

e. **Capture BOTH `path` (local) and `git` (URL).** The manifest records both: `path` is
   the local filesystem source that **drives the build** (precedence); `git` is the
   canonical URL that ig writes into the catalog so **the index is portable** — it is the
   member's identity, and it's what readers' `ig workspace` maps resolve against. Local
   path wins; if only `git` is given, ig checks the repo out to
   `~/.ig/projects/<project>/repos/<name>` on build.
   - **Ask the user for the local location.** `AskUserQuestion` (header: "Local path?") —
     they most likely already have the repo cloned. You MAY propose a path from memory/prior
     context, but confirm it — **never invent a path silently** — and verify with `test -d`.
   - **Derive the `git` URL** (always capture it): from the picked gh repo's `url`, or from
     the confirmed local clone via `git -C <path> remote get-url origin`.
   - If the user has no local clone, record `git` alone (omit `path`) — ig checks it out on
     build. If a repo is local-only with no remote, record `path` alone (omit `git`) — but
     warn: a member without `git` has no portable identity, so org readers can't resolve
     it locally.

f. **Pick the service + record the entry.** The manifest maps one repo → one `service` (a
   deploys_as edge). One service in the group → use it. Several → `AskUserQuestion`
   (header: "Deploys as") to pick the primary. Record
   `{name: <repo>, path: <local path>, git: <git url>, service: <service>}` — omit `path`
   when git-only, omit `git` when local-only.

### 5. Show the drafted manifest, confirm
Assemble and show the YAML, plus a one-line list of any auto-skipped artifacts (so the
user can override). `AskUserQuestion` (header: "Manifest", options: "Build it" /
"Revise"). Shape (exactly this):

```yaml
name: <project>
facets:
  project: <project>
  envs: [<env1>, <env2>]
repos:
  - {name: <repo>, path: <local path>, git: <git url>, service: <service>}
  # path drives the build (omit if git-only); git is captured for the index (omit if local-only)
```

Write it to a **stable, absolute** path — `~/Facets/ig/<project>.ig.yaml` (create the dir;
never rely on `./`, which in an agent context can resolve to the skill dir). Print the
absolute path. (If the org publishes catalogs, the manifest's durable home is on Praxis —
push it with `praxis ig manifest push <file>` (builder-local `path:` entries stripped);
see step 7.)

### 6. Build the catalog
- **Scope each member to real code first.** If a repo carries docs/fixtures/
  generated/vendored paths that skew its graph, propose a repo-root
  `.graphifyignore` (gitignore syntax, merged after `.gitignore`, only excludes
  more) — show it to the user and let them commit it to the source repo (never
  write into someone's repo silently). See `distributed-ci.md` for the pattern.
- `ig register ~/Facets/ig/<project>.ig.yaml` (registers the project in `~/.ig`).
- `AskUserQuestion` (header: "Build options"). **`-routes` is the DEFAULT posture** — it
  extracts HTTP front-end↔back-end routes per code member and rolls up `calls(http,N)`
  edges into the catalog, which is what makes the catalog show real service-to-service
  call structure instead of just deploys_as/provisions wiring. Offer these options:
  - **`-routes` (default, recommended)** — the standard posture; always include it.
  - **`-routes -enrich`** — routes *plus* LLM community naming (costs tokens; enrich
    alone without routes is a weaker build).
  - **Plain (no routes)** — only pick this if the user *explicitly* wants the bare
    structural build with no route extraction.
- `ig build -p <project> -routes [flags]`. **Always pass `-routes` unless the user opts
  out.** Relay the summary line and the catalog path.
- **Gate it:** `ig validate -p <project>` must print `✓ … portable` — a bundle that fails
  here is machine-welded and must not be published.
- **Bind it locally:** `ig workspace scan <user's code roots>` (once per machine), then
  `ig status` — resolve any `WORKSPACE_AMBIGUOUS` via AskUserQuestion +
  `ig workspace set <git-url> <path>`.
- **Print the project name** as the final line, e.g.
  `✅ Onboarded project: <project> — inspect with \`ig catalog -p <project>\``.

### 7. Publish to the org (offer it — this is how teammates get the catalog)

`AskUserQuestion` (header: "Publish?"): publish the built catalog to Praxis so every
teammate (and their agent) can `praxis ig sync <project>` it instead of rebuilding. On
yes:

```bash
# manifest (durable org copy — STRIP builder-local `path:` fields, keep `git:`):
cp <manifest> /tmp/<project>.ig.yaml   # then remove path: entries
praxis ig manifest push /tmp/<project>.ig.yaml

# each member (the portable subset only — graphs + metadata; no cache/, no repos/,
# no dated snapshots):
for m in ~/.ig/projects/<project>/member/*/; do
  praxis ig publish "$m" --catalog <project> --member "$(basename "$m")"
done
```

Praxis re-runs the portability gate on publish; nothing unportable can land.

## Extending cross-graph wiring (when built-in adapters miss a coupling)

`ig build -routes` wires members via shared interfaces (HTTP routes + queues) using built-in
adapters. If, after building, `ig catalog` is missing an edge you expect — a member's
language/framework isn't covered, or a bespoke queue/topic/gRPC/event-bus convention — ig is
extensible: you (Claude) can write a small **project-local extractor** script (any language)
that ig runs, with **no ig rebuild**. Discover the contract with `ig extractor spec`, scaffold
a template with `ig extractor scaffold`, and validate with `ig extractor test`.

**Read `cross-graph-wiring.md` (next to this SKILL.md)** for the built-in adapter table, the
full extractor workflow, and the JSON contract — load it when a project needs wiring the
built-ins don't provide.

## Distributed CI (source stays home)

When the org can't (or won't) give one CI job read access to every source repo,
each repo builds its own member graph in its own CI (`ig member build`) and
publishes it to Praxis, which joins them into the catalog (source-free). **Read
`distributed-ci.md` (next to this SKILL.md)** for the verbs, the per-repo CI
snippet, and when to choose central vs distributed.

## Quick reference

| Need | Command |
|------|---------|
| Org already publishes the catalog? | `praxis ig list` → reader path (step 0) |
| List projects (recency-sorted JSON) | `python3 "$SKILL_DIR/scripts/facets.py" projects` |
| List envs (labeled JSON) | `python3 "$SKILL_DIR/scripts/facets.py" envs <project>` |
| Artifact-bearing services | `python3 "$SKILL_DIR/scripts/facets.py" services <project>` |
| Repo candidates (search BOTH) | `gh repo list <org> ...` **and** `gh repo list --limit 200 ...` (personal) |
| Clone a picked repo | `gh repo clone <owner>/<repo> ~/Facets/Code/<repo>` |
| Register + build | `ig register ~/Facets/ig/<project>.ig.yaml && ig build -p <project> -routes` |
| Build ONLY the infra member | `ig infra build [-p name] [-manifest F] [-out D] [-profile P]` — raptor-fed, deterministic, no graphify, no LLM; the one member with no source repo — Praxis rebuilds it on every Facets deploy |
| Gate + bind + health | `ig validate -p <project> && ig workspace scan <roots> && ig status` |
| Publish to the org | step 7 → `praxis ig manifest push` + `praxis ig publish` (Praxis gates portability) |

## How "artifact attached" is decided (reference)

A resource has an artifact attached when its effective config sets, under `spec.release`,
either `image: ${blueprint.self.artifacts.<ciName>}` (direct) or `build.name: <name>`
(build reference). `facets.py services` already applies this — you don't parse configs
yourself. The extracted `artifact` is the join key for grouping/deduping repos.

## Common mistakes

- **Rebuilding a catalog the org already publishes.** Step 0 first — a reader installs in
  one `praxis ig sync <project>`; building needs source + graphify + raptor for nothing.
- **Calling `raptor` without `RAPTOR_NO_UPDATE_CHECK=1`.** Otherwise raptor appends an
  "update available" banner that breaks JSON parsing. `facets.py` sets it; if you run
  raptor directly, set it too.
- **Trusting a bare-generic artifact match.** A project-unprefixed name (`control-plane`,
  `billing-service`, `tenant-mgmt`) that exact-matches an org repo is risky even in a real
  project. Apply the collision guard (4c) — surface but don't pre-select.
- **Searching only the org for repos.** The best match is often in the user's personal
  account. Search both, and size the org `--limit` to its actual repo count (4a) — a
  hardcoded limit silently drops repos as the org grows.
- **Inventing a local path.** Never guess where a repo is cloned. Either the user types
  the path, or you `gh repo clone` it to a known location. The skill depends only on `gh`,
  `raptor`, and `ig`.
- **Asking for the same repo twice.** Group services by `artifact`; one prompt per artifact.
- **Raising a modal with no real answer.** Auto-skip artifacts with no candidate (4b).
- **Confusing `path` and `git`.** `path` is a local filesystem dir (drives the build);
  `git` is the remote URL — the member's PORTABLE IDENTITY (checked out only if no `path`,
  and what readers' workspace maps key on). Capture the git URL even when a local path
  exists.
- **Publishing an unvalidated or unpruned bundle.** `ig validate` must pass first, and the
  rsync filter must exclude `repos/`, `cache/`, html reports, and dated snapshots — ship
  the active graphs only (step 7).
- **`./<project>.ig.yaml`.** Use an absolute path (`~/Facets/ig/...`) and print it.
- **Omitting `-routes`.** `-routes` is the default posture (step 6) — building without it
  (e.g. `-enrich` alone, or a bare `ig build`) skips HTTP FE↔BE route extraction and the
  catalog loses its `calls(http,N)` service-to-service edges. Always pass `-routes` unless
  the user explicitly opts out.
- **Skipping the final project-name print.** End with the onboarded project name + `ig catalog` hint.
