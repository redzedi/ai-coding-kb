# Design language — build it like the rest of the product

The dashboard renders **inside the control-plane page**, in a drawer, next to
first-party UI. If it looks like a different product, it reads as a bolt-on. This
file is the mapping from "what I need to build" to "what this product builds it
with".

Source of truth is `control-plane-ui-react`. Note that the older
`webcomponents` repo is Tailwind-based — **do not copy it.** That mismatch is why
an earlier dashboard hit the `:root`-inside-shadow-root trap.

## Decision: AntD components **on the Facets theme**

The first dashboard shipped with a bespoke dark visual system — fixed navy hexes,
hand-rolled cards, custom teal/red/amber semantics, dark-only. **That system is
superseded.** Generated dashboards use AntD components driven by the **Facets
theme configuration**, which is what the React app actually runs.

**This is not stock Ant Design.** `control-plane-ui-react/src/theme/facetsTheme.ts`
carries roughly **118 token overrides** plus component-level overrides
(`Table`, `Menu`, `Input`, `Select`, `Segmented`), and `facetsDarkOverrides` adds
its own set. Handing `ConfigProvider` a bare `defaultAlgorithm` with one
`colorPrimary` gets you Ant Design's look, not this product's — wrong radii,
wrong control height, wrong font, wrong surfaces.

Non-negotiable specifics: `borderRadius: 6` / `SM 4` / `LG 8` / `XS 2`,
`controlHeight: 32`, and a custom `fontFamily` the **backend can override**.

| | Before (bespoke) | Now |
|---|---|---|
| Palette | fixed hex, dark only | Facets tokens, light **and** dark, tenant-brandable |
| Primitives | hand-rolled card/row/badge | AntD `Card` / `Table` / `Badge` / `Statistic` |
| Density | very dense, custom spacing | Facets `controlHeight`/padding — **fewer rows per screen, accepted** |
| Maintenance | a private design system | tracks the CP theme |

What this does **not** change: the information architecture below. Insight lines,
`not collected`, severity-first ordering and truncation are *content* decisions,
not styling — they survive and are the reason the dashboard is worth anything.

### The theme pipeline — replicate it, in this order

`useThemeLoader` composes the live theme like this, and a component that skips a
step looks subtly wrong:

```
1. facetsTheme                       vendored base — token + components
2. ⊕ GET /public/v1/themeFile        tenant override, deep-merged, WINS
                                     → { content: "<json string>" }, parse it
3. re-apply facetsTheme borderRadius at COMPONENT level
                                     the API theme sets Input/Select borderRadius:4,
                                     which beats the global token — put it back
4. if dark: strip every colour token and component colour override,
   KEEP colorPrimary and all non-colour tokens, then darkAlgorithm
                                     dark is not a second palette; it is the light
                                     theme with colours removed so antd can generate
```

Step 2's endpoint is **public — no auth** — so a component can fetch it directly.
Step 4 is the surprising one: there is no hand-authored dark palette to copy.

The React app has a fifth step this pipeline **deliberately omits**: it also emits
the theme's top-level keys as `--custom-properties` for the deprecated Angular UI.
Widgets here read tokens through `theme.useToken()` and never `var(--...)`, so
those keys are not vendored — carrying them would give a widget two sources of
truth for the same colour.

On failure (404, empty body, unparseable JSON) fall back to the in-code default
rather than to stock AntD. An unstyled-but-functional dashboard is still wrong.

### Vendoring, and the platform gap it exposes

`/public/v1/themeFile` serves only the **tenant override**. The Facets base lives
in code, so a tenant with no custom theme returns an empty body — and a component
relying on the endpoint alone renders stock Ant Design, exactly the failure this
decision exists to prevent.

So the template **vendors the theme**, already extracted and verified in
`assets/template/src/theme/`:

