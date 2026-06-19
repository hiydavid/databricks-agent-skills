# Genie Space History MCP — Design Spec

**Status:** Draft v1 (design only — no implementation)
**Audience:** Engineers building the MCP server; reviewers of the `genie-code/` skill suite
**Owner:** TBD
**Last updated:** 2026-06-18

> A custom Model Context Protocol (MCP) server, deployed and hosted on **Databricks Apps**, that the **Genie Code** skills in this directory call to **persist, version, and roll back** the artifacts they produce — Genie Space config snapshots, diagnostic write-ups, optimization runs, and benchmark eval results — to a governed **Unity Catalog table** (the queryable system-of-record).

---

## 1. Motivation & problem statement

The `genie-code/` skill suite (`create-genie-space`, `create-metric-view`, `diagnose-genie-space`, `optimize-genie-space`, `optimize-genie-query`) produces valuable artifacts but has **no durable, queryable, service-backed history**:

- **`diagnose-genie-space`** is plan-only and emits a Markdown *Diagnostic Write-Up* to chat/notebook — **persisted nowhere**.
- **`optimize-genie-space`** is the only skill that edits a Space. It *already mandates* capturing a "rollback-ready before snapshot in the approved local workspace history folder" and defines a detailed recommended file layout in `optimize-genie-space/references/optimization-guide.md` (`runs/`, `config_versions/`, `eval_results/`, `repair_analysis/`, `events.jsonl`). **But nothing enforces, indexes, queries, or actually performs a rollback** — it's hand-written files with a manual revert.
- **`optimize-genie-query`** emits a Markdown report — **persisted nowhere**.
- **`create-genie-space`** / **`create-metric-view`** emit a design proposal / YAML+DDL — **no snapshot/versioning**.
- **No skill defines a machine-readable Genie Space config object**; config read/write is delegated entirely to Genie Code's native editor/tools.

**The gap this server fills:** turn the skills' ad-hoc local files into a governed service that gives users (1) a **history** of every config change and analysis, (2) the ability to **diff** versions, and (3) a real, validated **rollback** of a Genie Space config to a prior snapshot.

The skill's own recommended schema in `optimization-guide.md` is the **contract we build against** — the MCP server is the durable backend for a layout the skills already know how to produce.

---

## 2. Goals / non-goals

### Goals

- Deploy as a **custom MCP server on Databricks Apps**, reachable at `/mcp` over streamable HTTP, callable from **Genie Code** (and AI Playground).
- Persist the concrete artifact types the skills emit, **versioned per `space_id`**, with parent/lineage pointers.
- Persist to a **single backend: Unity Catalog Delta tables (one per artifact type)** in a `genie_space_history` schema (governed, queryable system-of-record). *(A workspace-file mirror was considered and explicitly dropped — see §7.2.)*
- Provide a **lean MCP tool surface** (Genie Code caps total MCP access at **20 tools across all servers** — see §3), covering write / list / get / diff / rollback.
- Act under the **calling user's identity (OBO)** so artifacts are owned/attributed correctly and Unity Catalog permissions apply.
- Perform **rollback** by re-applying a stored `serialized_space` to the live Space via `w.genie.update_space` (full-replacement + body `etag` for optimistic concurrency), with server-side validation.

### Non-goals

