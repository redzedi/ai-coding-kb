---
name: common-java-coding-skills
description: Java coding and project handling guidelines and best practices
---

# common-java-coding-skills

## When to Use

- Use this skill when developing in   java projects

## Instructions


- **Make contracts explicit**: Using DTOs to pass metadata between methods eliminates fragile assumptions and makes the code more maintainable.


- **Correct way to use jenv before running Maven:**
	1. Run `jenv local 1.8` as a **separate command first** - this sets up JAVA_HOME properly
	2. Then run Maven commands separately
	3. **Do NOT** attempt to set JAVA_HOME in the same command as Maven - it messes up the Java home
	4. If needed, use `eval "$(jenv init -)"` to properly initialize jenv in the shell before setting the local version
	
	**Example:**
	```bash
	# Correct approach:
	jenv local 1.8
	mvn test
	
	# Or in a single command with initialization:
	eval "$(jenv init -)" && jenv local 1.8 && mvn test
	```


- **Critical rule:** When using Mockito matchers, **ALL arguments** in a method call must use matchers - you cannot mix raw values with matchers.

	**Incorrect:**
	```java
	when(mock.method("string", anySet(), "other", "value"))
	```
	
	**Correct:**
	```java
	when(mock.method(eq("string"), anySet(), eq("other"), eq("value")))
	```
	
	This applies to both `when()` and `verify()` calls.


- When mocking `RedisTemplate<String, Object>`, the `HashOperations` returned by `opsForHash()` has the type:
	- `HashOperations<String, Object, Object>` ✅
	- NOT `HashOperations<String, String, Object>` ❌
	
	The second generic parameter matches the RedisTemplate's value type (Object), not String.
	
	**Example:**
	```java
	HashOperations<String, Object, Object> hashOps = mock(HashOperations.class);
	when(redisTemplate.opsForHash()).thenReturn(hashOps);
	when(hashOps.get(anyString(), any())).thenReturn(null);  // Note: any() not anyString()
	```


- When comparing Integer values in JUnit tests:
	- If the getter returns a primitive `int`, use: `assertEquals(1, result.getDefaultId())`
	- If it returns `Integer`, be aware of potential ambiguity between `assertEquals(long, long)` and `assertEquals(Object, Object)`
	- Prefer direct primitive comparison when possible to avoid ambiguity



- **Important:** Never create `.m2` folder in project directory - it pollutes the git repository.

	- Always use the default Maven repository at `$HOME/.m2`
	- Remove any `.m2` folders created in project directories: `rm -rf dashboard-config-service/.m2`
	- Add `/.m2/` to `.gitignore` to prevent accidental commits
	- Run Maven commands directly without `-Dmaven.repo.local=.m2` flag
	- The default `$HOME/.m2` repository should be used always


- **Logback Configuration:**
	- Never commit user-specific paths in `logback.xml` (e.g., `/Users/username/projects/...`)
	- Use standard paths (e.g., `/var/logs/dashboard_config_service/application.log`)
	- Check the target branch (e.g., `develop-occ`) for the correct version: `git show develop-occ:path/to/logback.xml`
	

- **Pattern**: Use batch loading for frequently accessed data instead of individual queries
	- **Example**: `findAllByWidgetIdIn(List<Integer>)` instead of multiple `findByWidgetId()` calls
	- **Benefit**: Reduces database round trips significantly

- **Pattern**: Use `multiGet()` for efficient bulk reads from Redis
	- **Implementation**: Fetch multiple entries with a single Redis call, fall back to DB for misses, then asynchronously backfill Redis
	- **Key Insight**: Cache individual entries with multi-key access, not entire lists as a unit

- **Principle**: Never block on cache writes
	- **Pattern**: Use `CompletableFuture.runAsync()` or dedicated thread pool for cache backfill operations
	- **Benefit**: Keeps response times low while ensuring cache is populated for future requests

- **Principle**: Reuse staged entities (Page, Widget) for instrumentation instead of re-querying
	- **Pattern**: Pass persisted entities through the call chain to post-transaction async tasks
	- **Benefit**: Eliminates redundant database lookups in instrumentation flows

- **Pattern**: Preload data (widget templates, static configs) before entering transaction
	- **Benefit**: Keeps transaction duration minimal, improving concurrency and reducing lock contention
- **Principle**: Only database writes should be in transactions, not reads
- **Practice**: Don't annotate entire entry points (like `createPage`) that do significant reads before writes
- **Implementation**: Use `@Transactional` on named methods instead of `TransactionTemplate` lambdas for cleaner code
- **Pattern**: Extract transactional methods to a separate service component (`PersonalizationTransactionalService`) to avoid self-injection issues and maintain clear separation

- Use `Propagation.MANDATORY` for mutating methods - ensures they're always called within an existing transaction
	- Examine read methods separately - they may not need transaction scope
	- Use `Propagation.REQUIRED` (default) for methods that can create or join transactions

- Stage data (preload templates, static configs) **outside** transaction boundaries
- Keep transaction critical section as lean as possible - only DB inserts/updates
- Move all asynchronous side-effects (instrumentation, cache clears, LLM insights) to post-commit processing