| File | Layer | Source in `control-plane-ui-react` |
|---|---|---|
| `facets-base.json` | 117 tokens + 7 components | `src/theme/facetsTheme.ts` → `facetsTheme` |
| `facets-dark-overrides.json` | 61 tokens + 5 components | same file → `facetsDarkOverrides` |
| `facets-default-override.json` | 106 tokens + 9 components — applies when `themeFile` is empty | `src/theme/defaultThemeFallback.ts` → `DEFAULT_THEME_FALLBACK` (`token` + `components` only) |
| `resolveFacetsTheme.js` | the pipeline as runnable code, plus `fetchTenantTheme()` | ports `useThemeLoader.ts` + `theme.utils.ts` |

Extracted by compiling the TypeScript and serialising the exports — no
transcription, and the dump confirmed no function-valued keys, so the JSON is
lossless. Verified output: light `colorPrimary #4A3AF0` / `borderRadius 6` /
`controlHeight 32`, dark `#817DF9` / `#171718` with **zero** light-theme colours
surviving the strip.

**Not vendored:** `DEFAULT_THEME_FALLBACK`'s ~329 top-level keys. The React app
emits those as `--custom-properties` for the deprecated Angular UI. Nothing here
reads `var(--...)` — widgets read tokens — so they are deliberately excluded.
Verified that no vendored token references one.

**These files will drift** from the React app. That is accepted and contained:
four data files, so re-extracting is one diff with no logic change. Signals of
drift are components that look almost right, radii that disagree with the
surrounding page, or a brand colour that lags a rebrand.

Use it:

```tsx
const tenant = await fetchTenantTheme();          // public endpoint, may be null
const theme  = resolveFacetsTheme({ dark, tenantTheme: tenant });
<ConfigProvider theme={theme} getPopupContainer={() => popupHost}>
```

It will drift from the React app. That is accepted and contained — four data
files, so re-extracting is one diff with no logic change.

> **Platform ask:** expose the *effective* resolved theme (base ⊕ tenant ⊕ dark)
> from one endpoint. Today no external surface can obtain this product's design
> language without copying code out of the React app. Same shape of gap as
> component scoping was before `#2818`.

## Observability patterns → their AntD implementation

These came out of the shipped dashboard. Each is the product working; each now has
a stock rendering.

### The insight line — the differentiator

Every panel may carry one plain-language line explaining what the numbers *mean*.
Real examples that shipped:

> "CPU and Memory booked far above actual use — pods may fail to schedule while
> nodes sit idle."
> "Errors are graded against each service's own traffic, so a handful of failures
> on a quiet service outranks the same count on a busy one."
> "NXDOMAIN dominates with no SERVFAIL — the `ndots:5` search path is retrying
> every external lookup ~4× before it resolves."

This is the whole value. A number tells you *what*; the line tells you *what to
do*. No dashboard tool generates these — they come from the per-resource judgment
the skill encodes.

Render as the last child of the `Card`: `<Text type="secondary">` for an
observation, `<Alert type="warning" showIcon>` when there is an action. Never more
than one per panel — two competing explanations is noise.

### `not collected` — absent, rendered

A metric that does not exist renders the literal string **`not collected`** in
`token.colorTextSecondary`, never `0`, never `—`. Where a remediation is known,
name it:

> "4xx, ELB 5xx not collected by cloudwatch_exporter — absent, **not zero**. Add
> the matching HTTPCode blocks to enable."

This is contract #1 made visible. A gap that renders as `0` is a lie the customer
will act on.

### Severity-first ordering

Rows sort by severity, not alphabetically, under an explicit heading
(`NEEDS ATTENTION FIRST`). Per-row status uses AntD `Badge status="error" |
"warning" | "success"`. Truncate with a muted `… N more services` rather than
paginating — a health panel is for triage, not browsing.

### Grade against the resource's own baseline

4 errors on a service doing 0.2 req/s outranks 9 errors on one doing 29 req/s.
Absolute counts mislead. This belongs in the pure `lib/` layer as a scoring
function, and it is the kind of judgment someone writes once per resource type.

### Pickers only when unscoped

The shipped dashboard has project and environment dropdowns because scoping did
not exist when it was built. It does now.

| Registration | Pickers |
|---|---|
| `ENVIRONMENT` / `BLUEPRINT` scoped | **none** — read `project-name` / `environment-id` attributes |
| `NAV_APP` (org-wide) | render both, since there is no injected context |

