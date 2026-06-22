"""list_history (UNION + filter) and get_artifact (id resolution across tables)."""

from __future__ import annotations

import pytest

from server import schema
from server.errors import ToolValidationError
from server.sql import QueryResult
from server.tools import (
    get_artifact_core,
    list_history_core,
    save_config_snapshot_core,
    save_report_core,
)

from .conftest import param_value

_LIST_COLUMNS = ["id", "type", "version", "created_at", "created_by", "summary", "decision"]


def test_list_history_unions_all_tables_and_returns_items(store, backend):
    backend.list_result = QueryResult(
        _LIST_COLUMNS,
        [["abc", "config_snapshot", 1, "2026-01-01T00:00:00Z", "alice", "v1", None]],
    )
    result = list_history_core(store, space_id="s1")

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["items"] == backend.list_result.dicts()

    list_sql, params = backend.calls[-1]
    # Every artifact table participates in the UNION when no filter is given.
    for table_name in schema.ALL_TABLE_NAMES:
        assert table_name in list_sql
    assert param_value(params, "space_id") == "s1"


def test_list_history_filter_restricts_to_one_table(store, backend):
    backend.list_result = QueryResult(_LIST_COLUMNS, [])
    list_history_core(store, space_id="s1", artifact_type="diagnose_report")
    list_sql, _params = backend.calls[-1]
    assert schema.DIAGNOSE_REPORTS in list_sql
    assert schema.CONFIG_SNAPSHOTS not in list_sql
    assert schema.QUERY_REPORTS not in list_sql


def test_list_history_since_binds_param(store, backend):
    backend.list_result = QueryResult(_LIST_COLUMNS, [])
    list_history_core(store, space_id="s1", since="2026-01-01T00:00:00Z")
    list_sql, params = backend.calls[-1]
    assert "created_at >= :since" in list_sql
    assert param_value(params, "since") == "2026-01-01T00:00:00Z"


def test_list_history_limit_is_clamped_and_inlined(store, backend):
    backend.list_result = QueryResult(_LIST_COLUMNS, [])
    list_history_core(store, space_id="s1", limit=99999)
    list_sql, _params = backend.calls[-1]
    assert "LIMIT 1000" in list_sql  # clamped to the 1000 ceiling


def test_list_history_unknown_artifact_type_rejected(store):
    with pytest.raises(ToolValidationError):
        list_history_core(store, space_id="s1", artifact_type="nope")


def test_get_artifact_resolves_config_snapshot(store):
    saved = save_config_snapshot_core(store, space_id="s1", serialized_space='{"v":1}')
    found = get_artifact_core(store, id=saved["config_version_id"])
    assert found["ok"] is True
    assert found["type"] == "config_snapshot"
    assert found["table"] == schema.CONFIG_SNAPSHOTS
    assert found["record"]["config_json"] == '{"v":1}'


def test_get_artifact_resolves_report_across_tables(store):
    saved = save_report_core(
        store,
        space_id="s1",
        artifact_type="diagnose_report",
        title="t",
        content_md="body",
    )
    found = get_artifact_core(store, id=saved["artifact_id"])
    assert found["ok"] is True
    assert found["type"] == "diagnose_report"
    assert found["table"] == schema.DIAGNOSE_REPORTS
    assert found["record"]["content_md"] == "body"


def test_get_artifact_not_found(store):
    result = get_artifact_core(store, id="does-not-exist")
    assert result["ok"] is False
    assert result["error_type"] == "not_found"


def test_get_artifact_requires_id(store):
    with pytest.raises(ToolValidationError):
        get_artifact_core(store, id="")
