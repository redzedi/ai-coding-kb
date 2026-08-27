# Control-plane API — the curated map

Every endpoint here is part of the documented API surface. Read this **alongside**
the OpenAPI spec at `/v3/api-docs`, because the spec describes *shape* and this
file carries the *semantics and operational constraints* it cannot express:

- The word `prometheus` appears **zero times** across 515 paths, so nothing in
  the spec connects `/resourceDetails` to observability.
- 534 of 625 operations (85%) carry no summary and no description — everything is
  inferred from `operationId` and schema names.
- `/alerts` and `/open-alerts` are untyped siblings; the spec offers no basis to
  choose between them. §Alerts below does.
- `/v2/api-docs` returns **HTTP 200 with the SPA's `index.html`**, so naive
  probing "succeeds" and then fails to parse. The real spec is `/v3/api-docs`.

Every path below was read out of the controller source, not inferred, and every
controller it touches is part of the public surface.

> **Stay on the documented surface.** Some controllers are deliberately marked
> internal and excluded from the spec. That exclusion is a boundary, not an
> oversight — treat "absent from `/v3/api-docs`" as "not for this skill", and do
> not go looking for undocumented siblings of the endpoints below. Internal paths
> carry no compatibility promise and, in at least one case, an unguarded
> destructive operation.

## How the component itself talks to the platform

This part is the same on every surface, because it runs in the browser.

**The component inherits the viewer's session.** Use **relative** URLs —
`fetch('/cc-ui/v1/...')`. Never put an absolute URL or a token in component code.
The browser attaches the session cookie itself.

**The platform passes the signed-in user as an attribute:**

```js
const raw = this.getAttribute('user');
const user = raw ? JSON.parse(raw) : null;   // { email, name, roles, ... }
```

**To navigate the control plane from inside the component**, raise an event rather
than touching `window.location`:

```js
this.dispatchEvent(new CustomEvent('facets-navigate', {
  bubbles: true, composed: true,
  detail: { route: '/projects/my-project', queryParams: { tab: 'overview' } },
}));
```

`bubbles` and `composed` are both required — without `composed` the event stops at
the shadow boundary and nothing happens.

---

## Auth for the agent — this differs by surface

Use the local `raptor` binary wherever it models the call — it is authenticated and
permission-checked on the server. Confirm first:

```bash
raptor whoami   # prints the control plane you are logged into
```

For endpoints raptor does not model, curl with the stored credentials.
`raptor login` writes `~/.facets/credentials`, INI-style, selected by
`$FACETS_PROFILE` (else `[default]`):

```ini
[default]
control_plane_url = https://<tenant>.console.facets.cloud
username          = someone@example.com
token             = <personal access token>
```

The control plane takes **HTTP basic auth, `username:token`** — the same scheme
raptor itself uses (`pkg/client/client.go` sets `Authorization: Basic …`).

```bash
CP=$(awk -F'= *' '/^control_plane_url/{print $2; exit}' ~/.facets/credentials)
U=$(awk  -F'= *' '/^username/{print $2; exit}'          ~/.facets/credentials)
T=$(awk  -F'= *' '/^token/{print $2; exit}'             ~/.facets/credentials)
curl -sS -u "$U:$T" "$CP/cc-ui/v1/stacks/"
```

Do not print the token, and do not write it into a file the agent later reads
back. Read it at the point of use.

## The endpoints that matter

All paths are relative to `$CP`. "Env" = cluster; the two words are the same
thing in this API, and `environmentId == clusterId`.

### How to find the endpoint you need

In this order:

1. **Start from the tables below.** They were read from controller source.
2. **Learn the domain shape with a typed command.** `raptor get projects -o json`,
   `raptor get environments -p <project> -o json`. The raptor shape differs from the
   raw response, but the semantics are the same and easier to read.
3. **Confirm the exact response shape** with a read-only GET against the endpoint
   itself, using the credentials for your surface (see above).

Do not infer a path from a pattern. Several published paths omit the `stacks/`
segment and do not exist; every path below was verified.

### Topology

