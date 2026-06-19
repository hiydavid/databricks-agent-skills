# RUNBOOK — Genie Space History MCP, P0 spike

Copy-pasteable steps to reproduce every P0 exit criterion (design spec §13). Two kinds
of steps:

- 🟢 **Scriptable** (#3–#6): runnable from a laptop with CLI auth; the spike actually ran
  these — see `FINDINGS.md` for captured output.
- 🟡 **Needs deployed App + Genie Code UI** (#1, #2-over-OBO): commands + manual UI clicks.

## Spike inputs

| Thing | Value |
|---|---|
| Workspace | `https://fevm-dhuang.cloud.databricks.com/` |
| Genie Space (throwaway) | `01f16b396b3419ba8462d5efe167d947` |
| Catalog (pre-existing) | `dhuang_catalog` |
| Schema (auto-created) | `genie_space_history` |
| SQL warehouse | `78e36e2b033b2d06` |

## 0. One-time setup

```bash
# Auth the CLI/SDK to the TARGET workspace (interactive browser OAuth).
databricks auth login --host https://fevm-dhuang.cloud.databricks.com --profile fevm-dhuang
databricks current-user me -p fevm-dhuang        # sanity check

# Python env for the probes (databricks-sdk>=0.118.0 is required for genie etag).
cd genie-code/mcp-genie-space-history/spike
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
```

All probe commands below are run from `genie-code/mcp-genie-space-history/spike/`.
`config.py` already defaults to the spike inputs; override with env vars if needed.

---

## 🟢 #3 — Auto-provision schema + table (catalog NOT created)

> Pre-req (operator, once): grant the **app SP** `USE CATALOG` + `CREATE SCHEMA` on
> `dhuang_catalog`. The probe below runs as *you* (proving DDL idempotency + that the
> catalog is never created); the SP-grant sufficiency is confirmed when the deployed app
> calls `provision_history_schema` (step #1/#2).

```bash
python -m probes.run_all provision
```

Expect: `catalog_accessible=true`, `catalog_created_by_spike=false`, both
`ddl_run_1_state` and `ddl_run_2_state` = `SUCCEEDED`, `idempotent=true`.

Manual SQL equivalent (paste in a SQL editor on warehouse `78e36e2b033b2d06`):

```sql
SHOW SCHEMAS IN dhuang_catalog;                                   -- proves catalog exists
CREATE SCHEMA IF NOT EXISTS dhuang_catalog.genie_space_history;   -- idempotent
CREATE TABLE IF NOT EXISTS dhuang_catalog.genie_space_history.config_snapshots (
  config_version_id STRING NOT NULL, space_id STRING NOT NULL, version BIGINT NOT NULL,
  parent_version_id STRING, created_at TIMESTAMP DEFAULT current_timestamp(),
  created_by STRING DEFAULT current_user(), skill_name STRING, config_json STRING,
  config_hash STRING, diff_patch STRING, changed_surfaces ARRAY<STRING>, etag STRING,
  run_id STRING, rollback_reference STRING, change_summary STRING
) USING DELTA TBLPROPERTIES (
  delta.enableRowTracking = true,
  'delta.feature.allowColumnDefaults' = 'supported'   -- REQUIRED for the DEFAULT clauses (finding F-4)
);                                                     -- run twice; both succeed
-- NOTE: there is intentionally NO `CREATE CATALOG` here.
```

---

## 🟢 #4 — VARIANT probe

```bash
python -m probes.run_all variant
```

Expect `variant_usable=true` → `recommendation: VARIANT`, or `false` → `STRING`
(error captured). Manual SQL:

```sql
CREATE TABLE IF NOT EXISTS dhuang_catalog.genie_space_history._variant_probe (id STRING, payload VARIANT);
INSERT INTO dhuang_catalog.genie_space_history._variant_probe
  SELECT 'k1', parse_json('{"a": 1, "b": [2, 3]}');
SELECT id, payload:a::int AS a, to_json(payload:b) AS b
  FROM dhuang_catalog.genie_space_history._variant_probe;
DROP TABLE IF EXISTS dhuang_catalog.genie_space_history._variant_probe;
```

---

## 🟢 #5 — Genie get/update round-trip (idempotent no-op restore)

```bash
python -m probes.run_all roundtrip
```

Reads `serialized_space` + `etag`, then re-applies the **identical** payload (safe no-op).
Expect `applied=true`, `config_unchanged=true`. Read the caller's permission level with:

```bash
databricks --profile fevm-dhuang api get /api/2.0/permissions/genie/01f16b396b3419ba8462d5efe167d947
```

Verified working at **CAN MANAGE** in this spike; see `FINDINGS.md` #5 / F-5.

---

## 🟢 #6 — Stale-etag rejection (optimistic lock)

```bash
python -m probes.run_all etag
```

Reads `etag1`, does a valid update (→ `etag2`), then retries with the now-stale `etag1`
(and a bogus etag as fallback). Expect `stale_update_rejected=true`. Note (finding F-5): the
etag is **content-based**, so an identical re-apply keeps the same etag — a stale check only
trips when the content actually differs (here, the bogus etag triggers the `Aborted` conflict).

Run everything at once:

```bash
python -m probes.run_all
```

---

## 🟢/🟡 #1 — Deploy the App + connect from Genie Code

> **Done in this spike** — app is deployed & serving at
> `https://mcp-genie-space-history-7474650956504148.aws.databricksapps.com`
> (`/`, `/healthz` = 200; `/mcp` `initialize` + `tools/list` OK). The only remaining step is
> the Genie-Code "Add Server" UI click. Tear down with
> `databricks --profile fevm-dhuang apps delete mcp-genie-space-history`.

To reproduce from scratch:

```bash
cd genie-code/mcp-genie-space-history/spike
WS=/Workspace/Users/david.huang@databricks.com/mcp-genie-space-history-spike

databricks --profile fevm-dhuang apps create mcp-genie-space-history          # provisions compute (~min)
databricks --profile fevm-dhuang sync . "$WS" --full                          # .venv excluded via .gitignore
databricks --profile fevm-dhuang apps deploy mcp-genie-space-history --source-code-path "$WS"
databricks --profile fevm-dhuang apps get mcp-genie-space-history             # read the URL
```

Smoke-test the running app (needs an OAuth bearer token):

```bash
TOKEN=$(databricks --profile fevm-dhuang auth token | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
URL=https://mcp-genie-space-history-7474650956504148.aws.databricksapps.com
curl -s -H "Authorization: Bearer $TOKEN" "$URL/healthz"                      # -> 200
curl -s -X POST "$URL/mcp" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'            # -> lists the 6 tools
```

Then in the workspace UI:

1. **App SP grants (for #3 via the app):** grant the app's service principal `USE CATALOG` +
   `CREATE SCHEMA` on `dhuang_catalog`; bind a SQL-warehouse resource (`CAN USE`) and the
   Genie Space resource. (The spike's standalone probes already proved the DDL/VARIANT/Genie
   mechanics as the user — these grants make the *deployed app* able to do the same.)
2. **Genie Code → Settings → MCP Servers → Add Server → Custom MCP** → select the
   `mcp-genie-space-history` app. Requirements: same workspace, `/mcp`, stateless, CORS
   allow-lists the workspace URL, ≤20 tools total.
3. Confirm the tools appear and call `health`.

## 🟢/🟡 #2 — OBO identity through the App (X-Forwarded-Access-Token)

> **OBO is ENABLED — verified in this spike.** Calling the `whoami` tool over `/mcp` returned
> the calling user `david.huang@databricks.com` (the apps proxy injected
> `X-Forwarded-Access-Token`). **But** the app's default OBO scopes are only
> `iam.current-user:read` + `iam.access-control:read`, so a Genie/SQL call over OBO fails with
> `required scopes: genie` (finding F-6).

**Required config step (human-authorized — persistent permission grant, not run by the spike):**

```bash
databricks --profile fevm-dhuang apps update mcp-genie-space-history \
  --json '{"user_api_scopes":["iam.current-user:read","iam.access-control:read","sql","dashboards","genie"]}'
# may require user re-consent; redeploy/restart the app afterward
```

Re-test (expect the calling user, no scope error):

```bash
curl -s -X POST "$URL/mcp" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"whoami","arguments":{}}}'
```

From Genie Code (as yourself), call `whoami` → expect **your** user, proving the forwarded
token reached `current_user.me()` (not the app SP).
