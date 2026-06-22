"""UC storage adapter — :class:`UCTableStore` (spec §6/§7/§11).

All user data is bound server-side (:class:`~server.sql.Param`); nothing is
string-interpolated into SQL. Identifiers are validated + backtick-quoted.

The store is SDK-shape-free: it talks to a :data:`~server.sql.SqlExec` callable
that returns a normalized :class:`~server.sql.QueryResult`. Production wires that
to a real warehouse via :func:`~server.sql.make_sql_exec`; tests inject a fake.
Each write method takes the resolved ``user_name`` explicitly (the tool layer
resolves it from ``current_user.me()`` — spec §6) and stamps ``created_at``
server-side via ``current_timestamp()``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional, Sequence

from . import schema
from .config import Settings
from .sql import Param, QueryResult, SqlExec, quote_ident


def sha256_hex(text: str) -> str:
    """sha256 hex digest of a UTF-8 string (config_hash / idempotency basis)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _derive_id(namespace: str, key: str) -> str:
    """Deterministic 32-char hex id from (namespace, idempotency key).

    Same (namespace, key) always yields the same id, so a retried write resolves
    to the same row instead of inserting a duplicate (spec §6 idempotency). The
    32-char hex shape matches the spec's id convention.
    """
    return hashlib.sha256(f"{namespace}\x00{key}".encode("utf-8")).hexdigest()[:32]


def _new_id() -> str:
    """A fresh random 32-char hex id (used when no idempotency key is supplied)."""
    return uuid.uuid4().hex


def _infer_type(value: Any) -> Optional[str]:
    # bool is a subclass of int — check it first.
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "BIGINT"
    if isinstance(value, float):
        return "DOUBLE"
    return None


