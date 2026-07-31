# Genie Agent Versioning MCP v2

This Databricks App is a prompt-routed configuration version store for Genie Agents. It
exposes stateless streamable HTTP at `/mcp`, stores complete caller-supplied configuration
envelopes in Unity Catalog, and never reads or updates a live Genie Agent.

Genie Code remains responsible for reading the live configuration, saving it here before
an edit, stopping if that save fails, and applying edits or rollbacks with native tools.

## MCP tools

| Tool | Purpose |
| --- | --- |
| `save_agent_config_version` | Append a complete snapshot. Every successful call creates a new version, including identical content. |
| `list_agent_versions` | List one Agent's private history with deterministic cursor pagination. |
| `get_agent_version` | Retrieve one complete version using both `space_id` and `version_id`. |

`save_agent_config_version.config` must include these keys:

```json
{
  "serialized_space": "{...}",
  "title": "Agent title",
  "description": "Description or null",
  "warehouse_id": "warehouse-id",
  "parent_path": "/Workspace/path or null",
  "etag": "optional capture-time etag"
}
```

The five outer restore fields must be present even when a nullable value is `null`.
Additional JSON-safe configuration fields are preserved. The server adds `format_version`
and `space_id`, bounds the envelope to 5 MiB by default, and hashes canonical restore
content without the historical `etag`.

The optional `parent_version_id` records lineage. A `before_rollback` save must include a
visible, same-Agent `rollback_target_version_id`. The etag returned by
`get_agent_version` is historical provenance only; use a freshly read live etag to apply a
rollback.

## Architecture and security

- FastAPI + FastMCP on Databricks Apps, served by uvicorn.
- App identity provisions the schema, migration ledger, table, row filter, and grants.
- Every tool read/write runs as the calling user through OBO SQL.
- The only user OAuth scope is `sql`; the tool path makes no identity or Genie API call.
- A Unity Catalog row filter enforces `created_by = SESSION_USER()`, so histories are
  private per user even when users collaborate on the same Agent.
- `/healthz` is process liveness. `/readyz` returns HTTP 503 until migration, filtering,
  and required grantee table access succeed.
- Legacy v1 tables are never dropped or modified.

## Deploy a test App on Databricks

The deployment choices are FastAPI, combined app/user authorization, one SQL warehouse
resource, Unity Catalog managed tables, and the Databricks CLI deployment path.

### 1. Prerequisites

You need:

- Databricks CLI 1.x configured for the target workspace.
- Permission to create and manage a Databricks App.
- A running SQL warehouse.
- A pre-existing Unity Catalog catalog with managed storage.
- An account-level group containing the test users, for example
  `genie_versioning_testers`.
- A catalog owner or metastore administrator who can grant the initial catalog privileges.
- Databricks Apps user authorization enabled for the workspace.

Confirm the installed CLI and its current command syntax:

```bash
databricks --version
databricks apps -h
databricks apps create -h
databricks apps deploy -h
```

### 2. Create the App and identify its service principal

App names used by Genie Code should start with `mcp-`:

```bash
databricks apps create --name mcp-genie-agent-versioning-test \
  --json '{"description":"Test Genie Agent configuration version store"}'
databricks apps get mcp-genie-agent-versioning-test
```

If your CLI's `create -h` shows a positional name instead, use that form. Copy the App
service principal identity from the command output or the App's configuration page.

### 3. Grant the bootstrap prerequisites

As a catalog owner, run the following in a SQL editor. Use the exact App service principal
and account-group names:

```sql
GRANT USE CATALOG ON CATALOG <catalog> TO `<app-service-principal>`;
GRANT CREATE SCHEMA ON CATALOG <catalog> TO `<app-service-principal>`;

GRANT USE CATALOG ON CATALOG <catalog> TO `genie_versioning_testers`;
```

The last grant must be completed before setting
`HISTORY_GRANTEE_USE_CATALOG_CONFIRMED=true`. The App owns the schema it creates and will
grant the tester group `USE SCHEMA` plus `SELECT, MODIFY` only on the row-filtered version
table. It does not need `MANAGE` on the catalog.

For an upgrade that reuses an existing schema, the existing schema owner must additionally
allow the App service principal to create the v2 table/function and manage their grants, or
perform the migration as the owner.

### 4. Configure `app.yaml` and the SQL warehouse resource

Edit [`app.yaml`](app.yaml):

- Set `HISTORY_CATALOG` to the catalog from step 3.
- Leave `HISTORY_SCHEMA=genie_agent_versioning` for a fresh test.
- Set `HISTORY_GRANTEE=genie_versioning_testers`.
- Set `HISTORY_GRANTEE_USE_CATALOG_CONFIRMED=true` after the grant in step 3.
- Set `CORS_ALLOW_ORIGINS` to the exact workspace origin, such as
  `https://dbc-xxxxxxxx-xxxx.cloud.databricks.com`.

In the App configuration page:

