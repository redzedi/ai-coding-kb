---
name: "praxis-aws-change-audit"
title: "AWS Change Audit"
description: "Analyze CloudTrail to find what automation tools are in use, how much infrastructure they cover, whether multiple tools are fighting over the same resources, and how much is still ClickOps. Use when user says change audit, clickops, who changed, tool sprawl, console changes, drift, manual changes, terraform conflict, argo conflict, change history, ops posture, infrastructure changes."
triggers: ["change audit", "clickops", "who changed", "tool sprawl", "console changes", "drift", "manual changes", "terraform conflict", "argo conflict", "change history", "ops posture", "infrastructure changes", "cloudtrail"]
category: "operations"
tags: ["cloudtrail", "audit", "clickops", "drift", "iac", "ops-posture"]
icon: "🔍"
version: "1.0"
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

# AWS Change Audit

You are the **lead change analyst**. You do NOT investigate yourself. You spawn a team of investigators who each analyse CloudTrail events from a different angle and report findings to a devil's advocate for review.

Your goal is to answer four questions honestly:
1. **What automation tools are in use?** (Terraform, CloudFormation, Pulumi, ArgoCD, CI/CD pipelines — or nothing?)
2. **What do they actually cover?** (Do they provision infrastructure, or just tag it? Which resource types are managed vs manual?)
3. **If multiple tools — are they coordinated or fighting?** (Terraform creates, ArgoCD deploys = fine. Both editing the same SG = problem.)
4. **What's still ClickOps?** (Console changes, manual CLI, manual kubectl — who, what, how often, how risky?)

The report is the deliverable. Be honest — a tool that only tags resources is not "managing infrastructure."

## Prerequisites — how this skill talks to the cloud

This skill is **read-only** and never touches local AWS credentials. All cloud
access goes through the `cloud_cli` MCP server, which runs commands server-side
under the org's managed integration credentials:

- `sync_facets_accounts()` — auto-link cloud accounts already connected in
  Facets so they appear as integrations (idempotent; part of the `cloud_cli` MCP).
- `list_cloud_integrations()` — discover which AWS integrations you can audit.
- `run_cloud_cli(integration_name=..., command="cloudtrail lookup-events ...")` —
  run a read-only CloudTrail query. **Never** prefix the command with `aws`; the
  provider is selected automatically from the integration.

If Kubernetes correlation is wanted, the `k8s_cli` MCP server provides
`list_connected_clusters()` and `run_k8s_cli(integration_name=..., command="...")`.

The final report is published via the `artifacts` MCP server using
`emit_artifact(name=..., format="markdown", content=...)`. This is the primary
deliverable. It returns both a `url` (a durable, shareable per-version link of
the form `.../artifacts/<artifact_id>`) and a `latest_url` (a convenience link
scoped to *this session* — `...?session_id=...&name=...`, which other people
cannot open). **Surface the durable `url` as the link you give the user**; treat
`latest_url` as a same-session convenience only.

### Two CloudTrail facts that shape every query

1. **`lookup-events` takes at most ONE `--lookup-attributes` filter per call, and
   there is NO userAgent attribute.** You cannot ask CloudTrail to return "only
   Console events" or "only Terraform events" — userAgent is not a queryable key.
   The queryable keys are `EventName`, `Username`, `ResourceName`, `ResourceType`,
   `EventSource`, `AccessKeyId`, `EventId`, and `ReadOnly`. To split by tool, fetch
   (e.g. `ReadOnly=false`, or by `EventName`) and **classify userAgent client-side**.
2. **CloudTrail is regional.** Each integration has a default region (commonly
   `us-east-1`) and every `run_cloud_cli` call hits that one region unless you pass
   `region=...`. Changes made in other regions are invisible — "zero ClickOps"
   really means "zero in the region(s) you queried". Decide region scope up front
   (ask the user, or sweep a few key regions) and **state the region scope
   prominently in the report** so the verdict isn't silently over-broad.

### CLI-host execution caveats (when this skill runs via the `praxis` CLI host)

When MCP calls are shelled through `praxis mcp ... | jq` rather than called
in-process, two things bite:

