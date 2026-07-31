# mcp-genie-agent-versioning

> **Implementation status:** the current app is the legacy v1 passive-history server.
> The authoritative design now specifies a focused v2 configuration version store.
> Genie Code remains responsible for native reads, edits, and rollback execution.

Home of the **Genie Agent Versioning MCP** server — the backend that persists the
artifacts the `genie-code/` skills emit (config snapshots, reports, optimization
runs) to governed **Unity Catalog Delta tables** and serves them back. It runs on
**Databricks Apps**, mounted at **`/mcp`** over stateless streamable HTTP, and runs
every read/write **On-Behalf-Of-User (OBO)**. Both v1 and the proposed v2 touch UC only
and never call the Genie API. The authoritative design lives one level up in
`../genie-agent-versioning-mcp-design.md`.

The current v1 server is in [`app/`](app). The **P1 (write + read)** slice and the
**P2 `record_optimization_run`** tool have shipped — five MCP tools in total
(spec §6): `save_config_snapshot`, `save_report`, `record_optimization_run`,
`list_history`, `get_artifact`.

## Contents

| Path | What |
|---|---|
| `app/` | The production MCP server: FastAPI + FastMCP package (`server/`) with the shipped P1/P2 tools and its test suite. See [`app/README.md`](app/README.md). |

See `../genie-agent-versioning-mcp-design.md` for the full design and `app/README.md`
for the server's module layout, auth model, and dev inner loop.
