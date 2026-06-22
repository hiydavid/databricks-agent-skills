"""save_report: artifact_type routing, unknown-type rejection, redaction, dedupe."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp import FastMCP

from server import schema
from server import tools as tools_module
from server.config import Settings
from server.errors import ToolValidationError
from server.store import UCTableStore
from server.tools import register_tools, save_report_core

from .conftest import InMemoryBackend, param_value

ROUTING = [
    ("diagnose_report", schema.DIAGNOSE_REPORTS),
    ("query_report", schema.QUERY_REPORTS),
    ("design_proposal", schema.DESIGN_PROPOSALS),
    ("metric_view_ddl", schema.METRIC_VIEW_ARTIFACTS),
]


def _fresh_store(settings: Settings):
    backend = InMemoryBackend()
    return backend, UCTableStore(backend, settings, user_name="alice@example.com")


@pytest.mark.parametrize("artifact_type,table_name", ROUTING)
def test_artifact_type_routes_to_correct_table(settings, artifact_type, table_name):
    backend, store = _fresh_store(settings)
    result = save_report_core(
        store,
        space_id="s1",
        artifact_type=artifact_type,
        title="A report",
        content_md="# heading\nbody",
    )
    assert result["ok"] is True
    # Exactly one insert, and it targets the routed table only.
    assert len(backend.inserts_into(table_name)) == 1
    assert len(backend.all_inserts()) == 1


def test_unknown_artifact_type_is_rejected(store):
    with pytest.raises(ToolValidationError):
        save_report_core(
            store,
            space_id="s1",
            artifact_type="totally_bogus",
            title="t",
            content_md="c",
        )


def test_redacted_defaults_to_true(store, backend):
    save_report_core(
        store, space_id="s1", artifact_type="diagnose_report", title="t", content_md="c"
    )
    _sql, params = backend.inserts_into(schema.DIAGNOSE_REPORTS)[-1]
    assert param_value(params, "redacted") == "true"


def test_redacted_can_be_disabled(store, backend):
    save_report_core(
        store,
        space_id="s1",
        artifact_type="diagnose_report",
        title="t",
        content_md="c",
        redacted=False,
    )
    _sql, params = backend.inserts_into(schema.DIAGNOSE_REPORTS)[-1]
    assert param_value(params, "redacted") == "false"


def test_summary_derived_from_first_line_when_absent(store, backend):
    save_report_core(
        store,
        space_id="s1",
        artifact_type="query_report",
        title="t",
        content_md="First line summary\nmore detail here",
    )
    _sql, params = backend.inserts_into(schema.QUERY_REPORTS)[-1]
    assert param_value(params, "summary") == "First line summary"


def test_explicit_summary_is_kept(store, backend):
    save_report_core(
        store,
        space_id="s1",
        artifact_type="query_report",
        title="t",
        content_md="First line\nbody",
        summary="explicit summary",
    )
    _sql, params = backend.inserts_into(schema.QUERY_REPORTS)[-1]
    assert param_value(params, "summary") == "explicit summary"


def test_report_idempotency_key_dedupes(store, backend):
    r1 = save_report_core(
        store,
        space_id="s1",
        artifact_type="diagnose_report",
        title="t",
        content_md="c",
        idempotency_key="run-42",
    )
    r2 = save_report_core(
        store,
        space_id="s1",
        artifact_type="diagnose_report",
        title="t (retry)",
        content_md="c",
        idempotency_key="run-42",
    )
    assert r2["deduplicated"] is True
    assert r2["artifact_id"] == r1["artifact_id"]
    assert len(backend.inserts_into(schema.DIAGNOSE_REPORTS)) == 1


def test_created_by_is_server_side_current_user(store, backend):
    save_report_core(
        store, space_id="s1", artifact_type="diagnose_report", title="t", content_md="c"
    )
    sql, params = backend.inserts_into(schema.DIAGNOSE_REPORTS)[-1]
    # created_by uses current_user() so it matches the only_mine SESSION_USER() filter.
    assert "current_user()" in sql
    assert param_value(params, "created_by") is None


# --- N1: accept the spec's `redact` spelling as an alias for `redacted` -----
def _registered_tool(settings: Settings, name: str) -> Any:
    # get_tool(name) is the public single-tool accessor present in the pinned
    # FastMCP (3.x). It returns a FunctionTool with .parameters (JSON schema) + .fn;
    # typed as Any here since we introspect those attributes dynamically.
    mcp = FastMCP(name="test")
    register_tools(mcp, settings)
    return asyncio.run(mcp.get_tool(name))


def test_save_report_schema_accepts_both_redact_and_redacted(settings):
    tool = _registered_tool(settings, "save_report")
    props = tool.parameters["properties"]
    assert "redact" in props
    assert "redacted" in props


def test_redact_alias_overrides_redacted(settings, monkeypatch):
    backend = InMemoryBackend()
    store = UCTableStore(backend, settings, user_name="alice@example.com")
    monkeypatch.setattr(tools_module, "_build_user_store", lambda _s: store)

    tool = _registered_tool(settings, "save_report")
    result = tool.fn(
        space_id="s1",
        artifact_type="diagnose_report",
        title="t",
        content_md="c",
        redact=False,
    )
    assert result["ok"] is True
    _sql, params = backend.inserts_into(schema.DIAGNOSE_REPORTS)[-1]
    assert param_value(params, "redacted") == "false"


def test_redact_defaults_true_via_tool(settings, monkeypatch):
    backend = InMemoryBackend()
    store = UCTableStore(backend, settings, user_name="alice@example.com")
    monkeypatch.setattr(tools_module, "_build_user_store", lambda _s: store)

    tool = _registered_tool(settings, "save_report")
    tool.fn(space_id="s1", artifact_type="query_report", title="t", content_md="c")
    _sql, params = backend.inserts_into(schema.QUERY_REPORTS)[-1]
    assert param_value(params, "redacted") == "true"
