## Tool & Workflow Preferences


- **Bitbucket code search**: Use MCP server `user-bitbucket4` (not `user-bitbucket-cloud`). Workspace = `commerceiq`. Tool = `search_code` with `query` + `workspace` (no repoSlug — code search is workspace-level only). `user-bitbucket-cloud` returns 404 for `search_code`. (AGENTS.md, journal-ciq-etl-ingestion-role-programmer)
- **Finding table/workflow consumers**: Run `search_code` with table name, qualified name, and workflow name. Check athena_alertmodulusconfig for alert SQL configs.
- **Bitbucket `search_repositories`**: Filter `q` param requires **spaces around operators**: `name ~ "value"` (not `name~"value"`). Missing spaces → 400.
- **Bitbucket `merge_pull_request`**: Request body key must be `merge_strategy`, not `type`.
- **dbx-dev queries prod system tables**: `system.compute.warehouses`, `system.query.history`, and `system.billing.usage` are synced from prod into dbx-dev. Use dbx-dev MCP to query prod warehouse metadata and costs without prod access.

- **Atlassian MCP endpoint deprecation**: HTTP+SSE (`https://mcp.atlassian.com/v1/sse`) deprecated after 2026-06-30; migrate to Streamable HTTP `https://mcp.atlassian.com/v1/mcp`.

- - **Jira API v3 via Atlassian MCP**: Pass markdown directly as string for description — MCP handles markdown-to-ADF. Do NOT pass raw ADF objects.