A scoped dashboard that also asks which environment you meant is asking a question
it was already told the answer to.

## Package map — one job, one library

| Job | Use | Never |
|---|---|---|
| Layout | antd `Row` / `Col` / `Space` / `Flex` | hand-rolled flex utilities, CSS grid by hand |
| Container / panel | antd `Card` (`size="small"`) | a styled `div` |
| Stat tile | antd `Card` + `Statistic` | a `<h1>` with a number in it |
| Time series | **recharts** `LineChart` / `AreaChart` | chart.js, d3 by hand, an `<img>` of a Grafana panel |
| Categorical / breakdown | recharts `BarChart` / `PieChart` | |
| Progress / ratio | antd `Progress` (circle for utilisation) | a custom SVG arc |
| Table | antd `Table` | `<table>` |
| Empty surface | antd `Empty` (`PRESENTED_IMAGE_SIMPLE`) | a centred `<p>No data</p>` |
| Loading | `Card loading` / antd `Skeleton` | a spinner over the whole panel |
| Status dot | antd `Badge status="success\|warning\|error"` | a coloured `<span>` |
| Inline notice | antd `Alert` | a red-bordered div |
| Tag / label | antd `Tag` | |
| Icons | **lucide-react** | `@ant-design/icons` — the app migrated **away** from it |
| Topology / graph | reactflow + dagre + d3-force | only if the widget is genuinely a graph |
| Code / YAML | `@monaco-editor/react` | a `<pre>` for anything editable |
| Schema-driven form | `@rjsf/core` + `@rjsf/validator-ajv8` | |
| Data fetching | `@tanstack/react-query` | `useEffect` + `setState` |
| HTTP | `fetch` for tunnel calls (needs the timeout wrapper) · `axios` elsewhere | bare `fetch` on a tunnel — it will hang |
| Dates | `dayjs` (+ `relativeTime` plugin) | `Date.prototype.toLocaleString` for relative times |
| Utilities | `lodash` | |

React is **19**, antd is **5.27**, and `@ant-design/v5-patch-for-react-19` must be
imported once at entry or several antd components misbehave.

## Tokens, not values

```tsx
import { theme } from 'antd';
const { token } = theme.useToken();
```

`useToken()` returns the **resolved Facets theme** — base ⊕ tenant ⊕ dark — so
reading from it is what makes a widget inherit the product's look and every
tenant's rebrand for free.

Never hardcode a colour, spacing value, radius, or font size. A literal `#141414`
is wrong the moment a customer rebrands; a literal `borderRadius: 4` is wrong
today, because this theme uses **6**.

Reach for: `colorBgContainer`, `colorText`, `colorTextSecondary`, `colorBorder`,
`colorPrimary`, `colorSuccess`, `colorWarning`, `colorError`, `borderRadius`,
`controlHeight`, `fontFamily`, `fontSizeSM`, `fontWeightStrong`, `padding*`,
`margin*`.

Facets brand primary is `#4A3AF0`, shifted to `#817DF9` on dark for 4.5:1
contrast — read it from the token, never type it. Same for `fontFamily`: the
default is a system stack, but a tenant theme can replace it wholesale (the
documented example is `'MB Corpo S Text', sans-serif`), so a component that
hardcodes a font reads as foreign on exactly the deployments that care most about
branding.

## Chart colours — the one thing the existing code gets wrong

Two different palettes live in the same feature today, and **both are wrong**:

```
TrendChart.tsx      [colorPrimary, colorLink, colorSuccess, colorWarning, colorError, …]
useChartData.ts     ['#1890ff','#52c41a','#faad14','#f5222d','#722ed1', …]   hardcoded
```

- In the Facets theme **`colorLink === colorPrimary === #817DF9`**, so series 1
  and series 2 render the *same colour*. The `// Facets teal` comment beside it is
  stale.
- Semantic tokens **carry meaning**. A series painted `colorError` reads as "this
  series is bad" when it is just the third thing in a list.
