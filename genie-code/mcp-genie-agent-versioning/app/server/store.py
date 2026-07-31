"""UC storage adapter — :class:`UCTableStore` (spec §6/§7/§11).

All user data is bound server-side (:class:`~server.sql.Param`); nothing is
string-interpolated into SQL. Identifiers are validated + backtick-quoted.

The store is SDK-shape-free: it talks to a :data:`~server.sql.SqlExec` callable
that returns a normalized :class:`~server.sql.QueryResult`. Production wires that
to a real warehouse via :func:`~server.sql.make_sql_exec`; tests inject a fake.

``created_at`` and ``created_by`` are stamped **server-side** via
``current_timestamp()`` / ``current_user()`` so that ``created_by`` is guaranteed
to equal the ``SESSION_USER()`` the ``only_mine`` row filter compares against
(spec §5/§7.1) — i.e. a user can always read back their own writes.

Concurrency note (spec §6/§11): UC SQL warehouses enforce **no** PK/unique
constraints or row locks and give us no multi-statement transaction. Config
snapshots therefore carry **no monotonic version counter** — there is nothing to
contend on. A save is a single ``INSERT``; snapshots are ordered and identified by
the server-stamped ``created_at`` timestamp plus the ``config_version_id`` primary
key. Idempotency is preserved by deriving that id deterministically from the
idempotency key (default: ``config_hash``) and reading-before-write, so a repeated
key resolves to the existing row instead of inserting a duplicate.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Mapping, Optional, Sequence

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
    def _find_by_id(self, spec: schema.TableSpec, id_value: str) -> Optional[dict]:
        sql = (
            f"SELECT * FROM {self._fq_table(spec.name)} "
            f"WHERE {quote_ident(spec.id_column)} = :id LIMIT 1"
        )
        return self._run(sql, [Param("id", id_value)]).first()

    @staticmethod
    def _dedup_result(row: dict) -> dict:
        """Shape an existing config_snapshots row as a deduplicated save result."""
        return {
            "config_version_id": row.get("config_version_id"),
            "config_hash": row.get("config_hash"),
            "etag": row.get("etag"),
            "deduplicated": True,
        }

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
        """Persist a config snapshot; returns ``{config_version_id, config_hash, etag}``.

        Server-computed: ``config_hash`` (sha256 of ``serialized_space``) and the logical
        id (deterministic from the idempotency key — which defaults to ``config_hash``, so
        re-saving identical content is a no-op that returns the existing row, spec §6).

        There is **no monotonic version counter**: snapshots are ordered/identified by the
        server-stamped ``created_at`` plus ``config_version_id`` (spec §6/§11). A save is a
        single ``INSERT`` — no ``MAX(version)`` read, no post-insert reconciliation, nothing
        to contend on. Idempotency is enforced by a read-before-write on the deterministic
        id: a repeated key resolves to the existing row instead of inserting a duplicate.
        """
        config_hash = sha256_hex(serialized_space)
        idem = idempotency_key or config_hash
        config_version_id = _derive_id(f"config:{space_id}", idem)
        spec = schema.TABLE_SPECS[0]

        # Idempotency read-before-write: a repeated key (default: byte-identical content)
        # resolves to the existing row rather than inserting a duplicate (spec §6).
        existing = self._find_by_id(spec, config_version_id)
        if existing is not None:
            return self._dedup_result(existing)

        b = _InsertBuilder()
        b.set("config_version_id", config_version_id)
        b.set("space_id", space_id)
        b.set("parent_version_id", parent_version_id)
        b.set_raw("created_at", "current_timestamp()")
        b.set_raw("created_by", "current_user()")
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
        When ``idempotency_key`` is supplied the id is derived from it, so a sequential
        retry returns the existing row (read-before-write) instead of inserting again
        (spec §6). Without a key, each call gets a fresh random id (no dedupe intended).
        The same concurrent-same-key residual noted on ``save_config_snapshot`` applies.
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
        b.set_raw("created_by", "current_user()")
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

    # --- record_optimization_run ------------------------------------------
    def record_optimization_run(
        self,
        *,
        space_id: str,
        run_id: str,
        eval_results: Sequence[Mapping[str, Any]] = (),
        baseline_score: Optional[float] = None,
        candidate_score: Optional[float] = None,
        score_delta: Optional[float] = None,
        fixed_count: Optional[int] = None,
        regressed_count: Optional[int] = None,
        unchanged_count: Optional[int] = None,
        excluded_count: Optional[int] = None,
        decision: Optional[str] = None,
        parent_config_version_id: Optional[str] = None,
        result_config_version_id: Optional[str] = None,
        change_summary: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """Persist one ``optimization_runs`` row + N ``eval_results`` rows (FK ``run_id``).

        Returns ``{run_id, eval_count, deduplicated}``. The stored ``run_id`` is derived
        deterministically from the idempotency key (default: the caller's ``run_id``), so a
        retried record resolves to the existing run instead of inserting a duplicate — the
        same read-before-write pattern as ``save_config_snapshot``/``save_report`` (spec §6).
        On a dedupe hit the eval rows are **not** re-inserted.

        Each ``eval_results`` entry gets a stable ``eval_run_id`` derived from the run id +
        its position, and inherits the run's ``space_id``; ``created_at``/``created_by`` are
        stamped server-side on every row (spec §6/§7.1).
        """
        idem = idempotency_key or run_id
        run_row_id = _derive_id(f"run:{space_id}", idem)
        spec = next(s for s in schema.TABLE_SPECS if s.name == schema.OPTIMIZATION_RUNS)

        # Idempotency read-before-write: a repeated key resolves to the existing run row
        # rather than inserting a duplicate run (and its eval rows again) (spec §6).
        existing = self._find_by_id(spec, run_row_id)
        if existing is not None:
            return {
                "run_id": existing.get("run_id"),
                "eval_count": len(eval_results),
                "deduplicated": True,
            }

        b = _InsertBuilder()
        b.set("run_id", run_row_id)
        b.set("space_id", space_id)
        b.set_raw("created_at", "current_timestamp()")
        b.set_raw("created_by", "current_user()")
        b.set("baseline_score", baseline_score)
        b.set("candidate_score", candidate_score)
        b.set("score_delta", score_delta)
        b.set("fixed_count", fixed_count)
        b.set("regressed_count", regressed_count)
        b.set("unchanged_count", unchanged_count)
        b.set("excluded_count", excluded_count)
        b.set("decision", decision)
        b.set("parent_config_version_id", parent_config_version_id)
        b.set("result_config_version_id", result_config_version_id)
        b.set("change_summary", change_summary)
        sql, params = b.build(self._fq_table(schema.OPTIMIZATION_RUNS))
        self._run(sql, params)

        for index, entry in enumerate(eval_results):
            self._insert_eval_result(run_row_id, space_id, index, entry)

        return {"run_id": run_row_id, "eval_count": len(eval_results), "deduplicated": False}

    def _insert_eval_result(
        self, run_id: str, space_id: str, index: int, entry: Mapping[str, Any]
    ) -> None:
        """Insert one ``eval_results`` row (FK ``run_id``) for an already-validated entry."""
        question_id = entry.get("question_id")
        # Stable per-row PK: same (run, position) always yields the same id, so a row is
        # never silently duplicated even if the loop re-runs (spec §7.1).
        eval_run_id = _derive_id(f"eval:{run_id}", f"{index}:{question_id or ''}")
        b = _InsertBuilder()
        b.set("eval_run_id", eval_run_id)
        b.set("run_id", run_id)
        b.set("space_id", space_id)
        b.set_raw("created_at", "current_timestamp()")
        b.set_raw("created_by", "current_user()")
        b.set("question_id", question_id)
        b.set("assessment", entry.get("assessment"))
        b.set("primary_failure", entry.get("primary_failure"))
        b.set("baseline_sql_hash", entry.get("baseline_sql_hash"))
        b.set("candidate_sql_hash", entry.get("candidate_sql_hash"))
        b.set("baseline_result_digest", entry.get("baseline_result_digest"))
        b.set("candidate_result_digest", entry.get("candidate_result_digest"))
        b.set("latency_ms", entry.get("latency_ms"))
        sql, params = b.build(self._fq_table(schema.EVAL_RESULTS))
        self._run(sql, params)

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

        Each row: ``{id, type, version, created_at, created_by, summary, decision}``
        (``version`` is always NULL — config snapshots no longer carry a counter).
        ``type_label`` (optional) restricts to a single artifact type; ``since``
        filters on ``created_at``. ``limit`` is a server-validated integer, so it
        is inlined safely (parameter markers are not supported in LIMIT).

        Ordering is ``created_at DESC`` (newest first) with ``id`` as a stable
        secondary tiebreaker, so pagination / ``since`` stay deterministic even when
        two rows share a timestamp (spec §6).
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
        sql = f"SELECT * FROM (\n{union}\n) ORDER BY created_at DESC, id ASC LIMIT {safe_limit}"
        return self._run(sql, params).dicts()

    # --- get_artifact ------------------------------------------------------
    def get_artifact(self, id_value: str) -> Optional[dict]:
        """Resolve an id across all tables; returns the full record or ``None``.

        Searches each table's logical-PK column in order (config first). Optimization
        runs are written by ``record_optimization_run`` (P2) and resolved here by ``run_id``;
        eval-result rows have no dedicated get tool but are resolved here by ``eval_run_id``
        (spec §6).
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
