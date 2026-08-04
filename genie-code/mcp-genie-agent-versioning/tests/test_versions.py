"""Append-only save/get behavior and rollback provenance."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from server import schema
from server.errors import ToolValidationError
from server.store import _InsertBuilder
from server.tools import get_agent_version_core, save_agent_config_version_core

from .conftest import param_value


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