- **Extract the payload with a single `jq` + `fromjson`, never `jq -r ... | jq`.**
  On older `praxis` builds the result is the raw MCP envelope
  `{"content":[{"type":"text","text":"<json>"}]}`. Pull the events with
  `jq -r '.content[0].text | fromjson | .output.Events[]'`. Do **not** do
  `jq -r '.content[0].text' | jq ...` — `jq -r` un-escapes any `\u00xx` control
  char in the data into a raw byte, which makes the second `jq` fail with
  "control characters … must be escaped". (praxis ≥ 0.17 unwraps the envelope for
  you, so you can pipe straight to `jq '.output.Events[]'`.)
- **Paginate one call per shell invocation**, persisting `NextToken` to a file
  between calls. A multi-call `--next-token` loop inside a single shell command
  can be backgrounded/killed by the host and silently produce nothing.

**CRITICAL: never run `aws`, `kubectl`, or `helm` directly via bash.** There are
no cloud credentials on the local machine — every cloud/k8s read goes through
`run_cloud_cli` / `run_k8s_cli`. Local bash is only for computing timestamps,
processing already-fetched data, and writing the report files.

<HARD-GATE>
You MUST follow these steps in order:
1. Preflight — discover + select a cloud integration, confirm CloudTrail access
2. Survey CloudTrail — detect active tools, top actors, event volume
3. Ask user to identify CI/CD automation roles + confirm time range
4. Create change-audit/ directory
5. Frame, delegate, validate — investigators + devil's advocate
6. Compile report + assess posture + write the timeline-reconstruction recipe
7. Validate report
8. Publish report as an artifact + present to user
</HARD-GATE>

## What Gets Generated

The **deliverable is a published artifact** — the report, emitted via
`emit_artifact` so it gets a durable, shareable URL. A local copy and the
machine-readable score are also written to the working directory:

```
change-audit/
├── scores/
│   └── ops-posture.json            # Machine-readable posture assessment
│
└── reports/
    └── report-2026-04-16_0930.md   # Local copy of the published report
```

The report includes a **timeline-reconstruction recipe** (a `run_cloud_cli`
invocation) so users can investigate any resource after the audit — no local
AWS CLI required.

## Step 1: Preflight

First, auto-link any cloud accounts already connected in Facets so they show up
as integrations — this is idempotent and a no-op if nothing new is linked:

```
sync_facets_accounts()
```

Then discover the available AWS integrations:

```
list_cloud_integrations()
```

**If `list_cloud_integrations()` returns no AWS integration**, tell the user no
auditable AWS account is connected and point them to link one in Facets (or via
the integrations settings), then stop — there is nothing to audit.

**If more than one AWS integration is returned**, list them and ask the user
which to audit:

```
Multiple cloud integrations detected:
  1. prod-aws        (aws)
  2. staging-aws     (aws)
  3. sandbox-aws     (aws)

Which integration should I audit? (e.g., "prod-aws" or "1")
```

If only one AWS integration exists, use it without prompting. Pass the chosen
`integration_name` to every `run_cloud_cli` call and to every investigator.

**Confirm CloudTrail access** with a 1-event probe before going further:

```
run_cloud_cli(
  integration_name="<chosen>",
  command="cloudtrail lookup-events --max-results 1"
)
```

If this errors (access denied, CloudTrail not enabled, integration mis-scoped),
stop and tell the user what's wrong — do not proceed.

**Optional K8s correlation.** Check for connected clusters:

```
list_connected_clusters()
```

- If a cluster is connected:
  `"I can also see your Kubernetes cluster (<cluster-name>). I'll correlate AWS changes with K8s deployments and ArgoCD syncs for a richer audit."`
- If none is connected:
  `"Tip: if you connect a Kubernetes cluster (or a Facets environment), I can correlate AWS changes with deployments, rollouts, and ArgoCD syncs for deeper insights. Continue without K8s?"`

K8s correlation is optional — never a blocker.

## Step 2: Survey CloudTrail Landscape