def _to_param_str(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class _InsertBuilder:
    """Accumulates columns/value-expressions/params for a single INSERT.

    Columns whose value is ``None`` are omitted entirely so the table's DEFAULTs
    (or NULL) apply — this avoids binding NULLs into typed/JSON/array columns.
    """

    def __init__(self) -> None:
        self._cols: list[str] = []
        self._exprs: list[str] = []
        self._params: list[Param] = []

    def set(self, col: str, value: Any) -> None:
        if value is None:
            return
        self._cols.append(quote_ident(col))
        self._exprs.append(f":{col}")
        self._params.append(Param(col, _to_param_str(value), _infer_type(value)))

    def set_json(self, col: str, value: Any, *, use_variant: bool) -> None:
        if value is None:
            return
        text = value if isinstance(value, str) else json.dumps(value)
        self._cols.append(quote_ident(col))
        # parse_json(...) returns VARIANT; only valid when the column is VARIANT.
        self._exprs.append(f"parse_json(:{col})" if use_variant else f":{col}")
        self._params.append(Param(col, text, None))

    def set_array(self, col: str, values: Optional[Sequence[str]]) -> None:
        if values is None:
            return
        self._cols.append(quote_ident(col))
        self._exprs.append(f"from_json(:{col}, 'ARRAY<STRING>')")
        self._params.append(Param(col, json.dumps(list(values)), None))

    def set_raw(self, col: str, expr: str) -> None:
        """A column set to a raw SQL expression (e.g. ``current_timestamp()``)."""
        self._cols.append(quote_ident(col))
        self._exprs.append(expr)

    def build(self, fq_table: str) -> tuple[str, list[Param]]:
        cols = ", ".join(self._cols)
        exprs = ", ".join(self._exprs)
        return f"INSERT INTO {fq_table} ({cols}) VALUES ({exprs})", self._params


class UCTableStore:
    """Read/write adapter over the ``genie_space_history`` tables."""

    def __init__(self, sql_exec: SqlExec, settings: Settings, *, user_name: str):
        self._run = sql_exec
        self.settings = settings
        self.user_name = user_name

    # --- identifiers -------------------------------------------------------
    @property
    def _fq_schema(self) -> str:
        cat = quote_ident(self.settings.history_catalog)
        sch = quote_ident(self.settings.history_schema)
        return f"{cat}.{sch}"

    def _fq_table(self, table_name: str) -> str:
        return f"{self._fq_schema}.{quote_ident(table_name)}"

    # --- helpers -----------------------------------------------------------
    def _next_version(self, space_id: str) -> int:
        """Monotonic per-``space_id`` version (1, 2, 3…).

        Under OBO + the ``only_mine`` row filter this counts only the caller's own
        snapshots for the space (other users' rows are invisible) — the intended
        per-user history semantics (spec §5).
        """
        sql = (
            f"SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
            f"FROM {self._fq_table(schema.CONFIG_SNAPSHOTS)} WHERE space_id = :space_id"
        )
        result = self._run(sql, [Param("space_id", space_id)])
        value = result.scalar()
        return int(value) if value is not None else 1

    def _find_by_id(self, spec: schema.TableSpec, id_value: str) -> Optional[dict]:
        sql = (
            f"SELECT * FROM {self._fq_table(spec.name)} "
            f"WHERE {quote_ident(spec.id_column)} = :id LIMIT 1"
        )
        return self._run(sql, [Param("id", id_value)]).first()

    # --- save_config_snapshot ---------------------------------------------
    def save_config_snapshot(
        self,
        *,
        space_id: str,
        serialized_space: str,
        etag: Optional[str] = None,
        parent_version_id: Optional[str] = None,
        run_id: Optional[str] = None,
        changed_surfaces: Optional[Sequence[str]] = None,
        change_summary: Optional[str] = None,
        rollback_reference: Optional[str] = None,
        skill_name: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """Persist a config version; returns ``{config_version_id, version, config_hash, etag}``.

        Server-computed: ``config_hash`` (sha256 of ``serialized_space``), a monotonic
        per-space ``version``, and the logical id. ``idempotency_key`` defaults to
        ``config_hash`` so re-saving identical content is a no-op that returns the
        existing row (spec §6).
        """
        config_hash = sha256_hex(serialized_space)
        idem = idempotency_key or config_hash
        config_version_id = _derive_id(f"config:{space_id}", idem)

        existing = self._find_by_id(schema.TABLE_SPECS[0], config_version_id)
        if existing is not None:
            return {
                "config_version_id": existing.get("config_version_id"),
                "version": int(existing["version"])
                if existing.get("version") is not None
                else None,
                "config_hash": existing.get("config_hash"),
                "etag": existing.get("etag"),
                "deduplicated": True,
            }

        version = self._next_version(space_id)
        b = _InsertBuilder()
        b.set("config_version_id", config_version_id)
        b.set("space_id", space_id)
        b.set("version", version)
        b.set("parent_version_id", parent_version_id)
        b.set_raw("created_at", "current_timestamp()")
        b.set("created_by", self.user_name)
        b.set("skill_name", skill_name)
        b.set_json("config_json", serialized_space, use_variant=self.settings.use_variant)
        b.set("config_hash", config_hash)
        b.set_array("changed_surfaces", changed_surfaces)
        b.set("etag", etag)
        b.set("run_id", run_id)
        b.set("rollback_reference", rollback_reference)
        b.set("change_summary", change_summary)
        sql, params = b.build(self._fq_table(schema.CONFIG_SNAPSHOTS))
        self._run(sql, params)

        return {
            "config_version_id": config_version_id,
            "version": version,
            "config_hash": config_hash,
            "etag": etag,
            "deduplicated": False,
        }

    # --- save_report -------------------------------------------------------
    def save_report(
        self,
        *,
        space_id: str,
        artifact_type: str,
        title: str,
        content_md: str,
        summary: Optional[str] = None,
        scores_findings: Optional[Any] = None,
        run_id: Optional[str] = None,
        config_version_id: Optional[str] = None,
        skill_name: Optional[str] = None,
        redacted: bool = True,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """Persist a Markdown report to the routed table; returns ``{artifact_id}``.

        The caller has already validated ``artifact_type``; we resolve its table here.
        ``idempotency_key`` (when supplied) makes retries return the same row (§6).
        """
        table_name = schema.ARTIFACT_TYPE_TO_REPORT_TABLE[artifact_type]
        spec = schema.TYPE_LABEL_TO_SPEC[artifact_type]

        if idempotency_key:
            artifact_id = _derive_id(f"report:{space_id}:{artifact_type}", idempotency_key)
            existing = self._find_by_id(spec, artifact_id)
            if existing is not None:
                return {"artifact_id": existing.get("artifact_id"), "deduplicated": True}
        else:
            artifact_id = _new_id()

        b = _InsertBuilder()
        b.set("artifact_id", artifact_id)
        b.set("space_id", space_id)
        b.set_raw("created_at", "current_timestamp()")
        b.set("created_by", self.user_name)
        b.set("skill_name", skill_name)
        b.set("title", title)
        b.set("content_md", content_md)
        b.set("summary", summary)
        b.set_json("scores_findings", scores_findings, use_variant=self.settings.use_variant)
        b.set("run_id", run_id)
        b.set("config_version_id", config_version_id)
        b.set("redacted", redacted)
        sql, params = b.build(self._fq_table(table_name))
        self._run(sql, params)
        return {"artifact_id": artifact_id, "deduplicated": False}

    # --- list_history ------------------------------------------------------
    def list_history(
        self,
        *,
        space_id: str,
        type_label: Optional[str] = None,
        limit: int = 50,
        since: Optional[str] = None,
    ) -> list[dict]:
        """UNION across the artifact tables for a space → normalized timeline rows.

        Each row: ``{id, type, version, created_at, created_by, summary, decision}``.
        ``type_label`` (optional) restricts to a single artifact type; ``since``
        filters on ``created_at``. ``limit`` is a server-validated integer, so it
        is inlined safely (parameter markers are not supported in LIMIT).
        """
        specs: Sequence[schema.TableSpec]
        specs = [schema.TYPE_LABEL_TO_SPEC[type_label]] if type_label else schema.TABLE_SPECS

        params: list[Param] = [Param("space_id", space_id)]
        since_clause = ""
        if since:
            since_clause = " AND created_at >= :since"
            params.append(Param("since", since, "TIMESTAMP"))

        subqueries = []
        for spec in specs:
            subqueries.append(
                f"SELECT {quote_ident(spec.id_column)} AS id, "
                f"'{spec.type_label}' AS type, "
                f"{spec.version_expr} AS version, "
                f"created_at, created_by, "
                f"{spec.summary_expr} AS summary, "
                f"{spec.decision_expr} AS decision "
                f"FROM {self._fq_table(spec.name)} "
                f"WHERE space_id = :space_id{since_clause}"
            )

        safe_limit = max(1, min(int(limit), 1000))
        union = "\nUNION ALL\n".join(subqueries)
        sql = f"SELECT * FROM (\n{union}\n) ORDER BY created_at DESC LIMIT {safe_limit}"
        return self._run(sql, params).dicts()

    # --- get_artifact ------------------------------------------------------
    def get_artifact(self, id_value: str) -> Optional[dict]:
        """Resolve an id across all tables; returns the full record or ``None``.

        Searches each table's logical-PK column in order (config first). Optimization
        runs / eval results have no P1 write tool but are resolved here (spec §6).
        """
        for spec in schema.TABLE_SPECS:
            record = self._find_by_id(spec, id_value)
            if record is not None:
                return {
                    "id": id_value,
                    "type": spec.type_label,
                    "table": spec.name,
                    "record": record,
                }
        return None

    # exposed for the optional list_history filter validation in the tool layer.
    @staticmethod
    def known_type_labels() -> set[str]:
        return set(schema.TYPE_LABEL_TO_SPEC.keys())


def query_result_to_dicts(result: QueryResult) -> list[dict]:
    """Convenience re-export for callers that hold a raw QueryResult."""
    return result.dicts()
