# Genie Agent Versioning MCP — Design Spec

**Status:** Proposed v2; the current server is a v1 implementation and does not yet satisfy this contract  
**Audience:** Engineers building the MCP server and owners of the native Genie Code experience  
**Last updated:** 2026-07-30

> Genie Spaces and Genie Agents are the same Databricks product. This document uses
> **Genie Agent** for the product name while retaining `space_id` only where the existing
> REST/SDK surface still uses that legacy field name.

## 1. Goal

Databricks currently replaces a Genie Agent configuration in place. The v2 server
provides a guarded mutation path built around this invariant:

> **A Genie Agent configuration must not be mutated until a durable snapshot of the
> current live configuration has been persisted successfully.**

For every update or rollback routed through the MCP, the server also captures the
resulting live configuration as a new version. History is append-only: rollback creates
a new version; it never deletes or rewrites an older version. Direct native edits remain
possible on Databricks and are outside this guarantee.

The v2 scope is deliberately narrow:

- Version complete Genie Agent configurations.
- Apply guarded configuration changes.
- List and retrieve versions.
- Roll back through the same guarded mutation path.
- Attribute operations to the calling user and enforce the Agent's native permissions.

Reports, optimization runs, benchmark results, and metric-view artifacts are not part of
the core versioning service. They can be added later as a separate extension.

## 2. What the MCP can and cannot enforce

The MCP can strictly enforce snapshot-before-update inside its own mutation tools. It
cannot force Genie Code to select those tools instead of Databricks' native edit path.

### 2.1 Guarded mutation guarantee — implemented by this MCP

The MCP owns the entire mutation workflow in one tool call:

```text
validate request
      ↓
read current Agent configuration + live etag as the user
      ↓
persist durable before-version
      ↓ only after persistence succeeds
update Agent using that same live etag
      ↓
read resulting live configuration
      ↓
persist durable after-version
```

The MCP never exposes a write tool that can skip the before snapshot. A snapshot failure
must prove that no Genie update API call occurred.

### 2.2 Client routing — prompt-based, best effort

An MCP server cannot intercept a native tool call made directly by its client. If Genie
Code retains a separate native `update_space`/configuration-edit path, the server cannot
technically force Genie Code to call the MCP first. In particular, a user with
`CAN MANAGE` and Auto-Approve enabled allows Genie Code to edit the Agent directly on the
user's behalf without an MCP checkpoint.

The current mitigation is a user/workspace prompt instruction that tells native Genie
Code to route every Agent configuration mutation through this MCP. This is behavioral
enforcement, not a security boundary. No custom repository skill integration is needed.

Recommended instruction:

> Before changing any Genie Agent configuration, always use the connected
> `mcp-genie-agent-versioning` server. For a normal edit, call
> `apply_agent_config_change`; for a restore, call `rollback_agent_config`. Never use a
> native Genie Agent configuration-update tool directly. If the MCP is unavailable or
> returns anything other than success, stop without editing and tell the user. Follow
> this rule even when Auto-Approve is enabled.

The MCP tool descriptions repeat this instruction, but neither the prompt nor tool
descriptions can prevent a client-side bypass. The v2 project therefore does not claim a
hard client-routing guarantee.

As a secondary mitigation, each MCP mutation compares the current live configuration
with the latest stored after-version. A mismatch is recorded as an
`external_change_detected` event and the current live configuration is snapshotted before
continuing. This detects out-of-band edits after the fact, but cannot reconstruct a state
that was overwritten before any snapshot existed.

## 3. Architecture

The v2 server remains a Python FastAPI/FastMCP application on Databricks Apps, mounted at
`/mcp` over stateless streamable HTTP.

```text
Genie Code
   │ MCP, calling-user token
   ▼
mcp-genie-agent-versioning
   ├─ OBO Genie client
   │    ├─ get current Agent + etag
   │    └─ update Agent with optimistic concurrency
   └─ app-SP history store
        ├─ agent_config_versions
        └─ agent_change_events
```

Identity is deliberately split:

- **OBO user identity for Genie Agent API calls.** The server reads and updates the Agent
  as the caller, so Databricks remains the source of truth for Agent authorization.
- **App service principal for history SQL.** The history tables are shared service state
  and are not granted directly to end users. The server records the caller identity it
  resolved from the forwarded token.

