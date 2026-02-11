# common-skills

## Code Organization Principles

### Minimal Change Principle
- **Principle**: Minimize changes to avoid regressions - don't alter flow too much
- **Practice**: When refactoring, maintain behavioral consistency
- **Guideline**: Only change what's necessary to achieve the optimization goal

### Follow Existing Patterns
- **Principle**: Always examine existing metrics/logic in the codebase to understand filtering and structure patterns
- **Practice**: Maintain consistency with established patterns (e.g., filtering logic in cube definitions)
- **Benefit**: Reduces risk of introducing bugs and makes code more maintainable

### Component Measures for Complex Calculations
- **Pattern**: Break down complex calculations into component measures first
- **Use Case**: When calculation involves raw table columns that aren't available as separate measures
- **Implementation**: Create component measures (e.g., `_numerator`, `_denominator`, `_base`), then use them in `aggregateColumnSource`

---

## Error Handling & Defensive Coding

### Instrumentation Defensive Coding
- **Pattern**: Add null checks and default values for entity fields that might not be populated yet
- **Example**: Provide default `0` values for `pageId`, `defaultId`, `parentId` when they are null in Widget objects
- **Rationale**: Instrumentation processes staged widgets that might not have all fields populated

### Null-Safe JSON Patching
- **Pattern**: Handle null or empty base JSON in patching operations
- **Implementation**: Return deep copy of patch object when base is null/empty
- **Use Case**: Cloned widgets might have null `uiDefaultConfig`

### Graceful Degradation
- **Pattern**: Log warnings and continue with partial data rather than failing completely
- **Example**: If widget not found during instrumentation, log warning and send partial instrumentation message
- **Benefit**: Ensures partial instrumentation messages are still sent even if some widgets are missing

---

## Data Flow Principles

### Post-Action Data Flow
- **Critical Principle**: Pass actual persisted entities to post-transaction actions, not pre-processed templates
- **Pattern**: Use result objects (e.g., `WidgetPersistenceResult`) to return `(request, persistedWidget)` tuples from transactional layer
- **Rationale**: Post-actions need the actual saved entities with all DB-populated fields (like auto-increment IDs)

### Response Building Outside Transaction
- **Pattern**: Transform entities to response objects outside transaction boundary
- **Benefit**: Keeps transaction lean and allows response building to use fully populated entities

### Async Task Queue Pattern
- **Pattern**: Use dedicated thread pool executor for async post-commit tasks
- **Implementation**: Task requests submitted as command objects, actual request prep and processing happens completely asynchronously
- **Benefit**: Fully decouples task submission from task execution, including preparation of SQS messages and cache keys
- **Future-proofing**: Can easily offload to external task queue (e.g., RabbitMQ) later


## Git Commit Management

### Common skills

- - **Branching conventions**: Following team conventions (syncing `develop-occ` with `master-dbx` before creating feature branches) prevents merge conflicts and keeps branches aligned.


### Combining Multiple Commits

When you have multiple related commits (e.g., implementation + test additions) that should be combined:

**Method 1: Using git reset --soft (Recommended for combining recent commits)**
```bash
# Combine last N commits into one
git reset --soft HEAD~N
git commit -m "RIQ-XXXX: Combined commit message"
```

**Method 2: Using interactive rebase**
```bash
# Mark commits as squash in interactive rebase
git rebase -i HEAD~N
# Edit the rebase file to mark commits as 'squash'
git rebase --continue
```

### Commit Message Requirements

- All commits must have ticket prefix (e.g., `RIQ-1325:`) for Bitbucket pre-receive hooks
- Combine test-only commits with their related implementation commits when possible
- Use descriptive commit messages that explain both what and why

## Pull Request Structure

When creating PRs, include these sections:

1. **Problem Statement**: Clear description of the performance/latency issue observed
2. **Root Causes**: Enumerate the technical root causes (e.g., DB transactions per widget, no caching, single entity reads)
3. **Summary of Changes**: 2-3 line high-level summary of all changes (not just the latest commit)
4. **Notable Classes**: 2-3 classes where most changes occurred, with brief one-line descriptions of changes
5. **Future Changes**: Section left for reviewer/author to add follow-up items

**Key Insight**: Review commit history to understand full scope of changes, not just the most recent commit.




