# RUNBOOK — Genie Space History MCP (operator)

Operator procedure for deploying and connecting the production **Genie Space History
MCP** server in [`app/`](app). It covers the steps the app **cannot** self-perform: the
app-SP Unity Catalog grants, the deploy, the OBO scope/enablement, a smoke test, and
the Genie-Code connect click. Once deployed, the app idempotently bootstraps its own
schema + tables on startup (`server/provisioning.py`) — there is no manual DDL step.

> These commands assume a Databricks CLI profile authenticated to the **target
> workspace**. Substitute `<profile>`, `<workspace-host>`, and the catalog / group /
> warehouse values for your environment; the per-app config is declared in
> [`app/app.yaml`](app/app.yaml).

```bash
# Authenticate the CLI to the target workspace (interactive browser OAuth), if needed.
databricks auth login --host https://<workspace-host> --profile <profile>
databricks current-user me -p <profile>          # sanity check
```

## 1. Operator prerequisites (app cannot self-perform — spec §10)

Before the app's startup bootstrap can succeed:

- Grant the **app's service principal** `USE CATALOG` + `CREATE SCHEMA` on
  `HISTORY_CATALOG` (the **pre-existing** catalog; the app **never** creates it).
- Create the durable `HISTORY_OWNER_GROUP` account group and have a metastore admin
  run the one-time `OWNER TO HISTORY_OWNER_GROUP` if the SP isn't a member (the schema
  + tables must outlive the app/SP).
- Confirm **OBO is enabled** for the workspace in the **Previews portal**.

The bootstrap then idempotently creates the schema + the 7 tables (with
`delta.enableRowTracking` + `delta.feature.allowColumnDefaults`, P0 finding F-4),
creates the `only_mine` row filter, applies it per table, and grants `HISTORY_GRANTEE`
`SELECT`/`MODIFY` **only on tables whose filter applied**. The catalog is never created
and startup never crashes.

## 2. Deploy the App

```bash
APP=mcp-genie-space-history     # name must start with "mcp-" for AI Playground / Genie Code
WS=/Workspace/Users/<you>/mcp-genie-space-history

databricks --profile <profile> apps create "$APP"                       # provisions compute (~min); first deploy only
databricks --profile <profile> sync genie-code/mcp-genie-space-history/app "$WS" --full
databricks --profile <profile> apps deploy "$APP" --source-code-path "$WS"
databricks --profile <profile> apps get "$APP"                          # read the served URL
```

Bind the app's resources in the workspace UI (or via the apps API): a **SQL warehouse**
resource (`CAN USE`, surfaced as `SQL_WAREHOUSE_ID` via `valueFrom: sql-warehouse`).
Under Option A the server never calls the Genie API, so **no** Genie Space resource is
required.

## 3. OBO scopes

The app requests OBO scopes via [`app/app.yaml`](app/app.yaml), which declares the
only scope this server needs under Option A — `sql` (P0 finding F-6; a deployed app's
OBO token otherwise defaults to identity-only scopes and warehouse calls fail). To
inspect or adjust the scopes on a running app without redeploying:

```bash
databricks --profile <profile> apps update mcp-genie-space-history \
  --json '{"user_api_scopes":["sql"]}'
# may require user re-consent; restart the app afterward
```

## 4. Smoke-test the running app

```bash
TOKEN=$(databricks --profile <profile> auth token | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
URL=$(databricks --profile <profile> apps get mcp-genie-space-history | python3 -c 'import sys,json;print(json.load(sys.stdin)["url"])')

curl -s -H "Authorization: Bearer $TOKEN" "$URL/healthz"                      # -> 200
curl -s -X POST "$URL/mcp" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'            # -> lists the 5 tools
```

Expect the five MCP tools (spec §6): `save_config_snapshot`, `save_report`,
`record_optimization_run`, `list_history`, `get_artifact`.

## 5. Connect from Genie Code

In the workspace UI: **Genie Code → Settings → MCP Servers → Add Server → Custom MCP**
→ select the `mcp-genie-space-history` app. Requirements: same workspace, `/mcp`,
stateless, CORS allow-lists the workspace URL (`CORS_ALLOW_ORIGINS`), ≤20 tools total.
Confirm the tools appear, then call one (e.g. `list_history`) as yourself — OBO forwards
your `X-Forwarded-Access-Token` so `current_user()` resolves to **you**, not the app SP.
