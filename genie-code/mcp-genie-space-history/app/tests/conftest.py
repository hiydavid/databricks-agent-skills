"""Test fixtures — a fully in-memory SQL backend so tests need NO live workspace.

:class:`InMemoryBackend` is a fake :data:`~server.sql.SqlExec`: it records every
statement + bound params, simulates ``INSERT`` (stores the row keyed by its logical
PK) and ``SELECT ... WHERE pk = :id LIMIT 1`` (the store's idempotency dedupe /
get_artifact lookup). This lets the store and tool logic be exercised end-to-end
against real SQL strings + bound parameters, without the Databricks SDK ever making
a network call.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional, Sequence

import pytest

from server import schema
from server.config import Settings
from server.sql import Param, QueryResult
from server.store import UCTableStore

# `cat`.`schema`.`table` — capture the table name (3rd backtick-quoted part).
_TABLE_RE = re.compile(r"`[^`]+`\.`[^`]+`\.`([^`]+)`")


def param_value(params: Sequence[Param], name: str) -> Optional[str]:
    for p in params:
        if p.name == name:
            return p.value
    return None


def _table_of(sql: str) -> Optional[str]:
    m = _TABLE_RE.search(sql)
    return m.group(1) if m else None


_ID_COLUMN = {spec.name: spec.id_column for spec in schema.TABLE_SPECS}


class InMemoryBackend:
    """A stateful fake SqlExec simulating the genie_space_history tables."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Param]]] = []
        # table_name -> id_value -> row dict (col -> value)
        self.rows: dict[str, dict[str, dict]] = defaultdict(dict)
        # configurable canned result for list_history queries
        self.list_result = QueryResult([], [])

    # --- call recording helpers -------------------------------------------
    def inserts_into(self, table_name: str) -> list[tuple[str, list[Param]]]:
        return [
            (sql, params)
            for sql, params in self.calls
            if sql.lstrip().startswith("INSERT") and _table_of(sql) == table_name
        ]

    def all_inserts(self) -> list[tuple[str, list[Param]]]:
        return [(sql, params) for sql, params in self.calls if sql.lstrip().startswith("INSERT")]

    # --- the SqlExec interface --------------------------------------------
    def __call__(self, sql: str, parameters: Optional[Sequence[Param]] = None) -> QueryResult:
        params = list(parameters or [])
        self.calls.append((sql, params))
        stripped = sql.lstrip()

        if "ORDER BY created_at DESC" in sql:  # list_history
            return self.list_result

        if stripped.startswith("SELECT *") and "LIMIT 1" in sql:  # _find_by_id / get_artifact
            table = _table_of(sql)
            id_value = param_value(params, "id")
            row = self.rows.get(table or "", {}).get(id_value or "")
            if row is None:
                return QueryResult([], [])
            return QueryResult(list(row.keys()), [list(row.values())])

        if stripped.startswith("INSERT"):
            table = _table_of(sql) or ""
            row = {p.name: p.value for p in params}
            id_col = _ID_COLUMN.get(table)
            key = row.get(id_col) if id_col else None
            if key is not None:
                self.rows[table][key] = row
            return QueryResult([], [])

        return QueryResult([], [])


@pytest.fixture
def settings() -> Settings:
    return Settings(
        history_catalog="testcat",
        history_owner_group="owner_group",
        history_grantee="grantee_group",
        sql_warehouse_id="wh123",
        use_variant=False,
    )


@pytest.fixture
def backend() -> InMemoryBackend:
    return InMemoryBackend()


@pytest.fixture
def store(backend: InMemoryBackend, settings: Settings) -> UCTableStore:
    return UCTableStore(backend, settings, user_name="alice@example.com")
