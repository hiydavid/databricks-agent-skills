"""Startup bootstrap, run as the app service principal (spec §7.1 / §10).

Idempotently creates the ``genie_space_history`` schema and ALL SEVEN per-artifact
tables, the ``only_mine`` row-filter function, applies the row filter to every
table, reassigns ownership to the durable ``HISTORY_OWNER_GROUP``, and grants the
OBO ``HISTORY_GRANTEE`` (while keeping the SP's own SELECT/MODIFY).

Hard invariants (spec §7.1/§10):
  * The **catalog is NEVER created** — it must pre-exist; we only ``USE`` it.
  * Bootstrap is **fully idempotent** (``IF NOT EXISTS`` + existence checks).
  * Ownership reassignment **may legitimately fail** if the SP isn't a member of
    ``HISTORY_OWNER_GROUP`` (UC anti-escalation). That is captured as a structured
    WARNING and bootstrap continues — startup must NOT crash (an operator/metastore
    admin runs the one-time ``OWNER TO``).

The report this returns is logged at startup; nothing here raises.
"""

from __future__ import annotations

from typing import Any, Callable

from databricks.sdk import WorkspaceClient

from . import schema
from .config import Settings
from .sql import SqlError, exec_sql, quote_ident


def _quote_principal(name: str) -> str:
    """Backtick-quote a UC principal/group name (groups/SP-ids allow ``-``/spaces).

    Escapes embedded backticks. Names come from operator-set env, not user input.
    """
    return "`" + name.replace("`", "``") + "`"


def _run(w: WorkspaceClient, warehouse_id: str, sql: str):
    # All provisioning statements bind no user data — identifiers come from our own
    # schema constants / operator env, validated + quoted above.
    return exec_sql(w, warehouse_id, sql)


def _rows(resp) -> list:
    if resp is not None and resp.result and resp.result.data_array:
        return resp.result.data_array
    return []


class _Report:
    def __init__(self, settings: Settings) -> None:
        self.data: dict[str, Any] = {
            "ok": False,
            "catalog": settings.history_catalog,
            "schema": settings.fq_schema,
            "owner_group": settings.history_owner_group,
            "grantee": settings.history_grantee,
            "use_variant": settings.use_variant,
            "catalog_created": False,  # invariant: we never CREATE CATALOG
            "tables_created": [],
            "tables_existing": [],
            "steps": [],
            "warnings": [],
        }

    def step(self, name: str, status: str, **extra: Any) -> None:
        entry = {"step": name, "status": status, **extra}
        self.data["steps"].append(entry)

    def warn(self, name: str, exc: Exception) -> None:
        self.step(name, "warning", error=str(exc))
        self.data["warnings"].append(f"{name}: {exc}")

    def attempt(self, name: str, fn: Callable[[], Any]) -> bool:
        """Run ``fn``; on failure record a WARNING and continue (never raise)."""
        try:
            fn()
            self.step(name, "ok")
            return True
        except Exception as exc:  # noqa: BLE001 — bootstrap must never crash startup
            self.warn(name, exc)
            return False


