"""Bootstrap: idempotent, never creates the catalog, ownership failure → WARNING not crash."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from server import provisioning, schema
from server.sql import SqlError


class _FakeResp:
    def __init__(self, data_array=None):
        self.result = SimpleNamespace(data_array=data_array) if data_array is not None else None


def _fake_workspace_client() -> Any:
    # A duck-typed stand-in for WorkspaceClient (only current_user.me() is used).
    me = SimpleNamespace(user_name="sp-app-12345")
    return SimpleNamespace(current_user=SimpleNamespace(me=lambda: me))


def _install_fake_exec(monkeypatch, *, fail_substrings=()):
    recorded: list[str] = []

    def fake_exec(w, warehouse_id, statement, **kwargs):
        recorded.append(statement)
        for sub in fail_substrings:
            if sub in statement:
                raise SqlError(f"forced failure: {sub}", state="ERROR", statement=statement)
        # SHOW TABLES ... LIKE returns no rows -> table treated as newly created.
        return _FakeResp(data_array=None)

    monkeypatch.setattr(provisioning, "exec_sql", fake_exec)
    return recorded


def test_bootstrap_happy_path(monkeypatch, settings):
    recorded = _install_fake_exec(monkeypatch)
    report = provisioning.bootstrap(_fake_workspace_client(), settings)

    assert report["ok"] is True
    assert report["catalog_created"] is False
    assert not any(stmt.upper().startswith("CREATE CATALOG") for stmt in recorded)

    # All seven tables created.
    for table_name in schema.ALL_TABLE_NAMES:
        assert any(
            "CREATE TABLE IF NOT EXISTS" in stmt and table_name in stmt for stmt in recorded
        ), table_name
    assert sorted(report["tables_created"]) == sorted(schema.ALL_TABLE_NAMES)

    # Row-filter function + row filters on each table.
    assert any("CREATE FUNCTION IF NOT EXISTS" in stmt for stmt in recorded)
    for table_name in schema.ALL_TABLE_NAMES:
        assert any("SET ROW FILTER" in stmt and table_name in stmt for stmt in recorded)

    # Grants to the grantee + ownership handoff to the durable group.
    assert any("GRANT USE SCHEMA, SELECT, MODIFY ON SCHEMA" in stmt for stmt in recorded)
    assert any("OWNER TO" in stmt and settings.history_owner_group in stmt for stmt in recorded)


def test_bootstrap_required_tblproperties_present(monkeypatch, settings):
    recorded = _install_fake_exec(monkeypatch)
    provisioning.bootstrap(_fake_workspace_client(), settings)
    creates = [s for s in recorded if "CREATE TABLE IF NOT EXISTS" in s]
    assert len(creates) == 7
    for ddl in creates:
        assert "delta.enableRowTracking = true" in ddl
        assert "'delta.feature.allowColumnDefaults' = 'supported'" in ddl


def test_ownership_failure_is_warning_not_crash(monkeypatch, settings):
    _install_fake_exec(monkeypatch, fail_substrings=("OWNER TO",))
    report = provisioning.bootstrap(_fake_workspace_client(), settings)

    # The data path is still usable (schema + tables created) ...
    assert report["ok"] is True
    # ... and every OWNER TO failure was captured as a structured warning.
    assert report["warnings"]
    assert all("owner_to" in w for w in report["warnings"])


def test_catalog_inaccessible_returns_early_without_creating_anything(monkeypatch, settings):
    recorded = _install_fake_exec(monkeypatch, fail_substrings=("SHOW SCHEMAS",))
    report = provisioning.bootstrap(_fake_workspace_client(), settings)

    assert report["ok"] is False
    assert "note" in report
    # No schema/table creation attempted once the catalog is unreachable.
    assert not any("CREATE TABLE" in stmt for stmt in recorded)
    assert not any("CREATE SCHEMA" in stmt for stmt in recorded)


def test_bootstrap_is_rerunnable(monkeypatch, settings):
    _install_fake_exec(monkeypatch)
    first = provisioning.bootstrap(_fake_workspace_client(), settings)
    second = provisioning.bootstrap(_fake_workspace_client(), settings)
    assert first["ok"] is True
    assert second["ok"] is True


def test_never_creates_catalog_even_on_failures(monkeypatch, settings):
    recorded = _install_fake_exec(monkeypatch, fail_substrings=("OWNER TO", "GRANT"))
    provisioning.bootstrap(_fake_workspace_client(), settings)
    assert not any("CREATE CATALOG" in stmt.upper() for stmt in recorded)
