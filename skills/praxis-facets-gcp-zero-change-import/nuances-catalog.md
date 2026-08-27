# GCP-into-Facets nuances catalog

Pre-documented gotchas, each **symptom → cause → fix**. Read before Phase B. When you hit a NEW one,
add it here (and PR back to `Facets-cloud/facets-assets`). Seeded from the SaaS Labs (JustCall) EU-prod
engagement.

---

## Networking

**Cardinal isolation rule (shared project/VPC).** A new region/env often reuses the home env's GCP
project and default VPC. Before any shared-resource apply, prove isolation on EVERY surface — else you
can break prod:
```
  Surface                 Isolation check
  ──────────────────────  ─────────────────────────────────────────────────────────────
  Subnet / secondary CIDRs  non-overlapping with ALL home-env ranges (incl. the auto-mode /9)
  VPC-scope CloudDNS domain unique per cluster (e.g. prod="production", new="eu-prod")
  GKE master /28            distinct, non-overlapping
  Firewall rules            GKE namespaces by per-cluster HASH + node tag → eu rules hit only eu nodes
  VPC peerings              each cluster/service gets its OWN peering; adding one doesn't alter others
  Resource path             region-scoped resources (GKE, Redis, subnets) don't collide across regions
```
A shared cluster *name* is cosmetic IF GKE hashes its generated resources (it does) — verify via the
DNS zone + firewall-rule hashes before relying on it.

**Subnet create 403 `compute.networks.updatePolicy`.** Symptom: creating a regular subnet *with
secondary ranges* on a shared VPC fails 403 even though a plain (proxy) subnet succeeded. Cause: adding
a subnet with secondary ranges modifies network policy; needs `compute.networks.updatePolicy`, which a
least-privilege deploy role often lacks. Fix: add that permission to the deployer role.

**Cloud SQL "Couldn't find free blocks in allocated IP ranges" (PSA).** Cause: PSA ranges are reserved
but not attached to the VPC's servicenetworking peering (`manage_service_connection=false`), or the
peering is full. Fix: use **PSC instead of PSA** — set `psc_enabled=true` and drop the PSA fields
(`private_network`/`enable_private_path` → null). PSC needs no servicenetworking peering and sidesteps
the whole shared-peering-range problem. (PSA and PSC are mutually exclusive on an instance.)

---

## GKE (the highest-nuance type)

**Pod/service secondary ranges missing in the new region.** Symptom: greenfield GKE create fails — the
network module data-sources the home subnet's GKE-created secondary ranges, but the new region's default
subnet has none → empty range names. Two correct approaches:
- **OPT-1 (mirror prod):** gke module passes `cluster_ipv4_cidr_block`/`services_ipv4_cidr_block` (CIDRs,
  not names) → GKE auto-creates the ranges on the default subnet (this is how the home env's ranges
  came to exist; note the GKE-generated hash in their names). No network-module change; ranges are
  GKE-owned (not in TF state). Requires a gke-module change.
- **OPT-2 (TF-owned, gke module unchanged):** network module CREATES a dedicated GKE subnet with
  `secondary_ip_range` blocks (a `gke_subnet_json` override-only field) and emits `private_subnet_id` +
  the range NAMES in `network_details`; gke module consumes names unchanged. Ranges are Terraform-managed.
  Costs `compute.networks.updatePolicy` (see Networking). Prod stays 0-change when the field is empty.

**GKE create 400 `cluster_dns_domain must be specified when using VPC scope and CloudDNS`.** Cause:
`cluster_dns = CLOUD_DNS` + `cluster_dns_scope = VPC_SCOPE` requires a `cluster_dns_domain`, and it must
be **unique per cluster sharing the VPC**. Fix: set a distinct domain for the new cluster (home="production"
→ new="eu-prod").

