## java coding best practices

- **Mockito matchers**: ALL arguments in a mocked call must use matchers — cannot mix raw values with `anyX()`. Use `eq("string")` for literal args.
- 
- **Fallback with string replacement**: Never use `.replace(exactSqlSnippet, "")` as fallback — brittle against whitespace/formatting changes. Short-circuit with `return Collections.emptyList()` when preconditions guarantee zero results.
- **Redis set() exception handling**: Wrap Redis `set()` calls in try-catch: `try { redisTemplate.opsForValue().set(...); } catch (Exception e) { LOG.warn(...); }`.
- **`Thread.currentThread().getId()` deprecated**: Prefer `threadId()` in newer JDKs.