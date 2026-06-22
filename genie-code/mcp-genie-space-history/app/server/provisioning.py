"""Startup bootstrap, run as the app service principal (spec §7.1 / §10).

Idempotently creates the ``genie_space_history`` schema and ALL SEVEN per-artifact
tables, the ``only_mine`` row-filter function, applies the row filter to every
table, reassigns ownership to the durable ``HISTORY_OWNER_GROUP``, and grants the
OBO ``HISTORY_GRANTEE`` (while keeping the SP's own SELECT/MODIFY).

Hard invariants (spec §7.1/§10):
  * The **catalog is NEVER created** — it must pre-exist; we only ``USE`` it.
  * Bootstrap is **fully idempotent** (``IF NOT EXISTS`` + existence checks).
  * **Row isolation is REQUIRED, not best-effort (spec §5).** The ``only_mine``
    function and the per-table row filter must succeed, and ``HISTORY_GRANTEE`` is
    granted ``SELECT``/``MODIFY`` **per table, only on tables whose row filter
    actually applied** — never schema-wide. If the function or any table's filter
    fails, that table's grant is **withheld** and ``report["ok"]`` is ``False``, so
    the grantee can never reach an unfiltered table.
  * **Only** ownership reassignment may warn-and-continue: it legitimately fails if
    the SP isn't a member of ``HISTORY_OWNER_GROUP`` (UC anti-escalation), and an
    operator/metastore admin runs the one-time ``OWNER TO``. Startup never crashes.

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
            "row_filtered": [],
            "grants_withheld": [],  # tables denied grantee access because the filter didn't apply
            "steps": [],
            "warnings": [],
            "errors": [],
        }

    def step(self, name: str, status: str, **extra: Any) -> None:
        entry = {"step": name, "status": status, **extra}
        self.data["steps"].append(entry)

    def warn(self, name: str, exc: object) -> None:
        self.step(name, "warning", error=str(exc))
        self.data["warnings"].append(f"{name}: {exc}")

    def error(self, name: str, exc: object) -> None:
        self.step(name, "error", error=str(exc))
        self.data["errors"].append(f"{name}: {exc}")

    def attempt(self, name: str, fn: Callable[[], Any], *, required: bool = False) -> bool:
        """Run ``fn``; on failure record it and continue (never raise).

        ``required=True`` records a structured ERROR (gates ``report["ok"]``);
        otherwise a WARNING (warn-and-continue — only ownership transfer uses this).
        """
        try:
            fn()
            self.step(name, "ok")
            return True
        except Exception as exc:  # noqa: BLE001 — bootstrap must never crash startup
            if required:
                self.error(name, exc)
            else:
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
        report.error("config", RuntimeError(f"missing required env: {', '.join(missing)}"))
        return report.data

    # 1) Catalog must pre-exist and be accessible — we NEVER create it.
    try:
        _run(w, wh, f"SHOW SCHEMAS IN {cat}")
        report.step("catalog_accessible", "ok")
    except SqlError as exc:
        report.error("catalog_accessible", exc)
        report.data["note"] = (
            "Catalog missing or the app SP lacks USE CATALOG. The operator must grant the "
            "app SP `USE CATALOG` + `CREATE SCHEMA` on HISTORY_CATALOG (spec §10). "
            "The app never creates the catalog."
        )
        return report.data

    # 2) Schema (idempotent, required).
    schema_ok = report.attempt(
        "create_schema", lambda: _run(w, wh, f"CREATE SCHEMA IF NOT EXISTS {fq}"), required=True
    )

    # 3) Row-filter function (idempotent, REQUIRED — it gates row isolation, spec §5).
    function_ok = report.attempt(
        "create_only_mine_function",
        lambda: _run(w, wh, schema.only_mine_function_ddl(fq)),
        required=True,
    )

    # 4) The seven tables (idempotent, required). Track created-vs-existing.
    tables_present: set[str] = set()
    for table_name, ddl in schema.all_table_ddls(fq, use_variant=settings.use_variant):
        try:
            existed = bool(_rows(_run(w, wh, f"SHOW TABLES IN {fq} LIKE '{table_name}'")))
        except SqlError:
            existed = False
        ok = report.attempt(
            f"create_table:{table_name}", lambda d=ddl: _run(w, wh, d), required=True
        )
        if ok:
            tables_present.add(table_name)
            (report.data["tables_existing"] if existed else report.data["tables_created"]).append(
                table_name
            )

    # 5) Row filter on created_by for every present table (REQUIRED — spec §5). A table
    #    only counts as "protected" once its filter actually applied; without the function
    #    no filter can apply, so every grant is withheld below.
    row_filtered: set[str] = set()
    for table_name in schema.ALL_TABLE_NAMES:
        if table_name not in tables_present:
            continue
        if not function_ok:
            report.error(f"row_filter:{table_name}", "only_mine function unavailable")
            continue
        stmt = (
            f"ALTER TABLE {fq}.{quote_ident(table_name)} "
            f"SET ROW FILTER {fq}.{quote_ident(schema.ROW_FILTER_FUNCTION)} ON (created_by)"
        )
        if report.attempt(f"row_filter:{table_name}", lambda s=stmt: _run(w, wh, s), required=True):
            row_filtered.add(table_name)

    protected = {t for t in schema.ALL_TABLE_NAMES if t in tables_present and t in row_filtered}

    # 6) Grants for the OBO user group (HISTORY_GRANTEE), done BEFORE the ownership handoff
    #    (while the SP still owns the objects). USE CATALOG / USE SCHEMA are traversal-only
    #    (no data access) — best-effort. SELECT/MODIFY are granted PER TABLE and ONLY on
    #    row-filtered tables: a table whose filter didn't apply has its grant WITHHELD so
    #    the grantee can never read unfiltered rows (spec §5).
    grantee = _quote_principal(settings.history_grantee)
    report.attempt(
        "grant_use_catalog:grantee",
        lambda: _run(w, wh, f"GRANT USE CATALOG ON CATALOG {cat} TO {grantee}"),
    )
    report.attempt(
        "grant_use_schema:grantee",
        lambda: _run(w, wh, f"GRANT USE SCHEMA ON SCHEMA {fq} TO {grantee}"),
    )
    for table_name in schema.ALL_TABLE_NAMES:
        tbl = f"{fq}.{quote_ident(table_name)}"
        if table_name in protected:
            # Granting a protected table is operational (warn): failure just means the
            # grantee lacks access — it never EXPOSES unfiltered rows.
            report.attempt(
                f"grant_table:grantee:{table_name}",
                lambda t=tbl: _run(w, wh, f"GRANT SELECT, MODIFY ON TABLE {t} TO {grantee}"),
            )
        elif table_name in tables_present:
            report.error(
                f"grant_withheld:grantee:{table_name}",
                "row filter not applied; withholding SELECT/MODIFY to keep rows isolated",
            )
            report.data["grants_withheld"].append(table_name)

    # 7) Ensure the app SP keeps SELECT/MODIFY after it stops being owner (spec §7.1).
    #    The SP is the trusted bootstrapper, not the OBO isolation concern — grant it on
    #    every present table. Operational, so warn-and-continue.
    try:
        sp_name = w.current_user.me().user_name
    except Exception as exc:  # noqa: BLE001
        sp_name = None
        report.warn("resolve_sp_identity", exc)
    if sp_name:
        sp = _quote_principal(sp_name)
        report.attempt(
            "grant_use_schema:app_sp",
            lambda: _run(w, wh, f"GRANT USE SCHEMA ON SCHEMA {fq} TO {sp}"),
        )
        for table_name in sorted(tables_present):
            tbl = f"{fq}.{quote_ident(table_name)}"
            report.attempt(
                f"grant_table:app_sp:{table_name}",
                lambda t=tbl: _run(w, wh, f"GRANT SELECT, MODIFY ON TABLE {t} TO {sp}"),
            )

    # 8) Durable ownership handoff to HISTORY_OWNER_GROUP (schema + each table; the
    #    function transfer is admin-gated). Ownership does NOT inherit — do each one.
    #    This is the ONLY step allowed to warn-and-continue: it is EXPECTED to fail when
    #    the SP isn't a member of the group, and an admin runs the one-time OWNER TO.
    owner = _quote_principal(settings.history_owner_group)
    report.attempt("owner_to:schema", lambda: _run(w, wh, f"ALTER SCHEMA {fq} OWNER TO {owner}"))
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

    # Bootstrap "succeeded" only if the full row-isolation model is in place: schema +
    # function + all 7 tables created AND all 7 row-filtered (spec §5).
    report.data["row_filtered"] = sorted(row_filtered)
    report.data["ok"] = (
        schema_ok
        and function_ok
        and set(schema.ALL_TABLE_NAMES) <= tables_present
        and set(schema.ALL_TABLE_NAMES) <= row_filtered
    )
    return report.data
