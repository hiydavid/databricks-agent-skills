"""Test fixtures — a fully in-memory SQL backend so tests need NO live workspace.

:class:`InMemoryBackend` is a fake :data:`~server.sql.SqlExec`: it records every
statement + bound params, simulates ``INSERT`` (stores the row keyed by its logical
PK), ``SELECT ... WHERE pk = :id LIMIT 1`` (the store's dedupe / get_artifact lookup),
and ``COALESCE(MAX(version)) + 1`` (monotonic versioning). This lets the store and
tool logic be exercised end-to-end against real SQL strings + bound parameters,
without the Databricks SDK ever making a network call.
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
        # Concurrency simulation knobs for the config_snapshots verification query:
        #   pending_conflict    — a phantom row returned ONCE then cleared (a concurrent
        #                         writer that landed between our MAX(version) read + insert)
        #   persistent_conflict — a phantom row returned on EVERY verification (never converges)
        #   inject_dup_id       — return our own row twice ONCE (same-key concurrent insert)
        self.pending_conflict: Optional[dict] = None
        self.persistent_conflict: Optional[dict] = None
        self.inject_dup_id: bool = False

    # --- call recording helpers -------------------------------------------
    def inserts_into(self, table_name: str) -> list[tuple[str, list[Param]]]:
        return [
            (sql, params)
            for sql, params in self.calls
            if sql.lstrip().startswith("INSERT") and _table_of(sql) == table_name
        ]

    def all_inserts(self) -> list[tuple[str, list[Param]]]:
        return [(sql, params) for sql, params in self.calls if sql.lstrip().startswith("INSERT")]

    def deletes(self) -> list[tuple[str, list[Param]]]:
        return [(sql, params) for sql, params in self.calls if sql.lstrip().startswith("DELETE")]

    # --- the SqlExec interface --------------------------------------------
    def __call__(self, sql: str, parameters: Optional[Sequence[Param]] = None) -> QueryResult:
        params = list(parameters or [])
        self.calls.append((sql, params))
        stripped = sql.lstrip()

        if "COALESCE(MAX(version)" in sql:
            space_id = param_value(params, "space_id")
            versions = [
                int(row["version"])
                for row in self.rows[schema.CONFIG_SNAPSHOTS].values()
                if row.get("space_id") == space_id and row.get("version") is not None
            ]
            return QueryResult(["next_version"], [[(max(versions) + 1) if versions else 1]])

        if "config_version_id = :id OR version = :version" in sql:  # _snapshot_conflicts
            return self._conflicts(params)

        if "ORDER BY created_at DESC LIMIT" in sql:  # list_history
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

        if stripped.startswith("DELETE"):  # _delete_snapshot
            table = _table_of(sql) or ""
            id_value = param_value(params, "id")
            version = param_value(params, "version")
            row = self.rows.get(table, {}).get(id_value or "")
            if id_value is not None and row is not None and str(row.get("version")) == str(version):
                del self.rows[table][id_value]
            return QueryResult([], [])

        return QueryResult([], [])

    _CONFLICT_COLS = ["config_version_id", "version", "config_hash", "etag"]

    def _conflicts(self, params: Sequence[Param]) -> QueryResult:
        space_id = param_value(params, "space_id")
        id_value = param_value(params, "id")
        version = param_value(params, "version")
        matched: list[dict] = [
            r
            for r in self.rows[schema.CONFIG_SNAPSHOTS].values()
            if r.get("space_id") == space_id
            and (r.get("config_version_id") == id_value or str(r.get("version")) == str(version))
        ]
        out = [{c: r.get(c) for c in self._CONFLICT_COLS} for r in matched]

        if self.inject_dup_id:
            ours = next((r for r in out if r["config_version_id"] == id_value), None)
            if ours is not None:
                out.append(dict(ours))
            self.inject_dup_id = False
        if self.pending_conflict is not None:
            out.append({c: self.pending_conflict.get(c) for c in self._CONFLICT_COLS})
            self.pending_conflict = None
        if self.persistent_conflict is not None:
            out.append({c: self.persistent_conflict.get(c) for c in self._CONFLICT_COLS})

        return QueryResult(self._CONFLICT_COLS, [[r[c] for c in self._CONFLICT_COLS] for r in out])


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
