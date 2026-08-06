# Genie Agent Versioning MCP

This Databricks App is a prompt-routed configuration version store for Genie Agents. It
exposes stateless streamable HTTP at `/mcp`, reads complete live configurations with the
calling user's identity, and stores them in Unity Catalog. Its restore tool can apply only
a complete snapshot already visible in that user's version history.

Genie Code remains responsible for calling the save tool before an edit, stopping if that
save fails, and applying ordinary edits with native tools. Rollback is performed by the
MCP so the large serialized configuration never passes through model context.

## MCP tools

| Tool | Purpose |
| --- | --- |
| `save_agent_config_version` | Fetch and append the current live configuration. Every successful call creates a new version, including identical content. |
| `list_agent_versions` | List one Agent's private history with deterministic cursor pagination. |
| `get_agent_version` | Retrieve one complete version using both `space_id` and `version_id`. |
| `restore_agent_config_version` | Checkpoint the live Agent and restore one stored version with its current etag. |

`save_agent_config_version` fetches the live Agent with `include_serialized_space=true`
through the caller's OBO identity, so `serialized_space` never passes through Genie Code's
model context or tool arguments. The server adds `format_version` and `space_id`, bounds
the envelope to 5 MiB by default, and hashes canonical restore content. Saving requires
at least CAN EDIT on the Agent (that permission is required for `include_serialized_space=true`).

The optional `parent_version_id` records lineage. A direct `before_rollback` save must
include a visible, same-Agent `rollback_target_version_id`; callers normally do not need
to make that save because `restore_agent_config_version` creates it automatically. The
etag returned by `get_agent_version` is historical provenance only — read a fresh live etag
before applying a configuration.

Both snapshot and restore run as the caller, who needs the `genie` scope and sufficient
Agent permissions (currently at least CAN EDIT for the complete export and update); App
CAN MANAGE does not grant the caller access to a Genie Agent. Version persistence
additionally requires the `sql` scope and the documented Unity Catalog grants. See each
tool's description for its exact save and restore semantics, including the ordered
checkpoint-then-PATCH flow that makes `restore_agent_config_version` conflict-safe (not a
distributed transaction across Genie and SQL).

## Architecture and security

- FastAPI + FastMCP on Databricks Apps, served by uvicorn.
- App identity provisions the schema, table, row filter, and grants.
- The live Genie read/restore and every version read/write run as the caller through OBO.
- User authorization requires the `genie` and `sql` scopes.
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

`USE CATALOG` only permits referencing objects inside the catalog; it does not grant access
to other schemas or tables. A catalog owner must grant it to whichever principal will call
the MCP through OBO authorization — a single user's email or an account-level group. Set
`HISTORY_GRANTEE` to that principal and set `HISTORY_GRANTEE_USE_CATALOG_CONFIRMED=true` once
it has effective `USE CATALOG` (directly or through an existing group).

#### Single user

```sql
GRANT USE CATALOG ON CATALOG <catalog> TO `<your-email>`;
```

#### Multiple users

Create or reuse an account-level group, add the MCP users, and set `HISTORY_GRANTEE` to
that group name. The group must exist before the App starts.

```sql
GRANT USE CATALOG ON CATALOG <catalog> TO `genie_versioning_users`;
```

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
- Set `HISTORY_GRANTEE_USE_CATALOG_CONFIRMED=true` as confirmed in step 3.

In the App configuration page:

1. Add a **SQL warehouse** resource with key `sql-warehouse` and **CAN USE** permission.
2. Enable **User authorization** and approve the `sql` and `genie` scopes
   declared in `app.yaml`.
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

Genie Code calls the MCP from the workspace UI, which sends an `OPTIONS /mcp` CORS
preflight. The App automatically allows the `DATABRICKS_HOST` origin and official Databricks
domain aliases; for a nonstandard domain, add its exact HTTPS origin to
`DATABRICKS_ORIGIN_ALIASES`.

The MCP exposes versioning tools, but it cannot intercept native Genie Agent edits. Add a
persistent custom instruction so Genie Code applies the snapshot requirement throughout
long, multi-step tasks. Use a **user instruction** (personal deployment: **Customization** >
**Instructions** > edit `/Users/<your-username-or-email>/.assistant_instructions.md`) or a
**workspace instruction** (all users: an administrator edits
`/Workspace/.assistant_workspace_instructions.md`). Add the following to either file:

> Before making a normal Genie Agent configuration edit, call
> `save_agent_config_version` with its `space_id` and reason `before_update`; proceed only
> if the save succeeds. For rollback, call `list_agent_versions`, select a `version_id`,
> and pass it directly to `restore_agent_config_version`. Do not retrieve or relay the
> serialized configuration. If restore returns a conflict, inspect the new live state
> before deciding whether to retry. If it returns `restore_status: "unknown"`, inspect the
> live Agent before retrying. If the MCP is unavailable or a required save/restore fails,
> stop without making another edit. Follow this rule even with Auto-Approve enabled.

A persistent instruction is more reliable than putting the full requirement in individual
task prompts. See the
[Genie Code custom instructions documentation](https://docs.databricks.com/aws/en/genie-code/instructions).

## Configuration

| Variable | Meaning |
| --- | --- |
| `HISTORY_CATALOG` | Pre-existing Unity Catalog catalog; the App never creates it. |
| `HISTORY_SCHEMA` | Target schema; defaults to `genie_agent_versioning`. |
| `HISTORY_GRANTEE` | UC principal receiving OBO table access: a user email or account-level group. |
| `HISTORY_GRANTEE_USE_CATALOG_CONFIRMED` | Confirmation that the principal already has effective `USE CATALOG`, directly or through an existing group. |
| `SQL_WAREHOUSE_ID` | SQL warehouse resource injected from `sql-warehouse`. |
| `MAX_CONFIG_BYTES` | Maximum UTF-8 envelope size; defaults to 5 MiB. |
| `TRANSFER_OWNERSHIP` | Opt-in durable group ownership handoff; defaults to `false`. |
| `HISTORY_OWNER_GROUP` | Required only when ownership transfer is enabled. |
| `DATABRICKS_ORIGIN_ALIASES` | Optional comma-separated exact HTTPS origins for nonstandard workspace aliases. |

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
