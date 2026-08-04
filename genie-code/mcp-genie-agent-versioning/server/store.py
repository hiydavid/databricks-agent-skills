"""OBO SQL storage adapter for Genie Agent configuration versions."""

from __future__ import annotations

import uuid
from typing import Optional

from . import schema
from .config import Settings
from .contracts import VersionCursor
from .sql import Param, SqlExec, quote_ident


class _InsertBuilder:
    """Build a parameterized INSERT while keeping server expressions unbound."""

    def __init__(self) -> None:
        self._columns: list[str] = []
        self._expressions: list[str] = []
        self._parameters: list[Param] = []

    def set(self, column: str, value: Optional[str]) -> None:
        if value is None:
            return
        if not isinstance(value, str):
            raise TypeError(f"bound value for {column!r} must be a string or None")
        self._columns.append(quote_ident(column))
        self._expressions.append(f":{column}")
        self._parameters.append(Param(column, value))

    def set_raw(self, column: str, expression: str) -> None:
        self._columns.append(quote_ident(column))
        self._expressions.append(expression)

    def build(self, table: str) -> tuple[str, list[Param]]:
        columns = ", ".join(self._columns)
        expressions = ", ".join(self._expressions)
        return f"INSERT INTO {table} ({columns}) VALUES ({expressions})", self._parameters


class AgentVersionStore:
    """Read/write adapter over the v2 ``agent_config_versions`` table."""

    def __init__(self, sql_exec: SqlExec, settings: Settings):
        self._run = sql_exec
        self.settings = settings

    @property
    def _fq_schema(self) -> str:
        return (
            f"{quote_ident(self.settings.history_catalog)}."
            f"{quote_ident(self.settings.history_schema)}"
        )

    @property
    def _versions_table(self) -> str:
        return f"{self._fq_schema}.{quote_ident(schema.AGENT_CONFIG_VERSIONS)}"

    def get_agent_version(self, *, space_id: str, version_id: str) -> Optional[dict]:
        sql = (
            "SELECT version_id, space_id, reason, config_envelope, config_hash, "
            "change_summary, parent_version_id, rollback_target_version_id, "
            f"created_at, created_by FROM {self._versions_table} "
            "WHERE space_id = :space_id AND version_id = :version_id LIMIT 1"
        )
        return self._run(
            sql,
            [Param("space_id", space_id), Param("version_id", version_id)],
        ).first()

    def agent_version_exists(self, *, space_id: str, version_id: str) -> bool:
        """Check a lineage reference without loading its configuration envelope."""
        sql = (
            f"SELECT 1 AS present FROM {self._versions_table} "
            "WHERE space_id = :space_id AND version_id = :version_id LIMIT 1"
        )
        return (
            self._run(
                sql,
                [Param("space_id", space_id), Param("version_id", version_id)],
            ).first()
            is not None
        )

    def _get_saved_version_metadata(self, *, space_id: str, version_id: str) -> Optional[dict]:
        sql = (
            "SELECT version_id, created_at, created_by, config_hash "
            f"FROM {self._versions_table} "
            "WHERE space_id = :space_id AND version_id = :version_id LIMIT 1"
        )
        return self._run(
            sql,
            [Param("space_id", space_id), Param("version_id", version_id)],
        ).first()

    def save_agent_config_version(
        self,
        *,
        space_id: str,
        reason: str,
        config_envelope: str,
        config_hash: str,
        change_summary: Optional[str] = None,
        parent_version_id: Optional[str] = None,
        rollback_target_version_id: Optional[str] = None,
    ) -> dict:
        """Append a new event and return its SQL-stamped identity and timestamp."""
        version_id = uuid.uuid4().hex
        builder = _InsertBuilder()
        builder.set("version_id", version_id)
        builder.set("space_id", space_id)
        builder.set("reason", reason)
        builder.set("config_envelope", config_envelope)
        builder.set("config_hash", config_hash)
        builder.set("change_summary", change_summary)
        builder.set("parent_version_id", parent_version_id)
        builder.set("rollback_target_version_id", rollback_target_version_id)
        builder.set_raw("created_at", "current_timestamp()")
        builder.set_raw("created_by", "SESSION_USER()")
        sql, parameters = builder.build(self._versions_table)
        self._run(sql, parameters)

        saved = self._get_saved_version_metadata(space_id=space_id, version_id=version_id)
        if saved is None:
            raise RuntimeError("version insert succeeded but the saved row could not be read back")
        return saved

    def list_agent_versions(
        self,
        *,
        space_id: str,
        limit: int,
        cursor: Optional[VersionCursor] = None,
    ) -> list[dict]:
        parameters = [Param("space_id", space_id)]
        cursor_clause = ""
        if cursor is not None:
            cursor_clause = (
                " AND (created_at < :cursor_created_at OR "
                "(created_at = :cursor_created_at AND version_id < :cursor_version_id))"
            )
            parameters.extend(
                [
                    Param("cursor_created_at", cursor.created_at, "TIMESTAMP"),
                    Param("cursor_version_id", cursor.version_id),
                ]
            )

        # Fetch one extra row so the tool can emit a next cursor without a COUNT query.
        sql_limit = limit + 1
        sql = (
            "SELECT version_id, reason, created_at, created_by, config_hash, "
            "change_summary, parent_version_id, rollback_target_version_id "
            f"FROM {self._versions_table} WHERE space_id = :space_id{cursor_clause} "
            f"ORDER BY created_at DESC, version_id DESC LIMIT {sql_limit}"
        )
        return self._run(sql, parameters).dicts()
