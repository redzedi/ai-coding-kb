# Cross-graph wiring — built-in kinds + custom extractors

ig wires members together by extracting the **interfaces** they share (HTTP routes,
queues, topics, …). Two members that use the same interface on opposite sides get an
indicative catalog edge: `graph:A ──rel(kind, N)──▶ graph:B`. Run the wiring with
`ig build -routes` (or `ig routes -p <project>` to add it to an existing build).

## Built-in adapters (run automatically by the route pass)

| Adapter | Lang/framework | Side | Kind |
|---|---|---|---|
| `spring` | Java `@*Mapping` | provider | http (route) |
| `openapi-ts` | generated openapi-typescript client | consumer | http (route) |
| `fastapi` | Python `@app/@router.<verb>` | provider | http (route) |
| `python-client` | Python `_request(...)` / `client.get("/…")` | consumer | http (route) |
| `queue` | `.send/.publish` (out) + `@KafkaListener`/`@consume` (in) | both | queue |

The join is by **canonical key** (`route:GET /x`, `queue:orders`): both sides must emit
the *same* key. A consumer route with no matching provider is a dangling node, not an edge —
so extraction can be liberal; precision comes from the join.

## When a coupling is missing → write a custom extractor

If `ig catalog` doesn't show an edge you expect, first look at the route-pass output:
`routes <member>: +N interface nodes [adapter:count …]`. A member that shows **no adapter
matched** (e.g. a Go service, a gRPC link, a bespoke event bus) needs a **project-local
extractor** — a small script (any language) ig runs. No ig rebuild required.

### The workflow (all via `ig extractor`)

1. **See the contract:** `ig extractor spec` — prints the JSON I/O contract.
2. **Scaffold a template:** `ig extractor scaffold <name> -kind <queue|topic|grpc|pkg|custom>`
   → writes `./.ig/extractors/<name>.py` (a runnable template — this IS the interface to
   implement) and prints the manifest stanza.
3. **Edit** the PRODUCE/CONSUME (or provider/consumer) patterns for the project's convention.
4. **Validate:** `ig extractor test "python3 .ig/extractors/<name>.py" <member-src-dir>`
   → runs it and checks output conforms (`✓ contract OK: N hits …`).
5. **Declare it** in `<project>.ig.yaml` (the stanza from step 2):
   ```yaml
   connections:
     extractors:
       - {name: <name>, cmd: "python3 .ig/extractors/<name>.py", kind: <kind>}
   ```
6. **Wire it:** `ig routes -p <project>` — the extractor runs alongside the built-ins.

### The contract (what the script prints on stdout)

```json
[{"key":"<kind>:<identity>",   // canonical join key; bare "orders" → ig prefixes with kind
  "dir":"out"|"in",            // out = SENDS/CALLS/PRODUCES; in = RECEIVES/HANDLES/CONSUMES
  "symbol":"Class.method",     // enclosing code symbol — must match a graph node to resolve
  "file":"src/rel/path.py",    // path RELATIVE to the member src dir
  "line":42}, ...]
```

**The one discipline that makes it work:** both sides must produce the **identical** `key`.
Normalize identities the same everywhere (e.g. strip a topic prefix, collapse route params to
`{}`). If the producer emits `queue:order.created` and the consumer emits `queue:orders`, no
edge forms. When in doubt, `ig extractor test` both members and eyeball that the keys match.

## During onboarding

After the initial `ig build`, if the user expects a coupling the built-ins don't produce
(check the route-pass output + `ig catalog`), offer to author a custom extractor via the
workflow above — then `ig routes` to add the edges without a rebuild.
