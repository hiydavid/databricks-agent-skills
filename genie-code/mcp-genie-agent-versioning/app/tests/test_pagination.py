"""Deterministic keyset pagination for one Agent."""

from __future__ import annotations

import pytest

from server.contracts import decode_cursor, encode_cursor
from server.errors import ToolValidationError
from server.sql import QueryResult
from server.tools import list_agent_versions_core

from .conftest import param_value

_COLUMNS = [
    "version_id",
    "reason",
    "created_at",
    "created_by",
    "config_hash",
    "change_summary",
    "parent_version_id",
    "rollback_target_version_id",
]


def _row(version_id: str, created_at: str) -> list:
    return [version_id, "manual", created_at, "alice@example.com", "hash", None, None, None]


def test_list_fetches_one_extra_and_returns_cursor(store, backend):
    backend.list_result = QueryResult(
        _COLUMNS,
        [
            _row("v3", "2026-07-30T12:00:03Z"),
            _row("v2", "2026-07-30T12:00:02Z"),
            _row("v1", "2026-07-30T12:00:01Z"),
        ],
    )
    result = list_agent_versions_core(store, space_id="space-1", limit=2)
    assert [item["version_id"] for item in result["items"]] == ["v3", "v2"]
    assert result["next_cursor"] is not None

    decoded = decode_cursor(result["next_cursor"], expected_space_id="space-1")
    assert decoded.version_id == "v2"
    sql, _ = backend.calls[-1]
    assert "ORDER BY created_at DESC, version_id DESC LIMIT 3" in sql


def test_last_page_has_no_cursor(store, backend):
    backend.list_result = QueryResult(_COLUMNS, [_row("v1", "2026-07-30T12:00:01Z")])
    result = list_agent_versions_core(store, space_id="space-1", limit=2)
    assert result["next_cursor"] is None


def test_cursor_uses_timestamp_and_version_tiebreaker(store, backend):
    backend.list_result = QueryResult(_COLUMNS, [])
    cursor = encode_cursor(
        space_id="space-1",
        created_at="2026-07-30T12:00:02Z",
        version_id="v2",
    )
    list_agent_versions_core(store, space_id="space-1", limit=20, cursor=cursor)
    sql, params = backend.calls[-1]
    assert "created_at < :cursor_created_at" in sql
    assert "created_at = :cursor_created_at AND version_id < :cursor_version_id" in sql
    assert param_value(params, "cursor_created_at") == "2026-07-30T12:00:02Z"
    assert param_value(params, "cursor_version_id") == "v2"


@pytest.mark.parametrize("limit", [0, 101, True, 1.5])
def test_invalid_limits_are_rejected(store, limit):
    with pytest.raises(ToolValidationError, match="limit"):
        list_agent_versions_core(store, space_id="space-1", limit=limit)


def test_cross_space_cursor_is_rejected(store):
    cursor = encode_cursor(
        space_id="space-2",
        created_at="2026-07-30T12:00:02Z",
        version_id="v2",
    )
    with pytest.raises(ToolValidationError, match="different"):
        list_agent_versions_core(store, space_id="space-1", cursor=cursor)