**Greenfield GKE needs more than ranges.** Override-only spec fields the home env sets that the new env
also needs: `master_ipv4_cidr_block` (a distinct free /28), `master_authorized_networks_json` (admin
IPs — region-agnostic), `node_locations_json` (new-region zones), `cluster_dns_domain`.

**Default node pool lingers / cluster shows a `default-pool`.** Expected: `remove_default_node_pool=true`
removes it at create; if the create was interrupted it may persist but is inert (it + `node_config` +
`initial_node_count` are in the module's `ignore_changes`). A re-plan shows `No changes`.

---

## Naming (shared project ⇒ project-global names collide)

**Dual-mode naming.** Module name field: SET → used verbatim (import/home env PINS the live name in a
per-env override, keeping the blueprint env-agnostic); EMPTY → module DERIVES `{resource}-{suffix}`
(greenfield envs leave it empty → collision-safe, no per-resource override).

**Suffix by uniqueness scope:**
```
  GLOBAL names (GCS bucket, 63-char cap)      → suffix = {env.unique_name} (embeds project token)
  PROJECT-scoped (Pub/Sub, Cloud SQL)         → suffix = {env.name} (short; project-unique is enough)
  REGION-scoped (Redis ≤40, Cloud Tasks, GKE) → NO suffix (same name fine in a new region)
```

**`ignore_changes=[name]` makes name diffs inert** on existing (imported) resources — protects against
mis-pins, but a real rename needs disable → release --allow-destroy → clear override → enable → release.

---

## Cloud SQL

**`409 already exists` then `404 on describe`.** Cause: Cloud SQL reserves an instance name for **~1 week**
after a failed/deleted create ("name burning"). Fix: use a fresh name; don't retry the burned one.

**REGIONAL (HA) needs a secondary zone.** PSC and `private_network` are mutually exclusive. Names are
project-global (so they collide in a shared project — give the new env a distinct name).

---

## Permissions (least-privilege deploy SA gaps)

```
  compute.networks.updatePolicy   needed to create a subnet WITH secondary ranges on a shared VPC
  compute.machineTypes.get/list   the deploy SA often lacks it → machine-type describe/list FALSELY
                                  reports "not available". Use the HOME-env integration (broader perms)
                                  to check machine-type availability. Does NOT block node-pool create
                                  (GKE validates the type server-side).
  cloudtasks.queues.create        read-only import roles lack write; greenfield create needs it
```
General pattern: a read-only import role won't cover greenfield CREATE. Derive the minimal create role
from the modules' resources; split regional vs global perms; use GCP IAM Conditions for regional
resources (global services like GCS/PubSub can't be region-scoped via IAM — use org policy
`gcp.resourceLocations`).

---

## raptor / release mechanics

**The `-w` stall.** `raptor create release ... -w` blocks and can be watchdog-killed on slow envs that
pre-process all resources. Fix: **fire-and-poll** — run without `-w`, then poll `raptor get releases`
until SUCCEEDED/FAILED.

**`*_json` spec fields need `--spec-file`, not `--set`.** `--set spec.x='[...]'` parses the value as an
array → schema error (the field wants a JSON *string*). Use `--spec-file` with `json.dumps`-encoded
string values. `--spec-file` replaces the whole override spec — include all required fields (e.g.
`region`); blueprint-level defaults still merge in.

**FAILED release but the resource exists.** A create can complete + save TF state even though the release
shows FAILED (e.g. a later step errored). Symptom: the cloud resource is live. Fix: **re-plan** — if it
shows `No changes`, state already owns it; reconcile with a 0-change apply. NEVER destroy/recreate to
"fix" a FAILED release.

**`set-spec --type string` requires `--min-length`/`--max-length`.** Add bounds when adding string spec
fields, or the command errors.

**Gateway profile is global.** `praxis` gateway uses one active profile; a parallel job can own it.
`praxis login --profile <p>` flips it (reuses token, no browser). Gateway responses come either directly
(`{output:...}`) or MCP-wrapped (`{content:[{text:...}]}`) — handle both when parsing.
