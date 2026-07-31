# Genie Agent Versioning MCP — Design Spec

**Status:** Proposed v2; the current server is a v1 implementation and does not yet satisfy this contract
**Audience:** Engineers building the MCP server and users configuring native Genie Code
**Last updated:** 2026-07-30

> Genie Spaces and Genie Agents are the same Databricks product. This document uses
> **Genie Agent** for the product name while retaining `space_id` only where an existing
> API or stored record still uses that legacy field name.

## 1. Goal

Databricks currently replaces a Genie Agent configuration in place. The MCP provides
durable configuration snapshots so Genie Code can list previous versions and restore one
later with its native Genie Agent tools.

The intended workflow invariant is:

> **Before Genie Code changes a Genie Agent configuration, it first persists a complete
> snapshot through this MCP and proceeds only when the save succeeds.**

The MCP does not read or update Genie Agents. It never calls the Genie API. Genie Code
owns live configuration reads, configuration edits, optimistic concurrency, and rollback
execution through its native tools.

The v2 scope is deliberately narrow:

- Save complete Genie Agent configuration versions supplied by Genie Code.
- List versions for an Agent.
- Retrieve a complete version for inspection or rollback.
- Preserve lineage, rollback references, hashes, actor identity, and timestamps.

Reports, optimization runs, benchmark results, and metric-view artifacts are not part of
the core versioning service.

## 2. Responsibility boundary

### 2.1 MCP responsibilities

- Validate and persist caller-supplied configuration envelopes.
- Generate stable version identifiers.
- Preserve every snapshot event, even when its content matches an older version.
- List and retrieve versions scoped to the requested Agent and calling user.
- Return structured failures that Genie Code treats as blocking before an edit.

### 2.2 Genie Code responsibilities

- Read the current live Agent configuration, including all restorable outer fields.
- Capture the live `etag` with the snapshot as provenance.
- Call the MCP before every native configuration edit.
- Stop without editing when the before-snapshot call fails.
- Perform the native configuration update.
- For rollback, retrieve the target version from the MCP and apply it with native tools.
- Use a freshly read **live** etag for rollback; never use the target version's historical
  etag as the update lock.

### 2.3 What cannot be enforced

An MCP server cannot intercept a native tool call made directly by Genie Code. A user
with `CAN MANAGE` and Auto-Approve enabled allows Genie Code to edit the Agent directly
without an MCP checkpoint.

The current mitigation is a user/workspace prompt instruction. This is behavioral
enforcement, not a security boundary. The server cannot detect a bypass because it does
not read the live Agent or receive platform change events.

Recommended Genie Code instruction:

> Before changing any Genie Agent configuration, first read its complete current
> configuration and save it with the connected `mcp-genie-agent-versioning` server using
> `save_agent_config_version` with reason `before_update` or `before_rollback`. Proceed
> only if the save succeeds, then perform the edit or rollback with Genie Code's native
> tools. Use `list_agent_versions` and `get_agent_version` to select rollback targets. If
> the MCP is unavailable or the save fails, stop without making the edit and tell the
> user. Follow this rule even when Auto-Approve is enabled.

The MCP tool descriptions repeat this instruction. No repository-managed skill files are
required.

## 3. Architecture and identity

The server remains a Python FastAPI/FastMCP application on Databricks Apps, mounted at
`/mcp` over stateless streamable HTTP.

```text
Genie Code native tools
   ├─ read/update/rollback Genie Agent
   └─ call versioning MCP
             │
             ▼
      mcp-genie-agent-versioning
             │ OBO SQL only
             ▼
      UC agent_config_versions
```

All version reads and writes use the caller's OBO identity through a SQL warehouse. The
app service principal is used only for schema/table provisioning.

Required user OAuth scope: `sql`. The MCP needs no `dashboards.genie` scope and no Genie
Agent resource binding because it makes no Genie API calls.

### Privacy model

Without calling the Genie API, the MCP cannot verify that a caller is authorized on an
arbitrary Agent. The safe default is therefore private per-user history, enforced by a UC
row filter on `created_by = SESSION_USER()`.

This means collaborators do not automatically share versions even when they share an
Agent. Team-shared history requires a separate, explicit authorization design; it must
not be enabled merely by removing the row filter, because that could expose configuration
snapshots for Agents a caller cannot access.

## 4. MCP tool surface

Ship three focused tools.

### `save_agent_config_version`

Persist one complete configuration snapshot supplied by Genie Code.

Inputs:

- `space_id`
- `config` — complete restorable configuration, including its capture-time `etag` when
  available
- `reason` — `before_update`, `before_rollback`, or `manual`
- `change_summary?` — brief, single-line summary of the intended change (maximum 200
  characters)

Returns:

- `ok: true`
- `version_id`
- `created_at`
- `created_by`
- `config_hash`

The server generates the version id, timestamp, authenticated creator, envelope format
version, and hash. `created_by` is derived from the OBO identity and is never accepted as
tool input. Every successful call creates a distinct version, even if its configuration
is identical to an older version.

### `list_agent_versions`

List versions for one Agent using cursor pagination.

