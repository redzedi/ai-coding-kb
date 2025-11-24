# perf-optimization-skills


### Batch Loading Strategy
- **Pattern**: Use batch loading for frequently accessed data instead of individual queries
- **Example**: `findAllByWidgetIdIn(List<Integer>)` instead of multiple `findByWidgetId()` calls
- **Benefit**: Reduces database round trips significantly

### Redis Multi-Key Access
- **Pattern**: Use `multiGet()` for efficient bulk reads from Redis
- **Implementation**: Fetch multiple entries with a single Redis call, fall back to DB for misses, then asynchronously backfill Redis
- **Key Insight**: Cache individual entries with multi-key access, not entire lists as a unit

### Asynchronous Cache Backfill
- **Principle**: Never block on cache writes
- **Pattern**: Use `CompletableFuture.runAsync()` or dedicated thread pool for cache backfill operations
- **Benefit**: Keeps response times low while ensuring cache is populated for future requests

### Entity Reuse Pattern
- **Principle**: Reuse staged entities (Page, Widget) for instrumentation instead of re-querying
- **Pattern**: Pass persisted entities through the call chain to post-transaction async tasks
- **Benefit**: Eliminates redundant database lookups in instrumentation flows

### Preload Outside Transaction
- **Pattern**: Preload data (widget templates, static configs) before entering transaction
- **Benefit**: Keeps transaction duration minimal, improving concurrency and reducing lock contention