- The hardcoded set ignores the tenant's theme entirely.

**The rule: categorical colour and status colour are different systems.**

| System | Source | Used for |
|---|---|---|
| Categorical | a palette derived from `colorPrimary`, distinct hues, checked for contrast in both themes | series identity — queue names, instance types, services |
| Status | `colorSuccess` / `colorWarning` / `colorError` / `colorTextSecondary` | health, severity, up/down — **only** when the colour means that |

Node health *should* use semantic colours (Ready green, NotReady red) because the
colour is the meaning. Eight instance types should not.

Build the categorical palette once in the template, derive it from the resolved
token, and never let a widget pick its own hex. See the `dataviz` skill for the
palette-construction method and the contrast validator.

## Panel anatomy — three files, and why

```
lib/<domain>.js      PURE   endpoints/queries + build(raw) -> rows/tones   ← all tests here
hooks/use<X>.js      WIRE   one required call; the rest .catch(() => [])
widgets/<X>.jsx      DRAW   Card + five states
```

The pure layer takes a raw API response and returns rows and tones. It imports no
transport and no React, so every judgment in it is unit-testable against a fixture
captured from the real API — which is how you develop against a live environment
without opening a browser.

### A worked example, end to end

Deliberately boring, and deliberately **not** metrics — the same shape holds
whatever the data source.

**`lib/pods.js` — pure. No fetch, no React.**

```js
export const SOURCE = { kind: 'pods' };            // what to ask cp.js for
export const REQUIRED = 'pods';                    // the one call we cannot lose

/** raw -> rows + what was absent. `absent` is the whole point. */
export function build(raw) {
  const items = Array.isArray(raw?.items) ? raw.items : null;
  if (!items) return { rows: [], absent: ['pods'] };     // absent != empty
  const rows = items.map((p) => ({
    name: p?.metadata?.name ?? '—',
    phase: p?.status?.phase ?? null,                     // null, never "Unknown"
  }));
  return { rows, absent: [] };
}

export function tone({ rows }) {
  if (rows.some((r) => r.phase === 'Failed')) return 'error';
  if (rows.some((r) => r.phase === 'Pending')) return 'warning';
  return 'success';
}
```

**`hooks/usePods.js` — wire. One required call; the rest degrade.**

```js
import { useEffect, useState } from 'react';
import { explorerFetch } from '../transport/cp.js';
import { SOURCE, build } from '../lib/pods.js';

export function usePods(clusterId) {
  const [state, setState] = useState({ status: 'loading' });

  useEffect(() => {
    if (!clusterId) return setState({ status: 'no-config', reason: 'No environment' });
    const ac = new AbortController();
    let live = true;

    explorerFetch(clusterId, SOURCE.kind, { signal: ac.signal })
      .then((raw) => {
        if (!live) return;
        const data = build(raw);
        setState(data.rows.length ? { status: 'data', ...data } : { status: 'empty', ...data });
      })
      .catch((err) => {
        if (live && !ac.signal.aborted) setState({ status: 'error', message: err.message });
      });

    return () => { live = false; ac.abort(); };
  }, [clusterId]);

  return state;
}
```

**`widgets/PodsCard.jsx` — draw. Five states, no logic.**

```jsx
export function PodsCard({ state }) {
  const { token } = theme.useToken();
  const card = (children) => (
    <Card size="small" title="Pods" loading={state.status === 'loading'}>{children}</Card>
  );

  if (state.status === 'loading')   return card(null);
  if (state.status === 'error')     return card(<Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
                                        description={<Text type="danger">{state.message}</Text>} />);
  if (state.status === 'no-config') return card(<Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
                                        description={<Text type="secondary">{state.reason}</Text>} />);
  if (state.status === 'empty')     return card(<Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
                                        description="No pods in this environment" />);

  return card(
    <>
      <Table size="small" pagination={false} dataSource={state.rows} rowKey="name"
        columns={[
          { title: 'Pod', dataIndex: 'name' },
          { title: 'Phase', dataIndex: 'phase',
            // ABSENT != ZERO, and absent != "Unknown". Say what is true.
            render: (v) => v ?? <Text type="secondary">not collected</Text> },
        ]} />
      {state.absent.length > 0 && (
        <Alert type="warning" showIcon style={{ marginTop: token.marginXS }}
          message={`${state.absent.join(', ')} not collected — absent, not zero.`} />
      )}
    </>
  );
}
```

