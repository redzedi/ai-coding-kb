# SOP — Enabling the `<ENV>` environment, one resource per type  ·  <CUSTOMER>

> Instantiate this template per engagement: copy into the customer folder, fill every `<...>`, and
> work it top-to-bottom. Plan-gate every step. Phase B is **real provisioning** (new infra + cost),
> unlike the zero-change import. Log new nuances inline under §7 and PR them to the central
> `nuances-catalog.md`. (Source: `facets-gcp-zero-change-import` skill.)

---

## 0. Context (memorize)

```
  CP / project       <control-plane url>   ·   project <PROJECT_ID>   ·   FACETS_PROFILE=<profile>
  Gateway profile    praxis active_profile = <profile>   (global — restore if a parallel job needs it,
                                                          UNLESS told to keep this one)
  New env            <ENV>   (region <REGION>, RUNNING)
  Cloud account      <new-account>   (GCP project <GCP_PROJECT>)
  Home (prod) env    <HOME_ENV>   (region <HOME_REGION>)
  SHARED?            project shared with home: <yes/no>   ·   VPC shared: <yes/no>
                     → if either yes, the CARDINAL RULE applies (see §4 + catalog §Networking)
  Key variables      <e.g. GCP_DEFAULT_ZONE per env>
  Disabled-by-design <e.g. Atlas/secrets not set here>
```

The env was launched with all workload resources **disabled** except `cloud_account`. Enable ONE
representative per type, verify, then bulk-enable.

---

## 1. Enable order (dependency tiers)

```
  ✓ cloud_account ............ foundation (already enabled)
  1. network ................. VPC/subnet/NAT/PSA(or PSC); backs DBs/cache
  2. <stateless usage types> . object_store, pubsub, pubsub_subscription, cloud_tasks
  3. <stateful constant types> redis, mysql, postgres (need network)
  4. gke ..................... needs network; verify machine type offered in <REGION> first
  5. kubernetes_node_pool .... needs the gke cluster
  SKIP: <types to keep disabled>
```
Pick the smallest/cheapest representative per type to keep verification cheap.

---

## 2. Naming rule (fill if project is SHARED with home)

Project-global names collide with the home env's. Apply dual-mode naming + suffix-by-scope (catalog
§Naming). Record per-type decisions here:
```
  <type> → name field <empty→derive | pinned override=<name>>   suffix=<unique_name|env.name|none>
```

---

## 3. Per-resource workflow

Run the 6-step Phase-B workflow (a–f) from the skill for every `KIND/NAME`: read module → diff
blueprint vs home-effective → set overrides → plan-gate → apply (fire-and-poll) → verify live + diff
vs home.

---

## 4. Safety gates

- Plan-gate before every apply; 0 unexpected destroy/replace.
- **CARDINAL (shared project/VPC): no change here may affect `<HOME_ENV>`.** Run the isolation audit
  (catalog §Networking) before any shared-resource apply: CIDRs, VPC-scope CloudDNS domain, GKE master
  /28, firewall hashes, peerings.
- One per type before bulk-enable. Don't enable `<excluded types>`.
- Re-plan a FAILED-but-created resource; never destroy/recreate.
- No customer comms without owner review.

---

## 5. Reference: worked examples (fill as types complete)

```
  <type>:  resource <KIND/NAME>  ·  findings <...>  ·  overrides <...>  ·  plan <N add / 0 destroy>
           ·  live verify <gcloud output, diff vs home = identical except region/zone/name>
```

---

## 6. Customer progress tracker

One pinned message in `<channel>` (ts `<ts>`); `chat.update` it per type verified (don't spam new
messages). Footer `<footer>`. Format: code-block checklist, one line per resource type with
unicode emoji (`✅` done / `🔄` in progress / `⬜` pending — not `:shortcodes:`, they don't render
inside code blocks) + short detail, then a `Next:` line and a `_Last updated:_` footer.

---

## 7. Nuances log (NEW gotchas hit this engagement → PR to central catalog)

```
  - <symptom> → <cause> → <fix>
```