1. Add a **SQL warehouse** resource with key `sql-warehouse` and **CAN USE** permission.
2. Enable **User authorization** and approve the `sql` scope declared in `app.yaml`.
3. Give test users **CAN USE** on the App; reserve **CAN MANAGE** for trusted developers.

`SQL_WAREHOUSE_ID` uses `valueFrom: sql-warehouse`; do not replace it with a hardcoded ID.

### 5. Upload and deploy

Run these commands from this `app/` directory, replacing the workspace user path:

```bash
databricks workspace mkdirs \
  /Workspace/Users/<user-email>/apps/mcp-genie-agent-versioning-test

databricks workspace import-dir . \
  /Workspace/Users/<user-email>/apps/mcp-genie-agent-versioning-test \
  --overwrite

databricks apps deploy mcp-genie-agent-versioning-test \
  --source-code-path \
  /Workspace/Users/<user-email>/apps/mcp-genie-agent-versioning-test
```

Always include `--overwrite` on redeploy; otherwise changed workspace files may be skipped.

### 6. Verify provisioning and readiness

```bash
databricks apps get mcp-genie-agent-versioning-test
databricks apps logs mcp-genie-agent-versioning-test
```

Open the App URL while authenticated:

- `/healthz` should return `{"status":"healthy","check":"liveness"}`.
- `/readyz` should return HTTP 200 with `status: ready`.
- `/mcp` is the MCP endpoint; it is not a normal browser page.

If readiness returns 503, inspect its bootstrap report and the App logs. The usual causes
are a missing catalog/schema privilege, an incorrectly named account group, a row-filter
failure, or a SQL warehouse resource that is stopped or not bound with key
`sql-warehouse`.

### 7. Connect Genie Code and run a smoke test

Add a custom MCP server in Genie Code using:

```text
https://<app-url>/mcp
```

Add this user or workspace instruction:

> Before changing any Genie Agent configuration, first read its complete current
> configuration and save it with `save_agent_config_version` using reason
> `before_update` or `before_rollback`. Proceed only if the save succeeds. Use
> `list_agent_versions` and `get_agent_version` for rollback. If the MCP is unavailable
> or the save fails, stop without editing. For rollback, use a freshly read live etag,
> never the stored historical etag. Follow this rule even with Auto-Approve enabled.

Smoke-test in this order:

1. Ask Genie Code to list versions for a test Agent.
2. Ask it to make a harmless configuration edit and confirm a `before_update` version was
   saved first.
3. Save the same live configuration manually twice and confirm two version IDs with the
   same hash.
4. Ask for a rollback; confirm Genie Code saves the current state with
   `before_rollback`, retrieves the target, reads a fresh live etag, and then applies it.
5. Temporarily disconnect the MCP and verify Genie Code stops before a requested edit.

## Upgrade from v1

V2 is a breaking MCP tool-surface change. The v1 report, evaluation, and generic artifact
tools are no longer registered.

- To add v2 beside an existing deployment, explicitly set
  `HISTORY_SCHEMA=genie_space_history` before deploying.
- Bootstrap adds `agent_config_versions` and `schema_migrations`; it does not alter or drop
  the seven v1 tables.
- V1 snapshots generally contain only `serialized_space` and `etag`, so they cannot be
  promoted to rollback-ready v2 versions without the missing outer fields. They remain
  available as legacy partial records in `config_snapshots`.
- Fresh deployments default to `genie_agent_versioning`.
- Keep `TRANSFER_OWNERSHIP=false` while testing and while automatic migrations may still
  run. A production operator can enable a one-time transfer to a durable owner group after
  ensuring that owner will perform future migrations.

## Configuration

| Variable | Meaning |
| --- | --- |
| `HISTORY_CATALOG` | Pre-existing Unity Catalog catalog; the App never creates it. |
| `HISTORY_SCHEMA` | Target schema; defaults to `genie_agent_versioning`. |
| `HISTORY_GRANTEE` | Account group whose OBO users receive table access. |
| `HISTORY_GRANTEE_USE_CATALOG_CONFIRMED` | Operator confirmation that the group already has `USE CATALOG`. |
| `SQL_WAREHOUSE_ID` | SQL warehouse resource injected from `sql-warehouse`. |
| `CORS_ALLOW_ORIGINS` | Comma-separated workspace origin allowlist. |
| `OBO_ENABLED` | User-authorization feature flag; defaults to `true`. |
| `MAX_CONFIG_BYTES` | Maximum UTF-8 envelope size; defaults to 5 MiB. |
| `TRANSFER_OWNERSHIP` | Opt-in durable group ownership handoff; defaults to `false`. |
| `HISTORY_OWNER_GROUP` | Required only when ownership transfer is enabled. |

## Local verification

```bash
python3 -m pytest
uvx ruff check .
uvx ruff format --check .
uvx --with databricks-sdk --with fastapi --with fastmcp \
  --with "mcp[cli]" --with pydantic --with uvicorn --with pytest pyright
```

Local startup skips Databricks provisioning, so `/readyz` intentionally returns 503. Use
unit tests for the local loop and a deployed test App for OBO/readiness verification.