def bootstrap(w: WorkspaceClient, settings: Settings) -> dict:
    """Provision schema/tables/filter/ownership/grants idempotently. Never raises."""
    report = _Report(settings)
    cat = quote_ident(settings.history_catalog)
    fq = f"{quote_ident(settings.history_catalog)}.{quote_ident(settings.history_schema)}"
    wh = settings.sql_warehouse_id

    missing = settings.missing_required()
    if missing:
        report.data["ok"] = False
        report.warn("config", RuntimeError(f"missing required env: {', '.join(missing)}"))
        return report.data

    # 1) Catalog must pre-exist and be accessible — we NEVER create it.
    try:
        _run(w, wh, f"SHOW SCHEMAS IN {cat}")
        report.step("catalog_accessible", "ok")
    except SqlError as exc:
        report.data["ok"] = False
        report.warn("catalog_accessible", exc)
        report.data["note"] = (
            "Catalog missing or the app SP lacks USE CATALOG. The operator must grant the "
            "app SP `USE CATALOG` + `CREATE SCHEMA` on HISTORY_CATALOG (spec §10). "
            "The app never creates the catalog."
        )
        return report.data

    # 2) Schema (idempotent).
    report.attempt("create_schema", lambda: _run(w, wh, f"CREATE SCHEMA IF NOT EXISTS {fq}"))

    # 3) Row-filter function (idempotent).
    report.attempt(
        "create_only_mine_function",
        lambda: _run(w, wh, schema.only_mine_function_ddl(fq)),
    )

    # 4) The seven tables (idempotent). Track created-vs-existing for the report.
    for table_name, ddl in schema.all_table_ddls(fq, use_variant=settings.use_variant):
        try:
            existed = bool(_rows(_run(w, wh, f"SHOW TABLES IN {fq} LIKE '{table_name}'")))
        except SqlError:
            existed = False
        ok = report.attempt(f"create_table:{table_name}", lambda d=ddl: _run(w, wh, d))
        if ok:
            (report.data["tables_existing"] if existed else report.data["tables_created"]).append(
                table_name
            )

    # 5) Row filter on created_by for every table (idempotent — SET replaces).
    #    May fail on a restart once ownership has moved off the SP → captured as WARNING.
    for table_name in schema.ALL_TABLE_NAMES:
        stmt = (
            f"ALTER TABLE {fq}.{quote_ident(table_name)} "
            f"SET ROW FILTER {fq}.{quote_ident(schema.ROW_FILTER_FUNCTION)} ON (created_by)"
        )
        report.attempt(f"row_filter:{table_name}", lambda s=stmt: _run(w, wh, s))

    # 6) Grants for the OBO user group (HISTORY_GRANTEE). Done BEFORE the ownership
    #    handoff (while the SP still owns the objects), so the grants reliably apply
    #    and persist past the OWNER TO. USE CATALOG may warn if the SP can't grant at
    #    the catalog level — that grant is ultimately the operator's responsibility.
    grantee = _quote_principal(settings.history_grantee)
    report.attempt(
        "grant_use_catalog:grantee",
        lambda: _run(w, wh, f"GRANT USE CATALOG ON CATALOG {cat} TO {grantee}"),
    )
    report.attempt(
        "grant_schema:grantee",
        lambda: _run(w, wh, f"GRANT USE SCHEMA, SELECT, MODIFY ON SCHEMA {fq} TO {grantee}"),
    )

    # 7) Ensure the app SP keeps SELECT/MODIFY after it stops being owner (spec §7.1).
    try:
        sp_name = w.current_user.me().user_name
    except Exception as exc:  # noqa: BLE001
        sp_name = None
        report.warn("resolve_sp_identity", exc)
    if sp_name:
        sp = _quote_principal(sp_name)
        report.attempt(
            "grant_schema:app_sp",
            lambda: _run(w, wh, f"GRANT USE SCHEMA, SELECT, MODIFY ON SCHEMA {fq} TO {sp}"),
        )

    # 8) Durable ownership handoff to HISTORY_OWNER_GROUP (schema + each table; the
    #    function transfer is admin-gated). Ownership does NOT inherit — do each one.
    #    Failure here is EXPECTED when the SP isn't a member of the group → WARNING,
    #    and an operator/metastore admin runs the one-time OWNER TO (spec §7.1/§10).
    owner = _quote_principal(settings.history_owner_group)
    report.attempt(
        "owner_to:schema",
        lambda: _run(w, wh, f"ALTER SCHEMA {fq} OWNER TO {owner}"),
    )
    for table_name in schema.ALL_TABLE_NAMES:
        stmt = f"ALTER TABLE {fq}.{quote_ident(table_name)} OWNER TO {owner}"
        report.attempt(f"owner_to:{table_name}", lambda s=stmt: _run(w, wh, s))
    report.attempt(
        "owner_to:only_mine",
        lambda: _run(
            w,
            wh,
            f"ALTER FUNCTION {fq}.{quote_ident(schema.ROW_FILTER_FUNCTION)} OWNER TO {owner}",
        ),
    )

    # Bootstrap "succeeded" if the data path is usable: schema + all tables exist.
    created_or_existing = set(report.data["tables_created"]) | set(report.data["tables_existing"])
    report.data["ok"] = set(schema.ALL_TABLE_NAMES).issubset(created_or_existing)
    return report.data
