# mcp-genie-space-history

Home of the **Genie Space History MCP** server — the backend that persists the
artifacts the `genie-code/` skills emit (config snapshots, reports, optimization
runs) to governed **Unity Catalog Delta tables** and serves them back. It runs on
**Databricks Apps**, mounted at **`/mcp`** over stateless streamable HTTP, and runs
every read/write **On-Behalf-Of-User (OBO)**. Under Option A it touches UC only — it
**never calls the Genie API**. The authoritative design lives one level up in
`../genie-space-history-mcp-design.md`.

The production server is in [`app/`](app). The **P1 (write + read)** slice and the
**P2 `record_optimization_run`** tool have shipped — five MCP tools in total
(spec §6): `save_config_snapshot`, `save_report`, `record_optimization_run`,
`list_history`, `get_artifact`.

## Contents

| Path | What |
|---|---|
| `app/` | The production MCP server: FastAPI + FastMCP package (`server/`) with the shipped P1/P2 tools and its test suite. See [`app/README.md`](app/README.md). |
| `RUNBOOK.md` | Operator runbook for the `app/` server: app-SP grants, deploy (`databricks sync` + `databricks apps deploy`), OBO scopes, smoke test, and the Genie-Code connect step. |
| `FINDINGS.md` | Historical record: the P0 de-risking findings that resolved the design's §12 runtime residuals before the server was built. |

See `../genie-space-history-mcp-design.md` for the full design and `app/README.md`
for the server's module layout, auth model, and dev inner loop.
