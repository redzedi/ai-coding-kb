# Praxis Task DAG (AGENTS.md block for codex-style agents)

- For multi-step, gated, hours-to-weeks outcomes (PRD -> feature -> PR ->
  deploy, cloud migrations), use the Praxis task-DAG substrate. Single-session
  tasks: just do them.
- The ONLY interface is the MCP passthrough: `praxis mcp task_dag <fn> --body '<json>'`.
  There are no `dag` CLI verbs.
- Discover and start: `praxis mcp task_dag list_templates --body '{}'`, then
  `praxis mcp task_dag create_run --body '{"template_id": "...", "params": {...}, "idempotency_key": "..."}'`.
- Progress: `praxis mcp task_dag list_runs --body '{}'` and
  `praxis mcp task_dag get_dag --body '{"run_id": "..."}'`. Report conversationally;
  never surface nodes/claims/leases/verdicts unless asked.
- Human gates: relay yes/no via `praxis mcp task_dag approve --body '{...}'` or
  `praxis mcp task_dag reject --body '{...}'` (feedback lands on the attempt).
- Take a step: `praxis mcp task_dag own_node --body '{"run_id": "...", "node_id": "...", "mode": "manual"}'`
  (peek first with `praxis mcp task_dag next_node --body '{}'`). The work packet's
  brief + output_schema is the whole contract; heartbeat long work with
  `praxis mcp task_dag heartbeat --body '{...}'`.
- Before completing: fetch `praxis mcp task_dag judge_packet --body '{...}'`, judge
  your result with a FRESH empty-context subagent (criteria + result +
  artifacts only — never your transcript), fix `missing[]`, iterate up to
  max_iterations, then submit ONCE via
  `praxis mcp task_dag complete_node --body '{"run_id": "...", "node_id": "...", "envelope": {...}}'`.
- Rollback only on an explicit human decision:
  `praxis mcp task_dag rollback --body '{"run_id": "...", "target_node": "..."}'`.