- Not a replacement for the skills' analysis logic — it only **persists and restores**, it does not diagnose or optimize.
- Not a generic data catalog or audit system; scope is Genie-Space artifacts.
- Does **not** mutate source data, source schemas, or non-history workspace assets (mirrors the skills' guardrails).
- No multi-workspace federation in v1 (Genie Code requires the custom MCP app be in the **same workspace**).

---

## 3. Research-grounded context (key constraints)

These facts (from the investigation) directly constrain the design. Confidence + doc links carried where the research provided them.

### Databricks Apps (hosting) — *High confidence*

- Containerized serverless (Ubuntu 22.04, **Python 3.11**, default 2 vCPU / 6 GB), supports **FastAPI/Uvicorn**. Bind to `DATABRICKS_APP_PORT`. `app.yaml` at project root defines `command` + `env`. Deploy via `databricks apps create` / `databricks apps deploy` / `databricks sync` / DABs `resources.apps`.
  - [https://docs.databricks.com/aws/en/dev-tools/databricks-apps/](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/) · /app-runtime · /deploy
- **Every app gets a dedicated service principal** (auto-injected `DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET`).
- **OBO user auth (Public Preview — GA expected soon):** Databricks forwards the user token as the **`X-Forwarded-Access-Token`** header; app code passes it to SDK/SQL calls so the user's UC permissions (row filters, masks) apply. OBO is scope-gated (this server needs `sql` for warehouse queries + the Genie/dashboards scope for rollback). **Availability:** as of this writing OBO is **auto-enabled via the Previews portal for most workspaces**, so it is typically already on in the target workspace — confirm in the Previews portal.
  - [https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)
- **App resources / bindings** grant the app SP a permission: SQL warehouse (`CAN USE`), serving endpoint, secrets, **UC tables (`SELECT`/`MODIFY`)**, UC volumes/functions, **Genie Spaces**, Lakebase. `valueFrom` in `app.yaml` resolves them to env vars.
  - [https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources)
- App URL: `https://<app-name>-<workspace-id>.<region>.databricksapps.com`. Limits: 100 apps/workspace, 10 MB per source file, 15 s graceful shutdown; **no documented fixed per-request timeout** → use async / fast handlers.

### Custom MCP on Apps + Genie Code — *High (basics), Medium (Genie Code caller-identity wire detail)*

- Databricks distinguishes **Managed** (Genie, UC functions, Vector Search, SQL) / **External** (UC HTTP connection) / **Custom** MCP servers. Custom = "Host custom or third-party MCP servers as Databricks apps."
  - [https://docs.databricks.com/aws/en/generative-ai/mcp/custom-mcp](https://docs.databricks.com/aws/en/generative-ai/mcp/custom-mcp)
- Genie Code expects the custom app MCP endpoint at **`/mcp`**, **stateless streamable HTTP** (e.g. `mcp_server.http_app(stateless_http=True)`).
  - [https://docs.databricks.com/aws/en/genie-code/mcp](https://docs.databricks.com/aws/en/genie-code/mcp)
- Connect in Genie Code: **Settings → MCP Servers → Add Server → Custom MCP (select a Databricks App)**. Requirements: **same workspace**, `/mcp`, stateless, **CORS allowlist** for the workspace URL, and **a hard cap of 20 tools total across all MCP servers**.
- **OAuth recommended; PATs are *not* supported for custom MCP.** For per-user artifacts the server should read `X-Forwarded-Access-Token`, call Databricks with that token, and resolve the user via `current_user.me`.
- Genie Code is the **in-workspace** AI coding/data assistant (notebooks, SQL editor, pipelines, dashboards, MLflow) — *not a standalone local CLI*. Skills follow the Agent Skills standard under `.assistant/skills/` (workspace-wide or per-user), auto-loaded by description or invoked `@skill-name`.
  - Reference template: `databricks/app-templates → mcp-server-hello-world` (app name must start with `mcp-` for AI Playground). Labs: `databrickslabs/mcp`.

### Persistence + rollback — *High, with version-gated items flagged*

- **UC writes:** no "INSERT into Delta" REST primitive — all paths run SQL on a **SQL warehouse**. Recommended: SDK `w.statement_execution.execute_statement(...)` (clean for stateless apps; poll if > wait window) or `databricks-sql-connector`. **Always use server-side parameter binding.**
  - [https://databricks-sdk-py.readthedocs.io/en/stable/workspace/sql/statement_execution.html](https://databricks-sdk-py.readthedocs.io/en/stable/workspace/sql/statement_execution.html)
- **Identity = whichever token you hand the client.** OBO → write runs *as the user* (native attribution, UC row filters apply). SP → all writes attributed to the one app SP (you must stamp `created_by` yourself).
- **Per-user isolation** via **row filter** `... RETURN owner = SESSION_USER()` on `created_by` — **but row filters only isolate when reads run as the user (OBO)**; SP reads bypass them and must `WHERE created_by` manually. This is the central identity tension.
  - [https://docs.databricks.com/aws/en/data-governance/unity-catalog/filters-and-masks/manually-apply](https://docs.databricks.com/aws/en/data-governance/unity-catalog/filters-and-masks/manually-apply)
- **Workspace files:** `w.workspace.upload(path, bytes, format=AUTO, overwrite=True)` (+ `mkdirs`); `AUTO` + `.json`/`.txt` stores a **FILE** not a notebook. Import-API request limit ~**10 MB** (snapshots are tiny). OBO writes into the user's own `/Workspace/Users/<email>/...` need no extra grants.
  - [https://databricks-sdk-py.readthedocs.io/en/latest/workspace/workspace/workspace.html](https://databricks-sdk-py.readthedocs.io/en/latest/workspace/workspace/workspace.html) · [https://docs.databricks.com/api/workspace/workspace/import](https://docs.databricks.com/api/workspace/workspace/import)
- **`serialized_space` shape:** a `GenieSpace` has **outer** metadata (`space_id`, `title`, `description`, `warehouse_id`, `parent_path`) **plus** an inner **`serialized_space`** JSON-encoded *string* (double-escaped — parse twice). `title`/`description`/`warehouse_id` live in the **outer** object, *not* inside `serialized_space`. Top-level inner keys include `version` (2), `config.sample_questions[]`, `data_sources.tables[]/.metric_views[]`, etc.
  - [https://learn.microsoft.com/en-us/azure/databricks/genie/conversation-api](https://learn.microsoft.com/en-us/azure/databricks/genie/conversation-api)
- **Validation rules on restore** (from Genie API guidance / corroborated by the genie-workbench fix-agent conventions): 32-char lowercase-hex IDs, required sorting, uniqueness constraints, size limits. Capture an **`etag`** at snapshot time for **optimistic-lock** on rollback.

---

## 4. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ Databricks Workspace                                                   │
│                                                                        │
│  Genie Code (Agent mode)                                               │
│   ├─ skill: diagnose-genie-space   ──┐                                 │
│   ├─ skill: optimize-genie-space   ──┤  @-invoke / auto-load           │
│   ├─ skill: optimize-genie-query   ──┤                                 │
│   └─ Settings → MCP Servers → [this app]                               │
│                  │ MCP over streamable HTTP (OAuth, X-Forwarded-...)   │
│                  ▼                                                      │
│  Databricks App:  mcp-genie-space-history                              │
│   ┌────────────────────────────────────────────────────────────────┐ │
│   │ FastAPI + MCP server  (stateless_http=True)  → mounted at /mcp   │ │
│   │  • Auth layer:  read X-Forwarded-Access-Token → OBO WorkspaceClient│
│   │  • Tool handlers (see §6)                                        │ │
│   │  • Storage adapter:   UC Delta tables (per type) x7             │ │
│   │  • Genie adapter:  read / update serialized_space (rollback)     │ │
│   └────────────────────────────────────────────────────────────────┘ │
│        │ execute_statement (OBO)                                       │
│        ▼                                                                │
│  UC tables: genie_space_history.*                                      │
│        │ Genie API (OBO)                                               │
│        ▼                                                                │
│  Genie Space  (serialized_space)  ← rollback re-applies a snapshot     │
└──────────────────────────────────────────────────────────────────────┘
```

**Components**

1. **HTTP/MCP layer** — FastAPI app exposing the MCP server at `/mcp`, stateless streamable HTTP, CORS-allowlisted to the workspace URL.
2. **Auth layer** — per-request: extract `X-Forwarded-Access-Token`, build an OBO `WorkspaceClient`, resolve `current_user.me`. Never cache the user client.
3. **Storage adapter** — `UCTableStore` (the sole backend) behind a `write` / `list` / `get` / `diff` interface.
4. **Genie adapter** — `w.genie.get_space(include_serialized_space=True)` to read `serialized_space` + `etag`; `w.genie.update_space(...)` (full-replacement, body `etag`) to re-apply for rollback. No Genie Code native config-update tool exists, so the server owns this.

---

## 5. Identity & auth model

**Recommendation: OBO end-to-end for all artifact reads, writes, and rollbacks.** Rationale:

- Artifacts are attributed to the real human (native `created_by`), not a single shared SP.
- UC **row filters isolate per user only when reads run as the user** — OBO makes per-user history "just work."
- Rollback edits the Space under the user's own Genie permissions (correct authorization boundary).

**App service principal** is used only for **bootstrap/admin**: auto-creating the `genie_space_history` schema + the seven per-artifact tables at startup (catalog must pre-exist; SP granted `CREATE SCHEMA`), applying the row-filter function, granting the OBO user group, and health checks. It is *not* the write actor for user artifacts.

**Required OAuth scopes for OBO:** `sql` (warehouse writes/reads) plus the Genie/dashboards scope for the rollback update — declared explicitly as the app's **`user_api_scopes`** (`sql`, `genie`, `dashboards`); a deployed app's OBO token otherwise defaults to **identity-only scopes** and warehouse/Genie calls fail (P0 finding **F-6**). *(No `files.files` scope — this server does not write workspace files.)* The OBO user must also hold the **Genie Space permission** to read/update the config — reading `serialized_space` requires **CAN EDIT**; the exact permission for `update_space` is **not documented** (REST ref, SDK, Conversation API guide) — best inference from the [Genie Space ACL matrix](https://docs.databricks.com/aws/en/security/auth/access-control/#genie-space-acls) is **at least CAN EDIT** (CAN MANAGE also works); verify at runtime.

**Failure mode:** if the forwarded token lacks a needed scope (admin-restricted), the tool returns a structured `scope_error` telling the user which scope to enable — never silently falls back to SP for a user-scoped write.

> ℹ️ **OBO availability:** OBO is **Public Preview and expected to GA soon**. As of this writing it is **auto-enabled through the Previews portal for most workspaces**, so it is typically already on in the target workspace — confirm it's enabled in Previews before relying on it. Keep a feature flag so the server degrades gracefully if a particular workspace hasn't enabled it yet.

---

## 6. MCP tool surface

**Design driver: the 20-tools-across-all-servers cap.** Keep this server **lean** so it doesn't starve the user's other MCP servers. Proposed **6 tools** (leaves 14 for everything else). A **minimal 4-tool** fallback is noted if budget is tight.


| #   | Tool                      | Purpose                                                                                                            | Key inputs                                                                                                                                                       | Returns                                                                   |
| --- | ------------------------- | ------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| 1   | `save_config_snapshot`    | Capture a Genie Space config version (the mandatory before/after snapshot).                                        | `space_id`, `serialized_space` (or `fetch_live=true` to pull it), `version_label`, `parent_config_version_id`, `run_id?`, `changed_surfaces?`, `change_summary?` | `config_version_id`, `version`, `config_hash`, `etag`                     |
| 2   | `save_report`             | Persist a Markdown artifact (diagnose write-up, query-optimization report, design proposal, metric-view YAML/DDL). | `space_id`, `artifact_type`, `title`, `content_md`, `run_id?`, `scores_findings?`                                                                                | `artifact_id`                                                             |
| 3   | `record_optimization_run` | Persist a tuning run: run summary + per-question eval results + decision (the `runs/` + `eval_results/` records).  | `space_id`, `run_id`, run fields (see §7), `eval_results[]`, `decision`                                                                                          | `run_id`                                                                  |
| 4   | `list_history`            | Timeline of versions/runs/reports for a Space.                                                                     | `space_id`, `artifact_type?`, `limit?`, `since?`                                                                                                                 | array of `{id, type, version, created_at, created_by, summary, decision}` |
| 5   | `get_artifact`            | Fetch one stored item (full config JSON, report MD, run record).                                                   | `id` (config_version_id / artifact_id / run_id)                                                                                                                  | full record incl. `config_json` / `content_md`                            |
| 6   | `rollback_config`         | Re-apply a stored config version to the live Genie Space, recording a new "rollback" version.                      | `space_id`, `config_version_id`, `expected_etag?`, `dry_run?`                                                                                                    | new `config_version_id`, applied `etag`, validation report                |


**Helper (optional 7th):** `diff_configs(space_id, from_version_id, to_version_id)` → structured JSON diff of `serialized_space` (changed surfaces + before/after). Can also be implemented client-side by the skill from two `get_artifact` calls to save a tool slot.

**Minimal 4-tool fallback** (if 20-tool budget is contested): collapse 1–3 into a single generic `save_artifact(artifact_type, payload)`; keep `list_history`, `get_artifact`, `rollback_config`. Trades agent ergonomics/clarity for budget.

**Tool-design rules**

- Every tool takes `space_id`; every write stamps `created_by` (from `current_user.me`) and `created_at` server-side.
- All inputs validated against the field contracts in §7; reject unknown `artifact_type`. Writes **route to the per-artifact table** (§7.1); `list_history` UNIONs across the tables and `get_artifact` resolves an id across them.
- Idempotency: `save_*` accepts a client-supplied `idempotency_key` (e.g. `config_hash`) to avoid duplicate rows on retry.
- `rollback_config` supports `dry_run` (validate + diff, do not apply) and `expected_etag` (optimistic lock); it captures snapshots via `w.genie.get_space(include_serialized_space=True)` and applies the restore via `w.genie.update_space(...)` (see §8).

---

## 7. Data model

The schema **deliberately aligns with `optimize-genie-space/references/optimization-guide.md`** so the skill's existing field definitions and the service speak the same shape. **Unity Catalog Delta tables are the sole backend** — separate tables per artifact type, no workspace-file mirror (see §7.2 for the rationale).

### 7.1 UC Delta tables (system-of-record)

**Separate tables per artifact type** (decision — §12 #6), all under one schema **`${HISTORY_CATALOG}.genie_space_history`** (`HISTORY_CATALOG` = a deployment-configured, **pre-existing** catalog the operator picks; the schema name is fixed at `genie_space_history`). Each artifact's shape stays clean and independently queryable; `list_history` UNIONs and `get_artifact` resolves an id across them.

**(1) `config_snapshots`** — versioned Space config; the rollback-critical table.

```sql
CREATE TABLE IF NOT EXISTS ${HISTORY_CATALOG}.genie_space_history.config_snapshots (
  config_version_id   STRING    NOT NULL,        -- 32-char hex UUID, logical PK
  space_id            STRING    NOT NULL,
  version             BIGINT    NOT NULL,         -- monotonic per space_id (1,2,3…)
  parent_version_id   STRING,                     -- parent_config_version_id → rollback lineage
  created_at          TIMESTAMP DEFAULT current_timestamp(),
  created_by          STRING    DEFAULT current_user(),  -- attribution + row-filter key
  skill_name          STRING,
  config_json         STRING,                     -- JSON serialized_space; opt-in VARIANT on DBR >= 15.3
  config_hash         STRING,                     -- dedupe / integrity / idempotency key
  diff_patch          STRING,                     -- JSON diff vs parent (opt-in VARIANT)
  changed_surfaces    ARRAY<STRING>,              -- ['join_specs','column_configs',…]
  etag                STRING,                     -- Genie space etag at capture (rollback optimistic-lock)
  run_id              STRING,                     -- ties to an optimization_runs.run_id
  rollback_reference  STRING,                     -- set if this version was produced by a rollback
  change_summary      STRING
) USING DELTA TBLPROPERTIES (delta.enableRowTracking = true);
```

**(2) `optimization_runs`** — one row per tuning run (mirrors the skill's `runs/`).

```sql
CREATE TABLE IF NOT EXISTS ${HISTORY_CATALOG}.genie_space_history.optimization_runs (
  run_id                   STRING NOT NULL,        -- logical PK
  space_id                 STRING NOT NULL,
  created_at               TIMESTAMP DEFAULT current_timestamp(),
  created_by               STRING DEFAULT current_user(),
  baseline_score           DOUBLE,
  candidate_score          DOUBLE,
  score_delta              DOUBLE,
  fixed_count              INT,
  regressed_count          INT,
  unchanged_count          INT,
  excluded_count           INT,
  decision                 STRING,                 -- accepted | rejected | partial …
  parent_config_version_id STRING,                 -- snapshot the run started from
  result_config_version_id STRING,                 -- snapshot the run produced
  change_summary           STRING
) USING DELTA TBLPROPERTIES (delta.enableRowTracking = true);
```

**(3) `eval_results`** — per-question eval rows for a run (mirrors the skill's `eval_results/`).

```sql
CREATE TABLE IF NOT EXISTS ${HISTORY_CATALOG}.genie_space_history.eval_results (
  eval_run_id             STRING NOT NULL,         -- logical PK
  run_id                  STRING NOT NULL,         -- FK → optimization_runs.run_id
  space_id                STRING NOT NULL,
  created_at              TIMESTAMP DEFAULT current_timestamp(),
  created_by              STRING DEFAULT current_user(),
  question_id             STRING,
  assessment              STRING,                  -- pass | fail | …
  primary_failure         STRING,
  baseline_sql_hash       STRING,
  candidate_sql_hash      STRING,
  baseline_result_digest  STRING,
  candidate_result_digest STRING,
  latency_ms              BIGINT
) USING DELTA TBLPROPERTIES (delta.enableRowTracking = true);
```

**(4) Report-family tables** — `diagnose_reports`, `query_reports`, `design_proposals`, `metric_view_artifacts` (one table per artifact type; structurally identical, so each is created from this single template):

```sql
CREATE TABLE IF NOT EXISTS ${HISTORY_CATALOG}.genie_space_history.<report_table> (
  artifact_id         STRING    NOT NULL,          -- logical PK
  space_id            STRING    NOT NULL,
  created_at          TIMESTAMP DEFAULT current_timestamp(),
  created_by          STRING    DEFAULT current_user(),
  skill_name          STRING,
  title               STRING,
  content_md          STRING,                       -- write-up / report / proposal / DDL or YAML
  summary             STRING,
  scores_findings     STRING,                        -- JSON: optional structured findings (opt-in VARIANT)
  run_id              STRING,                         -- optional link to an optimization run
  config_version_id   STRING,                         -- optional link to a config snapshot
  redacted            BOOLEAN   DEFAULT true
) USING DELTA TBLPROPERTIES (delta.enableRowTracking = true);
```

> `metric_view_artifacts.content_md` carries the metric-view **YAML/DDL**; the body column is kept generic so all four reports share one template. These four are the one place where artifacts of *different* type share a shape — they can be collapsed into a single `reports` table with a `report_type` column if you ever want fewer objects; the current decision keeps them split.

> **DDL note (P0 finding F-4):** every `CREATE TABLE` above uses column `DEFAULT`s (`current_timestamp()`, `current_user()`), which require **`delta.feature.allowColumnDefaults = 'supported'`** in `TBLPROPERTIES` (alongside `delta.enableRowTracking`). The first spike provision failed without it — add it to each table's `TBLPROPERTIES`.

> **JSON columns default to `STRING`.** `VARIANT` is **Public Preview (not GA)** and requires DBR/SQL **≥ 15.3** ([VARIANT type](https://docs.databricks.com/aws/en/sql/language-manual/data-types/variant-type), [variant table feature](https://docs.databricks.com/aws/en/tables/features/variant)) — a customer-deployable server should not hard-require a Preview feature, so default to `STRING` (query via `col:path` / `from_json(...)`) and treat **`VARIANT` as an opt-in** once confirmed available on the target warehouse. Note `parse_json()` *returns* `VARIANT`, so it is not a STRING-mode fallback. *(High confidence — PrPr + version-gated.)*

**Per-user isolation — apply the same row filter to every table:**

```sql
CREATE FUNCTION IF NOT EXISTS ${HISTORY_CATALOG}.genie_space_history.only_mine(owner STRING)
  RETURN owner = SESSION_USER();
-- for each table T in (config_snapshots, optimization_runs, eval_results,
--                      diagnose_reports, query_reports, design_proposals, metric_view_artifacts):
ALTER TABLE ${HISTORY_CATALOG}.genie_space_history.<T>
  SET ROW FILTER ${HISTORY_CATALOG}.genie_space_history.only_mine ON (created_by);
```

(Only enforces when reads run as the user — i.e. OBO. See §5.)

**Provisioning & grants (decision — §12 #6):**

- The **catalog (`HISTORY_CATALOG`) must already exist** and is **never auto-created** by the app.
- The operator **grants the app service principal** `USE CATALOG` + `CREATE SCHEMA` on `HISTORY_CATALOG`.
- On first run the app SP **auto-creates** (idempotent `… IF NOT EXISTS`) the `genie_space_history` **schema**, the **seven per-artifact tables**, and the `only_mine` function; as owner it applies the row filter to each table and grants the configured OBO user group (`HISTORY_GRANTEE`) `USE CATALOG`/`USE SCHEMA` + `SELECT`,`MODIFY`, so per-user OBO reads/writes resolve under the row filter.
- Net: the OBO **writer** needs `USE CATALOG`, `USE SCHEMA`, `SELECT`,`MODIFY` on the tables (granted at bootstrap); the **app SP** needs catalog-level `CREATE SCHEMA` only. The app SP never creates or owns the catalog.

### 7.2 Why no workspace-file mirror

A workspace-file mirror (writing the skill's `/Workspace/Users/<email>/genie_optimization/<space_id>/` layout) was **considered and explicitly dropped** for this MCP:

- **One persistence path, no divergence.** A second store needs a system-of-record + best-effort mirror + consistency handling — not worth it when the UC table already provides history + rollback.
- **The UC table covers the user-facing need** via `list_history` / `get_artifact`, and adds querying / aggregation / governance that loose files can't.
- **Simpler auth surface:** UC-only needs `sql` + the Genie scope and drops the `files.files` workspace-write path entirely.

Consequence for the skill: the `optimize-genie-space` skill currently writes that local layout itself. With this MCP as the backend, that local persistence should be **reconciled** — either kept strictly as the *no-MCP fallback* or removed in favor of requiring the MCP. See §9 and §12 #5.

### 7.3 Privacy / data minimization

Carry over the skill's rules (`optimization-guide.md`): store hashes/digests/row-counts/summaries by default; store raw SQL/result samples only when needed to reproduce a decision; **redact sensitive literals** in questions, SQL, judge notes, errors, and config text. The server enforces a `redact=true` default on report payloads.

---

## 8. Rollback design

**Resolved API (High confidence).** Genie Spaces expose first-class read + update REST/SDK operations, and **no Genie Code native config-update tool exists** (the managed Genie MCP servers are read-only). So the MCP applies rollback itself via the Genie API (**path X**):


| Operation        | REST                                                                 | SDK                                                                                                                 | Notes                                                                                                                        |
| ---------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Read / snapshot  | `GET /api/2.0/genie/spaces/{space_id}?include_serialized_space=true` | `w.genie.get_space(space_id, include_serialized_space=True)`                                                        | Returns `GenieSpace` incl. `etag`, `serialized_space`, outer fields. Requires **CAN EDIT**.                                  |
| Update / restore | `PATCH /api/2.0/genie/spaces/{space_id}`                             | `w.genie.update_space(space_id, serialized_space=…, title=…, description=…, warehouse_id=…, parent_path=…, etag=…)` | `serialized_space` is a **full replacement**, sent as a JSON-**escaped string** at the top level (siblings: outer metadata). |


Optimistic concurrency is a **body `etag` field** (not an `If-Match` header): pass it and the update *fails if the space changed since*; omit it to apply unconditionally. **Requires `databricks-sdk ≥ 0.118.0`** — earlier SDKs (e.g. 0.102.0) have no `etag` field on `GenieSpace`/`update_space`, so optimistic locking silently cannot run (P0 finding **F-1**; pin the SDK floor). The `etag` is **content-based** (P0 **F-5**); a non-matching etag is rejected with `Aborted` — the spike proved rejection of a *non-matching* etag, but a truly *stale-after-real-edit* etag was not separately tested. CLI equivalents exist (`databricks genie get-space` / `update-space`) but the CLI does not document `include_serialized_space`, so don't rely on it for snapshot capture.

**Flow:**

1. **Snapshot first (enforced).** `save_config_snapshot` (`fetch_live=true`) calls `get_space(..., include_serialized_space=True)` and stores `serialized_space` + outer metadata + `config_hash` + the Space `etag` *before* any edit. Refuse to proceed if the snapshot fails (mirrors the skill's hard rule).
2. **Lineage.** `parent_version_id` + `run_id` + `baseline/candidate` pointers reconstruct the version DAG.
3. **`rollback_config`** flow:
  - Load the target version's stored `config_json` (+ outer metadata).
  - **`dry_run`:** re-validate against the documented rules (`version: 2`; 32-char lowercase-hex IDs; required sorting of tables/metric-views/columns/ID-arrays; uniqueness; string ≤ 25,000 chars, repeated fields ≤ 10,000 items, ≤ 1 text instruction; three-level `catalog.schema.table` identifiers; join-spec shape) and return a diff vs the live space — **no write**.
  - Re-read the live space for the current `etag`; if `expected_etag` is supplied and differs → return `conflict` (someone edited since).
  - **Re-apply** via `update_space(..., serialized_space=<stored>, etag=<chosen>)` under OBO; Databricks validates the payload server-side and rejects invalid JSON.
  - Record a **new** `config_version` (`artifact_type=config_snapshot`, `change_summary="rollback to <id>"`, `parent_version_id=<live>`) — rollback is itself versioned (forward-only; never destructive).

> **Permission note:** reading `serialized_space` requires **CAN EDIT** on the space; the docs do **not** name the exact permission `update_space` requires (best inference: at least CAN EDIT per the Genie Space ACL matrix, CAN MANAGE also works — verify at runtime via the P0 round-trip). The calling identity (the OBO user) must hold it. *(See §12 #1.)*

Docs: REST `genie/updatespace` + `genie/getspace`; SDK `w.genie.update_space` / `get_space`; guide `genie/conversation-api#understanding-the-serialized_space-field`.

---

## 9. Skill integration


| Skill                  | Calls                                                                                                                                  | When                                                                                                                  |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `diagnose-genie-space` | `save_report(artifact_type="diagnose_report")`                                                                                         | After producing the Diagnostic Write-Up (gives it durable history; today it persists nothing).                        |
| `optimize-genie-space` | `save_config_snapshot` (before edit, mandatory) → `record_optimization_run` (after eval) → `rollback_config` (on a ROLL BACK decision) | Replaces hand-written `config_versions/` + `runs/` files; makes "ROLL BACK" in the Acceptance Decision a real action. |
| `optimize-genie-query` | `save_report(artifact_type="query_report")`                                                                                            | After producing the query-optimization report.                                                                        |
| `create-genie-space`   | `save_report(artifact_type="design_proposal")` + optional `save_config_snapshot` on first apply                                        | Capture the initial proposal + the v1 config baseline.                                                                |
| `create-metric-view`   | `save_report(artifact_type="metric_view_ddl")`                                                                                         | Snapshot the approved YAML/DDL for change history.                                                                    |


Integration is **opt-in and additive**: skills detect the MCP server's tools and use them when present. **Decision (option B):** `optimize-genie-space` **keeps** its current local workspace-file layout strictly as the *no-MCP fallback*, so the mandatory pre-edit rollback snapshot still happens when the server isn't connected; the MCP is the durable, queryable, governed *upgrade* used when connected. `optimization-guide.md`'s field schema is **retained as the shared contract** the UC table mirrors. **This skill edit is deferred and is NOT part of building the MCP server** — it is a tracked follow-up (see §13, “Skill reconciliation”); do not edit the skills as part of MCP development. (The short `SKILL.md` notes pointing at the tools are bundled into that same follow-up — a docs change.)

---

## 10. Deployment & operations

- **App name** must start with `mcp-` (e.g. `mcp-genie-space-history`) for AI Playground recognition.
- **`app.yaml`** (sketch):
  ```yaml
  command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
  env:
    - name: HISTORY_CATALOG
      value: <pre-existing catalog>      # schema genie_space_history is auto-created inside it
    - name: HISTORY_GRANTEE
      value: <user group>                # OBO users granted SELECT/MODIFY at bootstrap
    - name: SQL_WAREHOUSE_ID
      valueFrom: sql-warehouse           # warehouse resource
  ```
- **App resources to bind:** SQL warehouse (`CAN USE`) and (for rollback) Genie Space resources. Separately, **grant the app SP `USE CATALOG` + `CREATE SCHEMA` on `HISTORY_CATALOG`** (SQL grant) so it can auto-create the schema + tables; it then owns them and grants `HISTORY_GRANTEE`. Bind secrets only if needed.
- **MCP mount:** `mcp_server.http_app(stateless_http=True)` mounted at `/mcp`; **CORS allowlist** the workspace URL.
- **Bind to** `DATABRICKS_APP_PORT`; handle SIGTERM within 15 s; keep handlers fast (no fixed per-request timeout documented → avoid long synchronous work; poll `execute_statement` rather than blocking).
- **Deploy** via DABs (`resources.apps`) for reproducibility, or `databricks apps deploy`. Start from `databricks/app-templates → mcp-server-hello-world`.
- **Bootstrap on startup (app SP):** auto-create the `genie_space_history` schema + the seven per-artifact tables (`CREATE … IF NOT EXISTS`; **the catalog is not created**), create the `only_mine` function, apply the row filter to each table, and grant `HISTORY_GRANTEE` `SELECT`/`MODIFY`. Idempotent.
- **Observability:** structured logs per tool call (user, tool, space_id, latency, outcome); optional MLflow tracing.

---

## 11. Security & governance summary

- OBO-only for user data; SP only for bootstrap (§5).
- UC row filter on `created_by` for per-user isolation; document the SP-read caveat.
- Server-side SQL parameter binding everywhere; no string interpolation of user data.
- Data minimization + redaction defaults (§7.3).
- No anonymous access (Apps disallows it); Genie Code calls are authenticated per user.
- All writes are **append-only / forward-only** — rollback creates a new version, never deletes history.

---

## 12. Open questions & verification items

1. **Genie Space update API — RESOLVED (High confidence).** Rollback uses `PATCH /api/2.0/genie/spaces/{space_id}` / SDK `w.genie.update_space(...)`; read/snapshot uses `GET ...?include_serialized_space=true` / `w.genie.get_space(...)`. `serialized_space` is a top-level JSON-escaped **full-replacement** string; concurrency via a body `etag`. No Genie Code native update tool exists (managed Genie MCP is read-only) → the MCP applies the update itself (path X). See §8. **Remaining sub-item (runtime-verify only):** the exact Genie Space permission `update_space` requires is **not documented** anywhere (REST ref, SDK, Conversation API guide). Best inference from the [Genie Space ACL matrix](https://docs.databricks.com/aws/en/security/auth/access-control/#genie-space-acls): **at least CAN EDIT** (grants editing instructions / sample questions / included tables), and **CAN MANAGE** also works. Confirm via the P0 `get_space → update_space` round-trip on a throwaway Space. **P0 result (PR #22):** the round-trip works — verified at **CAN MANAGE** (identical-snapshot restore, `config_hash` unchanged); the **minimum was NOT isolated** (CAN EDIT floor untested with a CAN-EDIT-only principal). **F-1:** the body `etag` requires **`databricks-sdk ≥ 0.118.0`** — earlier SDKs (e.g. 0.102.0) have no `etag` field at all, so optimistic locking silently can't run. **F-5:** the `etag` is content-based; Genie Space ACLs are read via `GET /api/2.0/permissions/genie/{id}`.
2. **OBO availability — RESOLVED (P0 live-workspace check).** Public Preview, **GA expected soon**, **auto-on via the Previews portal for most workspaces**. Action in the target workspace: confirm OBO is enabled in the **Previews portal** and that the app's OAuth scopes include **`sql`** + the **Genie/dashboards** scope. *(No `files.files` — UC-only.)* Keep a feature flag for graceful degradation. Tracked in the P0 spike. **P0 result (PR #22):** OBO is **enabled** in the target workspace — verified end-to-end through the deployed app (`current_user.me()` over `/mcp` returned the calling user via `X-Forwarded-Access-Token`). **F-6:** a deployed app's OBO token defaults to **identity-only scopes** — the app must explicitly declare `user_api_scopes` including **`sql`**, **`genie`**, and **`dashboards`**, else warehouse/Genie calls fail; this is an authorization step for the operator.
3. **`VARIANT` support — RESOLVED (decision: default to `STRING`).** `VARIANT` is **Public Preview, not GA**; requires DBR/SQL **≥ 15.3** (confirmed) and is supported on current SQL warehouses in principle. Because a customer-deployable server should not hard-require a Preview feature, **JSON columns default to `STRING`** (queried via `col:path` / `from_json`), with **`VARIANT` as an opt-in** once verified on the target warehouse (`parse_json` returns VARIANT, so it is not a STRING-mode fallback). Keep a P0 smoke test: `CREATE TABLE (… VARIANT)` + `INSERT … parse_json(...)` on the actual warehouse type/channel. **P0 result (PR #22):** the smoke test **passed** on the target warehouse (`VARIANT` usable; parameterized `parse_json(:payload)` insert works) — so `VARIANT` is available, but the spec default **stays `STRING`** (opt-in `VARIANT`) for portability.
4. **Tool-count budget — RESOLVED.** Ship the **6 core tools** by default; `diff_configs` is an optional 7th and can be folded into `get_artifact` to stay at 6. Document the **4-tool fallback** (§6) for users tight against the 20-tool cap. Guidance: this should be a user's only history MCP — budget accordingly against other connected servers.
5. **Skill reconciliation — RESOLVED (option B).** This MCP persists *only* to a UC table. `optimize-genie-space` **keeps** its local workspace-file layout as the **no-MCP fallback**; the MCP is the upgrade used when connected. Rejected: option (a), removing local persistence and requiring the MCP — that would make the skill unsafe/non-portable for rollback without the server installed. The follow-up skill edit is **deferred** and tracked in §13 (“Skill reconciliation”); the skills are **not** edited as part of MCP server development.
6. **Catalog/schema naming + provisioning — RESOLVED.** **Separate tables per artifact type** under a fixed-name schema **`genie_space_history`** in a deployment-configured, **pre-existing** catalog (`HISTORY_CATALOG`). The app **auto-creates the schema + tables (not the catalog)** on first run; the operator must **grant the app SP `USE CATALOG` + `CREATE SCHEMA`** on that catalog. Configurable: `HISTORY_CATALOG`, `HISTORY_GRANTEE` (schema name fixed). See §7.1 / §10. **P0 result (PR #22):** confirmed — provisioning **as the app SP** failed with `PERMISSION_DENIED: User does not have BROWSE on Catalog '...'` until the grant is applied, empirically validating that the operator must grant the SP `USE CATALOG` + `CREATE SCHEMA` first (the SP's SQL otherwise executes fine on the warehouse). **F-4:** the §7.1 DDL also needs `delta.feature.allowColumnDefaults = 'supported'` in `TBLPROPERTIES` because of the `DEFAULT current_timestamp()` / `current_user()` columns — the first provision failed without it.

## 13. Phased delivery (suggested)

- **P0 — Spike (de-risk before any build).** Goal: settle the runtime-only unknowns and prove the end-to-end mechanics on a throwaway Space, producing a short findings note that flips §12's residual verify-items to confirmed values (or records the fallback chosen). **Inputs the spike needs:** the **target workspace**, a **throwaway Genie Space ID** (spiker holds CAN EDIT / CAN MANAGE), a **pre-existing UC catalog** the app SP can be granted `CREATE SCHEMA` on, and a **SQL warehouse**. **Exit criteria:**
  - [x] **Hosting:** `mcp-server-hello-world` deployed on Databricks Apps; MCP reachable at `/mcp` (stateless streamable HTTP) and connectable from Genie Code.
  - [x] **OBO identity (§12 #2):** an OBO `current_user.me()` call (via `X-Forwarded-Access-Token`) returns the *calling* user — confirms OBO is enabled in the workspace and the `sql` + Genie/dashboards scopes are present.
  - [ ] **Auto-provision (§12 #6):** the app SP (granted `USE CATALOG` + `CREATE SCHEMA`) auto-creates the `genie_space_history` schema + one table via `… IF NOT EXISTS`; the **catalog is not created**.
  - [x] **VARIANT probe (§12 #3):** `CREATE TABLE (… VARIANT)` + `INSERT … parse_json(...)` on the chosen warehouse — succeeds → `VARIANT` usable; fails → default to `STRING`.
  - [ ] **Genie round-trip (§12 #1 sub-item):** `get_space(include_serialized_space=True)` → `update_space(serialized_space=…, etag=…)` re-applies the snapshot on the throwaway Space; **record the minimum permission that actually worked** (CAN EDIT vs CAN MANAGE).
  - [x] **etag concurrency:** a stale-`etag` update is rejected (proves the optimistic lock).
  > **P0 OUTCOME — executed against the target workspace; see [PR #22](https://github.com/hiydavid/databricks-agent-skills/pull/22) (`genie-code/mcp-genie-space-history/`, `FINDINGS.md`):**
  >
  > - ✅ **Hosting** — app deployed, `/mcp` stateless SSE serving, 6 tools listed (the Genie-Code “Add Server” click is the only manual step).
  > - ✅ **OBO identity** — `current_user.me()` over `/mcp` returned the caller; the app must declare `user_api_scopes` `sql`+`genie`+`dashboards` (**F-6**).
  > - 🟡 **Auto-provision** — DDL + `IF NOT EXISTS` idempotency + catalog-not-created verified **as the user**; the **app-SP** path runs as the SP but is **blocked until the operator grants it `USE CATALOG`+`CREATE SCHEMA`** (proven via `PERMISSION_DENIED`). DDL needs `delta.feature.allowColumnDefaults` (**F-4**).
  > - ✅ **VARIANT** usable on the warehouse (default still `STRING`).
  > - 🟡 **Genie round-trip** — works at **CAN MANAGE**; minimum **not isolated** (CAN EDIT floor untested). `etag` needs `databricks-sdk ≥ 0.118.0` (**F-1**).
  > - ✅ **etag** — a **non-matching** etag is rejected (`Aborted`); a truly-stale-after-real-edit etag was not separately tested.
  >
  > **Still open for the real build:** grant the app SP on the catalog; authorize `user_api_scopes`; isolate the true minimum Genie permission; test a truly-stale etag.
- **P1 — Write + read:** `save_config_snapshot`, `save_report`, `list_history`, `get_artifact` against the UC table (OBO + row filter). Wire `diagnose`/`optimize-query` reports.
- **P2 — Runs + rollback:** `record_optimization_run`, `rollback_config` (dry-run → apply with etag). Wire `optimize-genie-space`.
- **P3 — Polish:** `diff_configs`, redaction defaults, observability, DABs packaging.

### Skill reconciliation (deferred follow-up — NOT STARTED)

**Decision: option B** — keep the skills' local persistence as the no-MCP fallback. This is a **separate, deferred workstream from building the MCP server; do not edit the skills now.** When scheduled, it is a docs/prose change to the `genie-code/` skills (no code), best sequenced **after P1–P2** so the skill text points at tools that already exist:

- [ ] `optimize-genie-space/SKILL.md` — reframe the persistence steps to an order of preference: **(1)** if the history MCP is connected, capture snapshots / record runs / perform rollback via its tools; **(2)** otherwise fall back to the local workspace-file layout (current behavior). Keep the *mandatory pre-edit snapshot* guarantee intact under **both** paths.
- [ ] `optimize-genie-space/references/optimization-guide.md` — **retain the field schema** (it is the shared contract the UC table mirrors); relabel the file layout as the *fallback* store, not the primary one; add a short “History MCP” subsection describing the tool-based path.
- [ ] `diagnose-genie-space/SKILL.md` and `optimize-genie-query/SKILL.md` — add a one-line note that the write-up / report can be persisted via `save_report` when the MCP is connected.
- [ ] Do **not** delete any schema definitions — “removing persistence” (option A) was rejected; fallback writing stays.

Owner: TBD.

> Implementation note: every code task above (server scaffold, tool handlers, storage adapters, Genie adapter, tests) should be built by a coding agent and cross-reviewed by a different vendor; the per-skill `SKILL.md` pointers are docs edits. This document is design-only.

