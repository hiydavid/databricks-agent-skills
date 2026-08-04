"""The focused v2 MCP tools and their OBO/error wrappers."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Mapping, Optional
from urllib.parse import quote

from anyio import to_thread
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import Aborted, ResourceConflict
from databricks.sdk.errors.base import DatabricksError

from . import auth
from .config import Settings
from .contracts import (
    DEFAULT_LIST_LIMIT,
    decode_cursor,
    encode_cursor,
    prepare_envelope,
    require_nonempty_string,
    validate_change_summary,
    validate_limit,
    validate_reason,
)
from .errors import (
    OBOScopeError,
    ToolValidationError,
    error_payload,
    looks_like_scope_error,
    scope_error_payload,
    validation_error_payload,
)
from .sql import SqlError, make_sql_exec
from .store import AgentVersionStore

logger = logging.getLogger("mcp-genie-agent-versioning.tools")


class _RestoreApplyError(RuntimeError):
    """A restore failed after its safety checkpoint was durably persisted."""

    def __init__(
        self,
        *,
        cause: Exception,
        checkpoint_version_id: str,
        target_version_id: str,
    ) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.checkpoint_version_id = checkpoint_version_id
        self.target_version_id = target_version_id


def _genie_space_path(space_id: str) -> str:
    require_nonempty_string(space_id, "space_id")
    return f"/api/2.0/genie/spaces/{quote(space_id, safe='')}"


def _get_live_agent_config(workspace: WorkspaceClient, *, space_id: str) -> dict[str, Any]:
    """Fetch the complete live restore envelope, including its concurrency etag."""
    try:
        response = workspace.api_client.do(
            "GET",
            _genie_space_path(space_id),
            query={"include_serialized_space": True},
        )
    except Exception as exc:
        if looks_like_scope_error(exc):
            raise OBOScopeError(
                "The OBO token cannot read Genie spaces. Ensure the app declares the "
                "`genie` user scope and reconnect the MCP server.",
                required_scope="genie",
            ) from exc
        raise
    if not isinstance(response, Mapping):
        raise RuntimeError("Get Genie Agent returned an invalid response")
    return {
        "serialized_space": response.get("serialized_space"),
        "title": response.get("title"),
        "description": response.get("description"),
        "warehouse_id": response.get("warehouse_id"),
        "parent_path": response.get("parent_path"),
        "etag": response.get("etag"),
    }


def _update_agent_from_snapshot(
    workspace: WorkspaceClient,
    *,
    space_id: str,
    target: Mapping[str, Any],
    live_etag: str,
) -> Mapping[str, Any]:
    """Apply one stored snapshot with optimistic concurrency protection."""
    body = {
        "serialized_space": target["serialized_space"],
        "title": target["title"],
        "description": target["description"],
        "warehouse_id": target["warehouse_id"],
        "parent_path": target["parent_path"],
        "etag": live_etag,
    }
    response = workspace.api_client.do(
        "PATCH",
        _genie_space_path(space_id),
        body=body,
    )
    if not isinstance(response, Mapping):
        raise RuntimeError("Update Genie Agent returned an invalid response")
    return response


def _require_existing_reference(
    store: AgentVersionStore,
    *,
    space_id: str,
    version_id: Optional[str],
    field_name: str,
) -> Optional[str]:
    if version_id is None:
        return None
    require_nonempty_string(version_id, field_name)
    if not store.agent_version_exists(space_id=space_id, version_id=version_id):
        raise ToolValidationError(
            f"`{field_name}` does not identify a version visible for this `space_id`."
        )
    return version_id


def save_agent_config_version_core(
    store: AgentVersionStore,
    *,
    space_id: str,
    config: dict[str, Any],
    reason: str,
    change_summary: Optional[str] = None,
    parent_version_id: Optional[str] = None,
    rollback_target_version_id: Optional[str] = None,
) -> dict:
    """Validate and append one complete configuration snapshot."""
    require_nonempty_string(space_id, "space_id")
    valid_reason = validate_reason(reason)
    valid_summary = validate_change_summary(change_summary)

    if valid_reason == "before_rollback" and rollback_target_version_id is None:
        raise ToolValidationError(
            "`rollback_target_version_id` is required when reason is `before_rollback`."
        )
    if valid_reason != "before_rollback" and rollback_target_version_id is not None:
        raise ToolValidationError(
            "`rollback_target_version_id` is only valid when reason is `before_rollback`."
        )

    valid_parent = _require_existing_reference(
        store,
        space_id=space_id,
        version_id=parent_version_id,
        field_name="parent_version_id",
    )
    valid_rollback_target = _require_existing_reference(
        store,
        space_id=space_id,
        version_id=rollback_target_version_id,
        field_name="rollback_target_version_id",
    )
    prepared = prepare_envelope(
        space_id=space_id,
        config=config,
        max_config_bytes=store.settings.max_config_bytes,
    )
    saved = store.save_agent_config_version(
        space_id=space_id,
        reason=valid_reason,
        config_envelope=prepared.envelope_json,
        config_hash=prepared.config_hash,
        change_summary=valid_summary,
        parent_version_id=valid_parent,
        rollback_target_version_id=valid_rollback_target,
    )
    return {
        "ok": True,
        "version_id": saved["version_id"],
        "created_at": saved["created_at"],
        "created_by": saved["created_by"],
        "config_hash": saved["config_hash"],
    }


def save_live_agent_config_version_core(
    workspace: WorkspaceClient,
    store: AgentVersionStore,
    *,
    space_id: str,
    reason: str,
    change_summary: Optional[str] = None,
    parent_version_id: Optional[str] = None,
    rollback_target_version_id: Optional[str] = None,
) -> dict:
    """Fetch the exact live Genie export as the caller, then append its snapshot."""
    config = _get_live_agent_config(workspace, space_id=space_id)
    return save_agent_config_version_core(
        store,
        space_id=space_id,
        config=config,
        reason=reason,
        change_summary=change_summary,
        parent_version_id=parent_version_id,
        rollback_target_version_id=rollback_target_version_id,
    )


def restore_agent_config_version_core(
    workspace: WorkspaceClient,
    store: AgentVersionStore,
    *,
    space_id: str,
    version_id: str,
    change_summary: Optional[str] = None,
) -> dict:
    """Checkpoint the live Agent, then restore one visible stored snapshot."""
    require_nonempty_string(space_id, "space_id")
    require_nonempty_string(version_id, "version_id")
    valid_summary = validate_change_summary(change_summary)

    target_row = store.get_agent_version(space_id=space_id, version_id=version_id)
    if target_row is None:
        return {
            "ok": False,
            "error_type": "not_found",
            "message": "no version is visible with that `space_id` and `version_id`",
        }
    try:
        target = json.loads(target_row["config_envelope"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("stored target configuration envelope is invalid JSON") from exc
    if not isinstance(target, dict):
        raise RuntimeError("stored target configuration envelope is not a JSON object")
    prepare_envelope(
        space_id=space_id,
        config=target,
        max_config_bytes=store.settings.max_config_bytes,
    )

    current = _get_live_agent_config(workspace, space_id=space_id)
    live_etag = require_nonempty_string(current.get("etag"), "live Agent etag")
    checkpoint = save_agent_config_version_core(
        store,
        space_id=space_id,
        config=current,
        reason="before_rollback",
        change_summary=valid_summary,
        rollback_target_version_id=version_id,
    )

    try:
        updated = _update_agent_from_snapshot(
            workspace,
            space_id=space_id,
            target=target,
            live_etag=live_etag,
        )
    except (Aborted, ResourceConflict):
        return {
            "ok": False,
            "error_type": "conflict",
            "message": "the live Agent changed during rollback; no snapshot was applied",
            "restore_status": "not_applied",
            "before_rollback_version_id": checkpoint["version_id"],
            "rollback_target_version_id": version_id,
        }
    except Exception as exc:
        raise _RestoreApplyError(
            cause=exc,
            checkpoint_version_id=checkpoint["version_id"],
            target_version_id=version_id,
        ) from exc

    return {
        "ok": True,
        "space_id": space_id,
        "restore_status": "applied",
        "restored_version_id": version_id,
        "before_rollback_version_id": checkpoint["version_id"],
        "updated_etag": updated.get("etag"),
    }


def list_agent_versions_core(
    store: AgentVersionStore,
    *,
    space_id: str,
    limit: int = DEFAULT_LIST_LIMIT,
    cursor: Optional[str] = None,
) -> dict:
    require_nonempty_string(space_id, "space_id")
    valid_limit = validate_limit(limit)
    decoded_cursor = decode_cursor(cursor, expected_space_id=space_id) if cursor else None
    rows = store.list_agent_versions(
        space_id=space_id,
        limit=valid_limit,
        cursor=decoded_cursor,
    )
    has_more = len(rows) > valid_limit
    items = rows[:valid_limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(
            space_id=space_id,
            created_at=str(last["created_at"]),
            version_id=str(last["version_id"]),
        )
    return {
        "ok": True,
        "items": items,
        "next_cursor": next_cursor,
    }


def get_agent_version_core(
    store: AgentVersionStore,
    *,
    space_id: str,
    version_id: str,
) -> dict:
    require_nonempty_string(space_id, "space_id")
    require_nonempty_string(version_id, "version_id")
    row = store.get_agent_version(space_id=space_id, version_id=version_id)
    if row is None:
        return {
            "ok": False,
            "error_type": "not_found",
            "message": "no version is visible with that `space_id` and `version_id`",
        }
    try:
        config = json.loads(row["config_envelope"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("stored configuration envelope is invalid JSON") from exc
    historical_etag = config.get("etag")
    return {
        "ok": True,
        "version_id": row["version_id"],
        "space_id": row["space_id"],
        "reason": row["reason"],
        "config": config,
        "config_hash": row["config_hash"],
        "change_summary": row.get("change_summary"),
        "parent_version_id": row.get("parent_version_id"),
        "rollback_target_version_id": row.get("rollback_target_version_id"),
        "created_at": row["created_at"],
        "created_by": row["created_by"],
        "etag_provenance": {
            "value": historical_etag,
            "is_historical": True,
            "valid_for_update_lock": False,
            "instruction": "Read a fresh live etag before applying this configuration.",
        },
    }


def _build_user_context(settings: Settings) -> tuple[WorkspaceClient, AgentVersionStore]:
    """Build one OBO client shared by the live Genie read and snapshot SQL write."""
    workspace = auth.get_user_workspace_client()
    store = AgentVersionStore(make_sql_exec(workspace, settings.sql_warehouse_id), settings)
    return workspace, store


def _run_tool(
    settings: Settings,
    tool_name: str,
    core: Callable[[WorkspaceClient, AgentVersionStore], dict],
) -> dict:
    try:
        workspace, store = _build_user_context(settings)
        result = core(workspace, store)
        logger.info("tool=%s ok=%s", tool_name, result.get("ok", True))
        return result
    except _RestoreApplyError as exc:
        cause = exc.cause
        if looks_like_scope_error(cause):
            logger.warning("tool=%s scope_error after checkpoint: %s", tool_name, cause)
            result = scope_error_payload(str(cause), required_scope="genie")
        elif isinstance(cause, DatabricksError):
            logger.error("tool=%s genie_api_error after checkpoint: %s", tool_name, cause)
            result = error_payload("genie_api_error", str(cause))
        else:
            logger.exception("tool=%s internal_error after checkpoint: %s", tool_name, cause)
            result = error_payload("internal_error", str(cause))
        result["message"] += (
            " A before_rollback checkpoint was saved, but the restore outcome could not "
            "be confirmed; inspect the live Agent before retrying."
        )
        result.update(
            {
                "restore_status": "unknown",
                "before_rollback_version_id": exc.checkpoint_version_id,
                "rollback_target_version_id": exc.target_version_id,
            }
        )
        return result
    except OBOScopeError as exc:
        logger.warning("tool=%s scope_error: %s", tool_name, exc)
        return scope_error_payload(str(exc), required_scope=exc.required_scope)
    except ToolValidationError as exc:
        logger.info("tool=%s validation_error: %s", tool_name, exc)
        return validation_error_payload(str(exc))
    except SqlError as exc:
        if looks_like_scope_error(exc):
            logger.warning("tool=%s scope_error (sql): %s", tool_name, exc)
            return scope_error_payload(str(exc))
        logger.error("tool=%s sql_error: %s", tool_name, exc)
        return error_payload("sql_error", str(exc))
    except DatabricksError as exc:
        if looks_like_scope_error(exc):
            logger.warning("tool=%s scope_error (api): %s", tool_name, exc)
            return scope_error_payload(str(exc), required_scope="genie")
        logger.error("tool=%s genie_api_error: %s", tool_name, exc)
        return error_payload("genie_api_error", str(exc))
    except Exception as exc:  # noqa: BLE001
        if looks_like_scope_error(exc):
            logger.warning("tool=%s scope_error (auth): %s", tool_name, exc)
            return scope_error_payload(str(exc))
        logger.exception("tool=%s internal_error: %s", tool_name, exc)
        return error_payload("internal_error", str(exc))


def register_tools(mcp_server, settings: Settings) -> None:
    """Register the v2 configuration-version tools."""

    @mcp_server.tool
    async def save_agent_config_version(
        space_id: str,
        reason: str,
        change_summary: Optional[str] = None,
        parent_version_id: Optional[str] = None,
        rollback_target_version_id: Optional[str] = None,
    ) -> dict:
        """Save a complete Genie Agent configuration before any native edit.

        The MCP fetches the complete live Agent directly from the Genie API as the calling
        user, so callers must not relay ``serialized_space``. Genie Code must stop without
        editing if the result is not ``ok: true``. Use ``before_update`` before a normal
        native edit. For rollback, call ``restore_agent_config_version``; it creates its
        own ``before_rollback`` checkpoint. Every successful save appends a distinct
        version, even for identical content.
        """
        return await to_thread.run_sync(
            _run_tool,
            settings,
            "save_agent_config_version",
            lambda workspace, store: save_live_agent_config_version_core(
                workspace,
                store,
                space_id=space_id,
                reason=reason,
                change_summary=change_summary,
                parent_version_id=parent_version_id,
                rollback_target_version_id=rollback_target_version_id,
            ),
        )

    @mcp_server.tool
    async def list_agent_versions(
        space_id: str,
        limit: int = DEFAULT_LIST_LIMIT,
        cursor: Optional[str] = None,
    ) -> dict:
        """List the calling user's stored versions for one Genie Agent.

        Use the opaque ``next_cursor`` for the next page. Pass a selected ``version_id``
        directly to ``restore_agent_config_version``; callers must not relay the stored
        configuration payload.
        """
        return await to_thread.run_sync(
            _run_tool,
            settings,
            "list_agent_versions",
            lambda _workspace, store: list_agent_versions_core(
                store,
                space_id=space_id,
                limit=limit,
                cursor=cursor,
            ),
        )

    @mcp_server.tool
    async def get_agent_version(space_id: str, version_id: str) -> dict:
        """Retrieve one complete version scoped to its Genie Agent.

        This inspection tool can return a large configuration. For rollback, call
        ``restore_agent_config_version`` instead so the payload stays server-side.
        """
        return await to_thread.run_sync(
            _run_tool,
            settings,
            "get_agent_version",
            lambda _workspace, store: get_agent_version_core(
                store,
                space_id=space_id,
                version_id=version_id,
            ),
        )

    @mcp_server.tool
    async def restore_agent_config_version(
        space_id: str,
        version_id: str,
        change_summary: Optional[str] = None,
    ) -> dict:
        """Restore one stored version without relaying its configuration through the caller.

        The MCP reads the current live Agent and etag as the calling user, persists that
        state as a ``before_rollback`` checkpoint, and only then applies the selected
        stored snapshot with optimistic concurrency. A checkpoint failure prevents the
        update; a concurrent Agent change returns a conflict without overwriting it. If
        an update response is ambiguous, inspect the live Agent before retrying and use
        the returned ``before_rollback_version_id`` to recover if needed.
        """
        return await to_thread.run_sync(
            _run_tool,
            settings,
            "restore_agent_config_version",
            lambda workspace, store: restore_agent_config_version_core(
                workspace,
                store,
                space_id=space_id,
                version_id=version_id,
                change_summary=change_summary,
            ),
        )
