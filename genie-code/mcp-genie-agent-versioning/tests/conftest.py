"""In-memory SQL fixtures for the v2 store and tool contract."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional, Sequence

import pytest

from server import schema
from server.config import Settings
from server.sql import Param, QueryResult
from server.store import AgentVersionStore

_TABLE_RE = re.compile(r"`[^`]+`\.`[^`]+`\.`([^`]+)`")


def param_value(params: Sequence[Param], name: str) -> Optional[str]:
    for parameter in params:
        if parameter.name == name:
            return parameter.value
    return None


def _table_of(sql: str) -> Optional[str]:
    match = _TABLE_RE.search(sql)
    return match.group(1) if match else None


class InMemoryBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Param]]] = []
        self.rows: dict[str, dict[str, dict]] = defaultdict(dict)
        self.list_result: Optional[QueryResult] = None
        self.clock = 0

    def inserts_into(self, table_name: str) -> list[tuple[str, list[Param]]]:
        return [
            (sql, params)
            for sql, params in self.calls
            if sql.lstrip().startswith("INSERT") and _table_of(sql) == table_name
        ]

    def __call__(self, sql: str, parameters: Optional[Sequence[Param]] = None) -> QueryResult:
        params = list(parameters or [])
        self.calls.append((sql, params))
        stripped = sql.lstrip()

        if "ORDER BY created_at DESC, version_id DESC" in sql:
            if self.list_result is not None:
                return self.list_result
            rows = [
                row
                for row in self.rows[schema.AGENT_CONFIG_VERSIONS].values()
                if row["space_id"] == param_value(params, "space_id")
            ]
            rows.sort(key=lambda row: (row["created_at"], row["version_id"]), reverse=True)
            columns = [
                "version_id",
                "reason",
                "created_at",
                "created_by",
                "config_hash",
                "change_summary",
                "parent_version_id",
                "rollback_target_version_id",
            ]
            return QueryResult(columns, [[row.get(column) for column in columns] for row in rows])

        if stripped.startswith("SELECT") and "version_id = :version_id" in sql:
            version_id = param_value(params, "version_id") or ""
            row = self.rows[schema.AGENT_CONFIG_VERSIONS].get(version_id)
            if row is None or row["space_id"] != param_value(params, "space_id"):
                return QueryResult([], [])
            columns = list(row.keys())
            return QueryResult(columns, [[row[column] for column in columns]])

        if stripped.startswith("INSERT") and _table_of(sql) == schema.AGENT_CONFIG_VERSIONS:
            row = {parameter.name: parameter.value for parameter in params}
            self.clock += 1
            row["created_at"] = f"2026-07-30T12:00:{self.clock:02d}.000Z"
            row["created_by"] = "alice@example.com"
            row.setdefault("change_summary", None)
            row.setdefault("parent_version_id", None)
            row.setdefault("rollback_target_version_id", None)
            version_id = row["version_id"]
            assert isinstance(version_id, str)
            self.rows[schema.AGENT_CONFIG_VERSIONS][version_id] = row
            return QueryResult([], [])

        return QueryResult([], [])


@pytest.fixture
def settings() -> Settings:
    return Settings(
        history_catalog="testcat",
        history_schema="genie_agent_versioning",
        history_grantee="genie_testers",
        sql_warehouse_id="wh123",
        grantee_use_catalog_confirmed=True,
        workspace_origin="https://example.cloud.databricks.com",
    )


@pytest.fixture
def backend() -> InMemoryBackend:
    return InMemoryBackend()


@pytest.fixture
def store(backend: InMemoryBackend, settings: Settings) -> AgentVersionStore:
    return AgentVersionStore(backend, settings)


@pytest.fixture
def complete_config() -> dict:
    return {
        "serialized_space": (
            '{"version":2,"data_sources":{"tables":[]},'
            '"instructions":{"text_instructions":[]},"benchmarks":{}}'
        ),
        "title": "Revenue analyst",
        "description": "Answers revenue questions",
        "warehouse_id": "warehouse-1",
        "parent_path": "/Shared/Genie",
        "etag": "etag-at-capture",
    }
