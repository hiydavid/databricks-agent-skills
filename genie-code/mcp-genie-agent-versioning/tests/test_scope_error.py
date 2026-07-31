"""OBO failures are structured and the user path requires only SQL scope."""

from __future__ import annotations

import dataclasses

import pytest

from server import auth, tools
from server.errors import OBOScopeError, looks_like_scope_error
from server.sql import SqlError


@pytest.fixture
def no_obo_token():
    reset = auth.obo_token_var.set(None)
    try:
        yield
    finally:
        auth.obo_token_var.reset(reset)


def test_missing_obo_token_returns_scope_error(monkeypatch, settings, no_obo_token):
    monkeypatch.setenv("DATABRICKS_APP_NAME", "mcp-genie-agent-versioning")
    result = tools._run_tool(
        settings,
        "save_agent_config_version",
        lambda _store: pytest.fail("core must not run"),
    )
    assert result["ok"] is False
    assert result["error_type"] == "scope_error"
    assert result["required_scope"] == "sql"


def test_disabled_obo_returns_scope_error(monkeypatch, settings):
    monkeypatch.setenv("DATABRICKS_APP_NAME", "mcp-genie-agent-versioning")
    disabled = dataclasses.replace(settings, obo_enabled=False)
    result = tools._run_tool(disabled, "list_agent_versions", lambda _store: {})
    assert result["error_type"] == "scope_error"


def test_user_store_does_not_call_identity_api(monkeypatch, settings, backend):
    class IdentityAPI:
        def me(self):
            raise AssertionError("current_user.me() must not be called")

    class Workspace:
        current_user = IdentityAPI()

    monkeypatch.setattr(auth, "get_user_workspace_client", lambda **_kwargs: Workspace())
    monkeypatch.setattr(tools, "make_sql_exec", lambda _workspace, _warehouse: backend)
    store = tools._build_user_store(settings)
    assert store.settings == settings


def test_sql_scope_failure_is_classified(monkeypatch, settings, store):
    monkeypatch.setattr(tools, "_build_user_store", lambda _settings: store)

    def fail(_store):
        raise SqlError("401 insufficient_scope", state="ERROR")

    result = tools._run_tool(settings, "get_agent_version", fail)
    assert result["error_type"] == "scope_error"


def test_uc_grant_denial_is_not_mislabeled():
    assert looks_like_scope_error(SqlError("PERMISSION_DENIED: no SELECT on table")) is False
    assert looks_like_scope_error(SqlError("invalid_token")) is True


def test_auth_helper_never_falls_back_to_app_identity(monkeypatch, no_obo_token):
    monkeypatch.setenv("DATABRICKS_APP_NAME", "mcp-genie-agent-versioning")
    with pytest.raises(OBOScopeError):
        auth.get_user_workspace_client(obo_enabled=True)
