# system-design-skills

## Transaction Management Principles

### Keep Critical Sections Lean
- **Principle**: Only database writes should be in transactions, not reads
- **Practice**: Don't annotate entire entry points (like `createPage`) that do significant reads before writes
- **Implementation**: Use `@Transactional` on named methods instead of `TransactionTemplate` lambdas for cleaner code
- **Pattern**: Extract transactional methods to a separate service component (`PersonalizationTransactionalService`) to avoid self-injection issues and maintain clear separation

### Transaction Propagation Strategy
- Use `Propagation.MANDATORY` for mutating methods - ensures they're always called within an existing transaction
- Examine read methods separately - they may not need transaction scope
- Use `Propagation.REQUIRED` (default) for methods that can create or join transactions

### Transaction Boundary Design
- Stage data (preload templates, static configs) **outside** transaction boundaries
- Keep transaction critical section as lean as possible - only DB inserts/updates
- Move all asynchronous side-effects (instrumentation, cache clears, LLM insights) to post-commit processing