**And its test — the contract, executable.** The pure layer needs no DOM, so this
runs in milliseconds against fixtures from the real API.

```js
it('reports a missing response as absent, NOT as empty', () => {
  expect(build(undefined)).toEqual({ rows: [], absent: ['pods'] });
  expect(build({ items: [] })).toEqual({ rows: [], absent: [] });   // real empty
});

it('keeps a missing phase null rather than inventing one', () => {
  const { rows } = build({ items: [{ metadata: { name: 'a' }, status: {} }] });
  expect(rows[0].phase).toBeNull();
});
```

Those two tests are the two easiest mistakes to make. Write them first.

**Wire it up** in your own `src/App.jsx`, then render `<App />` from `element.tsx`
in place of the `Placeholder`. One `<Col>` per panel:

```jsx
<Row gutter={[token.margin, token.margin]}>
  <Col xs={24} xl={12}><PodsCard state={usePods(environmentId)} /></Col>
</Row>
```

### The five states — the Card makes skipping one awkward

| State | Render | Because |
|---|---|---|
| `loading` | `Card loading` / `Skeleton` | |
| `error` | `Empty` + `Text type="danger"` + the message | a failed query is not an empty one |
| `no-config` | `Empty` + what is missing + how to fix | "this cluster has no Loki" is not an error |
| `empty` | `Empty` "No data for this range" | measured, and there is genuinely nothing |
| `data` | the chart / table | |

**`no-config` is the state everyone forgets**, and it is the one that keeps a
missing backend from looking like a broken dashboard.

### Three contracts

1. **Absent ≠ zero.** A gap must never render as health. `null` and `0` are
   different pixels.
2. **One required query.** A widget declares exactly one query it cannot live
   without; every other query degrades with `.catch(() => [])`. One missing metric
   must not blank a whole widget.
3. **Five states.** Above. All of them.

## Canonical patterns to mirror

Read these before inventing anything:

| Pattern | File |
|---|---|
| Trend chart, tokenised | `EnvironmentMonitoring/components/TrendChart.tsx` |
| Stat tile with status + drill-down | `EnvironmentMonitoring/components/MetricCard.tsx` |
| Utilisation ring | `EnvironmentMonitoring/components/CircularProgressCard.tsx` |
| Grid of tiles | `EnvironmentMonitoring/components/MetricsDashboard.tsx` (`Row`/`Col`) |
| Tool availability + masked secrets | `EnvironmentMonitoring/components/MonitoringDetection.tsx` |
| Alerts table + severity filter | `EnvironmentAlerts/components/AlertsTable.tsx` |

`MetricCard` is the anatomy to copy: `Card` + `Statistic`, a `status` prop of
`normal | warning | error` mapped to tokens, a lucide status icon, an optional
`breakdown` line, and an optional drill-down button.

One judgment call in that file worth making **deliberately** rather than
inheriting: it treats `0` as an error (`podsError = !metrics?.activePodsCount`).
For pod counts that is defensible — a cluster with zero pods is broken. For a
queue depth or a 5xx count it is exactly the absent-vs-zero bug. Decide per
metric, and write the reason down.

## Shadow DOM — proven, with two required lines

The component mounts into an open shadow root. Verified working: antd renders,
recharts measures correctly, styles do not leak either direction.

```tsx
// resolveFacetsTheme() = vendored facetsTheme ⊕ /public/v1/themeFile ⊕ dark strip
// (see §The theme pipeline — do NOT pass a bare algorithm here)
<StyleProvider container={shadowRoot} hashPriority="high">
  <ConfigProvider
    theme={resolveFacetsTheme({ dark })}
    getPopupContainer={() => popupHost}   // inside the shadow root
  >
```

