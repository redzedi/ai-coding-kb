# Distributed catalog CI (Model B) — source stays home

Two ways an org keeps catalogs fresh:

- **Model A (central):** a central CI job clones every member repo, runs
  `ig build`, and `praxis ig publish`es the catalog. Simple; needs one token
  with read access to all sources.
- **Model B (distributed):** each source repo's CI builds ITS OWN member graph
  (`ig member build` — source never leaves) and publishes it straight to
  Praxis (`praxis ig publish <out-dir> --catalog <c> --member <m>`), which
  joins them (needs no source, no tokens, no LLM to join).

Pick B when a central source token is unacceptable (customer-owned repos),
when repos are huge (member rebuild in seconds vs full catalog re-clone), or
when members live across org boundaries.

## graphify is ig's PRIVATE backend — agents only ever type `ig`

`ig member build` drives graphify (`update` + `label`) under the hood; readers
(`ig query`/`explain`/`impact`/`path`) drive graphify too. Agents (and humans)
NEVER invoke `graphify` directly for building or querying — everything is `ig`.
CI installs graphify only so `ig` can call it. This keeps one interface and
avoids conflicting guidance from graphify's own agent skill.

## The three verbs

    ig member build <name> -manifest <f> [-manifest <f2> …] [-src .] [-out DIR]
        [-seed <prior-bundle>] [-label auto|on|off|full] [-backend B] [-model M]
        Builds a member from -src. Pipeline: SEED (restore prior graph+sidecar
        from -seed) → STRIP ig's interface overlay → graphify update --no-cluster
        → label (see below) → re-embed interface nodes → provenance.
        `-manifest` is REPEATABLE — pass one per catalog that claims this repo:
          • ONE  -manifest  → single bundle at member/<name>/…  (or -p P convenience)
          • MANY -manifest  → LABEL ONCE, then embed each catalog's overlay and
            write <catalog>/member/<name>/…  per catalog (-out is required).
        Output per member: graphify-out/graph.json (+ community_name if labeled),
        graphify-out/.graphify_labels.json (+ .sig), member-meta.json (git+SHA+
        digest+labels). `ig member build infra ...` builds the Facets infra member.

    ig infra build [-p name] [-manifest F] [-out D] [-profile P]
        Build ONLY the infra member (raptor-fed, deterministic, no graphify, no
        LLM); the one member with no source repo — Praxis rebuilds it on every
        Facets deploy. Output: <out>/member/infra/graphify-out/graph.json.

## Scope the graph to real code — `.graphifyignore` (per source repo)

A member graph should be the repo's *code*, not its docs, fixtures, generated
output, or vendored deps. graphify already honours each dir's `.gitignore`; a
repo-root **`.graphifyignore`** (identical `.gitignore` syntax, including `!`
negation) is merged on top and evaluated last, so it only ever excludes *more* —
it can never re-include something `.gitignore` already dropped.

**Commit a `.graphifyignore` to every source repo** so the member graph is stable
and CI-reproducible (an uncommitted local file would make a laptop build differ
from CI). Exclude what isn't application code:

```
# .graphifyignore — keep the member graph to real code
docs/            examples/        testdata/        fixtures/
**/__pycache__/  *.egg-info/      *.generated.*    vendor/
migrations/      mocks/           **/*_test.go      # if tests skew the graph
```

Onboarding tip: when a service's only candidate repo is a Facets
blueprint/GitOps *config* repo (mostly YAML, little code), a `.graphifyignore`
that keeps just its real source is what makes it a usable member instead of a
skip. Propose the file to the user, show it, and let them commit it — never
silently write into someone's repo.

    ig assemble [-p P|-manifest <f>] [-dir DIR]
        Joins the member graphs under -dir into the catalog + calls/provisions
        edges + metadata.json, reads community_name off each member graph for the
        catalog descriptors, then self-validates. ZERO source, graphify, raptor,
        LLM, or key.

## Secrets

**No GitHub PAT is required.** A source repo's CI needs no token to read the
private `infragraphify` source — the code graph is pushed to Praxis over its
API, and the tools install from public release repos.
`praxis` installs from the public praxis-cli release; the `ig` build binary
installs from the public **`Facets-cloud/ig-releases`** repo (binaries only, no
source) — the same pattern raptor uses via `Facets-cloud/raptor-releases`. Both
downloads need no auth. praxis-cli does not know about ig; ig ships from its own
releases repo on its own cadence. Only the compiled binary is public; ig source
stays in the private `infragraphify` repo.

**`PRAXIS_TOKEN`** — the ONE required secret on every member repo: a Praxis API
key for a CI principal. The server resolves `Authorization: Bearer <key>` before
any cookie. **Every workflow gates on it and green-no-ops when absent** — never
fail a source repo's CI. `praxis login --token "$PRAXIS_TOKEN"` is the
non-interactive path; every `praxis ig` verb (`publish`, `manifest pull`,
`claims`, `sync`, …) then authenticates with it. ig itself never sees a
credential and never talks to any server.