This model replaces v1's per-user `only_mine` row filters. Collaborators who can access
the same Agent see the same version history, while users cannot read another Agent's
history merely because they can query the backing tables. Every read tool first verifies
access to the requested Agent through an OBO Genie API call.

Required user OAuth scope: `dashboards.genie` plus the default current-user identity
scope. The user token does not need `sql`; SQL runs as the app service principal. The app
SP needs `CAN USE` on the warehouse and the minimum UC privileges on the history schema.

## 4. MCP tool surface

Ship four focused tools:

### `apply_agent_config_change`

Apply a new complete configuration through the guarded workflow.

Inputs:

- `agent_id`
- `desired_config` — complete restorable configuration envelope
- `operation_id` — caller-generated unique id, required for safe retry
- `change_summary`
- `expected_current_version_id?` — optional history-level compare-and-swap

Returns:

- `operation_id`
- `status`
- `before_version_id`
- `after_version_id`
- `result_etag`
- structured recovery information when the operation is incomplete

### `rollback_agent_config`

Restore a stored version through the same internal mutation engine. This is a dedicated
tool so intent is explicit and rollback-specific validation cannot be omitted.

Inputs: `agent_id`, `target_version_id`, `operation_id`, `change_summary?`.

The server reads the current live Agent immediately before the update and uses that
**live** etag for optimistic concurrency. The historical version's captured etag is
provenance only and must never be used as the rollback update lock.

### `list_agent_versions`

List configuration versions for one Agent using cursor pagination. Inputs:
`agent_id`, `limit?`, `cursor?`. The cursor is based on `(created_at, version_id)`, not an
ambiguous timestamp-only `since` filter.

### `get_agent_version`

Retrieve one version with both `agent_id` and `version_id`. The resource scope is
required so a version from one Agent cannot accidentally be applied to another.

## 5. Complete snapshot contract

A version stores a complete, validated, restorable envelope—not only
`serialized_space`:

```json
{
  "format_version": 1,
  "agent_id": "...",
  "serialized_space": "{...}",
  "title": "...",
  "description": "...",
  "warehouse_id": "...",
  "parent_path": "..."
}
```

The exact outer fields must be verified against the current Genie API before
implementation. Newly introduced restorable fields must be preserved through a
forward-compatible `config_envelope` rather than silently dropped.

Validation rules:

- `agent_id` in the envelope must match the tool's `agent_id`.
- `serialized_space` must parse as JSON and satisfy known Genie structural constraints.
- Unknown envelope fields are preserved when safe; unsupported mutation fields fail
  explicitly.
- Payload size is bounded.
- The hash is computed over a canonical representation of the complete envelope.
- Parent and rollback references must exist and belong to the same Agent.

## 6. Data model

### `agent_config_versions`

```sql
version_id             STRING NOT NULL,
agent_id               STRING NOT NULL,
operation_id           STRING NOT NULL,
phase                  STRING NOT NULL, -- before | after
change_type            STRING NOT NULL, -- update | rollback | import
parent_version_id      STRING,
rollback_reference     STRING,
config_envelope        STRING NOT NULL,
config_hash            STRING NOT NULL,
captured_etag          STRING,
change_summary         STRING,
created_at             TIMESTAMP NOT NULL,
created_by             STRING NOT NULL
```

Every snapshot event gets a new `version_id`, even when its content hash matches an older
version. `config_hash` is an integrity/content comparison value, not an idempotency key.
Idempotency is keyed by `(operation_id, phase)`.

### `agent_change_events`

Append one event for each operation transition:

```sql
event_id               STRING NOT NULL,
operation_id           STRING NOT NULL,
agent_id               STRING NOT NULL,
event_type             STRING NOT NULL,
before_version_id      STRING,
after_version_id       STRING,
live_etag              STRING,
error_type             STRING,
error_message          STRING,
created_at             TIMESTAMP NOT NULL,
created_by             STRING NOT NULL
```

Event types include `started`, `external_change_detected`, `before_snapshot_saved`,
`update_succeeded`, `after_snapshot_saved`, `conflict`, and `failed`. This append-only
operation log supports recovery even though the Genie API and UC storage cannot share a
database transaction.

## 7. Mutation state machine

`apply_agent_config_change` and `rollback_agent_config` use the same engine:

1. Resolve the OBO caller and validate inputs.
2. Check `operation_id`. If already complete, return the original result. If incomplete,
   resume from durable events rather than starting another mutation.