The Phase-0 spike passed `{ algorithm, token: { colorPrimary } }` — enough to
prove shadow DOM works, **not** enough to look like the product. Replace it with
the resolved theme when building the template.

- **`StyleProvider container`** — antd v5 is CSS-in-JS. Without this, styles go to
  `document.head` and nothing inside the root is styled.
- **`getPopupContainer`** — Select, Tooltip, Modal, DatePicker and Dropdown all
  portal to `document.body` by default, landing **outside** the root and rendering
  unstyled. Point them at a host element inside it.
- Make that host `position: absolute; top: 0; left: 0; height: 0` inside a
  `position: relative` wrapper, so popup offsets resolve from the component's own
  origin rather than drifting on a tall or scrolled card.

### Theme handoff

The host injects only `project-name` and `environment-id` — no theme. Resolve in
this order:

1. explicit `theme-mode` / `theme-primary` attributes, if the author set them;
2. the `--facets-color-primary` custom property — **custom properties inherit
   through shadow boundaries**, confirmed;
3. inference from the **inherited text colour**.

> Infer from `color`, **never** from `background-color`. `color` is inherited so
> it reaches the element from the host; `background-color` is not, so the
> element's own background computes to `rgba(0,0,0,0)` — and a luminance test
> reads transparent as black, rendering every component dark on a light host.
> That is the "dark component on a light drawer" bug, and it is one line deep.

## Build — the silent-blank-panel traps

All of these produce a blank panel with **no console error**:

| Trap | Fix |
|---|---|
| vite lib mode does not substitute `process.env.NODE_ENV`; React reads it at module scope → `process is not defined` | `define: { 'process.env.NODE_ENV': '"production"' }` |
| Tailwind v4 emits `:root`, which matches nothing inside a shadow root | do not use Tailwind — use antd tokens |
| host theme ignored | the handoff above |
| a watchdog/verify script that dies on a syntax error reports **silence**, which reads as health | make the script fail loudly and assert a positive signal |
| **`formats: ['umd']`** — the bundle registers as an AMD module and never defines the element | use `['iife']`. See below; this one only appears on some pages |

### The shipped file must be a classic script

The host loads the bundle with `script.type = 'text/javascript'` — **not** a module.
So the *output* file may contain no `import`, no `export`, and no top-level `await`.

Your *source* uses imports freely; the bundler resolves them. It is only the built
artifact that must be self-contained. That is what `formats: ['iife']` plus
`inlineDynamicImports: true` produces.

> **Do not switch to `umd`.** A UMD bundle tests for an AMD loader first. Monaco
> installs `window.define` with `.amd` the moment any editor mounts on the page, so a
> UMD component registers as an anonymous AMD module that nothing ever requires — its
> factory never runs and `customElements.define` is never reached. The panel is blank
> with no error, **and only on pages where an editor has mounted**, which makes it
> look intermittent. The host suppresses `.amd` during load to defend against this;
> IIFE avoids the situation entirely.

Register the element at **module scope**, never inside a function. If it is not
registered by the time the script finishes, the host has nothing to mount.

Build shape: `formats: ['iife']`, `inlineDynamicImports: true`, `cssCodeSplit:
false` — one served file.

### When a panel misbehaves

| Symptom | Cause |
|---|---|
| Nothing renders at all | the element was not registered at module scope |
| Styles leak into the host page, or the component is unstyled | no shadow root, or `StyleProvider` was not given the root |
| Requests return `401` | the component is being tested outside the platform; the session cookie only exists inside it |
| Requests return `403` | the signed-in user lacks the permission — check their roles |
| Panels are blank on one environment only | `baseClusterId` was skipped for a dependent environment |
| A dropdown appears far from its trigger | the popup host is not positioned at the component's origin |

**Measured**: React 19 + antd + recharts + lucide = **1.01 MB raw / 315 KB gzip**,
against an 8 MB server cap. There is room; there is not room to be careless. Do
not add a second chart library.

Do **not** append `?v=<sha>`. Cache-busting is platform-owned now (`no-cache` +
`Last-Modified` → 304), and the query string used to break element-name
derivation. See `hosting.md`.
