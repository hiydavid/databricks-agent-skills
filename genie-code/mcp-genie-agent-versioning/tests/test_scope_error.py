"""OBO failures are structured for the SQL and Genie user scopes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import Unauthenticated

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
        lambda _workspace, _store: pytest.fail("core must not run"),
    )
    assert result["ok"] is False
    assert result["error_type"] == "scope_error"
    assert result["required_scope"] == "sql"


def test_user_context_reuses_obo_client_without_identity_api(monkeypatch, settings, backend):
    class IdentityAPI:
        def me(self):
            raise AssertionError("current_user.me() must not be called")

    class Workspace:
        current_user = IdentityAPI()

    workspace = Workspace()
    monkeypatch.setattr(auth, "get_user_workspace_client", lambda **_kwargs: workspace)
    monkeypatch.setattr(tools, "make_sql_exec", lambda _workspace, _warehouse: backend)
    actual_workspace, store = tools._build_user_context(settings)
    assert actual_workspace is workspace
    assert store.settings == settings


def test_sql_scope_failure_is_classified(monkeypatch, settings, store):
    monkeypatch.setattr(tools, "_build_user_context", lambda _settings: (object(), store))

    def fail(_workspace, _store):
        raise SqlError("401 insufficient_scope", state="ERROR")

    result = tools._run_tool(settings, "get_agent_version", fail)
    assert result["error_type"] == "scope_error"


def test_genie_scope_failure_identifies_genie_scope(store):
    def fail(*_args, **_kwargs):
        raise Unauthenticated("insufficient_scope")

    workspace = cast(
        WorkspaceClient,
        SimpleNamespace(api_client=SimpleNamespace(do=fail)),
    )

    with pytest.raises(OBOScopeError) as raised:
        tools.save_live_agent_config_version_core(
            workspace,
            store,
            space_id="space-1",
            reason="before_update",
        )

    assert raised.value.required_scope == "genie"


def test_uc_grant_denial_is_not_mislabeled():
    assert looks_like_scope_error(SqlError("PERMISSION_DENIED: no SELECT on table")) is False
    assert looks_like_scope_error(SqlError("invalid_token")) is True


@pytest.mark.parametrize(
    "message",
    ["table orders_401 does not exist", "query returned 401 rows"],
)
def test_incidental_401_is_not_mislabeled(message):
    assert looks_like_scope_error(SqlError(message)) is False


def test_explicit_http_401_is_classified():
    assert looks_like_scope_error(SqlError("HTTP status 401")) is True


def test_auth_helper_never_falls_back_to_app_identity(monkeypatch, no_obo_token):
    monkeypatch.setenv("DATABRICKS_APP_NAME", "mcp-genie-agent-versioning")
    with pytest.raises(OBOScopeError):
        auth.get_user_workspace_client()
