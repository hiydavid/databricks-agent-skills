"""SQL execution + the param/result adapter (spec §11).

Two layers, deliberately split so the storage logic can be unit-tested with NO
live workspace:

  * :class:`Param` / :class:`QueryResult` — pure, SDK-free value objects the
    store builds and consumes. Tests inject a fake executor returning
    ``QueryResult`` directly.
  * :func:`exec_sql` / :func:`make_sql_exec` — the production adapter that talks
    to the Databricks SDK ``statement_execution`` API. Server-side parameter
    binding is used everywhere; user data is NEVER string-interpolated into SQL.

Identifier safety: catalog/schema/table names come from env config (not caller
args), but we still validate + backtick-quote every identifier so a stray value
can never break out into injected SQL.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem, StatementState


class SqlError(RuntimeError):
    """A SQL statement reached a non-SUCCEEDED terminal state."""

    def __init__(self, message: str, *, state: Optional[str] = None, statement: str = ""):
        super().__init__(message)
        self.state = state
        self.statement = statement


# Identifiers are a restricted charset; anything else is rejected outright.
_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")


def quote_ident(name: str) -> str:
    """Validate and backtick-quote a single SQL identifier."""
    if not name or not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return f"`{name}`"


@dataclass(frozen=True)
class Param:
    """A server-side bound parameter (SDK-free; the adapter maps it to the SDK type).

    ``value=None`` binds a SQL NULL. ``type`` is the SQL type name (e.g. ``BIGINT``,
    ``BOOLEAN``); when omitted the value binds as STRING and the server implicitly
    casts to the column type.
    """

    name: str
    value: Optional[str]
    type: Optional[str] = None


@dataclass
class QueryResult:
    """Normalized result of a query — column names + row values, SDK-shape-free."""

    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)

    def dicts(self) -> list[dict]:
        return [dict(zip(self.columns, row, strict=False)) for row in self.rows]

    def first(self) -> Optional[dict]:
        ds = self.dicts()
        return ds[0] if ds else None


# A storage-facing SQL executor: run a statement (with optional bound params) and
# return a normalized result. Production builds this from a WorkspaceClient; tests
# supply a fake.
SqlExec = Callable[[str, Optional[Sequence[Param]]], QueryResult]


def exec_sql(
    w: WorkspaceClient,
    warehouse_id: str,
    statement: str,
    *,
    parameters: Optional[list[StatementParameterListItem]] = None,
    timeout_s: int = 120,
):
    """Run one SQL statement on a warehouse, blocking until a terminal state.

    Uses server-side parameter binding when ``parameters`` is supplied (spec §11).
    Raises :class:`SqlError` on any non-SUCCEEDED terminal state, carrying the
    warehouse's own error message.
    """
    resp = w.statement_execution.execute_statement(
        statement=statement,
        warehouse_id=warehouse_id,
        wait_timeout="30s",
        parameters=parameters,
    )
    statement_id = resp.statement_id
    if statement_id is None:
        raise SqlError("no statement_id returned by warehouse", state="ERROR", statement=statement)
    deadline = time.time() + timeout_s
    while resp.status and resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        if time.time() > deadline:
            raise SqlError("statement timed out", state="TIMEOUT", statement=statement)
        time.sleep(1.0)
        resp = w.statement_execution.get_statement(statement_id)

    state = resp.status.state if resp.status else None
    if state == StatementState.CLOSED and re.match(r"^\s*INSERT\b", statement, re.IGNORECASE):
        # INSERT has no result set to recover. CLOSED means execution completed but the
        # statement/result metadata expired before it was read back, so retrying would
        # risk appending a duplicate row.
        return resp
    if state != StatementState.SUCCEEDED:
        err = ""
        if resp.status and resp.status.error:
            err = resp.status.error.message or ""
        state_value = state.value if state else "UNKNOWN"
        message = f"SQL {state_value}"
        if err:
            message += f": {err}"
        raise SqlError(message, state=state.value if state else None, statement=statement)
    return resp


def to_query_result(resp) -> QueryResult:
    """Convert an SDK ``StatementResponse`` to a normalized :class:`QueryResult`."""
    columns: list[str] = []
    if resp is not None and resp.manifest and resp.manifest.schema and resp.manifest.schema.columns:
        columns = [c.name or "" for c in resp.manifest.schema.columns]
    rows: list[list] = []
    if resp is not None and resp.result and resp.result.data_array:
        rows = [list(r) for r in resp.result.data_array]
    return QueryResult(columns=columns, rows=rows)


def _to_sdk_params(
    parameters: Optional[Sequence[Param]],
) -> Optional[list[StatementParameterListItem]]:
    if not parameters:
        return None
    return [StatementParameterListItem(name=p.name, value=p.value, type=p.type) for p in parameters]


def make_sql_exec(w: WorkspaceClient, warehouse_id: str) -> SqlExec:
    """Build the production :data:`SqlExec` bound to a client + warehouse."""

    def run(statement: str, parameters: Optional[Sequence[Param]] = None) -> QueryResult:
        resp = exec_sql(w, warehouse_id, statement, parameters=_to_sdk_params(parameters))
        return to_query_result(resp)

    return run
