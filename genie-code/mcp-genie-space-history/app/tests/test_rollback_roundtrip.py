"""Rollback round-trip uses existing P1 tools and stays append-only.

Rollback has no MCP tool. Genie Code fetches the target config with get_artifact,
re-applies it through its own Genie edit path, then records the result as a new
config snapshot. This test covers the MCP side of that contract only.
"""

from __future__ import annotations

from server import schema
from server.tools import get_artifact_core, save_config_snapshot_core

from .conftest import param_value


def _config_rows(backend):
    return backend.rows[schema.CONFIG_SNAPSHOTS]


def _assert_only_uc_sql_was_recorded(backend) -> None:
    forbidden_genie_api_fragments = (
        "/api/2.0/genie",
        "get_space",
        "update_space",
        "w.genie",
        "patch /api",
        "get /api",
    )
    expected_table = f"`testcat`.`genie_space_history`.`{schema.CONFIG_SNAPSHOTS}`"

    assert backend.calls
    for sql, _params in backend.calls:
        stripped_upper = sql.lstrip().upper()
        assert stripped_upper.startswith(("SELECT", "INSERT"))
        assert expected_table in sql
        assert not any(fragment in sql.lower() for fragment in forbidden_genie_api_fragments)


def test_rollback_round_trip_fetches_target_and_appends_lineage(store, backend):
    baseline_config = '{"space_id":"space-rollback","instructions":"baseline"}'
    live_config = '{"space_id":"space-rollback","instructions":"optimized"}'

    baseline = save_config_snapshot_core(
        store,
        space_id="space-rollback",
        serialized_space=baseline_config,
        etag="etag-baseline",
        change_summary="baseline before optimization",
        idempotency_key="baseline-before-edit",
    )
    baseline_id = baseline["config_version_id"]
    baseline_etag = baseline["etag"]
    assert baseline_etag == "etag-baseline"

    live = save_config_snapshot_core(
        store,
        space_id="space-rollback",
        serialized_space=live_config,
        etag="etag-live",
        parent_config_version_id=baseline_id,
        change_summary="optimized live config",
        idempotency_key="optimized-live",
    )
    live_id = live["config_version_id"]
    baseline_row_before_rollback = dict(_config_rows(backend)[baseline_id])

    fetched = get_artifact_core(store, id=baseline_id)

    assert fetched["ok"] is True
    assert fetched["type"] == "config_snapshot"
    assert fetched["table"] == schema.CONFIG_SNAPSHOTS
    assert fetched["record"]["config_json"] == baseline_config
    assert fetched["record"]["etag"] == baseline_etag

    rollback = save_config_snapshot_core(
        store,
        space_id="space-rollback",
        serialized_space=fetched["record"]["config_json"],
        etag="etag-after-rollback",
        parent_config_version_id=live_id,
        rollback_reference=baseline_id,
        change_summary=f"rollback to {baseline_id}",
        idempotency_key=f"rollback-{live_id}-to-{baseline_id}",
    )
    rollback_id = rollback["config_version_id"]

    assert rollback["ok"] is True
    assert rollback["deduplicated"] is False
    assert rollback_id not in {baseline_id, live_id}
    assert len(_config_rows(backend)) == 3
    assert _config_rows(backend)[baseline_id] == baseline_row_before_rollback

    rollback_row = _config_rows(backend)[rollback_id]
    assert rollback_row["config_json"] == baseline_config
    assert rollback_row["parent_version_id"] == live_id
    assert rollback_row["rollback_reference"] == baseline_id
    assert rollback_row["change_summary"] == f"rollback to {baseline_id}"
    assert rollback_row["etag"] == "etag-after-rollback"

    rollback_insert_sql, rollback_insert_params = backend.inserts_into(schema.CONFIG_SNAPSHOTS)[-1]
    assert "rollback_reference" in rollback_insert_sql
    assert param_value(rollback_insert_params, "rollback_reference") == baseline_id
    assert param_value(rollback_insert_params, "parent_version_id") == live_id

    assert not any(
        sql.lstrip().upper().startswith(("DELETE", "UPDATE", "MERGE"))
        for sql, _ in backend.calls
    )
    _assert_only_uc_sql_was_recorded(backend)
