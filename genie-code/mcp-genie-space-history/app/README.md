# Genie Space History MCP — server (`app/`)

Production server for the Genie Space History MCP, deployed on **Databricks Apps**
and mounted at **`/mcp`** over stateless streamable HTTP. It persists the artifacts
the `genie-code/` skills emit to governed **Unity Catalog Delta tables** and serves
them back. The MCP **never calls the Genie API** — it only touches UC (Option A).

This is the **P1 (write + read)** slice. The immutable P0 spike lives alongside in
[`../spike/`](../spike); the authoritative design is
[`../../genie-space-history-mcp-design.md`](../../genie-space-history-mcp-design.md).

## What ships in P1

Four MCP tools (spec §6), all running **On-Behalf-Of-User (OBO)**:

| Tool | Purpose | Writes |
| --- | --- | --- |
| `save_config_snapshot` | Persist a Space config version (the rollback-critical snapshot). Server computes a monotonic per-`space_id` `version`, a sha256 `config_hash`, stores the caller's `etag` verbatim, sets lineage via `parent_config_version_id`. | `config_snapshots` |
| `save_report` | Persist a Markdown artifact, routed by `artifact_type` (`diagnose_report` / `query_report` / `design_proposal` / `metric_view_ddl`); unknown types rejected; `redacted` defaults to `true`. | the routed report table |
| `list_history` | Timeline for a Space — UNION across all artifact tables; optional `artifact_type` / `since` filters. | — |
| `get_artifact` | Resolve a `config_version_id` / `artifact_id` / `run_id` across all tables and return the full record. | — |

> `record_optimization_run` (P2) is **out of scope**, but `optimization_runs` /
> `eval_results` tables still exist and `list_history` / `get_artifact` span them.

## Module layout (`server/`)

```
server/
├── config.py        # env-driven Settings (spec §10)
├── errors.py        # structured scope_error / validation_error payloads (spec §5)
├── sql.py           # exec_sql + identifier quoting + Param/QueryResult adapter (spec §11)
├── schema.py        # DDL for the 7 tables + only_mine row-filter function (spec §7.1)
├── auth.py          # OBO (per-request user) vs app-SP WorkspaceClient builders (spec §5)
├── provisioning.py  # idempotent startup bootstrap: schema/tables/filter/ownership/grants
├── store.py         # UCTableStore — server-side bound params, versioning, dedupe, list/get
├── tools.py         # the four P1 MCP tools + OBO/error wrapping
├── app.py           # FastAPI + FastMCP mount at /mcp, CORS, OBO middleware, lifespan bootstrap
└── main.py          # uvicorn entrypoint (binds DATABRICKS_APP_PORT)
```

## Identity & auth (spec §5)

- **OBO for all reads/writes.** A fresh `WorkspaceClient` is built per request from
  the `X-Forwarded-Access-Token` header (never cached). `created_by` is stamped from
  `current_user.me()`; `created_at` is server-side (`current_timestamp()`).
- **App SP for bootstrap/admin only** — provisioning. Never the write actor for a
  user artifact; the server **never silently falls back to the SP** for a user write.
- On a missing token / disabled OBO / missing `sql` scope, tools return a structured
  `scope_error` telling the user to enable the `sql` scope (`OBO_ENABLED` is a feature
  flag for graceful degradation where OBO isn't enabled yet).

## Configuration (env — see `app.yaml`)

| Var | Meaning |
| --- | --- |
| `HISTORY_CATALOG` | **Pre-existing** UC catalog. The app **NEVER** creates it. |
| `HISTORY_OWNER_GROUP` | Durable account group that OWNS the schema/tables (survives app/SP deletion). |
| `HISTORY_GRANTEE` | User group granted `SELECT`/`MODIFY` for OBO reads/writes. |
| `SQL_WAREHOUSE_ID` | Warehouse all UC SQL runs on (bind a `sql-warehouse` app resource). |
| `CORS_ALLOW_ORIGINS` | Comma-separated workspace origin allowlist. |
| `HISTORY_USE_VARIANT` | Opt-in VARIANT JSON columns (default `false` → STRING; spec §7.1/§12 #3). |
| `OBO_ENABLED` | OBO feature flag (default `true`). |

The schema name is fixed at `genie_space_history`. `app.yaml` declares
`user_api_scopes: sql` (required, P0 finding F-6).

## Startup bootstrap (app SP, idempotent — spec §7.1/§10)

On startup inside a deployed App, the SP idempotently: creates the schema + all 7
tables (with `delta.enableRowTracking` + `delta.feature.allowColumnDefaults`), creates
`only_mine`, applies the row filter to each table, grants `HISTORY_GRANTEE`, keeps the
SP's own `SELECT`/`MODIFY`, then reassigns `OWNER TO HISTORY_OWNER_GROUP`. The
**catalog is never created**. Ownership reassignment **may fail** if the SP isn't a
member of the owner group — that is captured as a structured WARNING and startup
continues (an operator/metastore admin runs the one-time `OWNER TO`).

**Operator prerequisites the app cannot self-perform** (spec §10): grant the app SP
`USE CATALOG` + `CREATE SCHEMA` on `HISTORY_CATALOG`; create/join `HISTORY_OWNER_GROUP`;
confirm OBO is enabled in the Previews portal.

## Dev inner loop

```bash
cd genie-code/mcp-genie-space-history/app

# Tests (no live workspace needed — the SQL layer is mocked)
python -m pytest

# Lint + format check
uvx ruff check .
uvx ruff format --check .

# Typecheck (deps installed alongside pyright so imports resolve)
uvx --with databricks-sdk --with fastapi --with fastmcp --with "mcp[cli]" \
    --with pydantic --with uvicorn --with pytest pyright

# Run locally (uses your Databricks CLI default creds; OBO is App-only)
uvicorn server.app:app --port 8000
```

Self-serve / DABs packaging is **P4** (out of scope here).
