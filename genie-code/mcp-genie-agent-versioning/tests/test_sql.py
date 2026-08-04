"""SQL statement terminal-state behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

from server.sql import SqlError, exec_sql


def _workspace_with(response) -> WorkspaceClient:
    class StatementExecution:
        def execute_statement(self, **_kwargs):
            return response

        def get_statement(self, _statement_id):
            raise AssertionError("terminal statements must not be polled")

    return cast(
        WorkspaceClient,
        SimpleNamespace(statement_execution=StatementExecution()),
    )


def _response(state: StatementState):
    return SimpleNamespace(
        statement_id="statement-id",
        status=SimpleNamespace(state=state, error=None),
    )


def test_closed_insert_is_treated_as_completed_to_avoid_duplicate_retry():
    response = _response(StatementState.CLOSED)

    result = exec_sql(_workspace_with(response), "warehouse", "  INSERT INTO t VALUES (1)")

    assert result is response


def test_closed_result_query_remains_an_error_with_clean_state_message():
    with pytest.raises(SqlError, match=r"^SQL CLOSED$") as exc_info:
        exec_sql(_workspace_with(_response(StatementState.CLOSED)), "warehouse", "SELECT 1")

    assert exc_info.value.state == "CLOSED"
