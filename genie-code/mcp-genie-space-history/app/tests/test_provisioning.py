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

    # Row-filter function + row filters on each table; all 7 reported as filtered.
    assert any("CREATE FUNCTION IF NOT EXISTS" in stmt for stmt in recorded)
    for table_name in schema.ALL_TABLE_NAMES:
        assert any("SET ROW FILTER" in stmt and table_name in stmt for stmt in recorded)
    assert sorted(report["row_filtered"]) == sorted(schema.ALL_TABLE_NAMES)
    assert report["grants_withheld"] == []
    assert report["errors"] == []

    # Grantee gets PER-TABLE SELECT/MODIFY (never schema-wide) + USE SCHEMA traversal.
    assert not any("SELECT, MODIFY ON SCHEMA" in stmt for stmt in recorded)
    assert any(
        "GRANT USE SCHEMA ON SCHEMA" in stmt and settings.history_grantee in stmt
        for stmt in recorded
    )
    for table_name in schema.ALL_TABLE_NAMES:
        assert any(
            "GRANT SELECT, MODIFY ON TABLE" in stmt
            and table_name in stmt
            and settings.history_grantee in stmt
            for stmt in recorded
        ), table_name

    # Ownership handoff to the durable group.
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

    # Row isolation is intact (function + all filters applied) so ok stays True ...
    assert report["ok"] is True
    # ... OWNER TO is the ONLY step allowed to warn-and-continue ...
    assert report["warnings"]
    assert all("owner_to" in w for w in report["warnings"])
    # ... and it is NOT treated as a hard error.
    assert report["errors"] == []


def test_row_filter_failure_withholds_grant_and_fails(monkeypatch, settings):
    # Fail the row filter for exactly one table.
    target = schema.CONFIG_SNAPSHOTS
    recorded = _install_fake_exec(monkeypatch, fail_substrings=(f"`{target}` SET ROW FILTER",))
    report = provisioning.bootstrap(_fake_workspace_client(), settings)

    # Bootstrap is NOT ok because not every table is row-filtered.
    assert report["ok"] is False
    assert target not in report["row_filtered"]
    # The grantee grant on the unfiltered table is WITHHELD (security gate).
    assert target in report["grants_withheld"]
    assert not any(
        "GRANT SELECT, MODIFY ON TABLE" in stmt
        and target in stmt
        and settings.history_grantee in stmt
        for stmt in recorded
    )
    # Other (filtered) tables still get their grantee grant.
    other = schema.QUERY_REPORTS
    assert other in report["row_filtered"]
    assert any(
        "GRANT SELECT, MODIFY ON TABLE" in stmt
        and other in stmt
        and settings.history_grantee in stmt
        for stmt in recorded
    )


def test_function_failure_blocks_all_filters_and_grantee_access(monkeypatch, settings):
    recorded = _install_fake_exec(monkeypatch, fail_substrings=("CREATE FUNCTION",))
    report = provisioning.bootstrap(_fake_workspace_client(), settings)

    assert report["ok"] is False
    assert report["row_filtered"] == []
    # Without the row-filter function, NO row filter is applied ...
    assert not any("SET ROW FILTER" in stmt for stmt in recorded)
    # ... and EVERY table's grantee access is withheld.
    assert sorted(report["grants_withheld"]) == sorted(schema.ALL_TABLE_NAMES)
    assert not any(
        "GRANT SELECT, MODIFY ON TABLE" in stmt and settings.history_grantee in stmt
        for stmt in recorded
    )


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
