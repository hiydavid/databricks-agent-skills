# Genie Agent Versioning MCP

This Databricks App is a prompt-routed configuration version store for Genie Agents. It
exposes stateless streamable HTTP at `/mcp`, stores complete caller-supplied configuration
envelopes in Unity Catalog, and never reads or updates a live Genie Agent.

Genie Code remains responsible for reading the live configuration, saving it here before
an edit, stopping if that save fails, and applying edits or rollbacks with native tools.
The contract and responsibility boundary are documented in
[`../genie-agent-versioning-mcp-design.md`](../genie-agent-versioning-mcp-design.md).

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

Retrieve this object with Get Genie Agent using `include_serialized_space=true` and pass
the returned `serialized_space` string exactly. A summary, benchmark result, pass rate, or
other progress metadata is not a restorable snapshot and is rejected. The parsed string
must contain the exported Genie fields `version`, `config`, and `data_sources`.

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
- App identity provisions the schema, table, row filter, and grants.
- Every tool read/write runs as the calling user through OBO SQL.
- The only user OAuth scope is `sql`; the tool path makes no identity or Genie API call.
- A Unity Catalog row filter enforces `created_by = SESSION_USER()`, so histories are
  private per user even when users collaborate on the same Agent.
- `/healthz` is process liveness. `/readyz` returns HTTP 503 until schema provisioning,
  filtering, and required grantee table access succeed.

## Deploy on Databricks

The deployment choices are FastAPI, combined app/user authorization, one SQL warehouse
resource, Unity Catalog managed tables, and the Databricks CLI deployment path.

### 1. Prerequisites

You need:

- Databricks CLI 1.x configured for the target workspace.
- Permission to create and manage a Databricks App.
- A running SQL warehouse.
- A pre-existing Unity Catalog catalog with managed storage.
- A Unity Catalog principal for MCP access: your user email for a single-user deployment,
  or an account-level group for a multi-user deployment.
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
databricks apps create --name mcp-genie-agent-versioning \
  --json '{"description":"Genie Agent configuration version store"}'
databricks apps get mcp-genie-agent-versioning
```

If your CLI's `create -h` shows a positional name instead, use that form. Copy the App
service principal identity from the command output or the App's configuration page.

### 3. Grant the bootstrap prerequisites and choose the MCP user principal

The App service principal and the user calling the MCP are separate identities. The App
service principal provisions the schema, table, row filter, and grants. Give it bootstrap
access using the exact service-principal identity from step 2:

```sql
GRANT USE CATALOG ON CATALOG <catalog> TO `<app-service-principal>`;
GRANT CREATE SCHEMA ON CATALOG <catalog> TO `<app-service-principal>`;
```

Next choose the principal that will call the MCP through OBO authorization.

#### Single user

Set `HISTORY_GRANTEE` to your Databricks user email. If you already have effective
`USE CATALOG` access, directly or through an existing group, no additional user grant is
needed. Set `HISTORY_GRANTEE_USE_CATALOG_CONFIRMED=true` to confirm that access.

If you do not already have catalog access, a catalog owner must grant it:

```sql
GRANT USE CATALOG ON CATALOG <catalog> TO `<your-email>`;
```

#### Multiple users

Create or reuse an account-level group, add the MCP users, and set `HISTORY_GRANTEE` to
that group name. The group must exist before the App starts. If it does not already have
effective catalog access, a catalog owner must grant it:

```sql
GRANT USE CATALOG ON CATALOG <catalog> TO `genie_versioning_users`;
```

Then set `HISTORY_GRANTEE_USE_CATALOG_CONFIRMED=true`. `USE CATALOG` is only permission to
reference objects inside the catalog; it does not grant access to other schemas or tables.

In either case, the App owns the schema it creates and grants the selected
`HISTORY_GRANTEE` principal `USE SCHEMA` plus `SELECT, MODIFY` only on the row-filtered
version table. A grantee is required by this implementation, but it does not have to be a
group. The App does not need `MANAGE` on the catalog.

### 4. Configure `app.yaml` and the SQL warehouse resource

Edit [`app.yaml`](app.yaml):

- Set `HISTORY_CATALOG` to the catalog from step 3.
- Leave `HISTORY_SCHEMA=genie_agent_versioning` for a fresh deployment.
- For one user, set `HISTORY_GRANTEE` to that user's email. For multiple users, set it to
  the account-level group from step 3.
- Set `HISTORY_GRANTEE_USE_CATALOG_CONFIRMED=true` after confirming that principal has
  effective `USE CATALOG`, whether directly or through an existing group.

In the App configuration page:

1. Add a **SQL warehouse** resource with key `sql-warehouse` and **CAN USE** permission.
2. Enable **User authorization** and approve the `sql` scope declared in `app.yaml`.
3. Give App users **CAN USE** on the App; reserve **CAN MANAGE** for trusted developers.

`SQL_WAREHOUSE_ID` uses `valueFrom: sql-warehouse`; do not replace it with a hardcoded ID.

### 5. Deploy

For deployment from this Git repository, use `genie-code/mcp-genie-agent-versioning` as
the source directory (relative to the repository root):

```bash
databricks apps deploy mcp-genie-agent-versioning \
  --json '{"git_source":{"branch":"main","source_code_path":"genie-code/mcp-genie-agent-versioning"}}'
