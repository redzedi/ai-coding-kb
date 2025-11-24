# common-java-coding-skills

## jenv Usage Pattern

**Correct way to use jenv before running Maven:**
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

## Mockito Matcher Rules

**Critical rule:** When using Mockito matchers, **ALL arguments** in a method call must use matchers - you cannot mix raw values with matchers.

**Incorrect:**
```java
when(mock.method("string", anySet(), "other", "value"))
```

**Correct:**
```java
when(mock.method(eq("string"), anySet(), eq("other"), eq("value")))
```

This applies to both `when()` and `verify()` calls.

## ConfigType Enum Behavior

In this codebase, the `ConfigType` enum's `getConfigType()` method returns **lowercase strings** ("widget", "page"), not the uppercase enum constant names.

When mocking or verifying calls that use `ConfigType.WIDGET.getConfigType()`, use the lowercase string "widget" in the matchers:

```java
when(helper.getStaticConfigs("client", 1, "widget", "clientName"))  // lowercase!
```

## Redis Template Mocking

When mocking `RedisTemplate<String, Object>`, the `HashOperations` returned by `opsForHash()` has the type:
- `HashOperations<String, Object, Object>` ✅
- NOT `HashOperations<String, String, Object>` ❌

The second generic parameter matches the RedisTemplate's value type (Object), not String.

**Example:**
```java
HashOperations<String, Object, Object> hashOps = mock(HashOperations.class);
when(redisTemplate.opsForHash()).thenReturn(hashOps);
when(hashOps.get(anyString(), any())).thenReturn(null);  // Note: any() not anyString()
```

## JUnit assertEquals with Integer Types

When comparing Integer values in JUnit tests:
- If the getter returns a primitive `int`, use: `assertEquals(1, result.getDefaultId())`
- If it returns `Integer`, be aware of potential ambiguity between `assertEquals(long, long)` and `assertEquals(Object, Object)`
- Prefer direct primitive comparison when possible to avoid ambiguity

## Maven Repository Management

**Important:** Never create `.m2` folder in project directory - it pollutes the git repository.

- Always use the default Maven repository at `$HOME/.m2`
- Remove any `.m2` folders created in project directories: `rm -rf dashboard-config-service/.m2`
- Add `/.m2/` to `.gitignore` to prevent accidental commits
- Run Maven commands directly without `-Dmaven.repo.local=.m2` flag
- The default `$HOME/.m2` repository should be used always

## Configuration File Management

**Logback Configuration:**
- Never commit user-specific paths in `logback.xml` (e.g., `/Users/username/projects/...`)
- Use standard paths (e.g., `/var/logs/dashboard_config_service/application.log`)
- Check the target branch (e.g., `develop-occ`) for the correct version: `git show develop-occ:path/to/logback.xml`
