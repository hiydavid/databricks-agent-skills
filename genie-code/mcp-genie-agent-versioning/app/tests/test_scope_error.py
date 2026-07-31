"""The scope_error path (spec §5): missing OBO token / disabled OBO never falls back to SP."""

from __future__ import annotations

import dataclasses

import pytest

from server import auth, tools
from server.errors import OBOScopeError, looks_like_scope_error, scope_error_payload
from server.sql import SqlError


def _never_runs(_store):
    raise AssertionError("core must not run when OBO auth fails")


@pytest.fixture
def no_obo_token():
    """Ensure the per-request OBO token ContextVar is unset for the test."""
    reset = auth.obo_token_var.set(None)
    try:
        yield
    finally:
        auth.obo_token_var.reset(reset)


def test_missing_obo_token_in_app_returns_scope_error(monkeypatch, settings, no_obo_token):
    # Simulate running inside a deployed App with NO forwarded token.
    monkeypatch.setenv("DATABRICKS_APP_NAME", "mcp-genie-agent-versioning")

    result = tools._run_tool(settings, "save_config_snapshot", _never_runs)

    assert result["ok"] is False
    assert result["error_type"] == "scope_error"
    assert result["required_scope"] == "sql"
    assert "user_api_scopes" in result["remediation"]


def test_disabled_obo_returns_scope_error(monkeypatch, settings):
    # OBO disabled raises before the token is ever consulted.
    monkeypatch.setenv("DATABRICKS_APP_NAME", "mcp-genie-agent-versioning")
    disabled = dataclasses.replace(settings, obo_enabled=False)

    result = tools._run_tool(disabled, "list_history", _never_runs)

    assert result["error_type"] == "scope_error"


def test_get_user_workspace_client_raises_when_token_missing(monkeypatch, no_obo_token):
    monkeypatch.setenv("DATABRICKS_APP_NAME", "mcp-genie-agent-versioning")
    with pytest.raises(OBOScopeError):
        auth.get_user_workspace_client(obo_enabled=True)


def test_sql_layer_scope_failure_is_classified(monkeypatch, settings, store):
    # A SqlError whose message looks like an OAuth-scope failure maps to scope_error.
    def boom(_store):
        raise SqlError("403 Unauthorized: insufficient_scope", state="ERROR")

    monkeypatch.setattr(tools, "_build_user_store", lambda _s: store)
    result = tools._run_tool(settings, "save_report", boom)
    assert result["error_type"] == "scope_error"


def test_ordinary_sql_error_is_not_scope_error(monkeypatch, settings, store):
    def boom(_store):
        raise SqlError("SQL FAILED: table not found", state="ERROR")

    monkeypatch.setattr(tools, "_build_user_store", lambda _s: store)
    result = tools._run_tool(settings, "save_report", boom)
    assert result["error_type"] == "sql_error"


def test_scope_error_classifier_is_conservative():
    # A plain UC grant denial must NOT be mislabeled an OAuth-scope error.
    assert looks_like_scope_error(SqlError("PERMISSION_DENIED: no SELECT on table")) is False
    assert looks_like_scope_error(SqlError("invalid_token")) is True


# --- N2: token/identity-auth failures during current_user.me() -> scope_error ---
def test_classifier_detects_unauthenticated_by_class_name():
    # The SDK's Unauthenticated (401) is detected by class name, even with a generic
    # message; PermissionDenied (403, a UC grant denial) is NOT a scope error.
    class Unauthenticated(Exception):
        pass

    class PermissionDenied(Exception):
        pass

    assert looks_like_scope_error(Unauthenticated("token rejected")) is True
    assert looks_like_scope_error(PermissionDenied("forbidden")) is False


def test_identity_resolution_auth_failure_maps_to_scope_error(monkeypatch, settings):
    # An auth failure raised while building the OBO store (e.g. me()) -> scope_error,
    # not internal_error.
    class Unauthenticated(Exception):
        pass

    def boom(_settings):
        raise Unauthenticated("401: token lacks required scope")

    monkeypatch.setattr(tools, "_build_user_store", boom)
    result = tools._run_tool(settings, "save_config_snapshot", _never_runs)
    assert result["error_type"] == "scope_error"


def test_generic_internal_error_is_not_scope_error(monkeypatch, settings):
    def boom(_settings):
        raise RuntimeError("something unrelated blew up")

    monkeypatch.setattr(tools, "_build_user_store", boom)
    result = tools._run_tool(settings, "save_config_snapshot", _never_runs)
    assert result["error_type"] == "internal_error"


def test_scope_error_payload_shape():
    payload = scope_error_payload("nope", required_scope="sql")
    assert payload == {
        "ok": False,
        "error_type": "scope_error",
        "required_scope": "sql",
        "message": "nope",
        "remediation": payload["remediation"],
    }
    assert "sql" in payload["remediation"]