Inputs: `space_id`, `limit?`, `cursor?`.

Returns summary rows including `version_id`, `reason`, `created_at`, `created_by`,
`config_hash`, and `change_summary`. The cursor is based on
`(created_at, version_id)`.

### `get_agent_version`

Retrieve one complete version.

Inputs: `space_id`, `version_id`.

Both identifiers are required so a version from one Agent is not accidentally selected
for another. The returned configuration's historical `etag` is explicitly labeled as
provenance, not a valid lock for a future update.

## 5. Complete snapshot contract

A version stores a complete, validated, restorable envelope—not only
`serialized_space`:

```json
{
  "format_version": 1,
  "space_id": "...",
  "serialized_space": "{...}",
  "title": "...",
  "description": "...",
  "warehouse_id": "...",
  "parent_path": "...",
  "etag": "..."
}
```

The exact outer fields must be verified against the current native Genie Code read/update
contract before implementation. Newly introduced restorable fields must be preserved in
a forward-compatible envelope rather than silently dropped.

Validation rules:

- `serialized_space` must parse as JSON and satisfy known structural constraints.
- Unknown envelope fields are preserved when safe.
- Payload size is bounded.
- `change_summary`, when provided, must be a single line of at most 200 characters.
- Hashing uses a canonical representation of the restorable configuration fields and
  excludes the historical `etag`.
- `reason` must be one of the three documented values.

Because the MCP does not read the Agent, it validates shape but cannot prove
that a supplied envelope is the current live configuration. That remains part of the
Genie Code prompt contract.

## 6. Data model

One table is sufficient for the core service:

```sql
CREATE TABLE agent_config_versions (
  version_id          STRING    NOT NULL,
  space_id            STRING    NOT NULL,
  reason              STRING    NOT NULL,
  config_envelope     STRING    NOT NULL,
  config_hash         STRING    NOT NULL,
  change_summary      STRING,
  created_at          TIMESTAMP NOT NULL,
  created_by          STRING    NOT NULL
) USING DELTA;
```

Every snapshot event gets a new `version_id`, even when its content hash matches an older
version. `config_hash` is an integrity/content-comparison value, not an idempotency key or
version identity.

## 7. Native edit workflow

For a normal update, Genie Code follows this sequence:

1. Read the complete live configuration and live etag with native tools.
2. Call `save_agent_config_version(reason="before_update")`.
3. If the save fails, stop. Do not edit.
4. Apply the desired configuration using native tools and the appropriate live etag.

The MCP is not part of step 1 or step 4.

## 8. Rollback workflow

Rollback is executed entirely by Genie Code's native tools:

1. Call `list_agent_versions(space_id)` and select a target.
2. Call `get_agent_version(space_id, target_version_id)`.
3. Read the current live Agent configuration and live etag with native tools.
4. Save the current state with reason `before_rollback`.
5. If the save fails, stop. Do not roll back.
6. Apply the target envelope with native tools using the **current live etag**, not the
   target version's captured etag.

Rollback never deletes history. The `before_rollback` snapshot preserves the current
state, so the rollback can itself be undone later.

## 9. Failure and security rules

- The MCP must contain no Genie API client or Agent update code.
- Never accept `created_by` or `created_at` from tool input.
- Never log forwarded access tokens or full configuration payloads.
- Reject invalid snapshot reasons.
- A failed before-save is a blocking result for Genie Code.
- Clearly distinguish the stored historical etag from the fresh live etag needed for an
  update.
- All snapshot writes are append-only; a pre-rollback snapshot creates a new row.
- Health/readiness must not claim ready while snapshots cannot be persisted.

## 10. Migration from v1

The current code is a passive history implementation with five generic artifact tools
and seven tables. V2 keeps the storage-only boundary but narrows the contract to Agent
configuration versioning.

Migration steps:

1. Add `agent_config_versions` with an explicit schema version/migration mechanism.
2. Implement the three v2 tools and the simplified save contract.
3. Keep OBO SQL and per-user row isolation.
4. Import valid v1 snapshots only when a complete restorable envelope can be constructed;
   otherwise preserve them as legacy partial records, not rollback targets.
5. Retire report/evaluation tools from the core service while preserving existing data.

Existing deployments may retain the `genie_space_history` schema during migration. New
deployments should default to `genie_agent_versioning`; changing an existing schema name
is an explicit data migration.

## 11. Acceptance criteria

- The MCP makes zero Genie API calls and contains no mutation tool.
- Invalid or incomplete envelopes cannot be stored as rollback-ready versions.
- Every successful save creates a distinct version, including repeated identical content.
- `created_by` always matches the authenticated OBO user and cannot be supplied by the
  caller.
- Multiline or over-200-character change summaries are rejected.
- List pagination is deterministic and every get is scoped by `space_id`.
- A stored version contains every field required by Genie Code's native restore path.
- The recommended prompt is tested end-to-end for update and rollback, including with
  Auto-Approve enabled.
- Tests prove the prompt workflow stops before a native edit when the before-save fails.

Describe the system as a **prompt-routed configuration version store**, not as an update
gateway or universally enforced versioning system.