| Method | Path | Gives |
|---|---|---|
| GET | `/cc-ui/v1/stacks/` | projects (blueprints) |
| GET | `/cc-ui/v1/stacks/{stackName}/clusters` | environments of a project |
| GET | `/cc-ui/v1/stacks/{stackName}/clusters-metadata` | same, lighter payload — prefer it for a picker |
| GET | `/cc-ui/v1/stacks/{stackName}/{resourceType}/` | resources of one type in a project |
| GET | `/cc-ui/v1/clusters/{clusterId}` | cluster common info — **`baseClusterId`**, `namespace` |
| GET | `/cc-ui/v1/clusters/{clusterId}/deployments` | releases for one environment |
| GET | `/cc-ui/v1/users/` · `/cc-ui/v1/user-groups/` | people and groups |

Releases are **per environment**, not per project. Older guidance listed them under
a project path that does not exist.

### Capability discovery — the one the spec hides

| Method | Path | Gives |
|---|---|---|
| GET | `/cc-ui/v1/clusters/{clusterId}/resourceDetails` | the capability manifest: `{key, resourceType, name, value}[]` |

This is the endpoint an unaided agent does not find, and the dashboard cannot
work without it. See `discovery.md` for how to read it.

### Alerts — two surfaces, and they are not interchangeable

| Method | Path | Reads | Returns |
|---|---|---|---|
| GET | `/cc-ui/v1/clusters/{clusterId}/alerts` | prometheus + alertmanager + grafana | **rule definitions + firing + silenced** |
| GET | `/cc-ui/v1/clusters/{clusterId}/open-alerts` | alertmanager only | firing only; throws `NotSupportedException` on some cluster types |

**"What rules already exist?" can only be answered by
`/clusters/{clusterId}/alerts`.** `/open-alerts` returns no rule definitions, so it
structurally cannot answer it. Use `/alerts` for any panel that lists rules or
needs firing + silenced together, and `/open-alerts` only when you want firing
state alone.

Both are read-only here. **Authoring or changing alert rules is out of scope** —
`entities/alert_doctor/` owns that.

Both are per-cluster. For a multi-environment view, iterate clusters from
`/cc-ui/v1/stacks/{stackName}/clusters-metadata` — there is no public
cross-cluster alerts endpoint, and the internal one is off-limits (see the
boundary note above).

Response shape of `/alerts` is the Prometheus rules API — `data.groups[].rules[]`
with `state`, `alerts[]`, and each alert carrying `status.state`
(`active` | `suppressed`) plus `silenceDetails[]` grafted on from Alertmanager.

| Method | Path | Notes |
|---|---|---|
| POST | `/cc-ui/v1/clusters/{clusterId}/silence-alerts` | needs `AlertsConfigurePermission` |
| DELETE | `/cc-ui/v1/clusters/{clusterId}/alerts/silence/{silenceId}` | same — removes one silence by id |

Note the shape: silences are created and removed **per cluster and per silence
id**. Any alert-deletion path that takes neither is not the one you want.

### Kubernetes explorer

Base: `/cc-ui/v1/clusters/{clusterId}/k8s-explorer`

`/pods` `/deployments` `/statefulsets` `/replicasets` `/daemonSets` `/services`
`/ingresses` `/ingress-rules` `/hpa` `/pvc` `/pv` `/cronJobs` `/jobs`
`/configMaps` `/secrets` · `/{type}/{name}/events` ·
`pods/{pod}/{container}/logs?tail=N` · `deployments/{name}` ·
`configMaps/{name}` · `secrets/{name}`

`/hpa` is the one people forget, and it is what catches "this rule fires on every
HPA pinned at `maxReplicas: 1`".

### Blueprint resource content

| Method | Path | Gives |
|---|---|---|
| GET | `/cc-ui/v1/dropdown/…` (`getResourceByClusterId`) | a blueprint resource with `content` **and** `override`; ask for `includeContent=true` |

Overrides are a **separate field** — you must merge them yourself, or you will
read a spec the environment is not running.

### Web components — registration

Base: `/cc-ui/v1/web-components`

| Method | Path | Notes |
|---|---|---|
| GET · POST | `/` | list · create |
| GET · PUT · DELETE | `/{id}` | |
| GET | `/assets/**` | serves an uploaded bundle; **authenticated** — no public host needed |
| POST | `/{id}/bundle` | multipart, field name `file`. Upload mode |