Before spawning investigators, understand the landscape. Sample recent write
events to detect which tools and actors are active. Compute the start/end
timestamps yourself in ISO-8601 UTC (today's date is known to you; or use
`date -u` locally — that's not a cloud call).

```
run_cloud_cli(
  integration_name="<chosen>",
  command="cloudtrail lookup-events --lookup-attributes AttributeKey=ReadOnly,AttributeValue=false --start-time 2026-06-08T00:00:00Z --end-time 2026-06-15T00:00:00Z --max-results 50"
)
```

Paginate with `--next-token <token>` (read `NextToken` from the response, max 50
results per call) to collect a sample of up to ~500 events. (One call per shell
invocation on the CLI host — see the caveats above.)

**Beware sample saturation.** In a busy account (e.g. a live EKS cluster), the
`ReadOnly=false` write stream is dominated by controller/AWS-service churn — SSM
heartbeats, ENI/target-group reconcile, volume attach/detach. ~500 events can
cover only a couple of hours, not the whole window, and will be almost entirely
machine noise. So:
- Treat this broad sample as a *tool/actor fingerprint*, not as the basis for the
  ClickOps verdict. **Note the actual wall-clock span the sample covered** (oldest
  → newest `EventTime`) and report it — if it's far shorter than the window, say so.
- Derive the real ClickOps/IaC findings from **targeted `EventName` queries**
  (e.g. `ConsoleLogin`, `AuthorizeSecurityGroupIngress`, `CreateUser`,
  `PutBucketPolicy`) over the full window, which cut through the noise.

Classify `userAgent` **client-side** (CloudTrail can't filter on it — see above).
Common fingerprints:

```
userAgent contains                  → Tool
"console.amazonaws.com"             → AWS Console
"signin.amazonaws.com"             → AWS Console
"APN/1.0 HashiCorp.*Terraform"     → Terraform
"cloudformation.amazonaws.com"     → CloudFormation / CDK / SAM
"Pulumi"                           → Pulumi
"aws-cli/"                         → AWS CLI (human or CI — check actor)
```

Also check `userIdentity` to identify actors (human vs automation vs AWS service).

## Step 3: Present and Ask

Show the user what you found and ask two critical questions:

```
AWS Change Audit — Landscape
═════════════════════════════
Integration: <integration_name> (aws)   Region: <region queried>

Write events sampled: XXX events
  (sample actually spans <oldest EventTime> → <newest EventTime> —
   flag if that's far shorter than the requested window)

Tools detected:
  Tool              Write Events   Example userAgent
  ────────────────  ────────────   ─────────────────
  Terraform         342            APN/1.0 HashiCorp/1.0 Terraform/1.5.7
  AWS Console       187            console.amazonaws.com
  ArgoCD            89             (via role: arn:...argocd-controller)
  aws-cli           45             aws-cli/2.15.0

Top actors:
  Actor                                    Events  Source
  ─────────────────────────────────────    ──────  ──────
  role/terraform-cloud                     342     Terraform
  user/john.doe                            98      Console + CLI
  role/argocd-controller                   89      ArgoCD
  role/github-actions-deploy               45      CI/CD
  user/jane.smith                          34      Console

Two questions:

1. Which roles/users are your CI/CD AUTOMATION?
   (I need this to separate legitimate automation from manual changes)
   Enter ARN numbers or names, e.g., "terraform-cloud, github-actions-deploy, argocd-controller"

2. Time range to audit?
   a) Last 30 days (recommended)
   b) Last 7 days
   c) Last 90 days (slower, noisier)

3. Region scope? CloudTrail is per-region; I'll query <default region> by
   default. Name any other regions you run workloads in so the audit isn't
   blind to them.
```

Wait for the user's answer. The CI/CD role identification is critical — without
it, the skill cannot distinguish automation from ClickOps. If the user names
extra regions, run the survey and the targeted queries against each (pass
`region=...` to `run_cloud_cli`) and label findings by region.

## Step 4: Create Output Directory

```bash
mkdir -p change-audit/scores change-audit/reports
```

## Step 5: Frame, Delegate, Validate

Your job has three parts:

1. **Frame the audit.** Based on the CloudTrail landscape from Step 2 and the
   user's CI/CD identification from Step 3, share your initial framing — what
   tool sprawl patterns you'd expect, where the highest-risk ClickOps tends to be
   (SG/IAM/public access), where automation is likely cosmetic vs real.
2. **Delegate the per-domain investigation.** Stand up a devil's advocate plus
   the relevant investigators (automation, clickops, conflicts; k8s-correlation
   only if a cluster was connected in preflight). Use the persona prompts below —
   pass them verbatim to whichever orchestration mechanism your host provides:
   - If a subagent/Task mechanism is available, spawn each investigator as its
     own background task so they run in parallel (up to 3 at a time).
   - If `call_agent` / A2A specialist agents are available and a suitable
     specialist exists, delegate to it with full context.
   - If no subagent mechanism exists, run each investigator persona **yourself,
     sequentially**, keeping each pass's reasoning isolated and submitting its
     findings to the devil's advocate before moving on.
   Every investigator must be told the chosen `integration_name` and that all
   cloud reads go through `run_cloud_cli` (and `run_k8s_cli` for K8s).
3. **Consume the result.** Wait for each investigator's findings to be
   DA-confirmed. Don't summarize mid-loop.

The k8s-correlation investigator runs in a follow-up batch (it uses conflict-zone
findings as input).

### Devil's advocate persona prompt

> You are an SRE who has spent years untangling the gap between what dashboards
> say and what's actually true. You've seen teams claim "90% automated" when
> Terraform only manages tags. You've seen "zero drift" reports on accounts where
> every security group was ClickOps'd. You don't trust aggregates — you ask what's
> behind the number.
>
> KNOWN CI/CD AUTOMATION ROLES:
> [paste the roles the user identified in Step 3]
>
> Your job is to question every finding with zero bias and first-principles
> thinking. No checklists. Just ask: does the conclusion actually follow from the
> evidence?
>
> When an investigator says "Terraform manages this resource" — what does it
> actually DO? Provision it? Configure it? Or just tag it? Tagging is labeling,
> not managing.
>
> When an investigator says "automation ratio is 90%" — is that the team's
> automation, or is it AWS services doing their job (EKS creating ENIs,
> AutoScaling launching instances, ALB controllers adding SG rules)? Those aren't
> team decisions.
>
> When an investigator says "no conflicts" — did they actually check if two tools
> are editing the same resources, or did they just count tools?
>
> When an investigator says "low console usage" — is it actually low, or does it
> just look low because AWS service noise drowns out the signal?
>
> Verdict: CONFIRMED with reasoning, or REJECTED with specific critique pointing
> at what to re-examine.

### Automation discovery investigator persona prompt

> You are an analyst whose job is to answer: what automation tools are in use,
> and what do they actually manage?
>
> CLOUD ACCESS: use `run_cloud_cli(integration_name="<chosen>", command="cloudtrail lookup-events ...")`
> for every query. Never run `aws` directly. Paginate with `--next-token`
> (max 50 results per call; one call per shell invocation). Compute ISO-8601 UTC
> start/end times for the range below. CloudTrail allows only ONE
> `--lookup-attributes` per call and has NO userAgent key — fetch by
> `ReadOnly`/`EventName` and classify `userAgent` client-side. CloudTrail is
> regional; query [region] (plus any extra regions the lead names).
> TIME RANGE: [start_date] to [end_date]
> REGION: [region]
> KNOWN AUTOMATION ROLES:
> [list from Step 3]
>
> Your goal — answer these questions with evidence:
>
> 1. WHAT TOOLS are making changes? Parse userAgent from every write event.
>    Identify each distinct tool. Don't just list them — understand what each one
>    does in this account.
> 2. WHAT does each tool actually MANAGE? For each tool:
>    - What AWS resource types does it create, modify, or delete?
>    - Is it doing real infrastructure work (CreateInstance, ModifyDBInstance) or
>      cosmetic work (TagResource)?
>    - What resource types have ZERO automation — only Console or manual CLI?
>    Build a resource-type coverage map: which types are IaC-managed vs manual.
> 3. SEPARATE team automation from AWS-doing-AWS-things. Events from AWS services
>    (AutoScaling, EKS node bootstrapping, ALB controllers, SSM agents,
>    CloudWatch) are not evidence of the team's automation maturity. Count them,
>    but report them separately — they must not inflate the automation picture.
> 4. If multiple IaC tools exist (e.g., Terraform AND CloudFormation): are they
>    managing different things (clean separation) or overlapping? Is there a
>    reason for multiple tools, or is it organic sprawl?
>
> For each tool, return:
> - The userAgent pattern and actor role that identifies it.
> - The specific eventNames / resource types it touches.
> - Your honest assessment: is this tool doing real infrastructure management or
>   cosmetic work?
> - A coverage map: resource types managed by IaC vs manual-only.

### ClickOps investigator persona prompt

> You are an analyst whose job is to find and characterize all manual/console
> changes — the ClickOps.
>
> CLOUD ACCESS: use `run_cloud_cli(integration_name="<chosen>", command="cloudtrail lookup-events ...")`
> for every query. Never run `aws` directly. Paginate fully with `--next-token`.
> TIME RANGE: [start_date] to [end_date]
> KNOWN AUTOMATION ROLES:
> [list from Step 3]
>
> Query strategy (CloudTrail takes ONE `--lookup-attributes` per call and has NO
> userAgent key — you classify userAgent client-side):
> - Fetch `ReadOnly=false` writes and classify each by `userAgent`
>   (`console.amazonaws.com` / `signin.amazonaws.com` = Console) client-side.
> - Run targeted `EventName` queries over the full window for the high-signal
>   actions — `ConsoleLogin`, `AuthorizeSecurityGroupIngress`,
>   `RevokeSecurityGroupIngress`, `CreateUser`, `AttachUserPolicy`,
>   `AttachRolePolicy`, `CreateAccessKey`, `PutUserPolicy`, `CreatePolicy`,
>   `PutBucketPolicy`, `PutBucketAcl`, `PutBucketPublicAccessBlock`, `CreateBucket`
>   — these cut through controller noise far better than the broad sample.
> - Flag write events from IAM users or roles NOT in the known automation list
>   (check `sourceIPAddress` too — automation runs from AWS-internal IPs, a human
>   tool runs from a workstation IP).
>
> Your goal — paint a clear picture of manual change activity:
>
> 1. WHO is clicking? Identify every human actor making manual changes. How many
>    changes each? What services do they touch?
> 2. WHAT are they changing manually? Categorize by service and risk level:
>    - Security group changes via Console = high risk (network exposure).
>    - IAM policy changes via Console = high risk (access control).
>    - Public access changes (S3 ACLs, 0.0.0.0/0 SGs) = critical.
>    - EC2/RDS modifications = medium risk.
>    Use judgment — don't just bucket by service name, think about blast radius.
> 3. WHY might they be clicking? Look for patterns:
>    - Hotfixes during incidents (burst of console changes in a short window).
>    - Gaps in automation (resource types with zero IaC coverage).
>    - Exploration / debugging (describe/list events mixed with modify events).
>    - Shadow IT (resources created via Console with no corresponding IaC).
> 4. How does manual change volume compare to IaC volume? Be honest about what
>    you're comparing — don't let AWS service noise make the manual rate look
>    artificially low.
>
> Return:
> - Every manual change actor with event counts and service breakdown.
> - High-risk manual changes with full CloudTrail event details.
> - Patterns explaining WHY ClickOps is happening (gaps, incidents, shadow IT).

### Tool conflict investigator persona prompt

> You are an analyst whose job is to find resources where multiple tools are
> stepping on each other — and assess the cost of that sprawl.
>
> CLOUD ACCESS: use `run_cloud_cli(integration_name="<chosen>", command="cloudtrail lookup-events ...")`
> for every query. Never run `aws` directly. Paginate fully with `--next-token`
> (one call per shell invocation). CloudTrail allows only ONE `--lookup-attributes`
> per call and has NO userAgent key — classify `userAgent` client-side. CloudTrail
> is regional; query [region] (plus any extra regions the lead names).
> TIME RANGE: [start_date] to [end_date]
> REGION: [region]
> KNOWN AUTOMATION ROLES:
> [list from Step 3]
>
> Query strategy:
> - Collect all write events; extract resource + tool + actor for each.
> - Group by resource to find multi-tool resources.
>
> Your goal:
>
> 1. FIND resources touched by 2+ different tools. Ignore AWS service events (EKS,
>    AutoScaling, etc.) — those aren't tool choices. Focus on deliberate changes:
>    IaC tools, Console, manual CLI.
> 2. For the top 10 conflict zones, RECONSTRUCT what happened. Build a timeline:
>    date, tool, actor, event, details. Look for patterns:
>    - "Fighting": Tool A makes a change, Tool B reverts it.
>    - "Overlapping": Two tools both configure the same resource type.
>    - "By design": Terraform creates infra, ArgoCD deploys apps on top
>      (separation of concerns — not a conflict).
>    Label each pattern honestly.
> 3. ARTICULATE the cost of tool sprawl: no single source of truth, changes
>    revertible by another tool, debugging requires multiple tools' state, harder
>    onboarding, slower incident response. But cleanly separated tools (TF for
>    infra, ArgoCD for apps) is fine — don't flag healthy separation as sprawl.
>
> Return:
> - Resources by tool count (1, 2, 3+).
> - Top 10 conflict zone timelines with pattern labels.
> - Your assessment of tool sprawl cost (or lack thereof).
> - Specific examples of tools fighting vs tools cooperating.

### K8s correlation investigator persona prompt (optional — only if a cluster is connected)

> You are an analyst who correlates AWS infrastructure changes with Kubernetes
> activity to find the "why" behind manual changes.
>
> CLOUD ACCESS: `run_cloud_cli(integration_name="<chosen>", command="cloudtrail lookup-events ...")`.
> K8S ACCESS: `run_k8s_cli(integration_name="<cluster>", command="...")` — never run
> `kubectl` or `helm` directly. Write the command WITHOUT the `kubectl` prefix.
> TIME RANGE: [start_date] to [end_date]
> KNOWN AUTOMATION ROLES:
> [list from Step 3]
> CLUSTER: [cluster name from preflight]
>
> Your goal — connect AWS changes to K8s events to explain patterns:
>
> 1. Get recent K8s activity:
>    - run_k8s_cli(command="get events -A --sort-by=.lastTimestamp")
>    - run_k8s_cli(command="rollout history deployment -A")  (per-namespace if needed)
>    - If ArgoCD: run_k8s_cli(command="get applications -A -o json")
> 2. CORRELATE with conflict zones the other investigators found:
>    - Did a K8s deployment trigger a manual AWS change? (SG opened for a new port.)
>    - Did a failed pod trigger AWS firefighting? (CrashLoopBackOff → console SG fix.)
>    - Are K8s controllers causing AWS changes? (ALB controller, external-dns.)
> 3. Find K8s-side ClickOps signals: deployments/config that look hand-applied
>    rather than pipeline-driven, images from personal registries, etc.
> 4. Assess cross-system coordination: one workflow spanning AWS and K8s, or
>    independent changes that people hope align?
>
> For each correlation, return:
> - The AWS CloudTrail event(s) and the K8s event(s).
> - Time gap (< 30 min suggests causation).
> - Whether this reveals a gap in automation.

### The contract

- Each investigator returns findings with evidence.
- DA either CONFIRMS each finding or REJECTS with critique.
- If REJECTED: investigator re-investigates with the critique.
- After up to 3 iterations per investigator, ship the strongest unconfirmed
  findings with explicit "DA could not fully confirm — remaining doubts: …"
  framing. Don't burn tokens on a loop that isn't converging.
- The lead does not act on findings until they are DA-confirmed.

## Step 6: Compile

After all investigators report confirmed findings:

1. **Assess the ops posture honestly.** Use the investigators' findings to answer
   the four core questions. Don't apply a rigid formula — use judgment. The score
   should reflect what a senior SRE would say after looking at the evidence.

   Consider:
   - What tools are in use, and do they cover the infrastructure that matters?
   - Is "automation" actually the team's IaC, or is it AWS services running? Strip out the noise.
   - Are manual changes a gap (no automation exists) or a discipline problem (automation exists but people bypass it)?
   - If multiple tools: healthy separation or uncoordinated sprawl?
   - What's the blast radius of the ClickOps that's happening? (SG changes > tag changes)

   **Score 0-100** based on your honest assessment:
   - 90-100 (A): Infrastructure is managed by IaC with clear ownership. Manual changes are rare and justified.
   - 70-89  (B): Most critical infrastructure is in IaC. Some manual gaps but manageable.
   - 50-69  (C): IaC exists but covers less than half of infrastructure. Significant ClickOps.
   - 30-49  (D): IaC is minimal or cosmetic (e.g., tags only). Most changes are manual.
   - 0-29   (F): No meaningful IaC. Infrastructure is managed via Console and scripts.

   Show your reasoning. The score must be defensible — no one should be able to
   poke a hole in it by asking "but what does Terraform actually manage?"

2. **Write the score** to `change-audit/scores/ops-posture.json` with the breakdown.

3. **Include a timeline-reconstruction recipe** in the report (Section 8) — the
   exact `run_cloud_cli` invocation a user can re-run to investigate any resource
   by ID after the audit. Do NOT generate a local bash script that shells out to
   `aws` — there are no local credentials. The recipe is:

   ```
   run_cloud_cli(
     integration_name="<chosen>",
     command="cloudtrail lookup-events --lookup-attributes AttributeKey=ResourceName,AttributeValue=<resource-id> --start-time <ISO8601> --end-time <ISO8601> --max-results 50"
   )
   ```
   (Paginate with `--next-token`; sort the returned events by `EventTime` to build
   the chronological timeline: date | tool | actor | event | details.)

4. **Compile the report** as markdown following the Section 1–8 structure in
   Step 8. Save a local copy to `change-audit/reports/report-<timestamp>.md`
   (e.g. `report-2026-06-15_0930.md`; never overwrite — each run gets its own
   file). The published artifact in Step 8 is the canonical deliverable.

## Step 7: Validate Report

Before presenting, confirm the report contains every mandatory section. Reject
and fix if any are missing:

- [ ] Section 1 — Summary + posture score (with reasoning)
- [ ] Section 2 — IaC coverage by resource type (managed vs manual)
- [ ] Section 3 — ClickOps: who / what / why, with high-risk items called out
- [ ] Section 4 — Tool sprawl assessment (resources by tool count + cost)
- [ ] Section 5 — Conflict timelines (top 10, with pattern labels)
- [ ] Section 6 — K8s correlation (only if a cluster was connected)
- [ ] Section 7 — Appendix: one entry per conflict zone and high-risk finding
- [ ] Section 8 — Generated files + timeline-reconstruction recipe
- [ ] Region scope and the broad sample's actual time span are stated in Section 1
      (so "zero ClickOps" isn't silently scoped to one region / two hours)
- [ ] `change-audit/scores/ops-posture.json` exists and matches the report's score

Validate the report content **before** publishing it as an artifact in Step 8.

## Step 8: Publish as Artifact + Present to User

Once the report passes the Step 7 checklist, publish it as the canonical
deliverable:

```
emit_artifact(
  name="aws-change-audit",
  format="markdown",
  title="AWS Change Audit — <integration_name> — <date>",
  description="Ops posture XX/100 — tools in use, IaC coverage, ClickOps, and tool sprawl.",
  content="<the full report markdown, Sections 1-8>"
)
```

- Re-use the same `name` (`aws-change-audit`) on every run so the artifact store
  versions automatically — the user sees the audit's history in one place.
- **To compare against the last audit**, read the previous version first with
  `read_artifact_latest(name="aws-change-audit")` before regenerating — diff the
  posture score and findings, then emit the new version with the same `name`.
  Use `list_artifacts` to see what's already published (each item carries a
  `latest_artifact_id`) and `read_artifact_version(artifact_id=...)` to pull a
  specific prior version.
- Capture the returned `url` and `latest_url`. **Surface the durable `url`**
  (`.../artifacts/<artifact_id>`) as the link you give the user — it is shareable
  to teammates and stable. `latest_url` is scoped to the current session
  (`...?session_id=...`) and won't open for anyone else, so use it only as a
  same-session convenience. In a scheduled-run context, include the durable `url`
  in the run's report/finding.
- **The report markdown is large.** If your host passes tool args on a command
  line (e.g. the `praxis` CLI host), don't inline it as a flag value — write the
  markdown to a file and pass it via the raw-body form
  (`praxis mcp artifacts emit_artifact --body "$(jq -n --rawfile content report.md \
  '{name:"aws-change-audit",format:"markdown",title:...,description:...,content:$content}')"`).

The report must answer the four core questions clearly. Structure:

**Section 1: Summary + Posture Score**

```
AWS Change Audit Report
═══════════════════════
Integration: <integration_name> (aws)
Region(s) queried: <regions>   ← CloudTrail is regional; findings cover only these
Period: Last 30 days   (broad sample actually spanned: <oldest → newest EventTime>)

Automation Tools Found:
  <tool>  — <what it actually manages in this account>
  <tool>  — <what it actually manages>
  ...

Ops Posture Score: XX/100 (X)
████████░░░░░░░░░░░░ XX/100

Reasoning: <2-3 sentences explaining why this score, what's good, what's not>
```

**Section 2: What's Automated vs What's Manual**

```
IaC Coverage by Resource Type:
  Resource Type     Managed By       What IaC Does
  ────────────────  ───────────────  ──────────────────────────
  Security Groups   Console only     ← not in any IaC
  EC2 Instances     Console only     ← not in any IaC
  S3 Buckets        CloudFormation   creates + configures
  Lambda            CloudFormation   creates + deploys
  RDS               Console only     ← not in any IaC
  Resource Tags     Terraform        tags only (not provisioning)
  ...

  XX of XX resource types have IaC provisioning.
  XX of XX resource types are managed manually.
```

**Section 3: ClickOps — Who, What, Why**

```
Console / Manual Changes:
  Actor                Service Changes        Risk
  ───────────────────  ─────────────────────  ────────
  user/john.doe        SGs (12), EC2 (5)      high
  ...

  High-risk ClickOps:
  <list of specific dangerous manual changes with evidence>

  Why is this happening?
  <patterns: gaps in automation, incident hotfixes, shadow IT, etc.>
```

**Section 4: Tool Sprawl Assessment**

```
Resources by Tool Count:
  1 tool:   XXX resources  (XX%)
  2 tools:  XXX resources  (XX%)
  3+ tools: XXX resources  (XX%)

Top Conflict Zones:
  <table of multi-tool resources with risk>

Cost of Sprawl:
  <honest assessment: is multi-tool a problem here, or is it clean separation?>
```

**Section 5: Conflict Timelines (top 10)**

For EACH conflict zone, the timeline:

```
### <resource-id> — XX changes, X tools

  Date        Tool        Actor              Event
  ──────────  ──────────  ─────────────────  ─────────────────────────
  Apr 02      Terraform   terraform-cloud    AuthorizeSecurityGroupIngress (443)
  Apr 05      Console     user/john.doe      AuthorizeSecurityGroupIngress (8080)
  Apr 06      Terraform   terraform-cloud    RevokeSecurityGroupIngress (8080)
  ...

  Pattern: <what the timeline reveals>
  Risk: <assessment>
```

**Section 6: K8s Correlation (only if a cluster was connected)**

```
AWS Changes × Kubernetes Activity:
  <correlations between AWS and K8s events>
  <manual kubectl changes>
  <cross-system patterns>
```

**Section 7: Appendix — MANDATORY for every conflict zone and high-risk finding**

For EACH conflict zone resource and each high-risk ClickOps finding:

```
### <resource-id> — <one-line summary>

**What:** <what the resource is>
**Evidence:** <specific CloudTrail events>
**Impact:** <what could go wrong>
**Recommended action:** <bring under IaC / codify the change / etc.>
**Risk:** safe / review / dangerous
```

**Section 8: Deliverables + Reconstruction Recipe**

```
Published report (artifact): <durable url — .../artifacts/<artifact_id>>

Local copies:
  change-audit/scores/ops-posture.json   ← machine-readable posture score
  change-audit/reports/report-<ts>.md    ← local copy of the published report

To investigate a specific resource after this audit, re-run:
  run_cloud_cli(
    integration_name="<chosen>",
    command="cloudtrail lookup-events --lookup-attributes AttributeKey=ResourceName,AttributeValue=<resource-id> --max-results 50"
  )
```

Tell the user:
- "Report published as an artifact — open it here: `<durable url>`. This link is shareable with your team or can be attached to a ticket."
- "To investigate a specific resource, re-run the `run_cloud_cli` recipe in Section 8 with the resource ID."
- "Score saved to `change-audit/scores/ops-posture.json` — re-run this skill periodically to track improvement; the artifact versions automatically so you can compare runs."

If you stood up a team of background investigators, shut it down once the report is done.

---

## What You Never Do

- **Never modify CloudTrail, IAM, or any AWS resource** — this skill is read-only audit (the `cloud_cli` MCP enforces this too).
- **Never run `aws`, `kubectl`, or `helm` directly via bash** — all cloud/k8s reads go through `run_cloud_cli` / `run_k8s_cli`.
- **Never investigate yourself when a subagent mechanism exists** — delegate; only run investigators inline as the no-subagent fallback.
- **Never skip the devil's advocate** — every finding must be confirmed.
- **Never present before the report passes the Step 7 checklist.**
- **Never count AWS service events as team automation** — EKS creating ENIs is not your IaC.
- **Never call tagging "infrastructure management"** — be honest about what IaC covers.
- **Never name any product** — the gaps speak for themselves.
