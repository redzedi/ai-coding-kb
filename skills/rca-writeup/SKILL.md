---
name: rca-writeup
description: Draft, adversarially review, and publish a rigorous RCA/technical investigation doc (Confluence + Jira) for cross-team circulation.
---

# RCA writeup

Use this when Suman asks to turn an investigation into a shareable RCA, cost-spike writeup, or similar cross-team technical doc — especially one that will be "rigorously reviewed" by other teams (data platform, CCP, app teams, etc.) and needs to be watertight.

## 1. Draft structure

Use this section skeleton (rename headers to fit the specific investigation, but keep the shape):

1. **Problem statement & scope** — what it is, headline impact figures (cost/time/whatever), and a one-line framing of what actually caused the headline number vs. what's just a pre-existing/contributing condition.
2. **Timeline** of the key event — a table of dates/times, with real clickable evidence links where possible (actual run URLs, not descriptions).
3. **Contributing/pre-existing factors**, kept clearly separate from the acute trigger event, so causal weight isn't muddled.
4. **Root cause** via five-whys or an equivalent causal chain. It's fine — good, even — for the last "why" to end in "not determined."
5. **Explicit Limitations section.** State plainly what could not be determined, and what was checked-and-ruled-out vs. never investigated. A named limitations section is more credible than a doc that quietly omits the gap.
6. **Recommendations**, organized on a spectrum, not a flat list: **Prevention** (eliminates a known cause outright) → **Risk reduction** (lowers probability/severity, no guarantee) → **Mitigation** (accepts recurrence, caps cost) — plus a **Process** bucket for detection/monitoring gaps the investigation surfaced, and a separate **Functional issues found** bucket for real bugs that are out of scope of the RCA's actual question.
7. Recommendation items go in **tables**: `# | Description | Jira ref | Status`. Link every existing ticket; mark missing ones "Not yet raised."

**Leanness:**
- Push detailed evidence trails, retracted theories, and methodology caveats into a **separate companion doc**, linked from the main RCA. Keep the main doc a clean, current statement of findings — not an audit trail of how you got there.
- Sourcing/attribution detail (exactly how a number was computed) goes in a **footnote/Notes section at the bottom**, not an inline paragraph breaking up the main narrative.
- Don't restate the same number's derivation in two places with different confidence levels — reconcile or drop one.

**Verifiability:**
- Every claim should be independently traceable. Prefer real links over descriptions: construct Databricks run URLs as `<workspace-host>/jobs/<job_id>/runs/<run_id>?o=<workspace_id>` — ask the user for the workspace host/job_id if unknown, never guess a URL.
- State your verification method explicitly (e.g. "every run ID cross-checked via table X join, independent of the query that surfaced it").
- Sub-designs (an LLD for a specific fix) belong on a **Confluence child page**, not flattened into the RCA — link it from the relevant recommendation row.
- If you need a repo/branch reference and the repo is cloned locally, prefer `git remote -v`/`git fetch`/`git show` over an MCP tool that may unreliably 404 on a real repo.

## 2. Adversarial review — do not skip

Before publishing, run the draft through a `reviewer` subagent (via the Agent tool) and do not publish until it returns an explicit PASS.

- Give the reviewer the draft **and every source document** it was distilled from (raw investigation log, corrections/retractions doc, supporting analysis). It needs to trace every claim back to a source, not just judge plausibility.
- Ask it explicitly to check: factual consistency of every number/date/ID against sources; claims stated more strongly than sources support; whether "retracted/uncertain" items in sources are correctly NOT asserted as fact in the draft; whether a hostile domain-expert reader would find an easy hole.
- On every re-submission after a fix, give the **full context again**, not just the diff, and ask for a full fresh pass — a reviewer told to only check the fix will miss regressions introduced elsewhere in the same edit round.
- Iterate fix → re-review until PASS. When a reviewer flags a specific factual claim, the right fix is to **re-verify against the live source system**, not just re-word the claim more cautiously.
- Expect this to take several rounds on a real doc — that's the loop working, not a sign something is wrong.

## 3. Publish

- **Confluence**: create as a child page of the relevant tracker/parent page (get `spaceId`/`parentId` from the parent via `getConfluencePage`). Pass the actual markdown content as the `body` string — **shell substitution like `$(cat file)` does NOT work inside tool-call parameters**; read the file and paste its contents. Fetch the page back afterward to confirm it rendered as intended.
- **Jira**: check `getJiraIssueTypeMetaWithFields` before assuming a `priority` field is settable — not every project exposes one on the create screen. Some projects require an explicit assignee (look up the account ID via `lookupJiraAccountId`) even when you didn't intend to set one. Every ticket description should **link back to the wiki page**, and the wiki's recommendation table row should link forward to the ticket — bidirectional linking, not just one direction.
- Only raise tickets for the specific items asked for — if the user excludes one recommendation item from ticket creation, leave its Jira-ref cell as "Not yet raised" rather than silently including it.

See memory entries `rca-review-loop`, `rca-doc-structure`, `atlassian-mcp-quirks`, and `bitbucket-mcp-quirks` for more detail and the worked example this skill was extracted from (`automation-resolve-wf-rca`).