Payload fields:

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | the custom element name, hyphenated |
| `type` | yes | `NAV_APP` · `BLUEPRINT` · `ENVIRONMENT` |
| `scopeDetails` | for scoped types | `{ blueprintName, environmentId, environmentName }` |
| `sourceMode` | yes | `UPLOAD` · `URL` · `GIT` |
| `remoteURL` | URL mode | address of the hosted file |
| `entryFile` | git (and upload, later) | in git mode, the path to the built file **inside the repository** |
| `enabled` | yes | whether it renders |
| `iconURL` · `tooltip` · `order` | no | sidebar presentation |
| `contextualAttributes` | no | extra attributes the author supplies |

Three corrections to older guidance, all verified in source:

- **`TAB_APP` is deprecated.** The server rejects it with "renders nowhere". Do not
  use it. `RESERVED`/`RESOURCE` is reserved and also rejected.
- **Components are no longer global only.** `BLUEPRINT` and `ENVIRONMENT` scope a
  component to a project or one environment. `scopeDetails.environmentId` is the
  match key and requires `blueprintName`. `environmentName` is a display label and
  is never matched on.
- **Page context beats `contextualAttributes`.** The drawer injects
  `project-name` and `environment-id`; if a key appears in both, the page wins.

### Where the file comes from — three modes, two available

**Set exactly one source.** The server rejects a payload carrying more than one.

| Mode | Available? | You provide | Who hosts |
|---|---|---|---|
| `URL` | ✅ live | `remoteURL` | you |
| `GIT` | ✅ live | `gitUrl` + `gitAccountId` + `gitBranch` + `entryFile` | the control plane clones and serves |
| `UPLOAD` | ⏳ **not merged yet** | the built file, by request | the control plane, from its database |

Upload mode is the future shape — one file, one row, replaced in place, 8 MB limit.
**It is not available today.** Do not plan a deploy around it until it lands; use
`URL` or `GIT`.

> **This section has an expiry. Verified 2026-08-14.**
> Two changes will invalidate it: `control-plane#2820` adds upload mode, and
> `control-plane#2819` fixes the git-mode defects below. Both were open on that date.
> **If either has merged, re-check this section and the warnings under GIT mode
> before trusting them** — the workarounds here become unnecessary, and telling
> someone to re-apply a registration they no longer need to touch is its own defect.

Regardless of mode: assets carry `Cache-Control: no-cache` + `Last-Modified`, so the
browser revalidates and gets a `304` when nothing changed. **Never append
`?v=<sha>`** — it is unnecessary and the query string breaks element-name derivation.

### GIT mode — how it works, and what is currently broken

`gitAccountId` is a **VCS account already registered in the control plane**, not a
raw credential. `entryFile` is the path to the built file *inside the repository*.
The control plane clones the branch onto pod-local disk and serves that path.

The asset route is **authenticated**, so a private repository is fine.

**`entryFile` rules.** A bad value saves without complaint and then never serves:

- it must actually exist in the repository on that branch;
- **no dot-prefixed path segment** — `.output/app.js` is refused;
- **no empty segment** — `dist//app.js` is refused;
- prefer **`.js`**. An `.mjs` entry returns 200 and then **silently never executes**,
  because the server has no MIME type for it and sends `application/octet-stream`,
  which the browser refuses under `nosniff`. The template's build outputs `.js`.

> **The live defect worth planning around: a push to the tracked branch is not
> picked up.** The clone happens on create and update only, so the pod keeps serving
> the original commit indefinitely. It fails **silently** — the asset returns 200
> with a valid, older bundle, so a developer who pushes a fix and reloads concludes
> their own code is wrong. This was reported on a real production component.
>
> Until the fix ships, **re-apply the registration to force a re-clone** after every
> push. Byte-identical values are enough.

**Seven further defects are live**, all of the same family — the request succeeds and
the result is wrong or missing, with no error anywhere:

| What happens | Why |
|---|---|
| Editing a git component through the UI fails validation | the API *computes* `remoteURL` for git mode, so a read-then-write round trip sends it back next to `gitUrl` and trips the "exactly one source" check |
| A deleted, renamed, or URL-switched component **keeps being served** | the serve path trusted disk, so a private-repo bundle stays fetchable at the old address until the pod restarts |
| A save can race the self-heal | both delete then clone the same directory, and the lock was held only on the heal path |
| A request arriving during a re-clone fails | measured under load: 21 of about 8,500 requests across a single refresh |
| A wrong file path saves and never serves | and it re-clones the whole repository on **every** request |
| A pod killed part-way through a clone stays broken | the directory exists, so the heal skips it and it serves half a repository |
| An `.mjs` entry succeeds and never executes | no MIME type for it, so `application/octet-stream`, which the browser refuses under `nosniff` |

**None of this makes GIT mode unusable** — it is how the existing production
dashboard ships. It means: expect to re-apply after a push, and do not diagnose a
stale bundle as your own bug.

`raptor` covers create, set and delete for both live modes:

```bash
raptor get web-components [-o wide]

# URL mode
raptor create web-component <name> --remote-url <url> --enabled \
  [--icon-url <url>] [--tooltip "<text>"]

# GIT mode
raptor create web-component <name> \
  --git-url <repo> --git-account-id <vcs-account> --git-branch <branch> \
  --entry-file dist/<name>.js --enabled

raptor set web-component <name> [--remote-url <url>] [--git-branch <branch>] [--enabled ...]
raptor delete web-component <name> [--yes]
```

`--remote-url` and `--git-url` are mutually exclusive. raptor does **not** yet expose
`--type` or `scopeDetails`, so a scoped registration needs curl.

For `URL` mode you must host the file. GitHub Pages works: `gh repo create`, then
`gh api repos/<org>/<repo>/pages -X POST -f build_type=workflow` after the first push.
It needs a public repository. GIT mode avoids that, at the cost of the staleness
behaviour above.

## What no spec could tell you

Each of these is a defect someone already paid for.

**1. `labels` is declared `required: true` and is not required.**
Every explorer endpoint takes `@RequestParam Map<String, String> labels` — a
catch-all that binds *all* query params. The generator cannot express "arbitrary
param map", so it marks it required. **Send no query params at all and you get
200.** An agent that believes the spec builds a client around a mandatory
parameter that does not exist.

**2. The explorer proxy 500s under concurrency.**
Fire several explorer endpoints in parallel and roughly 3 of 4 fail; run the same
12 serially and 12 succeed. **Every explorer call must go through a single-slot
queue.** This is not rate limiting you can retry your way out of — parallelism
itself is the fault.

**3. Only Grafana is tunnelled.**
`/tunnel/{clusterId}/grafana/**` is a Zuul 1 prefilter that gates on the path
segment being literally `grafana`. **There is no `/tunnel/{id}/prometheus/…`.** A
browser reaches metrics only through Grafana's datasource proxy. See
`access-paths.md`.

**4. Dependent environments tunnel through their base cluster.**
Use `cluster.baseClusterId || clusterId` for any tunnel URL. Skip it and every
widget is blank on every sub-environment, with no error to explain why.

**5. Tunnel calls hang rather than fail.**
When a tunnel is down the request never returns, and because it shares the
browser's per-origin connection pool it starves unrelated requests app-wide. A
hard timeout (~15s) is mandatory. Grafana Live's WebSocket is deliberately
short-circuited with **501** — Zuul 1 cannot proxy an HTTP upgrade — so no
streaming panels.

**6. `?refresh=true`** busts the prefilter's in-memory URL/credential cache,
keyed `clusterId-resourceType`. The escape hatch after a tools domain changes.

## raptor or curl?

`raptor` is preferred wherever it models the call — it is authenticated, typed,
and RBAC-enforced server-side. It covers blueprint reads, module publishing,
resources, environments, and `create/set/delete web-component`.

It does **not** cover: `resourceDetails`, alerts, the k8s explorer, bundle
upload, or the new `--type` / `scopeDetails` scope flags — and it has no raw HTTP
passthrough. Those go through curl, using the profile above.

When a raptor subcommand exists, use it. Reaching for curl where raptor already
models the call loses RBAC clarity for nothing.
