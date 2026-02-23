# Journal: Maven library dependency version chain

**Date**: 2026-02-13  
**Milestone**: Lesson from athena_brands-modulus-service cubesdk update (BIPLATFORM-573)

## Rule to remember

When updating a **dependency reference** in a **library** module in a Maven multi-module (or multi-repo) project:

1. **Bump the library's own version** — changing what it depends on changes its effective API/build, so it must be reversioned.
2. **Update every consumer** of that library to the new version.
3. **If a consumer is itself a library**, bump its version and update *its* consumers.
4. Repeat until you reach the **top-level application**; update its dependency ref(s) and its own version.

Do not only change the leaf dependency (e.g. cubesdk in brands-api) without bumping brands-api and propagating through brands-commons → brands-service.

## Example chain (athena_brands-modulus-service)

- cubesdk → brands-api → brands-commons → brands-service

Updating cubesdk in brands-api implies: bump brands-api version, update brands-commons to new brands-api and bump brands-commons, update brands-service to new brands-commons and bump brands-service.

## Why it matters

- Without version bumps, consumers still point at the old library version and may not get the new transitive dependency.
- Without updating refs up the chain, the new library build is never used by the app.
- This pattern applies to any Maven project where library modules are consumed by other modules or services.
