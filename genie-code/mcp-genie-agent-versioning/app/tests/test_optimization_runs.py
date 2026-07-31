"""record_optimization_run: 1 run row + N eval rows, idempotency, validation, resolution.

One ``optimization_runs`` row plus one ``eval_results`` row per entry are written via
``_InsertBuilder`` with server-side ``created_at``/``created_by``. The run is keyed by an
id derived from the idempotency key (default ``run_id``) with read-before-write, so a
retry never duplicates the run or its eval rows (spec §6/§7.1).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp import FastMCP

from server import schema
from server import tools as tools_module
from server.config import Settings
from server.errors import ToolValidationError
from server.sql import QueryResult
from server.store import UCTableStore
from server.tools import (
    get_artifact_core,
    list_history_core,
    record_optimization_run_core,
    register_tools,
)

from .conftest import InMemoryBackend, param_value

_LIST_COLUMNS = ["id", "type", "version", "created_at", "created_by", "summary", "decision"]

# A representative eval batch: mix of fully-populated, minimal, and partial entries.
EVALS = [
    {
        "question_id": "q1",
        "assessment": "pass",
        "primary_failure": None,
        "baseline_sql_hash": "bh1",
        "candidate_sql_hash": "ch1",
        "baseline_result_digest": "bd1",
        "candidate_result_digest": "cd1",
        "latency_ms": 1200,
    },
    {"question_id": "q2", "assessment": "fail", "primary_failure": "wrong_join"},
    {"question_id": "q3", "assessment": "pass", "latency_ms": 800},
]


def _run_inserts(backend):
    return backend.inserts_into(schema.OPTIMIZATION_RUNS)


def _eval_inserts(backend):
    return backend.inserts_into(schema.EVAL_RESULTS)


# --- happy path -------------------------------------------------------------
def test_happy_path_one_run_row_and_n_eval_rows(store, backend):
    result = record_optimization_run_core(
        store,
        space_id="s1",
        run_id="run-123",
        eval_results=EVALS,
        baseline_score=0.5,
        candidate_score=1.0,
        fixed_count=2,
        regressed_count=1,
        unchanged_count=5,
        excluded_count=0,
        decision="accepted",
        parent_config_version_id="cfg-parent",
        result_config_version_id="cfg-result",
        change_summary="tightened joins",
    )

    assert result["ok"] is True
    assert result["deduplicated"] is False
    assert result["eval_count"] == 3
    assert len(result["run_id"]) == 32  # 32-char hex logical id

    # Exactly one run row + one row per eval entry.
    run_calls = _run_inserts(backend)
    assert len(run_calls) == 1
    assert len(_eval_inserts(backend)) == 3
    assert len(backend.rows[schema.OPTIMIZATION_RUNS]) == 1
    assert len(backend.rows[schema.EVAL_RESULTS]) == 3


def test_run_row_columns_and_params(store, backend):
    result = record_optimization_run_core(
        store,
        space_id="s1",
        run_id="run-123",
        eval_results=EVALS,
        baseline_score=0.5,
        candidate_score=1.0,
        fixed_count=2,
        regressed_count=1,
        unchanged_count=5,
        excluded_count=0,
        decision="accepted",
        parent_config_version_id="cfg-parent",
        result_config_version_id="cfg-result",
        change_summary="tightened joins",
    )
    sql, params = _run_inserts(backend)[-1]

    # The stored PK is the derived run id that the tool returns.
    assert param_value(params, "run_id") == result["run_id"]
    assert param_value(params, "space_id") == "s1"
    assert param_value(params, "baseline_score") == "0.5"
    assert param_value(params, "candidate_score") == "1.0"
    # score_delta derived from candidate - baseline when omitted.
    assert param_value(params, "score_delta") == "0.5"
    assert param_value(params, "fixed_count") == "2"
    assert param_value(params, "regressed_count") == "1"
    assert param_value(params, "unchanged_count") == "5"
    assert param_value(params, "excluded_count") == "0"  # 0 is bound, not dropped
    assert param_value(params, "decision") == "accepted"
    assert param_value(params, "parent_config_version_id") == "cfg-parent"
    assert param_value(params, "result_config_version_id") == "cfg-result"
    assert param_value(params, "change_summary") == "tightened joins"
    # created_at/created_by stamped server-side (no bound params).
    assert "current_timestamp()" in sql
    assert "current_user()" in sql
    assert param_value(params, "created_at") is None
    assert param_value(params, "created_by") is None


def test_eval_rows_carry_fk_inherited_space_and_distinct_ids(store, backend):
    result = record_optimization_run_core(
        store, space_id="s1", run_id="run-123", eval_results=EVALS
    )
    eval_calls = _eval_inserts(backend)
    assert len(eval_calls) == 3

    eval_run_ids = set()
    for sql, params in eval_calls:
        # FK back to the run + the run's space_id inherited onto every eval row.
        assert param_value(params, "run_id") == result["run_id"]
        assert param_value(params, "space_id") == "s1"
        # created_at/created_by stamped server-side on eval rows too.
        assert "current_timestamp()" in sql
        assert "current_user()" in sql
        assert param_value(params, "created_by") is None
        eval_run_ids.add(param_value(params, "eval_run_id"))
    assert len(eval_run_ids) == 3  # each eval row gets a distinct stable PK

    # Per-field binding on the fully-populated first entry.
    _sql0, p0 = eval_calls[0]
    assert param_value(p0, "question_id") == "q1"
    assert param_value(p0, "assessment") == "pass"
    assert param_value(p0, "baseline_sql_hash") == "bh1"
    assert param_value(p0, "candidate_sql_hash") == "ch1"
    assert param_value(p0, "baseline_result_digest") == "bd1"
    assert param_value(p0, "candidate_result_digest") == "cd1"
    assert param_value(p0, "latency_ms") == "1200"


def test_explicit_score_delta_takes_precedence(store, backend):
    record_optimization_run_core(
        store,
        space_id="s1",
        run_id="run-1",
        baseline_score=0.5,
        candidate_score=1.0,
        score_delta=0.42,
    )
    _sql, params = _run_inserts(backend)[-1]
    assert param_value(params, "score_delta") == "0.42"


def test_no_eval_results_is_valid(store, backend):
    result = record_optimization_run_core(store, space_id="s1", run_id="run-1")
    assert result["ok"] is True
    assert result["eval_count"] == 0
    assert len(_run_inserts(backend)) == 1
    assert len(_eval_inserts(backend)) == 0


# --- idempotency ------------------------------------------------------------
def test_idempotent_retry_does_not_duplicate(store, backend):
    evals = [
        {"question_id": "q1", "assessment": "pass"},
        {"question_id": "q2", "assessment": "fail"},
    ]
    r1 = record_optimization_run_core(
        store, space_id="s1", run_id="run-x", eval_results=evals, decision="accepted"
    )
    r2 = record_optimization_run_core(
        store, space_id="s1", run_id="run-x", eval_results=evals, decision="accepted"
    )

    assert r1["deduplicated"] is False
    assert r2["deduplicated"] is True
    assert r2["run_id"] == r1["run_id"]
    assert r2["eval_count"] == 2
    # The retry inserts neither a second run row nor the eval rows again.
    assert len(_run_inserts(backend)) == 1
    assert len(_eval_inserts(backend)) == 2


def test_explicit_idempotency_key_dedupes_across_run_ids(store, backend):
    # Same key, different run_id input => same derived run row (retry semantics).
    r1 = record_optimization_run_core(
        store,
        space_id="s1",
        run_id="run-a",
        eval_results=[{"assessment": "pass"}],
        idempotency_key="batch-7",
    )
    r2 = record_optimization_run_core(
        store,
        space_id="s1",
        run_id="run-b",
        eval_results=[{"assessment": "pass"}],
        idempotency_key="batch-7",
    )
    assert r2["deduplicated"] is True
    assert r2["run_id"] == r1["run_id"]
    assert len(_run_inserts(backend)) == 1
    assert len(_eval_inserts(backend)) == 1


def test_distinct_runs_persist_separately(store, backend):
    r1 = record_optimization_run_core(store, space_id="s1", run_id="run-a")
    r2 = record_optimization_run_core(store, space_id="s1", run_id="run-b")
    assert r1["run_id"] != r2["run_id"]
    assert len(_run_inserts(backend)) == 2
    assert len(backend.rows[schema.OPTIMIZATION_RUNS]) == 2


# --- validation -------------------------------------------------------------
def test_missing_space_id_rejected(store):
    with pytest.raises(ToolValidationError):
        record_optimization_run_core(store, space_id="", run_id="run-1")


def test_missing_run_id_rejected(store):
    with pytest.raises(ToolValidationError):
        record_optimization_run_core(store, space_id="s1", run_id="")


def test_eval_results_must_be_a_list(store):
    bad: Any = {"assessment": "pass"}  # an object, not a list of objects
    with pytest.raises(ToolValidationError):
        record_optimization_run_core(store, space_id="s1", run_id="run-1", eval_results=bad)


def test_non_object_eval_entry_rejected(store):
    with pytest.raises(ToolValidationError):
        record_optimization_run_core(
            store, space_id="s1", run_id="run-1", eval_results=["not-an-object"]
        )


def test_unknown_eval_field_rejected(store):
    with pytest.raises(ToolValidationError):
        record_optimization_run_core(
            store,
            space_id="s1",
            run_id="run-1",
            eval_results=[{"assessment": "pass", "bogus_field": 1}],
        )


def test_bad_latency_type_rejected(store):
    with pytest.raises(ToolValidationError):
        record_optimization_run_core(
            store, space_id="s1", run_id="run-1", eval_results=[{"latency_ms": "fast"}]
        )


def test_bool_latency_rejected(store):
    # bool is an int subclass — must not slip through as a latency value.
    with pytest.raises(ToolValidationError):
        record_optimization_run_core(
            store, space_id="s1", run_id="run-1", eval_results=[{"latency_ms": True}]
        )


def test_bad_string_field_type_rejected(store):
    with pytest.raises(ToolValidationError):
        record_optimization_run_core(
            store, space_id="s1", run_id="run-1", eval_results=[{"assessment": 123}]
        )


def test_validation_error_inserts_nothing(store, backend):
    with pytest.raises(ToolValidationError):
        record_optimization_run_core(
            store, space_id="s1", run_id="run-1", eval_results=[{"bogus_field": 1}]
        )
    assert backend.all_inserts() == []


# --- list_history / get_artifact resolution ---------------------------------
def test_get_artifact_resolves_run(store):
    saved = record_optimization_run_core(
        store,
        space_id="s1",
        run_id="run-x",
        eval_results=[{"assessment": "pass"}],
        decision="accepted",
    )
    found = get_artifact_core(store, id=saved["run_id"])
    assert found["ok"] is True
    assert found["type"] == "optimization_run"
    assert found["table"] == schema.OPTIMIZATION_RUNS
    assert found["record"]["run_id"] == saved["run_id"]
    assert found["record"]["decision"] == "accepted"


def test_get_artifact_resolves_eval_row(store, backend):
    saved = record_optimization_run_core(
        store,
        space_id="s1",
        run_id="run-x",
        eval_results=[{"question_id": "q1", "assessment": "pass"}],
    )
    _sql, params = _eval_inserts(backend)[0]
    eval_run_id = param_value(params, "eval_run_id")
    assert eval_run_id is not None
    found = get_artifact_core(store, id=eval_run_id)
    assert found["ok"] is True
    assert found["type"] == "eval_result"
    assert found["table"] == schema.EVAL_RESULTS
    assert found["record"]["run_id"] == saved["run_id"]
    assert found["record"]["question_id"] == "q1"


def test_list_history_unions_optimization_runs(store, backend):
    run_row = ["rid", "optimization_run", None, "2026-01-01", "alice", "tightened", "accepted"]
    backend.list_result = QueryResult(_LIST_COLUMNS, [run_row])
    result = list_history_core(store, space_id="s1")
    assert result["ok"] is True
    list_sql, _params = backend.calls[-1]
    # Both run + eval tables participate in the unfiltered UNION.
    assert schema.OPTIMIZATION_RUNS in list_sql
    assert schema.EVAL_RESULTS in list_sql
    assert result["items"][0]["type"] == "optimization_run"
    assert result["items"][0]["decision"] == "accepted"


def test_list_history_filter_restricts_to_optimization_runs(store, backend):
    backend.list_result = QueryResult(_LIST_COLUMNS, [])
    list_history_core(store, space_id="s1", artifact_type="optimization_run")
    list_sql, _params = backend.calls[-1]
    assert schema.OPTIMIZATION_RUNS in list_sql
    assert schema.CONFIG_SNAPSHOTS not in list_sql
    assert schema.EVAL_RESULTS not in list_sql


# --- tool layer (register_tools + _run_tool wiring) -------------------------
def _registered_tool(settings: Settings, name: str) -> Any:
    mcp = FastMCP(name="test")
    register_tools(mcp, settings)
    return asyncio.run(mcp.get_tool(name))


def test_tool_schema_exposes_inputs(settings):
    tool = _registered_tool(settings, "record_optimization_run")
    props = tool.parameters["properties"]
    for key in ("space_id", "run_id", "eval_results", "decision", "baseline_score"):
        assert key in props


def test_record_run_via_tool(settings, monkeypatch):
    backend = InMemoryBackend()
    store = UCTableStore(backend, settings, user_name="alice@example.com")
    monkeypatch.setattr(tools_module, "_build_user_store", lambda _s: store)

    tool = _registered_tool(settings, "record_optimization_run")
    result = tool.fn(
        space_id="s1",
        run_id="run-7",
        eval_results=[{"question_id": "q1", "assessment": "pass"}],
        decision="accepted",
    )
    assert result["ok"] is True
    assert result["deduplicated"] is False
    assert result["eval_count"] == 1
    assert len(backend.inserts_into(schema.OPTIMIZATION_RUNS)) == 1
    assert len(backend.inserts_into(schema.EVAL_RESULTS)) == 1