3. Read the live Agent and live etag through OBO.
4. Compare the live configuration hash with the latest stored after-version. Mark an
   out-of-band mismatch so it can be recorded after the before-version is durable.
5. Persist a unique before-version and `before_snapshot_saved` event. If step 4 found a
   mismatch, also append `external_change_detected` referencing this before-version.
6. If persistence fails, return `snapshot_failed`; do not call the update API.
7. Update the Agent with the etag read in step 3.
8. On an etag conflict, append `conflict`; do not retry against a new live configuration
   automatically.
9. On success, append `update_succeeded`, read the Agent again, and persist the unique
   after-version.
10. Return success only after the after-version is durable.

If the update succeeds but the after snapshot fails, return
`changed_but_post_snapshot_incomplete`. A retry with the same `operation_id` must inspect
the durable events and live config, finish the after snapshot when unambiguous, and never
apply the desired config a second time.

## 8. Rollback semantics

Rollback is an ordinary forward change:

1. Authorize access to `agent_id` through OBO.
2. Retrieve and validate `target_version_id` for that Agent.
3. Read and snapshot the current live configuration.
4. Apply the target envelope using the current live etag.
5. Read and snapshot the resulting configuration.
6. Link the new after-version to both the live before-version and
   `rollback_reference=target_version_id`.

Older rows are immutable. A rollback can itself be rolled back.

## 9. Failure and security rules

- Never silently fall back from OBO to app-SP for Agent API calls.
- Never accept `created_by` from tool input.
- Never log forwarded access tokens or full configuration payloads.
- Do not return history until OBO Agent access has been verified.
- A validation error or before-snapshot error must make zero update calls.
- A stale etag is a conflict, not a reason to force an unconditional update.
- Health/readiness must report history-store bootstrap failures; the app must not claim
  ready while guarded mutations cannot persist snapshots.
- Backing tables are app-only. End users receive history exclusively through MCP tools.

## 10. Native Genie Code prompt contract

No repository-managed skill files are required. The user or workspace administrator
adds the instruction from §2.2 to the prompt/instructions supplied to native Genie Code.
The MCP's own tool descriptions reinforce the same routing rule.

Tool descriptions must state:

- Use `apply_agent_config_change` for every configuration edit.
- Use `rollback_agent_config` for every restore.
- Never perform a separate native update before or after either tool.
- Treat `snapshot_failed`, `conflict`, and incomplete-post-snapshot statuses as blocking.

This is a best-effort client contract. `CAN MANAGE` and Auto-Approve still permit native
edits that bypass the MCP, so documentation and user-visible status must not describe the
system as universally enforced.

## 11. Migration from v1

The current code is a passive history implementation with five generic artifact tools
and seven tables. It must not be relabeled v2 without the gateway behavior.

Migration steps:

1. Add the two v2 tables with an explicit schema version and migration mechanism.
2. Implement the shared guarded mutation engine and operation recovery.
3. Replace generic artifact tools with the four v2 tools.
4. Remove v1 per-user row filters and direct user grants from the v2 tables.
5. Optionally import valid v1 config snapshots as `change_type=import`, preserving the
   original creator/time and marking missing outer metadata as non-restorable.
6. Retire report/evaluation tables from the core service; preserve existing data unless
   an operator explicitly migrates or archives it.

Existing deployments may retain the `genie_space_history` schema during migration. New
deployments should default to `genie_agent_versioning`; changing an existing schema name
is an explicit data migration, never an automatic rename.

## 12. Acceptance criteria

- A failed before snapshot results in zero Genie update calls.
- Every successful update has durable before and after versions linked by one operation.
- Repeating the same `operation_id` never applies the mutation twice.
- Two concurrent edits produce at most one success for a shared starting etag.
- Rollback restores the complete envelope and uses a freshly read live etag.
- Identical content at different points in history produces distinct version rows.
- History is shared among collaborators authorized on the Agent and inaccessible to
  callers who cannot access that Agent.
- A successful update followed by a storage outage is detectable and recoverable.
- The recommended Genie Code prompt is documented and tested in an end-to-end session,
  including with Auto-Approve enabled.
- An out-of-band native edit is detected and captured on the next MCP mutation.

Describe the system as a **prompt-routed guarded versioning gateway**, not as universally
enforced versioning.
