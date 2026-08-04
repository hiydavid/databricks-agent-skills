"""Append-only save/get behavior and rollback provenance."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast

import pytest
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import PermissionDenied, ResourceConflict

from server import schema, tools
from server.errors import ToolValidationError
from server.sql import SqlError
from server.store import _InsertBuilder
from server.tools import (
    get_agent_version_core,
    restore_agent_config_version_core,
    save_agent_config_version_core,
    save_live_agent_config_version_core,
)

from .conftest import param_value


class FakeGenieApiClient:
    def __init__(self, get_response, *, patch_response=None, patch_error=None, before_patch=None):
        self.get_response = get_response
        self.patch_response = patch_response or {}
        self.patch_error = patch_error
        self.before_patch = before_patch
        self.calls = []

    def do(self, method, path, *, query=None, body=None):
        self.calls.append({"method": method, "path": path, "query": query, "body": body})
        if method == "GET":
            return self.get_response
        if method == "PATCH":
            if self.before_patch:
                self.before_patch()
            if self.patch_error:
                raise self.patch_error
            return self.patch_response
        raise AssertionError(f"unexpected method: {method}")


def _workspace_with_api(api_client) -> WorkspaceClient:
    return cast(WorkspaceClient, SimpleNamespace(api_client=api_client))


def test_live_save_fetches_exact_export_server_side(store, backend, complete_config):
    api = FakeGenieApiClient({**complete_config, "etag": "live-etag"})

    result = save_live_agent_config_version_core(
        _workspace_with_api(api),
        store,
        space_id="space-1",
        reason="before_update",
    )

    assert result["ok"] is True
    assert api.calls == [
        {
            "method": "GET",
            "path": "/api/2.0/genie/spaces/space-1",
            "query": {"include_serialized_space": True},
            "body": None,
        }
    ]
    row = backend.rows[schema.AGENT_CONFIG_VERSIONS][result["version_id"]]
    envelope = json.loads(row["config_envelope"])
    assert envelope["serialized_space"] == complete_config["serialized_space"]
    assert envelope["title"] == complete_config["title"]
    assert envelope["etag"] == "live-etag"


def test_live_save_rejects_missing_serialized_export_before_write(store, backend):
    api = FakeGenieApiClient(
        {
            "title": "Revenue analyst",
            "description": None,
            "warehouse_id": "warehouse-1",
            "parent_path": None,
            "serialized_space": None,
            "etag": "live-etag",
        }
    )

    with pytest.raises(ToolValidationError, match="serialized_space"):
        save_live_agent_config_version_core(
            _workspace_with_api(api),
            store,
            space_id="space-1",
            reason="before_update",
        )

    assert backend.inserts_into(schema.AGENT_CONFIG_VERSIONS) == []


def test_restore_checkpoints_current_state_before_etag_guarded_patch(
    store, backend, complete_config
):
    target = save_agent_config_version_core(
        store,
        space_id="space-1",
        config={**complete_config, "title": "Target title", "etag": "historical-etag"},
        reason="manual",
    )
    current = {**complete_config, "title": "Current title", "etag": "live-etag"}

    def assert_checkpoint_exists():
        assert len(backend.rows[schema.AGENT_CONFIG_VERSIONS]) == 2

    api = FakeGenieApiClient(
        current,
        patch_response={"etag": "updated-etag"},
        before_patch=assert_checkpoint_exists,
    )

    result = restore_agent_config_version_core(
        _workspace_with_api(api),
        store,
        space_id="space-1",
        version_id=target["version_id"],
        change_summary="Restore known-good instructions",
    )

    assert result == {
        "ok": True,
        "space_id": "space-1",
        "restore_status": "applied",
        "restored_version_id": target["version_id"],
        "before_rollback_version_id": result["before_rollback_version_id"],
        "updated_etag": "updated-etag",
    }
    patch = api.calls[1]
    assert patch["method"] == "PATCH"
    assert patch["body"] == {
        "serialized_space": complete_config["serialized_space"],
        "title": "Target title",
        "description": complete_config["description"],
        "warehouse_id": complete_config["warehouse_id"],
        "parent_path": complete_config["parent_path"],
        "etag": "live-etag",
    }
    checkpoint_row = backend.rows[schema.AGENT_CONFIG_VERSIONS][
        result["before_rollback_version_id"]
    ]
    checkpoint_envelope = json.loads(checkpoint_row["config_envelope"])
    assert checkpoint_row["reason"] == "before_rollback"
    assert checkpoint_row["rollback_target_version_id"] == target["version_id"]
    assert checkpoint_envelope["title"] == "Current title"
    assert checkpoint_envelope["etag"] == "live-etag"


def test_restore_conflict_keeps_checkpoint_without_claiming_success(
    store, backend, complete_config
):
    target = save_agent_config_version_core(
        store, space_id="space-1", config=complete_config, reason="manual"
    )
    api = FakeGenieApiClient(
        {**complete_config, "etag": "live-etag"},
        patch_error=ResourceConflict("etag mismatch"),
    )

    result = restore_agent_config_version_core(
        _workspace_with_api(api),
        store,
        space_id="space-1",
        version_id=target["version_id"],
    )

    assert result["ok"] is False
    assert result["error_type"] == "conflict"
    assert result["restore_status"] == "not_applied"
    assert result["rollback_target_version_id"] == target["version_id"]
    assert result["before_rollback_version_id"] in backend.rows[schema.AGENT_CONFIG_VERSIONS]


def test_restore_api_failure_reports_durable_checkpoint_and_unknown_status(
    monkeypatch, settings, store, backend, complete_config
):
    target = save_agent_config_version_core(
        store, space_id="space-1", config=complete_config, reason="manual"
    )
    api = FakeGenieApiClient(
        {**complete_config, "etag": "live-etag"},
        patch_error=PermissionDenied("update denied"),
    )
    workspace = _workspace_with_api(api)
    monkeypatch.setattr(tools, "_build_user_context", lambda _settings: (workspace, store))

    result = tools._run_tool(
        settings,
        "restore_agent_config_version",
        lambda active_workspace, active_store: restore_agent_config_version_core(
            active_workspace,
            active_store,
            space_id="space-1",
            version_id=target["version_id"],
        ),
    )

    assert result["ok"] is False
    assert result["error_type"] == "genie_api_error"
    assert result["restore_status"] == "unknown"
    assert result["rollback_target_version_id"] == target["version_id"]
    assert result["before_rollback_version_id"] in backend.rows[schema.AGENT_CONFIG_VERSIONS]
    assert "inspect the live Agent before retrying" in result["message"]


def test_restore_requires_live_etag_before_checkpoint_or_patch(store, backend, complete_config):
    target = save_agent_config_version_core(
        store, space_id="space-1", config=complete_config, reason="manual"
    )
    api = FakeGenieApiClient({**complete_config, "etag": None})

    with pytest.raises(ToolValidationError, match="live Agent etag"):
        restore_agent_config_version_core(
            _workspace_with_api(api),
            store,
            space_id="space-1",
            version_id=target["version_id"],
        )

    assert len(backend.rows[schema.AGENT_CONFIG_VERSIONS]) == 1
    assert all(call["method"] != "PATCH" for call in api.calls)


def test_restore_checkpoint_failure_prevents_patch(monkeypatch, store, complete_config):
    target = save_agent_config_version_core(
        store, space_id="space-1", config=complete_config, reason="manual"
    )
    api = FakeGenieApiClient({**complete_config, "etag": "live-etag"})

    def fail_checkpoint(**_kwargs):
        raise SqlError("checkpoint failed")

    monkeypatch.setattr(store, "save_agent_config_version", fail_checkpoint)

    with pytest.raises(SqlError, match="checkpoint failed"):
        restore_agent_config_version_core(
            _workspace_with_api(api),
            store,
            space_id="space-1",
            version_id=target["version_id"],
        )

    assert all(call["method"] != "PATCH" for call in api.calls)


def test_restore_missing_target_does_not_call_genie_api(store, complete_config):
    api = FakeGenieApiClient({**complete_config, "etag": "live-etag"})

    result = restore_agent_config_version_core(
        _workspace_with_api(api),
        store,
        space_id="space-1",
        version_id="missing",
    )

    assert result["ok"] is False
    assert result["error_type"] == "not_found"
    assert api.calls == []


def test_save_returns_sql_stamped_metadata(store, backend, complete_config):
    result = save_agent_config_version_core(
        store,
        space_id="space-1",
        config=complete_config,
        reason="before_update",
        change_summary="Tune join guidance",
    )

    assert result["ok"] is True
    assert len(result["version_id"]) == 32
    assert result["created_by"] == "alice@example.com"
    assert result["created_at"].startswith("2026-07-30")

    sql, params = backend.inserts_into(schema.AGENT_CONFIG_VERSIONS)[0]
    assert "SESSION_USER()" in sql
    assert "current_timestamp()" in sql
    assert param_value(params, "created_by") is None
    assert param_value(params, "created_at") is None


def test_identical_successful_saves_create_distinct_events(store, backend, complete_config):
    first = save_agent_config_version_core(
        store, space_id="space-1", config=complete_config, reason="manual"
    )
    second = save_agent_config_version_core(
        store, space_id="space-1", config=complete_config, reason="manual"
    )

    assert first["version_id"] != second["version_id"]
    assert first["config_hash"] == second["config_hash"]
    assert len(backend.rows[schema.AGENT_CONFIG_VERSIONS]) == 2
    assert not any("deduplic" in sql.lower() for sql, _ in backend.calls)


def test_stored_envelope_is_complete(store, backend, complete_config):
    saved = save_agent_config_version_core(
        store, space_id="space-1", config=complete_config, reason="manual"
    )
    row = backend.rows[schema.AGENT_CONFIG_VERSIONS][saved["version_id"]]
    envelope = json.loads(row["config_envelope"])
    assert envelope["format_version"] == 1
    assert envelope["space_id"] == "space-1"
    assert envelope["serialized_space"] == complete_config["serialized_space"]


def test_progress_summary_is_rejected_before_table_write(store, backend, complete_config):
    config = {
        **complete_config,
        "serialized_space": (
            '{"state":"after_second_update","pass_rate":"30/39","failed":8,"needs_review":1}'
        ),
    }

    with pytest.raises(ToolValidationError, match="not a complete Genie Agent export"):
        save_agent_config_version_core(
            store,
            space_id="space-1",
            config=config,
            reason="before_update",
        )

    assert backend.inserts_into(schema.AGENT_CONFIG_VERSIONS) == []


@pytest.mark.parametrize("reason", ["before_update", "before_rollback", "manual"])
def test_documented_reasons_are_accepted(store, complete_config, reason):
    kwargs = {}
    if reason == "before_rollback":
        target = save_agent_config_version_core(
            store, space_id="space-1", config=complete_config, reason="manual"
        )
        kwargs["rollback_target_version_id"] = target["version_id"]
    result = save_agent_config_version_core(
        store, space_id="space-1", config=complete_config, reason=reason, **kwargs
    )
    assert result["ok"] is True


def test_invalid_reason_and_summary_are_rejected(store, complete_config):
    with pytest.raises(ToolValidationError, match="reason"):
        save_agent_config_version_core(
            store, space_id="space-1", config=complete_config, reason="after_update"
        )
    with pytest.raises(ToolValidationError, match="single line"):
        save_agent_config_version_core(
            store,
            space_id="space-1",
            config=complete_config,
            reason="manual",
            change_summary="line one\nline two",
        )
    with pytest.raises(ToolValidationError, match="at most 200"):
        save_agent_config_version_core(
            store,
            space_id="space-1",
            config=complete_config,
            reason="manual",
            change_summary="x" * 201,
        )


def test_before_rollback_requires_visible_same_space_target(store, complete_config):
    with pytest.raises(ToolValidationError, match="required"):
        save_agent_config_version_core(
            store,
            space_id="space-1",
            config=complete_config,
            reason="before_rollback",
        )

    other = save_agent_config_version_core(
        store, space_id="space-2", config=complete_config, reason="manual"
    )
    with pytest.raises(ToolValidationError, match="visible"):
        save_agent_config_version_core(
            store,
            space_id="space-1",
            config=complete_config,
            reason="before_rollback",
            rollback_target_version_id=other["version_id"],
        )


def test_rollback_event_preserves_target_and_lineage(store, backend, complete_config):
    target = save_agent_config_version_core(
        store, space_id="space-1", config=complete_config, reason="manual"
    )
    current_config = {**complete_config, "title": "Current title", "etag": "live-etag"}
    current = save_agent_config_version_core(
        store,
        space_id="space-1",
        config=current_config,
        reason="before_rollback",
        parent_version_id=target["version_id"],
        rollback_target_version_id=target["version_id"],
    )
    row = backend.rows[schema.AGENT_CONFIG_VERSIONS][current["version_id"]]
    assert row["parent_version_id"] == target["version_id"]
    assert row["rollback_target_version_id"] == target["version_id"]
    assert len(backend.rows[schema.AGENT_CONFIG_VERSIONS]) == 2
    assert not any(
        sql.lstrip().upper().startswith(("UPDATE", "DELETE", "MERGE")) for sql, _ in backend.calls
    )


def test_save_lineage_checks_and_readback_never_select_envelope(store, backend, complete_config):
    target = save_agent_config_version_core(
        store, space_id="space-1", config=complete_config, reason="manual"
    )
    backend.calls.clear()

    save_agent_config_version_core(
        store,
        space_id="space-1",
        config=complete_config,
        reason="before_rollback",
        parent_version_id=target["version_id"],
        rollback_target_version_id=target["version_id"],
    )

    selects = [sql for sql, _params in backend.calls if sql.lstrip().startswith("SELECT")]
    assert len(selects) == 3
    assert sum("SELECT 1 AS present" in sql for sql in selects) == 2
    assert any("SELECT version_id, created_at, created_by, config_hash" in sql for sql in selects)
    assert all("config_envelope" not in sql for sql in selects)


def test_insert_builder_rejects_non_string_bound_values():
    builder = _InsertBuilder()
    with pytest.raises(TypeError, match="must be a string or None"):
        builder.set("reason", cast(Any, False))


def test_get_is_scoped_by_space_and_labels_historical_etag(store, complete_config):
    saved = save_agent_config_version_core(
        store, space_id="space-1", config=complete_config, reason="manual"
    )
    found = get_agent_version_core(store, space_id="space-1", version_id=saved["version_id"])
    assert found["ok"] is True
    assert found["config"]["etag"] == "etag-at-capture"
    assert found["etag_provenance"]["valid_for_update_lock"] is False

    not_found = get_agent_version_core(store, space_id="space-2", version_id=saved["version_id"])
    assert not_found["ok"] is False
    assert not_found["error_type"] == "not_found"
