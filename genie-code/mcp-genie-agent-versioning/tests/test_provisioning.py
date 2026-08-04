"""V2 provisioning, row-filter, grant, and legacy-preservation bootstrap tests."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from typing import cast

from databricks.sdk import WorkspaceClient

from server import provisioning, schema


def _workspace() -> WorkspaceClient:
    return cast(WorkspaceClient, object())


def _response(rows=None):
    return SimpleNamespace(result=SimpleNamespace(data_array=rows or []))


def _runner(calls, *, fail_fragment=None, legacy=False):
    def run(_workspace, _warehouse_id, sql):
        calls.append(sql)
        if fail_fragment and fail_fragment in sql:
            raise RuntimeError(f"forced failure: {fail_fragment}")
        if "SHOW TABLES" in sql and "config_snapshots" in sql:
            return _response([["", "config_snapshots"]] if legacy else [])
        return _response()

    return run


def test_bootstrap_creates_only_v2_user_table(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(provisioning, "_run", _runner(calls))
    report = provisioning.bootstrap(_workspace(), settings)

    assert report["ok"] is True
    joined = "\n".join(calls)
    assert schema.AGENT_CONFIG_VERSIONS in joined
    assert "schema_migrations" not in joined
    assert "optimization_runs" not in joined
    assert "diagnose_reports" not in joined
    assert not any("CREATE CATALOG" in sql for sql in calls)
    assert not any("GRANT USE CATALOG" in sql for sql in calls)


def test_table_has_required_defaults_and_row_filter(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(provisioning, "_run", _runner(calls))
    provisioning.bootstrap(_workspace(), settings)
    joined = "\n".join(calls)
    assert "created_at                 TIMESTAMP NOT NULL DEFAULT current_timestamp()" in joined
    assert "created_by                 STRING    NOT NULL DEFAULT SESSION_USER()" in joined
    assert "delta.enableRowTracking = true" in joined
    assert "SET ROW FILTER" in joined
    assert "ON (created_by)" in joined


def test_existing_expected_row_filter_is_not_reapplied(monkeypatch, settings):
    calls = []
    expected_rows = [
        ["# Row Filter", "", ""],
        ["Function", "`testcat`.`genie_agent_versioning`.`only_mine`", ""],
        ["Arguments", "[`created_by`]", ""],
        ["# Detailed Table Information", "", ""],
    ]

    def run(_workspace, _warehouse_id, sql):
        calls.append(sql)
        if "DESCRIBE TABLE EXTENDED" in sql:
            return _response(expected_rows)
        return _response()

    monkeypatch.setattr(provisioning, "_run", run)
    report = provisioning.bootstrap(_workspace(), settings)

    assert report["ok"] is True
    assert not any("SET ROW FILTER" in sql for sql in calls)
    assert {
        "step": "row_filter:agent_config_versions",
        "status": "already_configured",
    } in report["steps"]


def test_different_existing_row_filter_fails_closed(monkeypatch, settings):
    calls = []
    unexpected_rows = [
        ["# Row Filter", "", ""],
        ["Function", "`testcat`.`other`.`filter`", ""],
        ["Arguments", "[`tenant_id`]", ""],
    ]

    def run(_workspace, _warehouse_id, sql):
        calls.append(sql)
        if "DESCRIBE TABLE EXTENDED" in sql:
            return _response(unexpected_rows)
        return _response()

    monkeypatch.setattr(provisioning, "_run", run)
    report = provisioning.bootstrap(_workspace(), settings)

    assert report["ok"] is False
    assert not any("SET ROW FILTER" in sql for sql in calls)
    assert not any("GRANT SELECT, MODIFY" in sql for sql in calls)
    assert any("different row filter" in error for error in report["errors"])


def test_row_filter_failure_withholds_data_grant(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(provisioning, "_run", _runner(calls, fail_fragment="SET ROW FILTER"))
    report = provisioning.bootstrap(_workspace(), settings)
    assert report["ok"] is False
    assert not any("GRANT SELECT, MODIFY" in sql for sql in calls)
    assert any("grant_withheld" in error for error in report["errors"])


def test_grant_failure_makes_readiness_report_fail(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(
        provisioning,
        "_run",
        _runner(calls, fail_fragment="GRANT SELECT, MODIFY"),
    )
    report = provisioning.bootstrap(_workspace(), settings)
    assert report["ok"] is False
    assert any("grant_table" in error for error in report["errors"])


def test_legacy_config_snapshots_are_detected_but_not_modified(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(provisioning, "_run", _runner(calls, legacy=True))
    report = provisioning.bootstrap(
        _workspace(), dataclasses.replace(settings, history_schema="genie_space_history")
    )
    assert report["legacy_tables_preserved"] == ["config_snapshots"]
    assert not any(
        statement.lstrip().upper().startswith(("DROP", "UPDATE", "DELETE", "MERGE"))
        for statement in calls
    )


def test_ownership_transfer_is_opt_in(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(provisioning, "_run", _runner(calls))
    provisioning.bootstrap(_workspace(), settings)
    assert not any("OWNER TO" in sql for sql in calls)

    calls.clear()
    with_transfer = dataclasses.replace(
        settings,
        transfer_ownership=True,
        history_owner_group="genie_history_owners",
    )
    provisioning.bootstrap(_workspace(), with_transfer)
    assert any("OWNER TO `genie_history_owners`" in sql for sql in calls)


def test_missing_configuration_returns_failed_report(settings):
    invalid = dataclasses.replace(settings, history_catalog="")
    report = provisioning.bootstrap(_workspace(), invalid)
    assert report["ok"] is False
    assert "HISTORY_CATALOG" in report["errors"][0]
