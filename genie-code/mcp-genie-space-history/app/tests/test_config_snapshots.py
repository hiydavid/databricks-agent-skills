"""save_config_snapshot: version monotonicity, config_hash, lineage, idempotency."""

from __future__ import annotations

import hashlib

import pytest

from server import schema
from server import store as store_module
from server.errors import StorageContentionError, ToolValidationError
from server.store import MAX_SAVE_ATTEMPTS
from server.tools import save_config_snapshot_core

from .conftest import param_value


def _config_inserts(backend):
    return backend.inserts_into(schema.CONFIG_SNAPSHOTS)


def _cvid(space_id: str, serialized: str, idempotency_key: str | None = None) -> str:
    """Recompute the deterministic config_version_id the store will derive."""
    idem = idempotency_key or store_module.sha256_hex(serialized)
    return store_module._derive_id(f"config:{space_id}", idem)


def test_version_is_monotonic_per_space(store, backend):
    r1 = save_config_snapshot_core(store, space_id="s1", serialized_space='{"v":1}')
    r2 = save_config_snapshot_core(store, space_id="s1", serialized_space='{"v":2}')
    r3 = save_config_snapshot_core(store, space_id="s1", serialized_space='{"v":3}')
    assert [r1["version"], r2["version"], r3["version"]] == [1, 2, 3]

    # A different space restarts its own counter at 1.
    other = save_config_snapshot_core(store, space_id="s2", serialized_space='{"v":1}')
    assert other["version"] == 1


def test_config_hash_is_sha256_of_serialized_space(store):
    serialized = '{"data_sources":{"tables":[]}}'
    result = save_config_snapshot_core(store, space_id="s1", serialized_space=serialized)
    expected = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    assert result["config_hash"] == expected


def test_lineage_parent_version_id_is_persisted(store, backend):
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
    # created_at uses current_timestamp() (no bound param) so it's server-stamped.
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
    assert r2["version"] == r1["version"]
    # The retry must NOT insert a second row.
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


# --- B1: version-allocation race / optimistic-retry ------------------------
def test_version_collision_backs_out_and_retries(store, backend):
    """A concurrent different-config writer grabs our version; the larger-id writer
    backs out its row (DELETE) and retries, converging on a unique version."""
    serialized = '{"v":1}'
    cvid = _cvid("s1", serialized)
    # Phantom shares version 1 but has a SMALLER id -> our writer yields (deletes+retries).
    backend.pending_conflict = {
        "config_version_id": cvid[:-1],
        "version": 1,
        "config_hash": "other-config",
        "etag": None,
    }

    result = save_config_snapshot_core(store, space_id="s1", serialized_space=serialized)

    assert result["deduplicated"] is False
    assert result["config_version_id"] == cvid
    assert result["version"] == 1  # recomputed after backing out
    assert len(backend.deletes()) == 1  # backed out exactly once
    assert len(_config_inserts(backend)) == 2  # first attempt + retry
    assert len(backend.rows[schema.CONFIG_SNAPSHOTS]) == 1  # one row survives


def test_version_collision_winner_keeps_its_row(store, backend):
    """When our id is the smaller one in a collision, we keep our row (no retry/delete)."""
    serialized = '{"v":1}'
    cvid = _cvid("s1", serialized)
    backend.pending_conflict = {
        "config_version_id": cvid + "0",  # larger id -> the OTHER writer yields
        "version": 1,
        "config_hash": "other-config",
        "etag": None,
    }

    result = save_config_snapshot_core(store, space_id="s1", serialized_space=serialized)

    assert result["deduplicated"] is False
    assert result["version"] == 1
    assert backend.deletes() == []
    assert len(_config_inserts(backend)) == 1


def test_unresolvable_contention_raises_clean_error(store, backend):
    """If every attempt collides (persistent contention), surface a clean error rather
    than leaving a colliding row."""
    serialized = '{"v":1}'
    cvid = _cvid("s1", serialized)
    backend.persistent_conflict = {
        "config_version_id": cvid[:-1],  # always smaller -> we always yield
        "version": 1,
        "config_hash": "other-config",
        "etag": None,
    }

    with pytest.raises(StorageContentionError):
        save_config_snapshot_core(store, space_id="s1", serialized_space=serialized)

    assert len(_config_inserts(backend)) == MAX_SAVE_ATTEMPTS
    assert len(backend.deletes()) == MAX_SAVE_ATTEMPTS
    assert backend.rows[schema.CONFIG_SNAPSHOTS] == {}  # nothing left behind


def test_concurrent_same_key_returns_single_logical_result(store, backend):
    """A concurrent insert sharing the idempotency key is detected post-insert and
    collapsed to one logical (deduplicated) result (documented residual)."""
    serialized = '{"v":1}'
    cvid = _cvid("s1", serialized)
    backend.inject_dup_id = True

    result = save_config_snapshot_core(store, space_id="s1", serialized_space=serialized)

    assert result["deduplicated"] is True
    assert result["config_version_id"] == cvid
    assert len(backend.deletes()) == 0  # identical rows can't be safely targeted
