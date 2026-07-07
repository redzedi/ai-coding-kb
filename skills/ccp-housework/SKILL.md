---
name: ccp-housework
description: >-
  Post-validation housework for CCP cost optimization. Handles version bumps in
  buildconfig.yaml and module YAMLs, unit test scaffolding, PR creation
  following common-skills conventions, and Confluence wiki page creation
  documenting the optimization with problem statement, changes, expected vs
  observed gains, and beta evidence.
---

# CCP Housework

## When to Use
- After the A/B comparison passes (PROCEED verdict) and Suman approves
- When @analyst or the uber orchestrator needs to finalize a cost optimization change
- Do NOT use before comparison validation is complete

## Prerequisites
- The comparison report from /ccp-ab-compare with PROCEED verdict
- The original cost optimization analysis doc
- The LLD document with implementation details
- Access to the code repo (feature branch with changes)
- `common-skills` skill for git/PR conventions
- MCP: `plugin-atlassian-atlassian` for Confluence page creation
- MCP: `user-bitbucket4` for PR creation (if using Bitbucket)

## Phase 1: Version Updates
Check if version bumps are needed:

**For PySpark modules:**
- Read `buildconfig.yaml` — check if `version` needs incrementing
- Read the module YAML under `ccp-configs/pyspark/<module>/<module>.yaml` — update `pysparkExecutableConfig.version` to match
- Follow semantic versioning: patch bump for optimization-only changes (e.g., `0.1.0` → `0.1.1`)

**For Spark (Java) modules:**
- Update `executableConfig.version` in the module YAML
- If the code repo uses Maven, update `pom.xml` version accordingly (see `wf-java-stack` journal for multi-module version chain updates)

**For SQL modules:**
- No version bump needed — VTL files are deployed directly via `ccp link`

## Phase 2: Unit Tests
Assess whether unit tests are needed for the changes:

**For SQL (VTL) changes:**
- VTL templates don't typically have unit tests — the beta A/B comparison serves as the functional test
- Document in the PR description that functional equivalence was validated via bidirectional EXCEPT in beta

**For PySpark/Spark code changes:**
- Check existing test patterns in the code repo (`tests/`, `src/test/`)
- Add or update tests that cover the changed logic
- Run existing tests to confirm no regressions:
  ```bash
  # PySpark
  pytest tests/ -v

  # Java/Spark
  mvn test -pl <module>
  ```

## Phase 3: Commit and PR
Follow `common-skills` conventions:

1. Stage all changes:
   ```bash
   git add -A
   git status  # verify only expected files are staged
   ```

2. Commit with Jira ticket prefix:
   ```bash
   git commit -m "<JIRA-ID>: <brief description of optimization>"
   ```

3. Push the feature branch:
   ```bash
   git push origin <feature-branch>
   ```

4. Create PR via Bitbucket:
   - Title: `<JIRA-ID>: <optimization description>`
   - Description should include:
     - Problem: monthly cost, waste %
     - Changes: what was modified and why
     - Evidence: link to comparison report, key metrics (runtime delta, functional equivalence)
     - Rollback: how to revert (revert the commit, re-link master)
   - Reviewers: ask Suman who to add

## Phase 4: Confluence Wiki Page
First, ask Suman whether a wiki page is needed using `AskUserQuestion`:
```
"The optimization is validated and PR is raised.

Do you need a Confluence wiki page for this optimization?
If yes, please provide the parent page link (e.g., 'https://boomerang.atlassian.net/wiki/spaces/MLE/pages/12345/Cost+Optimization+Results')."
```

If Suman says no wiki page is needed, skip this phase entirely and proceed to Phase 5.

If yes, create the page via Atlassian MCP (`createConfluencePage`) under the specified parent:

**Page title:** `<Workflow Name> — Cost Optimization: <Brief Description>`

**Page content structure (use markdown — MCP handles conversion):**

```markdown
# <Workflow Name> — Cost Optimization

## Problem Statement
- Monthly cost: $X/month
- Key waste finding: [from analysis doc executive summary]
- Affected workflow: <name>, triggered by <upstream>, runs <N> times/day

## Proposed Changes

### Recommendation: <title>
- **Type:** code / config / architecture
- **Description:** [from LLD doc]
- **Expected gain:** X% runtime reduction, $Y/month savings

### Code Changes
[Brief description of what was changed, with before/after snippets if helpful]

## Beta Validation Evidence

### Test Parameters
- Client ID: <id>
- Date range: <range>
- Environment: AWS_BETA

### Functional Equivalence
- Method: Bidirectional EXCEPT on all output tables
- Result: PASS — zero row differences across all tables

### Performance Results
| Metric | Feature Branch | Master Branch | Delta |
|---|---|---|---|
| Runtime | X min | Y min | -Z% |
| Est. DBU Cost | $A | $B | -$C |

Expected gain: X%
Observed gain: Y%
Assessment: ALIGNED

### Query Profile Analysis
[If available: key physical plan improvements — scan reduction, shuffle elimination, etc.]
[If not: "Profile analysis pending"]

## Implementation
- PR: [link to PR]
- Jira: [link to Jira ticket]
- Branch: <feature-branch>

## Rollback Plan
- Revert the PR commit
- Re-link master branch to CCP beta/prod
- No data migration needed (output tables are regenerated each run)

## Next Steps
- [ ] PR review and merge
- [ ] Monitor first prod run after deployment
- [ ] Validate prod cost reduction after 1 week
```

## Phase 5: Update Jira
Update the Jira ticket with:
- Status: move to "In Review" or appropriate status
- Add comment with PR link and comparison report summary
- Attach or link to the Confluence page

## Key Gotchas
- Always follow `common-skills` branching conventions — feature branches from `develop-occ` or `develop`
- Commit prefix must include Jira ticket ID: `BIPLATFORM-500: optimize self-join in competition_look_back`
- Never disable tests without Suman's explicit approval
- For Java repos: run `jenv local 1.8` separately before Maven commands (do NOT combine in one shell line)
- Use `claude-analysis/` as the work directory (not `cursor-analysis/`)
- The Confluence page is Suman's primary pitch material — make it clear, data-driven, and visually structured
