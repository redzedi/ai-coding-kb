## Behavioral — verify causal claims before concluding

Don't present a plausible root-cause mechanism as confirmed just because it fits the pattern so
far — check it against a specific counter-example, the exact config value, or a full-population
recomputation before stating it as settled. Suman reads carefully and reliably catches an
unverified leap; the reliable move is to front-load the verification, not let him find the gap.

**Origin**: ESM-6504 `workbench_v3_wf` Databricks cost investigation (2026-08-22,
`custom_brands_cubes` repo). This happened repeatedly in one session and was caught every time:
- "2.6x duplication factor" from a `COUNT(DISTINCT start_date, end_date)` query — turned out to be
  a restatement of an already-known avg-per-day stat, not new evidence (caught by `advisor()`).
- "Fan-out from N children causes duplicate SQS messages" — asserted without checking; direct log
  inspection showed every SQS message actually carried the *parent's* client ID, never a child's.
  Wrong mechanism entirely.
- "IST/UTC scheduler collision explains a single client's inflated trigger count" — Suman pushed
  back with "but if we consider any 1 region it should be 18" and was right: the two regions
  queried disjoint client lists, so the collision couldn't affect a single-region client's count
  at all.
- "Audit-log-tracker timeout→Lambda-retry causes a real duplicate trigger downstream" — plausible
  and half-right (true for one Lambda), but checking the *other* Lambda's actual
  `EventInvokeConfig` showed retries were explicitly disabled there — the same-sounding mechanism
  didn't apply, and the cost angle for that specific finding "went away" once checked.

**How to apply**:
1. Check the exact config value or code path involved (`get-function-event-invoke-config`,
   `get-policy`, the actual query result) rather than reasoning from what "should" be true
   architecturally or by analogy to a sibling resource.
2. Size on the full population when a number is going into a dollar figure, a ticket, or any
   externally-visible artifact — not a volume-biased sample, even if the sample was convenient to
   compute first. Present sample-based numbers explicitly as samples, with the bias direction
   named, until the full-population number is in hand.
3. When a new finding conflicts with an earlier one, say so explicitly and correct the earlier
   claim/doc/ticket rather than letting both stand unreconciled.
