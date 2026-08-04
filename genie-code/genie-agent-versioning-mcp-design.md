# Genie Agent Versioning MCP — Design Spec

**Status:** Implemented in server v2
**Audience:** Engineers building the MCP server and users configuring native Genie Code
**Last updated:** 2026-08-03

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

The MCP reads Genie Agents only to capture snapshots; it never updates them. Genie Code
owns configuration edits, optimistic concurrency, and rollback execution through its
native tools.

The v2 scope is deliberately narrow:

- Fetch and save complete live Genie Agent configuration versions.
- List versions for an Agent.
- Retrieve a complete version for inspection or rollback.
- Preserve lineage, rollback references, hashes, actor identity, and timestamps.

Reports, optimization runs, benchmark results, and metric-view artifacts are not part of
the core versioning service.

## 2. Responsibility boundary

### 2.1 MCP responsibilities

- Fetch the complete live configuration as the calling user, validate it, and persist it.
- Generate stable version identifiers.
- Preserve every snapshot event, even when its content matches an older version.
- List and retrieve versions scoped to the requested Agent and calling user.
- Return structured failures that Genie Code treats as blocking before an edit.

### 2.2 Genie Code responsibilities

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

> Before changing any Genie Agent configuration, call `save_agent_config_version` on the
> connected `mcp-genie-agent-versioning` server with the Agent's `space_id` and reason
> `before_update` or `before_rollback`. The MCP fetches the complete live configuration
> directly. Proceed only if the save succeeds, then perform the edit or rollback with
> Genie Code's native tools. Use `list_agent_versions` and `get_agent_version` to select
> rollback targets. If the MCP is unavailable or the save fails, stop without making the
> edit and tell the user. Follow this rule even when Auto-Approve is enabled.

The MCP tool descriptions repeat this instruction. No repository-managed skill files are
required.

## 3. Architecture and identity

The server remains a Python FastAPI/FastMCP application on Databricks Apps, mounted at
`/mcp` over stateless streamable HTTP.

```text
Genie Code ──call──▶ mcp-genie-agent-versioning
                         ├─ OBO GET ──▶ Genie Agent
                         └─ OBO SQL ──▶ UC agent_config_versions

Genie Code ──native tools──▶ update/rollback Genie Agent
```

The snapshot fetch and all version reads/writes use the caller's OBO identity. The app
service principal is used only for schema/table provisioning.

Required user OAuth scopes: `dashboards.genie` for the live snapshot read and `sql` for
version persistence. Fetching `serialized_space` also requires CAN EDIT on the Agent.

### Privacy model

The snapshot read verifies that the caller can edit the requested Agent. Version history
remains private per user, enforced by a UC row filter on
`created_by = SESSION_USER()`.

This means collaborators do not automatically share versions even when they share an
Agent. Team-shared history requires a separate, explicit authorization design; it must
not be enabled merely by removing the row filter, because that could expose configuration
snapshots for Agents a caller cannot access.

## 4. MCP tool surface

Ship three focused tools.

### `save_agent_config_version`

Fetch and persist one complete live configuration snapshot.

Inputs:

- `space_id`
- `reason` — `before_update`, `before_rollback`, or `manual`
- `change_summary?` — brief, single-line summary of the intended change (maximum 200
  characters)
- `parent_version_id?` — optional same-Agent lineage reference
- `rollback_target_version_id?` — required for `before_rollback`; identifies the
  same-Agent version that will be applied

Returns:

- `ok: true`
- `version_id`
- `created_at`
- `created_by`
- `config_hash`

The server calls Get Genie Agent with `include_serialized_space=true`, then generates the
version id, timestamp, authenticated creator, envelope format version, and hash.
`created_by` and configuration content are never accepted as tool input. Every successful
call creates a distinct version, even if its configuration is identical to an older
version.

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
  "parent_path": "..."
}
```

The server constructs this envelope from the live Genie API response. `description` and
`parent_path` may be null. Legacy stored envelopes may also contain a capture-time `etag`.

Validation rules:

- `serialized_space` must parse as JSON and contain an integer `version`, object
  `instructions`, and object `data_sources`. Legacy exports with an object `config` in
  place of `instructions` remain accepted. Known data-source collections must be arrays.
  This rejects status notes and benchmark summaries that are JSON objects but are not
  restorable Genie exports.
- Unknown envelope fields are preserved when safe.
- Payload size is bounded to 5 MiB by default and is operator-configurable.
- `change_summary`, when provided, must be a single line of at most 200 characters.
- Hashing uses sorted compact JSON, parses `serialized_space` before hashing so formatting
  is insignificant, includes preserved restorable fields, and excludes historical `etag`,
  `space_id`, `format_version`, and event metadata.
- `reason` must be one of the three documented values.

Because the MCP obtains the export directly, the model never needs to view, reconstruct,
or relay the serialized payload. The Genie read and SQL write are one MCP operation, but
they are separate services and therefore not a distributed transaction.

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
  parent_version_id   STRING,
  rollback_target_version_id STRING,
  created_at          TIMESTAMP NOT NULL,
  created_by          STRING    NOT NULL
) USING DELTA;
```

Every snapshot event gets a new `version_id`, even when its content hash matches an older
version. `config_hash` is an integrity/content-comparison value, not an idempotency key or
version identity.

## 7. Native edit workflow

For a normal update, Genie Code follows this sequence:

1. Call `save_agent_config_version(space_id, reason="before_update")`.
2. If the save fails, stop. Do not edit.
3. Read any live state/etag needed by the native update tool.
4. Apply the desired configuration using native tools and the appropriate live etag.

The MCP performs the live snapshot read in step 1 but remains outside the native update.

## 8. Rollback workflow

Rollback is coordinated by Genie Code using the MCP and native tools:

1. Call `list_agent_versions(space_id)` and select a target.
2. Call `get_agent_version(space_id, target_version_id)`.
3. Save the current state with reason `before_rollback`; the MCP reads it directly.
4. If the save fails, stop. Do not roll back.
5. Read the current live etag with native tools.
6. Apply the target envelope with native tools using the **current live etag**, not the
   target version's captured etag.

Rollback never deletes history. The `before_rollback` snapshot preserves the current
state, so the rollback can itself be undone later.

## 9. Failure and security rules

- The MCP may call the read-only Get Genie Agent API but must contain no Agent update code.
- Never accept `created_by` or `created_at` from tool input.
- Never log forwarded access tokens or full configuration payloads.
- Reject invalid snapshot reasons.
- A failed before-save is a blocking result for Genie Code.
- Clearly distinguish the stored historical etag from the fresh live etag needed for an
  update.
- All snapshot writes are append-only; a pre-rollback snapshot creates a new row.
- Health/readiness must not claim ready while snapshots cannot be persisted.

## 10. Migration from v1

The original code was a passive history implementation with five generic artifact tools
and seven tables. V2 narrows the contract to Agent configuration versioning.

Migration steps:

1. Add `agent_config_versions` as the v2 configuration history table.
2. Implement the three v2 tools and the simplified save contract.
3. Keep OBO SQL and per-user row isolation.
4. Preserve v1 snapshots as legacy partial records. The shipped v1 schema did not retain
   every required outer restore field, so the server does not automatically promote them
   to rollback-ready versions.
5. Retire report/evaluation tools from the core service while preserving existing data.

Existing deployments may retain the `genie_space_history` schema during migration. New
deployments should default to `genie_agent_versioning`; changing an existing schema name
is an explicit data migration.

## 11. Acceptance criteria

- Each save reads the live Agent directly and the MCP contains no Genie mutation tool.
- The serialized export never passes through model context or MCP tool arguments.
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
