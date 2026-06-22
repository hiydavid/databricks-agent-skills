"""save_config_snapshot: single-INSERT persistence, config_hash, lineage, idempotency.

There is no monotonic version counter: each save is one INSERT, and snapshots are
ordered/identified by ``created_at`` + ``config_version_id`` (B1 resolution).
"""

from __future__ import annotations

import hashlib

import pytest

from server import schema
from server.errors import ToolValidationError
from server.tools import save_config_snapshot_core

from .conftest import param_value


def _config_inserts(backend):
    return backend.inserts_into(schema.CONFIG_SNAPSHOTS)


def test_save_returns_no_version_field(store):
    result = save_config_snapshot_core(store, space_id="s1", serialized_space='{"v":1}')
    # The monotonic version concept is gone entirely — the result no longer carries it.
    assert "version" not in result
    assert result["ok"] is True
    assert result["deduplicated"] is False


def test_save_is_a_single_insert_with_no_version_machinery(store, backend):
    save_config_snapshot_core(store, space_id="s1", serialized_space='{"v":1}')
    # One INSERT, no MAX(version) read, no post-insert reconciliation query, no DELETE.
    assert len(_config_inserts(backend)) == 1
    assert not any("MAX(version)" in sql for sql, _ in backend.calls)
    assert not any(sql.lstrip().startswith("DELETE") for sql, _ in backend.calls)
    # No version column is bound on the INSERT.
    _sql, params = _config_inserts(backend)[-1]
    assert param_value(params, "version") is None


def test_two_rapid_snapshots_persist_as_distinct_rows(store, backend):
    """Two successive snapshots for the same space (distinct content) both persist."""
    r1 = save_config_snapshot_core(store, space_id="s1", serialized_space='{"v":1}')
    r2 = save_config_snapshot_core(store, space_id="s1", serialized_space='{"v":2}')

    assert r1["deduplicated"] is False
    assert r2["deduplicated"] is False
    assert r1["config_version_id"] != r2["config_version_id"]
    # Each save is exactly one INSERT; both rows survive as distinct rows.
    assert len(_config_inserts(backend)) == 2
    assert len(backend.rows[schema.CONFIG_SNAPSHOTS]) == 2


def test_config_hash_is_sha256_of_serialized_space(store):
    serialized = '{"data_sources":{"tables":[]}}'
    result = save_config_snapshot_core(store, space_id="s1", serialized_space=serialized)
    expected = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    assert result["config_hash"] == expected


def test_lineage_parent_reference_is_keyed_on_config_version_id(store, backend):
    """Lineage points at the artifact id (config_version_id), never a version number."""
    r1 = save_config_snapshot_core(store, space_id="s1", serialized_space='{"v":1}')
    save_config_snapshot_core(
        store,
        space_id="s1",
        serialized_space='{"v":2}',
        parent_config_version_id=r1["config_version_id"],
    )
    _sql, params = _config_inserts(backend)[-1]
    assert param_value(params, "parent_version_id") == r1["config_version_id"]


def test_created_by_is_server_side_current_user(store, backend):
    save_config_snapshot_core(store, space_id="s1", serialized_space='{"v":1}')
    sql, params = _config_inserts(backend)[-1]
    # created_by uses current_user() (no bound param) so it always matches SESSION_USER()
    # used by the only_mine row filter.
    assert "current_user()" in sql
    assert param_value(params, "created_by") is None


def test_created_at_is_server_side(store, backend):
    save_config_snapshot_core(store, space_id="s1", serialized_space='{"v":1}')
    sql, params = _config_inserts(backend)[-1]
    # created_at uses current_timestamp() (no bound param) so it's server-stamped — it is
    # the ordering/identity key now that there is no version counter.
    assert "current_timestamp()" in sql
    assert param_value(params, "created_at") is None


def test_etag_stored_verbatim_and_returned(store, backend):
    result = save_config_snapshot_core(
        store, space_id="s1", serialized_space='{"v":1}', etag="etag-abc-123"
    )
    assert result["etag"] == "etag-abc-123"
    _sql, params = _config_inserts(backend)[-1]
    assert param_value(params, "etag") == "etag-abc-123"


def test_changed_surfaces_bound_as_json_array(store, backend):
    save_config_snapshot_core(
        store,
        space_id="s1",
        serialized_space='{"v":1}',
        changed_surfaces=["join_specs", "column_configs"],
    )
    sql, params = _config_inserts(backend)[-1]
    assert "from_json(:changed_surfaces, 'ARRAY<STRING>')" in sql
    assert param_value(params, "changed_surfaces") == '["join_specs", "column_configs"]'


def test_idempotency_default_dedupes_identical_config(store, backend):
    serialized = '{"v":1}'
    r1 = save_config_snapshot_core(store, space_id="s1", serialized_space=serialized)
    r2 = save_config_snapshot_core(store, space_id="s1", serialized_space=serialized)

    assert r2["deduplicated"] is True
    assert r2["config_version_id"] == r1["config_version_id"]
    # The repeat must NOT insert a second row.
    assert len(_config_inserts(backend)) == 1


def test_explicit_idempotency_key_dedupes(store, backend):
    # Different content but the same caller-supplied key => same row (retry semantics).
    r1 = save_config_snapshot_core(
        store, space_id="s1", serialized_space='{"v":1}', idempotency_key="retry-key"
    )
    r2 = save_config_snapshot_core(
        store, space_id="s1", serialized_space='{"v":2}', idempotency_key="retry-key"
    )
    assert r2["deduplicated"] is True
    assert r2["config_version_id"] == r1["config_version_id"]
    assert len(_config_inserts(backend)) == 1


def test_version_label_folds_into_change_summary_when_absent(store, backend):
    save_config_snapshot_core(
        store, space_id="s1", serialized_space='{"v":1}', version_label="baseline-v1"
    )
    _sql, params = _config_inserts(backend)[-1]
    assert param_value(params, "change_summary") == "baseline-v1"


def test_explicit_change_summary_takes_precedence_over_version_label(store, backend):
    save_config_snapshot_core(
        store,
        space_id="s1",
        serialized_space='{"v":1}',
        version_label="baseline-v1",
        change_summary="real summary",
    )
    _sql, params = _config_inserts(backend)[-1]
    assert param_value(params, "change_summary") == "real summary"


def test_missing_required_inputs_rejected(store):
    with pytest.raises(ToolValidationError):
        save_config_snapshot_core(store, space_id="", serialized_space='{"v":1}')
    with pytest.raises(ToolValidationError):
        save_config_snapshot_core(store, space_id="s1", serialized_space="")