**`OPENAI_API_KEY`** (or `GEMINI_API_KEY`) — an OPTIONAL secret on **each SOURCE
repo** that wants LLM community names. It is where the labeling happens now.
**Praxis needs NO LLM key** (joining published member graphs is keyless).
Absent on a source repo → that member ships with placeholder community names
(cluster-only), the catalog just gives it no descriptor. LLM is strictly
additive; a keyless build is first-class. Privacy note: labeling sends
symbol/file names to an LLM, so a customer-owned repo can simply leave the key
unset.

## Wiring checklist (what an agent does per source repo)

1. Inspect FIRST: the repo's **default branch** (often `master`, not `main`) and
   its existing `.github/workflows/` (touch NOTHING there).
2. Add exactly ONE new file: `.github/workflows/ig-member-graph.yml`.
3. Triggers: `push` to the default branch + `workflow_dispatch` ONLY. **Never
   `pull_request`** — a broken graph build must not block anyone's merge.
4. First step gates on `secrets.PRAXIS_TOKEN` (green-no-op when absent).
5. Open a **draft PR**; humans mark ready/merge.

## Member repo CI job — ONE generic multi-catalog workflow for every source repo

Proven live across all source repos (raptor, control-plane, control-plane-ui-react,
agent-factory, cross-control-plane, billing-service, tenant-mgmt-service). The
workflow file is **identical on every repo** — it discovers which catalogs claim
the repo at run time, so it never needs per-repo edits and a repo joining a new
catalog needs no workflow change. Triggers: `push` to `[main, master]` (push only
fires for the repo's real default branch) + `workflow_dispatch`; never `pull_request`.
Canonical copy: `.github/workflows/ig-member-graph.yml` in any of the repos above.

Its steps (all gated on `secrets.PRAXIS_TOKEN`, green-no-op when absent):

1. **checkout** the source (stays in the repo).
2. **discover claiming catalogs** — `praxis ig claims --git <this repo's
   canonical URL>` returns which catalogs claim this repo. For each claiming
   catalog, `praxis ig manifest pull <catalog>` fetches its manifest (+ any
   cross-repo extractors it homes). Emit `proj⇥name⇥member⇥manifest` per
   claiming catalog. No claims → notice + green exit.
3. **install praxis + ig** — `praxis` from the public praxis-cli release, `ig`
   from the public `Facets-cloud/ig-releases` repo (same as raptor's
   `raptor-releases`); both token-free. Then **install graphify**: `uv tool
   install graphifyy --with openai`. GOTCHA: graphify does NOT declare the openai
   SDK as a dep, so `--backend openai` WITHOUT `--with openai` silently ships
   DEFAULT labels. (`--with google` for gemini.) There is no `go build` and no
   clone of `infragraphify` — a source repo never needs access to ig's private
   source.
4. **build — LABEL ONCE across all claiming catalogs.** Collect every claiming
   manifest into a single call, mirror each cross-repo extractor pulled via
   `praxis ig manifest pull` into the checkout (see extractor-homes below), seed
   the code labels from one claiming catalog's prior bundle (`praxis ig sync
   <seed-proj>`; labels are code-derived → any claiming catalog is valid), then:
   ```
   flags="-label auto"; [ -n "$OPENAI_API_KEY" ] && flags="-label auto -backend openai -model gpt-4.1-nano"
   ig member build "$MEMBER" -manifest m1 -manifest m2 … -src . -out /tmp/ig-out \
     -seed ~/.ig/projects/<seed-proj> $flags
   ```
   Labels the code graph ONCE, writes `/tmp/ig-out/<catalog>/member/<m>/` per catalog
   (single-catalog repo → flat `/tmp/ig-out/member/<m>/`; the publish step accepts
   either). `-label auto` = label iff a key is present, no key → cluster-only
   placeholders, no error. `-seed` makes it INCREMENTAL (graphify label
   --missing-only + node-overlap remap keeps existing names, no key needed to KEEP).
5. **publish to every claiming catalog** — for each claiming catalog, `praxis ig
   publish /tmp/ig-out/<catalog>/member/<m> --catalog <catalog> --member <m>`
   (single-catalog repo: `/tmp/ig-out/member/<m>`). Praxis takes only the
   portable subset it needs (`graph.json`, `.graphify_labels.json`, `.sig`,
   `member-meta.json` — never graphify's `cache/`, `GRAPH_REPORT.md`,
   `.graphify_root`) and is idempotent — a re-publish at the same sha is a
   no-op (a concurrent push+dispatch at the same sha may have already landed it).

## Multi-catalog: label once, publish per catalog

A repo can be a member of several catalogs (e.g. control-plane is in BOTH
capillary-cloud and saas-cp). Its community NAMES are code-derived, so they are
IDENTICAL across every catalog — it would be pure waste to LLM-label per catalog.
So `ig member build -manifest a -manifest b …` labels the code graph exactly ONCE,
then embeds each catalog's DISTINCT interface overlay and writes one bundle per
catalog. The catalog-specific part (which calls-edges form) is a pure assemble-time
join. Verified live: control-plane's descriptor is byte-identical in both catalogs,
built from one SHA; only the callers differ (raptor in capillary, cross-control-plane
in saas-cp) because catalog membership differs. Never label a shared repo per catalog.

## Extractor homes (project-local route extractors)

A manifest's `connections.extractors` cmd resolves relative to ig's CWD at build
time. Two valid homes:
- **In the source repo (repo-local):** `.ig/extractors/<x>.py`, cmd `python3
  .ig/extractors/<x>.py` — needs no fetching, it's already in CI's checkout;
  other members' CI skips it harmlessly.
- **Cross-repo (homed with the catalog's manifest):** `<project>/.ig/extractors/<x>.py`,
  cmd `python3 <project>/.ig/extractors/<x>.py` — travels WITH the manifest:
  `praxis ig manifest pull <catalog>` (step 2, above) fetches it alongside the
  manifest, and the member workflow MIRRORS `<project>/.ig` into the checkout
  before building so the relative cmd resolves. graphify skips hidden `.ig/`
  dirs, so the mirrored copy never pollutes the code graph.
Either way the extractor bridges what built-in adapters can't see (e.g.
cross-control-plane's dynamic-base-URL outbound calls) and its hits become
`route:`/`queue:` interface nodes that rendezvous into catalog edges at assemble.

## Catalog assembly (Model B) — now server-side on Praxis, keyless, graphify-free

There is no separate "assemble" CI job to wire anymore. Each `praxis ig publish`
(step 5, above) lands one member's graph on Praxis; Praxis runs the join itself
(`ig assemble`'s logic — zero source, graphify, raptor, LLM, or key) and keeps
the catalog + metadata.json current. Nothing to add to a repo's CI for this step.

## Incremental LLM labeling (in `ig member build`, source-repo CI)

Labeling is graphify-native and lives with the source, seeded from the last
publish so it is incremental — cost scales with communities CHANGED, not size:

- **`update --no-cluster` then `label --missing-only`.** `-seed` restores the
  prior `graph.json` + `.graphify_labels.json`; graphify re-clusters, remaps new
  community ids to the prior ones BY NODE-OVERLAP (survives re-clustering), and
  sends ONLY new/placeholder communities to the LLM. Existing names are preserved
  even with NO key — so a keyless CI run never clobbers prior LLM names (custody
  is automatic).
- **Bootstrap:** the first labeled run per repo (no `member-meta.labels.source==
  llm`) wipes the sidecar and full-labels once; every run after is incremental.
- **Provenance:** `member-meta.labels = {source:llm, backend, model, at}` is
  written only when a keyed label ran. Assemble's descriptor gate keys on it, so
  placeholder/unlabeled members get NO descriptor (catalog stays clean).
- **Strip/re-embed:** ig removes its `route:`/`queue:` overlay BEFORE graphify
  (else graphify re-types them to `concept`, keeps `dir`, and a deleted route
  becomes a phantom catalog edge forever) and re-embeds the fresh overlay AFTER.

The ONE gotcha that cost real cycles: **`uv tool install graphifyy --with openai`**
in the SOURCE repo. Without the SDK extra, `--backend openai` exits 0 with default
(non-LLM) labels — silently wrong. (Works on a dev laptop only if `openai` is
globally installed.) Gemini: `--with google` + `GEMINI_API_KEY`.

## Reading the pipeline's "nothing to do" outputs (HEALTHY, not failures)

- `member graph unchanged — nothing to publish` (member job): rebuilt graph is
  byte-identical to what's published. Normal for re-runs at the same sha.
- `catalogs unchanged — nothing to publish` (assemble): the new member graph
  joins into the exact catalog Praxis already has — determinism working as
  designed. Do NOT retry or escalate on these.
- A member refresh that doesn't change the catalog still updates that member's
  `member-meta.json`, but metadata.json's SHAs only refresh on the next
  catalog-changing assemble. For per-member freshness, trust `member-meta.json`
  first.

## The one discipline

Member graphs join on canonical interface keys (`route:GET /x`, `queue:orders`)
embedded at member-build time. A member built WITHOUT `ig member build` (bare
graphify) has no interface nodes → it joins but produces no calls edges. Always
publish via `ig member build`. `ig assemble` folds each member-meta SHA into
metadata.json — `ig status` freshness/lag works identically to a monolithic build.