```

Alternatively, upload a local checkout through the Databricks workspace. Run these
commands from the `mcp-genie-agent-versioning/` directory, replacing the workspace user
path:

```bash
databricks workspace mkdirs \
  /Workspace/Users/<user-email>/apps/mcp-genie-agent-versioning

databricks workspace import-dir . \
  /Workspace/Users/<user-email>/apps/mcp-genie-agent-versioning \
  --overwrite

databricks apps deploy mcp-genie-agent-versioning \
  --source-code-path \
  /Workspace/Users/<user-email>/apps/mcp-genie-agent-versioning
```

Always include `--overwrite` on redeploy; otherwise changed workspace files may be skipped.

### 6. Verify provisioning and readiness

```bash
databricks apps get mcp-genie-agent-versioning
databricks apps logs mcp-genie-agent-versioning
```

Open the App URL while authenticated:

- `/healthz` should return `{"status":"healthy","check":"liveness"}`.
- `/readyz` should return HTTP 200 with `status: ready`.
- `/mcp` is the MCP endpoint; it is not a normal browser page.

If readiness returns 503, inspect its bootstrap report and the App logs. The usual causes
are a missing catalog/schema privilege, an incorrectly named grantee principal, a row-filter
failure, or a SQL warehouse resource that is stopped or not bound with key
`sql-warehouse`.

### 7. Connect Genie Code

Connect the deployed App through the Genie Code UI:

1. Open **Genie Code settings**.
2. Under **MCP Servers**, click **Add Server**.
3. Select **Custom MCP server**, then select the deployed Databricks App.
4. Click **Save**.

The App exposes the endpoint Genie Code requires at `https://<app-url>/mcp`; users select
the App in the UI rather than entering this URL manually. See the
[Genie Code MCP documentation](https://docs.databricks.com/aws/en/genie-code/mcp).

Genie Code calls the MCP from the workspace UI, so the browser first sends an
`OPTIONS /mcp` CORS preflight. The App automatically allows the workspace origin supplied
by the Databricks Apps runtime in `DATABRICKS_HOST`. If Genie Code is served from a
different workspace alias, add that exact HTTPS origin to `DATABRICKS_ORIGIN_ALIASES`;
unlisted Databricks workspaces are rejected.

The MCP exposes versioning tools, but it cannot intercept native Genie Agent edits. Add a
persistent custom instruction so Genie Code applies the snapshot requirement throughout
long, multi-step tasks:

- **User instruction:** Best for a personal deployment. In full-page Genie Code, open
  **Customization** > **Instructions**. Under **User instructions**, select **Add
  instructions file** and edit the generated
  `/Users/<your-username-or-email>/.assistant_instructions.md` file.
- **Workspace instruction:** Best when every Genie Code user must follow the policy. A
  workspace administrator must add the instruction to
  `/Workspace/.assistant_workspace_instructions.md`.

Add the following text to either instruction file:

> Before changing any Genie Agent configuration, first read its complete current
> configuration using Get Genie Agent with `include_serialized_space=true`, and save the
> exact returned configuration with `save_agent_config_version` using reason
> `before_update` or `before_rollback`. Proceed only if the save succeeds. Use
> `list_agent_versions` and `get_agent_version` for rollback. If the MCP is unavailable
> or the save fails, stop without editing. For rollback, use a freshly read live etag,
> never the stored historical etag. Follow this rule even with Auto-Approve enabled.

For extra visibility, task prompts can also include: “Follow the Genie Agent versioning
instruction before every configuration edit.” Putting the full requirement only in an
individual task prompt works for one-off use, but a persistent user or workspace
instruction is more reliable across long sessions. See the
[Genie Code custom instructions documentation](https://docs.databricks.com/aws/en/genie-code/instructions).

## Configuration

| Variable | Meaning |
| --- | --- |
| `HISTORY_CATALOG` | Pre-existing Unity Catalog catalog; the App never creates it. |
| `HISTORY_SCHEMA` | Target schema; defaults to `genie_agent_versioning`. |
| `HISTORY_GRANTEE` | UC principal receiving OBO table access: a user email or account-level group. |
| `HISTORY_GRANTEE_USE_CATALOG_CONFIRMED` | Confirmation that the principal already has effective `USE CATALOG`, directly or through inheritance. |
| `SQL_WAREHOUSE_ID` | SQL warehouse resource injected from `sql-warehouse`. |
| `MAX_CONFIG_BYTES` | Maximum UTF-8 envelope size; defaults to 5 MiB. |
| `TRANSFER_OWNERSHIP` | Opt-in durable group ownership handoff; defaults to `false`. |
| `HISTORY_OWNER_GROUP` | Required only when ownership transfer is enabled. |
| `DATABRICKS_ORIGIN_ALIASES` | Optional comma-separated exact HTTPS workspace origins allowed by CORS in addition to `DATABRICKS_HOST`. |

Leave `TRANSFER_OWNERSHIP=false` while the App manages schema changes. An operator can
enable a one-time transfer to a durable owner group after deciding that the group will
manage future schema changes.

## Local verification

```bash
python3 -m pytest
uvx ruff check .
uvx ruff format --check .
uvx --with databricks-sdk --with fastapi --with fastmcp \
  --with "mcp[cli]" --with pydantic --with uvicorn --with pytest pyright
```

Local startup skips Databricks provisioning, so `/readyz` intentionally returns 503. Use
unit tests for the local loop and a deployed App for OBO/readiness verification.
