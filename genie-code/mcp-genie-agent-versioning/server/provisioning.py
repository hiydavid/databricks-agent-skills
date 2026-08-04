"""Idempotent v2 schema provisioning, row isolation, and least-privilege grants."""

from __future__ import annotations

from typing import Any, Callable

from databricks.sdk import WorkspaceClient

from . import schema
from .config import Settings
from .sql import exec_sql, quote_ident


def _quote_principal(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def _run(workspace: WorkspaceClient, warehouse_id: str, sql: str):
    return exec_sql(workspace, warehouse_id, sql)


def _rows(response) -> list:
    if response is not None and response.result and response.result.data_array:
        return response.result.data_array
    return []


def _normalized_identifier(value: str) -> str:
    return "".join(value.replace("`", "").lower().split())


def _row_filter_binding(response) -> tuple[str, str] | None:
    """Extract the function and arguments from DESCRIBE TABLE EXTENDED output."""
    in_row_filter = False
    function = ""
    arguments = ""
    for row in _rows(response):
        cells = ["" if value is None else str(value).strip() for value in row]
        if not cells:
            continue
        label = cells[0].lower().lstrip("# ").replace("_", " ")
        value = " ".join(cell for cell in cells[1:] if cell)
        if label == "row filter":
            in_row_filter = True
            # Some runtimes report the whole binding on the section-heading row.
            if value:
                function = value
                arguments = value
            continue
        if in_row_filter and cells[0].startswith("#"):
            break
        if not in_row_filter:
            continue
        if label == "function":
            function = value
        elif label in ("arguments", "argument"):
            arguments = value
    if not function and not arguments:
        return None
    return function, arguments


def _is_expected_row_filter(
    binding: tuple[str, str], *, expected_function: str, expected_argument: str
) -> bool:
    function, arguments = binding
    return _normalized_identifier(expected_function) in _normalized_identifier(
        function
    ) and _normalized_identifier(expected_argument) in _normalized_identifier(arguments)


class _Report:
    def __init__(self, settings: Settings) -> None:
        self.data: dict[str, Any] = {
            "ok": False,
            "catalog": settings.history_catalog,
            "schema": settings.fq_schema,
            "grantee": settings.history_grantee,
            "owner_group": settings.history_owner_group or None,
            "catalog_created": False,
            "legacy_tables_preserved": [],
            "steps": [],
            "warnings": [],
            "errors": [],
        }

    def step(self, name: str, status: str, **extra: Any) -> None:
        self.data["steps"].append({"step": name, "status": status, **extra})

    def warn(self, name: str, error: object) -> None:
        self.step(name, "warning", error=str(error))
        self.data["warnings"].append(f"{name}: {error}")

    def error(self, name: str, error: object) -> None:
        self.step(name, "error", error=str(error))
        self.data["errors"].append(f"{name}: {error}")

    def attempt(self, name: str, action: Callable[[], Any], *, required: bool) -> bool:
        try:
            action()
            self.step(name, "ok")
            return True
        except Exception as exc:  # noqa: BLE001 - bootstrap returns a complete report
            if required:
                self.error(name, exc)
            else:
                self.warn(name, exc)
            return False


def bootstrap(workspace: WorkspaceClient, settings: Settings) -> dict:
    """Provision v2 objects as the app service principal; never raise.

    Existing v1 tables are neither altered nor dropped. If ``HISTORY_SCHEMA`` points at
    ``genie_space_history``, the v2 table is added alongside those legacy tables.
    """
    report = _Report(settings)
    missing = settings.missing_required()
    if missing:
        report.error("config", RuntimeError(f"missing required env: {', '.join(missing)}"))
        return report.data

    catalog = quote_ident(settings.history_catalog)
    fq_schema = f"{catalog}.{quote_ident(settings.history_schema)}"
    warehouse_id = settings.sql_warehouse_id

    try:
        _run(workspace, warehouse_id, f"SHOW SCHEMAS IN {catalog}")
        report.step("catalog_accessible", "ok")
    except Exception as exc:  # noqa: BLE001 - bootstrap always returns a report
        report.error("catalog_accessible", exc)
        report.data["note"] = (
            "The catalog must pre-exist. Grant the app service principal USE CATALOG and "
            "CREATE SCHEMA; this app never creates a catalog."
        )
        return report.data

    schema_ok = report.attempt(
        "create_schema",
        lambda: _run(
            workspace,
            warehouse_id,
            f"CREATE SCHEMA IF NOT EXISTS {fq_schema} "
            "COMMENT 'Private per-user Genie Agent configuration versions'",
        ),
        required=True,
    )
    function_ok = report.attempt(
        "create_only_mine_function",
        lambda: _run(workspace, warehouse_id, schema.only_mine_function_ddl(fq_schema)),
        required=True,
    )
    table_ok = report.attempt(
        "create_agent_config_versions",
        lambda: _run(workspace, warehouse_id, schema.agent_config_versions_ddl(fq_schema)),
        required=True,
    )

    versions_table = f"{fq_schema}.{quote_ident(schema.AGENT_CONFIG_VERSIONS)}"
    filter_ok = False
    if function_ok and table_ok:
        filter_step = "row_filter:agent_config_versions"
        filter_function = f"{fq_schema}.{quote_ident(schema.ROW_FILTER_FUNCTION)}"
        filter_sql = (
            f"ALTER TABLE {versions_table} SET ROW FILTER {filter_function} ON (created_by)"
        )
        try:
            described = _run(
                workspace,
                warehouse_id,
                f"DESCRIBE TABLE EXTENDED {versions_table}",
            )
            binding = _row_filter_binding(described)
            if binding is None:
                _run(workspace, warehouse_id, filter_sql)
                report.step(filter_step, "ok")
            elif _is_expected_row_filter(
                binding,
                expected_function=filter_function,
                expected_argument="created_by",
            ):
                report.step(filter_step, "already_configured")
            else:
                raise RuntimeError(
                    "table already has a different row filter; refusing to replace it: "
                    f"function={binding[0]!r}, arguments={binding[1]!r}"
                )
            filter_ok = True
        except Exception as exc:  # noqa: BLE001 - bootstrap returns a complete report
            report.error(filter_step, exc)
    else:
        report.error("row_filter:agent_config_versions", "table or row-filter function unavailable")

    # V1 rows cannot be promoted automatically because v1 did not persist all outer
    # restore fields. Detect and report the legacy table, but deliberately leave it intact.
    try:
        legacy = _rows(
            _run(workspace, warehouse_id, f"SHOW TABLES IN {fq_schema} LIKE 'config_snapshots'")
        )
        if legacy:
            report.data["legacy_tables_preserved"].append("config_snapshots")
            report.step("legacy_config_snapshots", "preserved")
    except Exception as exc:  # noqa: BLE001 - informational only
        report.warn("detect_legacy_config_snapshots", exc)

    grantee = _quote_principal(settings.history_grantee)
    # A schema owner cannot grant on its parent catalog. A catalog owner must grant
    # HISTORY_GRANTEE USE CATALOG before deployment; the explicit confirmation setting
    # prevents readiness from silently assuming that prerequisite was completed.
    grant_catalog_ok = settings.grantee_use_catalog_confirmed
    report.step("grantee_use_catalog", "operator_confirmed")
    grant_schema_ok = report.attempt(
        "grant_use_schema:grantee",
        lambda: _run(
            workspace,
            warehouse_id,
            f"GRANT USE SCHEMA ON SCHEMA {fq_schema} TO {grantee}",
        ),
        required=True,
    )
    grant_table_ok = False
    if filter_ok:
        grant_table_ok = report.attempt(
            "grant_table:grantee:agent_config_versions",
            lambda: _run(
                workspace,
                warehouse_id,
                f"GRANT SELECT, MODIFY ON TABLE {versions_table} TO {grantee}",
            ),
            required=True,
        )
    else:
        report.error(
            "grant_withheld:grantee:agent_config_versions",
            "row filter not verified; not issuing SELECT/MODIFY (existing grants, if any, "
            "are unchanged)",
        )

    # Ownership transfer is opt-in because it makes future automatic schema changes require
    # the durable owner (or a principal with equivalent ALTER privileges). It is useful
    # after a production schema stabilizes, but unnecessary for a test deployment.
    if settings.transfer_ownership:
        owner = _quote_principal(settings.history_owner_group)
        for object_name, statement in (
            (
                "agent_config_versions",
                f"ALTER TABLE {versions_table} OWNER TO {owner}",
            ),
            (
                "only_mine",
                f"ALTER FUNCTION {fq_schema}.{quote_ident(schema.ROW_FILTER_FUNCTION)} "
                f"OWNER TO {owner}",
            ),
            ("schema", f"ALTER SCHEMA {fq_schema} OWNER TO {owner}"),
        ):
            report.attempt(
                f"owner_to:{object_name}",
                lambda sql=statement: _run(workspace, warehouse_id, sql),
                required=False,
            )

    report.data["ok"] = all(
        (
            schema_ok,
            function_ok,
            table_ok,
            filter_ok,
            grant_catalog_ok,
            grant_schema_ok,
            grant_table_ok,
        )
    )
    return report.data
