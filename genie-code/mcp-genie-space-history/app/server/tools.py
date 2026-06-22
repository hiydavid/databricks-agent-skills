"""The four P1 MCP tools (spec §6), plus their input validation.

Split into two layers so the logic is unit-testable with no live workspace:

  * ``*_core(store, ...)`` — pure functions that validate inputs against the §7
    contracts and call :class:`~server.store.UCTableStore`. They raise
    :class:`~server.errors.ToolValidationError` on bad input.
  * :func:`register_tools` — wraps each core fn with OBO identity resolution and
    structured error handling, then registers it on the FastMCP server.

All reads/writes run OBO (the calling user). ``created_by``/``created_at`` are
stamped server-side via SQL ``current_user()``/``current_timestamp()`` (spec §6),
so ``created_by`` always matches the ``SESSION_USER()`` the row filter compares.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Sequence

from . import auth, schema
from .config import Settings
from .errors import (
    OBOScopeError,
    ToolValidationError,
    error_payload,
    looks_like_scope_error,
    scope_error_payload,
    validation_error_payload,
)
from .sql import SqlError, make_sql_exec
from .store import UCTableStore

logger = logging.getLogger("mcp-genie-space-history.tools")


def _require(value: Optional[str], name: str) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ToolValidationError(f"`{name}` is required and must be non-empty.")
    return value


# ---------------------------------------------------------------------------
# Core tool logic (workspace-free; takes an already-built store)
# ---------------------------------------------------------------------------
def save_config_snapshot_core(
    store: UCTableStore,
    *,
    space_id: str,
    serialized_space: str,
    etag: Optional[str] = None,
    version_label: Optional[str] = None,
    parent_config_version_id: Optional[str] = None,
    run_id: Optional[str] = None,
    changed_surfaces: Optional[Sequence[str]] = None,
    change_summary: Optional[str] = None,
    rollback_reference: Optional[str] = None,
    skill_name: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    _require(space_id, "space_id")
    _require(serialized_space, "serialized_space")

    # §7.1 config_snapshots has no version_label column. To avoid dropping the
    # caller-supplied label, fold it into change_summary when no summary was given.
    effective_summary = change_summary
    if effective_summary is None and version_label:
        effective_summary = version_label

    result = store.save_config_snapshot(
        space_id=space_id,
        serialized_space=serialized_space,
        etag=etag,
        parent_version_id=parent_config_version_id,
        run_id=run_id,
        changed_surfaces=changed_surfaces,
        change_summary=effective_summary,
        rollback_reference=rollback_reference,
        skill_name=skill_name,
        idempotency_key=idempotency_key,
    )
    result["ok"] = True
    return result


def save_report_core(
    store: UCTableStore,
    *,
    space_id: str,
    artifact_type: str,
    title: str,
    content_md: str,
    run_id: Optional[str] = None,
    scores_findings: Optional[Any] = None,
    summary: Optional[str] = None,
    config_version_id: Optional[str] = None,
    skill_name: Optional[str] = None,
    redacted: bool = True,
    idempotency_key: Optional[str] = None,
) -> dict:
    _require(space_id, "space_id")
    _require(artifact_type, "artifact_type")
    _require(title, "title")
    _require(content_md, "content_md")

    if artifact_type not in schema.ARTIFACT_TYPE_TO_REPORT_TABLE:
        valid = ", ".join(sorted(schema.ARTIFACT_TYPE_TO_REPORT_TABLE))
        raise ToolValidationError(
            f"unknown artifact_type {artifact_type!r}; expected one of: {valid}"
        )

    # Derive a short summary for list_history when the caller didn't provide one.
    effective_summary = summary
    if effective_summary is None and content_md:
        first_line = content_md.strip().splitlines()[0] if content_md.strip() else ""
        effective_summary = first_line[:280] or None

    result = store.save_report(
        space_id=space_id,
        artifact_type=artifact_type,
        title=title,
        content_md=content_md,
        summary=effective_summary,
        scores_findings=scores_findings,
        run_id=run_id,
        config_version_id=config_version_id,
        skill_name=skill_name,
        redacted=redacted,
        idempotency_key=idempotency_key,
    )
    result["ok"] = True
    return result


def list_history_core(
    store: UCTableStore,
    *,
    space_id: str,
    artifact_type: Optional[str] = None,
    limit: int = 50,
    since: Optional[str] = None,
) -> dict:
    _require(space_id, "space_id")
    if artifact_type is not None and artifact_type not in store.known_type_labels():
        valid = ", ".join(sorted(store.known_type_labels()))
        raise ToolValidationError(
            f"unknown artifact_type {artifact_type!r}; expected one of: {valid}"
        )
    items = store.list_history(
        space_id=space_id,
        type_label=artifact_type,
        limit=limit,
        since=since,
    )
    return {"ok": True, "items": items, "count": len(items)}


def get_artifact_core(store: UCTableStore, *, id: str) -> dict:
    _require(id, "id")
    found = store.get_artifact(id)
    if found is None:
        return {"ok": False, "error_type": "not_found", "message": f"no artifact with id {id!r}"}
    found["ok"] = True
    return found


# ---------------------------------------------------------------------------
# OBO identity + structured error wrapping
# ---------------------------------------------------------------------------
def _build_user_store(settings: Settings) -> UCTableStore:
    """Build an OBO-backed store for the calling user.

    Raises :class:`OBOScopeError` when the token is absent / OBO is disabled. A
    token/identity-auth failure from ``current_user.me()`` (e.g. SDK ``Unauthenticated``)
    is also re-raised as :class:`OBOScopeError` so it surfaces as a ``scope_error``
    rather than a generic internal error (a deployed app's OBO token can default to
    identity-only scopes — spec §5, P0 finding F-6).
    """
    w = auth.get_user_workspace_client(obo_enabled=settings.obo_enabled)
    try:
        me = w.current_user.me()
    except OBOScopeError:
        raise
    except Exception as exc:  # noqa: BLE001
        if looks_like_scope_error(exc):
            raise OBOScopeError(f"OBO identity resolution failed: {exc}") from exc
        raise
    user_name = me.user_name or "unknown"
    return UCTableStore(make_sql_exec(w, settings.sql_warehouse_id), settings, user_name=user_name)


def _run_tool(settings: Settings, tool_name: str, core: Callable[[UCTableStore], dict]) -> dict:
    """Resolve OBO identity, run ``core(store)``, and map errors to structured payloads.

    Emits one structured log line per call (tool + outcome) for observability (spec §10).
    """
    try:
        store = _build_user_store(settings)
        result = core(store)
        logger.info("tool=%s ok=%s", tool_name, result.get("ok", True))
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
    except Exception as exc:  # noqa: BLE001 — surface anything else as a structured error
        # Classify a token/OAuth failure as scope_error; everything else is internal.
        if looks_like_scope_error(exc):
            logger.warning("tool=%s scope_error (auth): %s", tool_name, exc)
            return scope_error_payload(str(exc))
        logger.exception("tool=%s internal_error: %s", tool_name, exc)
        return error_payload("internal_error", str(exc))


def register_tools(mcp_server, settings: Settings) -> None:
    """Register the four P1 tools on the FastMCP server."""

    @mcp_server.tool
    def save_config_snapshot(
        space_id: str,
        serialized_space: str,
        etag: Optional[str] = None,
        version_label: Optional[str] = None,
        parent_config_version_id: Optional[str] = None,
        run_id: Optional[str] = None,
        changed_surfaces: Optional[list[str]] = None,
        change_summary: Optional[str] = None,
        rollback_reference: Optional[str] = None,
        skill_name: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """Persist a Genie Space config snapshot (the mandatory before/after snapshot).

        The caller supplies ``serialized_space`` — the MCP never fetches it. The server
        computes a sha256 ``config_hash``, stores the caller's ``etag`` verbatim, and sets
        lineage via ``parent_config_version_id``. Snapshots are ordered/identified by
        ``created_at`` + ``config_version_id`` (no monotonic version counter). Returns
        ``{config_version_id, config_hash, etag}``. (Writes config_snapshots.)
        """
        return _run_tool(
            settings,
            "save_config_snapshot",
            lambda store: save_config_snapshot_core(
                store,
                space_id=space_id,
                serialized_space=serialized_space,
                etag=etag,
                version_label=version_label,
                parent_config_version_id=parent_config_version_id,
                run_id=run_id,
                changed_surfaces=changed_surfaces,
                change_summary=change_summary,
                rollback_reference=rollback_reference,
                skill_name=skill_name,
                idempotency_key=idempotency_key,
            ),
        )

    @mcp_server.tool
    def save_report(
        space_id: str,
        artifact_type: str,
        title: str,
        content_md: str,
        run_id: Optional[str] = None,
        scores_findings: Optional[str] = None,
        summary: Optional[str] = None,
        config_version_id: Optional[str] = None,
        skill_name: Optional[str] = None,
        redacted: bool = True,
        redact: Optional[bool] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """Persist a Markdown artifact, routed by ``artifact_type`` to its table.

        ``diagnose_report`` → diagnose_reports, ``query_report`` → query_reports,
        ``design_proposal`` → design_proposals, ``metric_view_ddl`` → metric_view_artifacts.
        Unknown types are rejected. Returns ``{artifact_id}``.

        Redaction defaults to true. The spec spells the flag ``redact`` (§6/§7.3); both
        ``redact`` and ``redacted`` are accepted (``redact`` wins if both are sent).
        """
        effective_redacted = redact if redact is not None else redacted
        return _run_tool(
            settings,
            "save_report",
            lambda store: save_report_core(
                store,
                space_id=space_id,
                artifact_type=artifact_type,
                title=title,
                content_md=content_md,
                run_id=run_id,
                scores_findings=scores_findings,
                summary=summary,
                config_version_id=config_version_id,
                skill_name=skill_name,
                redacted=effective_redacted,
                idempotency_key=idempotency_key,
            ),
        )

    @mcp_server.tool
    def list_history(
        space_id: str,
        artifact_type: Optional[str] = None,
        limit: int = 50,
        since: Optional[str] = None,
    ) -> dict:
        """Timeline of versions/runs/reports for a Space (UNION across all artifact tables).

        Returns ``{items: [{id, type, version, created_at, created_by, summary, decision}]}``.
        ``artifact_type`` optionally restricts to one type; ``since`` filters on created_at.
        """
        return _run_tool(
            settings,
            "list_history",
            lambda store: list_history_core(
                store,
                space_id=space_id,
                artifact_type=artifact_type,
                limit=limit,
                since=since,
            ),
        )

    @mcp_server.tool
    def get_artifact(id: str) -> dict:
        """Fetch one stored item by id (config_version_id / artifact_id / run_id).

        Resolves the id across all artifact tables and returns the full record
        (including ``config_json`` / ``content_md``).
        """
        return _run_tool(settings, "get_artifact", lambda store: get_artifact_core(store, id=id))
