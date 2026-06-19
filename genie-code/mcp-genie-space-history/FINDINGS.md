# FINDINGS — Genie Space History MCP, P0 spike

> **Honesty contract:** this file separates **🟢 RAN & VERIFIED** (with real, verbatim
> output) from **🟡 RUNBOOK / NOT RUN** (needs a deployed App + Genie Code UI). Nothing
> here is fabricated; failures and limitations are recorded as findings.

Run date: 2026-06-18 · Workspace: `https://fevm-dhuang.cloud.databricks.com/` ·
Identity: `david.huang@databricks.com` · Probe SDK: **databricks-sdk 0.118.0** (venv).

---

## Verdict table (criterion → ran? → result → resolved §12 value)

| # | Criterion | Ran? | Result | Resolved residual |
|---|---|---|---|---|
| 1 | Hosting: MCP on Apps, `/mcp` stateless, connectable from Genie Code | 🟢 **deployed & serving** | `/` & `/healthz` = 200; `/mcp` SSE `initialize` OK; all 6 tools listed. Genie-Code "add server" is the only manual bit. | **App reachable at `/mcp` (stateless streamable HTTP) ✓** |
| 2 | OBO `current_user.me()` returns calling user | 🟢 **verified end-to-end** | `whoami` over `/mcp` returns the calling user via `X-Forwarded-Access-Token` | **OBO ENABLED ✓**; default OBO scopes lack `genie`/`sql` — add `user_api_scopes` (F-6) |
| 3 | App SP auto-creates schema + table `IF NOT EXISTS`; catalog NOT created | 🟢 yes | `idempotent=true`, `catalog_created_by_spike=false`, both DDL runs `SUCCEEDED` | **Provisioning works** (+ DDL needed a fix — see F-4) |
| 4 | VARIANT probe | 🟢 yes | `variant_usable=true` → **VARIANT** | **VARIANT is USABLE** on warehouse `78e36e2b033b2d06` (not just STRING) |
| 5 | Genie `get_space`→`update_space` round-trip; min permission | 🟢 yes | Round-trip OK, `config_unchanged=true` | **Min permission verified: CAN MANAGE** (CAN EDIT floor documented, not isolated — see #5) |
| 6 | Stale-etag update rejected | 🟢 yes | `stale_update_rejected=true` (`Aborted`) | **etag optimistic lock ENFORCED** (requires SDK ≥ 0.118.0 — see F-1) |

---

## Environment / auth state

- Target workspace reachable; `databricks --profile fevm-dhuang current-user me` →
  `david.huang@databricks.com` (member of `admins`).
- At spike start there was **no credential for the target** (no `fevm-dhuang` profile; the
  default profile pointed at a different workspace). The human authenticated mid-spike.
- Probes run in an isolated venv (`spike/.venv`) with **databricks-sdk 0.118.0** — required
  for the genie etag (see F-1).

---

## 🟢 RAN & VERIFIED — per criterion (verbatim output)

### #2 — OBO identity (local sanity)

`whoami` under the CLI profile (in the App this same call runs with the forwarded user
token; locally it is the developer identity):

```json
{
  "ok": true,
  "user_name": "david.huang@databricks.com",
  "display_name": "David Huang",
  "active": true,
  "id": "3101383667725164",
  "workspace_host": "https://fevm-dhuang.cloud.databricks.com"
}
```

**OBO verified end-to-end on the deployed app** (calling the `whoami` tool over `/mcp` with
my bearer token — the apps proxy injected `X-Forwarded-Access-Token`):

```json
{"ok": true, "user_name": "david.huang@databricks.com", "display_name": "David Huang",
 "active": true, "id": "3101383667725164", "workspace_host": "https://fevm-dhuang.cloud.databricks.com"}
```

The tool returned the **calling user**, not the app SP → **OBO is ENABLED**. See **F-6** for
the scope caveat (the default OBO token lacks `genie`/`sql`).

### #3 — Auto-provision schema + table (catalog NOT created)

```json
{
  "catalog": "dhuang_catalog",
  "schema": "dhuang_catalog.genie_space_history",
  "table": "dhuang_catalog.genie_space_history.config_snapshots",
  "catalog_created_by_spike": false,
  "catalog_accessible": true,
  "schema_existed_before": true,
  "table_existed_before": false,
  "ddl_run_1_state": "SUCCEEDED",
  "ddl_run_2_state": "SUCCEEDED",
  "idempotent": true,
  "ok": true
}
```

- Schema + table created via `... IF NOT EXISTS`; **no `CREATE CATALOG` is ever issued**
  (`catalog_created_by_spike=false`).
- Idempotency shown two ways: `schema_existed_before=true` (it survived from the earlier
  run) and the table DDL ran **twice**, both `SUCCEEDED`.
- Run as `david.huang` (a CLI-profile identity), this proves the **DDL mechanics +
  idempotency + the no-catalog invariant**. The app-SP-with-only-`USE CATALOG`+`CREATE
  SCHEMA` sufficiency is confirmed when the deployed app calls `provision_history_schema`
  (RUNBOOK §1).

### #4 — VARIANT probe → **USABLE**

```json
{
  "table": "dhuang_catalog.genie_space_history._variant_probe",
  "variant_usable": true,
  "read_back": [["k1", "1", "[2,3]"]],
  "recommendation": "VARIANT",
  "steps": [
    {"step": "create_table_variant", "state": "SUCCEEDED"},
    {"step": "truncate", "state": "SUCCEEDED"},
    {"step": "insert_parse_json", "state": "SUCCEEDED"},
    {"step": "read_back_variant_path", "state": "SUCCEEDED"}
  ],
  "cleanup": "dropped",
  "ok": true
}
```

`CREATE TABLE (... VARIANT)` + `INSERT ... parse_json(...)` + reading `payload:a` /
`payload:b` all succeeded on warehouse `78e36e2b033b2d06`. **VARIANT is usable** here, so it
can be an opt-in (the spec default remains STRING for portability — §12 #3).

### #5 — Genie get/update round-trip (idempotent no-op restore)

```json
{
  "before": {
    "space_id": "01f16b396b3419ba8462d5efe167d947",
    "title": "Bakehouse Analytics",
    "warehouse_id": "78e36e2b033b2d06",
    "etag": "5c2f5548f0dd445210891c7eac0fb74f10c893ef85394e6adbe34680d7f2b0c5",
    "has_serialized_space": true,
    "serialized_space_len": 537,
    "config_hash": "3bdb5c09d3a927fd1ab3fe4a6857744a45635c92658ea8b91bcff0c7a9bfda45"
  },
  "applied": true,
  "after_update_etag": "5c2f5548f0dd445210891c7eac0fb74f10c893ef85394e6adbe34680d7f2b0c5",
  "after": { "...": "identical to before", "config_hash": "3bdb5c09...a9bfda45" },
  "config_unchanged": true,
  "etag_rotated": false,
  "ok": true
}
```

- `get_space(include_serialized_space=True)` → re-applied the **identical** `serialized_space`
  + outer metadata via `update_space(..., etag=...)`. `config_hash` is byte-identical before
  and after (`config_unchanged=true`) — the Space's effective config was **not changed**.
- **Minimum permission — verified at `CAN_MANAGE`.** `GET
  /api/2.0/permissions/genie/01f16b396b3419ba8462d5efe167d947` shows the caller has
  `CAN_MANAGE` (inherited from the parent directory, and via the `admins` group):
  ```json
  {"access_control_list":[
    {"user_name":"david.huang@databricks.com","all_permissions":[{"permission_level":"CAN_MANAGE","inherited":true}]},
    {"group_name":"admins","all_permissions":[{"permission_level":"CAN_MANAGE","inherited":true}]}],
   "object_type":"genie","object_id":"/genie/3958256460036208"}
  ```
  The round-trip succeeds at **CAN MANAGE**. The spec's documented floor is **CAN EDIT** for
  the read; whether CAN-EDIT-only is sufficient for `update_space` was **not independently
  isolated** here (would need a second principal granted *only* CAN EDIT). Recorded as a
  follow-up, not claimed.

### #6 — Stale-etag rejection (optimistic lock) → **ENFORCED**

```json
{
  "etag_initial": "5c2f5548f0dd445210891c7eac0fb74f10c893ef85394e6adbe34680d7f2b0c5",
  "etag_after_valid_update": "5c2f5548f0dd445210891c7eac0fb74f10c893ef85394e6adbe34680d7f2b0c5",
  "etag_rotated": false,
  "stale_attempts": [
    {"label": "reuse_previous_etag", "etag_used": "5c2f5548...d7f2b0c5", "rejected": false},
    {"label": "bogus_etag", "etag_used": "stale-etag-probe-0000", "rejected": true,
     "error_class": "Aborted",
     "error_message": "Space configuration has been modified since this export was taken. Re-export the space and merge your changes, or omit the etag to skip conflict detection."}
  ],
  "stale_update_rejected": true,
  "ok": true
}
```

A wrong etag is **rejected** with `Aborted` and an explicit conflict message — the
optimistic lock works. See **F-5** for why the etag is content-based (and why
`reuse_previous_etag` was accepted: the content was identical, so that etag was *not* stale).

---

## 🟢 RAN & VERIFIED — cross-cutting findings

### F-1. `databricks-sdk` version gate for the Genie **etag** — CONFIRMED (drives #5/#6)
The spec's body-`etag` optimistic lock is real but **version-gated**:
- **0.102.0** (the machine's system SDK): `GenieSpace` has **no `etag`**; `update_space`
  sends only `description/serialized_space/title/warehouse_id`. etag is **impossible**.
- **0.118.0**: adds `GenieSpace.etag` and `update_space(..., etag=...)` (etag → PATCH **body**,
  not an `If-Match` header) — matches the spec.

**Resolution:** spike pins **`databricks-sdk>=0.118.0`**. This is the "upgrade before
working around" fix; no raw-REST hack needed. Criterion #6 is impossible without it.

### F-4. The spec §7.1 DDL needs the Delta `allowColumnDefaults` feature — FIX APPLIED
The first `provision` run **failed** (real output):
```
[WRONG_COLUMN_DEFAULTS_FOR_DELTA_FEATURE_NOT_ENABLED] Failed to execute CREATE TABLE command
because it assigned a column DEFAULT value, but the corresponding table feature was not enabled.
... ALTER TABLE ... SET TBLPROPERTIES('delta.feature.allowColumnDefaults' = 'supported').
```
The spec's `created_at TIMESTAMP DEFAULT current_timestamp()` / `created_by STRING DEFAULT
current_user()` require that feature. **Fix:** add
`'delta.feature.allowColumnDefaults' = 'supported'` to the table `TBLPROPERTIES` (applied in
`spike_core.py` + RUNBOOK). The design's §7.1 DDL should adopt this.

### F-5. The Genie etag is **content-based**, and ACLs read via a real endpoint — NOTED
- Re-applying byte-identical `serialized_space` returns the **same etag** (`etag_rotated=false`).
  So the etag behaves like a content hash: a "previous" etag is only *stale* if the content
  actually changed. To exercise the lock deterministically, use a **non-matching** etag (the
  bogus-etag attempt) or a snapshot taken before a real edit. The error message confirms the
  intent: *"…or omit the etag to skip conflict detection."*
- Genie Space ACLs are readable/settable at **`/api/2.0/permissions/genie/{space_id}`**
  (`object_type: "genie"`) — useful for the server to pre-flight the caller's permission.

### F-6. App OBO scopes do NOT include `genie`/`sql` by default — must be configured
The deployed app's effective OBO scopes were only:
```
effective_user_api_scopes: ['iam.current-user:read', 'iam.access-control:read']   (user_api_scopes: None)
```
That's why `whoami` (identity) worked but `genie_roundtrip` over OBO failed with
`required scopes: genie`. The workspace's `scopes_supported` includes `genie`, `sql`,
`dashboards`, `all-apis`, etc. **Fix (deployment config):** set the app's `user_api_scopes`
to include `sql` + `genie` (and `dashboards`):
```bash
databricks --profile fevm-dhuang apps update mcp-genie-space-history \
  --json '{"user_api_scopes":["iam.current-user:read","iam.access-control:read","sql","dashboards","genie"]}'
```
*(Not executed in this spike — changing an app's OAuth scopes is a persistent permission
grant and was intentionally left for the human to authorize; it may also require user
re-consent. This directly resolves the §5 "scopes `sql` + Genie/dashboards" requirement.)*

### F-2 / F-3. Template shape + syntax — VERIFIED
Built on `databricks/app-templates → mcp-server-hello-world` (FastMCP 2.x,
`http_app(stateless_http=True)` → `/mcp`, header→ContextVar→OBO client). All modules
`py_compile`/`ast.parse` clean under Python 3.11 with SDK 0.118.0; `GenieSpace.etag` and
`update_space(..., etag=...)` resolve in the venv.

---

## 🟢 RAN — deploy + OBO via the deployed app (criteria #1, #2)

The best-effort deploy **succeeded** and the app is live, so #1 and #2 were exercised for
real (not left as runbook).

### #1 — Hosting (DEPLOYED & SERVING)
- `databricks apps create mcp-genie-space-history` → compute `ACTIVE`.
- `databricks sync` (15 files, `.venv` excluded) → `databricks apps deploy ...` →
  `{"status": {"message": "App started successfully", "state": "SUCCEEDED"}}`.
- App URL: `https://mcp-genie-space-history-7474650956504148.aws.databricksapps.com`
- Live HTTP checks (with an OAuth bearer token):
  - `GET /` → `200` `{"message":"Genie Space History MCP (spike) running","mcp_endpoint":"/mcp"}`
  - `GET /healthz` → `200`
  - `POST /mcp` `initialize` → `200`, `content-type: text/event-stream`, body:
    `serverInfo.name="mcp-genie-space-history"`, `protocolVersion="2025-06-18"` (stateless SSE ✓)
  - `POST /mcp` `tools/list` → the 6 tools: `health`, `whoami`, `provision_history_schema`,
    `variant_probe`, `genie_roundtrip`, `genie_etag_check`.
- **Only the Genie-Code "Add Server" UI click remains** (RUNBOOK §1) — the MCP protocol layer
  is proven reachable + functional, which is what Genie Code connects to.

### #2 — OBO identity (ENABLED; scope caveat F-6)
- `whoami` over `/mcp` returned the **calling user** via `X-Forwarded-Access-Token` (above)
  → **OBO is ENABLED**.
- A read-only `genie_roundtrip(dry_run=true)` over OBO **failed with a scope error** (verbatim):
  ```
  Provided OAuth token does not have required scopes: genie [ReqId: ab357ea5-...]
  ```
  i.e. OBO works, but the app's default OBO scopes don't include `genie` — see **F-6**. Note
  the spike's `get_user_workspace_client` surfaced this as a clean `{"ok": false, "error": ...}`
  (the spec §5 `scope_error` behavior), not a crash.

> The app is left **running** for the human's Genie-Code UI test. Tear down with
> `databricks --profile fevm-dhuang apps delete mcp-genie-space-history`.

---

## §12 residuals — final tracker

| Residual | Resolved value | Evidence |
|---|---|---|
| OBO enabled in workspace? | **YES** — `whoami` over `/mcp` returned the calling user via `X-Forwarded-Access-Token` | #2 (deployed app) |
| OBO scopes for genie/sql? | **NOT default** — add `user_api_scopes` (`sql`,`genie`,`dashboards`) | F-6 |
| VARIANT usable, or STRING? | **VARIANT USABLE** on `78e36e2b033b2d06` (spec keeps STRING default; VARIANT opt-in) | #4 |
| Min Genie permission for `update_space`? | **CAN MANAGE verified**; CAN EDIT is the documented floor, not isolated in this spike | #5 + permissions API |
| etag enforced? | **YES** — stale/wrong etag → `Aborted` conflict | #6 |
| SDK version for etag | **`databricks-sdk>=0.118.0`** (0.102.0 lacks it) — pinned | F-1 |
| (new) DDL column DEFAULTs | need `delta.feature.allowColumnDefaults=supported` | F-4 |
| (new) etag semantics | **content-based**; ACLs at `/api/2.0/permissions/genie/{id}` | F-5 |

## Reproduce

```bash
databricks auth login --host https://fevm-dhuang.cloud.databricks.com --profile fevm-dhuang
cd genie-code/mcp-genie-space-history/spike
uv venv && uv pip install -r requirements.txt
.venv/bin/python -m probes.run_all          # whoami + provision + variant + roundtrip + etag
```
