"""Core spike logic shared by the MCP tools (server/) and the local probes (probes/).

Every function takes an already-authenticated ``databricks.sdk.WorkspaceClient`` and
returns a plain JSON-serializable ``dict`` describing exactly what happened — including
raw API output where it matters — so callers can print it (probes) or return it over
MCP unchanged (server tools).

Design anchors: spec §7.1 (tables), §8 (rollback / Genie API), §13 P0 (exit criteria).

IMPORTANT: nothing here fabricates results. Each returned dict reflects a real API
call's outcome, and probes that can legitimately *fail* (e.g. the VARIANT probe) record
the failure instead of crashing, because the failure itself is the finding.
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem, StatementState


class SqlError(RuntimeError):
    """A SQL statement reached a non-SUCCEEDED terminal state."""

    def __init__(self, message: str, *, state: Optional[str] = None, statement: str = ""):
        super().__init__(message)
        self.state = state
        self.statement = statement


# Catalog/schema/table identifiers come from env config (not caller args), but validate +
# backtick-quote them anyway so a stray value can never break out into SQL injection.
_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _ident(name: str) -> str:
    if not name or not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return f"`{name}`"


# ---------------------------------------------------------------------------
# SQL helper
# ---------------------------------------------------------------------------
def exec_sql(
    w: WorkspaceClient,
    warehouse_id: str,
    statement: str,
    *,
    parameters: Optional[list] = None,
    timeout_s: int = 120,
):
    """Run one SQL statement on a warehouse and block until it reaches a terminal state.

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
    deadline = time.time() + timeout_s
    while resp.status and resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        if time.time() > deadline:
            raise SqlError("statement timed out", state="TIMEOUT", statement=statement)
        time.sleep(1.0)
        resp = w.statement_execution.get_statement(resp.statement_id)

    state = resp.status.state if resp.status else None
    if state != StatementState.SUCCEEDED:
        err = ""
        if resp.status and resp.status.error:
            err = resp.status.error.message or ""
        raise SqlError(
            f"SQL {state}: {err}",
            state=state.value if state else None,
            statement=statement,
        )
    return resp


def _rows(resp) -> list:
    """Extract the row array from a StatementResponse (empty list for DDL)."""
    if resp is not None and resp.result and resp.result.data_array:
        return resp.result.data_array
    return []


# ---------------------------------------------------------------------------
# Criterion #2 — OBO identity
# ---------------------------------------------------------------------------
def whoami(w: WorkspaceClient) -> dict:
    """Return the identity behind this client (``current_user.me()``).

    In the deployed App this client is built from ``X-Forwarded-Access-Token``, so it
    proves OBO returns the *calling* user. Locally it returns the developer identity.
    """
    me = w.current_user.me()
    return {
        "ok": True,
        "user_name": me.user_name,
        "display_name": me.display_name,
        "active": me.active,
        "id": me.id,
        "workspace_host": w.config.host,
    }


# ---------------------------------------------------------------------------
# Criterion #3 — auto-provision schema + one table (catalog NOT created)
# ---------------------------------------------------------------------------
# The rollback-critical table from spec §7.1 (1). JSON columns default to STRING
# (VARIANT is opt-in, gated on criterion #4).
_CONFIG_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS {fq}.config_snapshots (
  config_version_id   STRING    NOT NULL,
  space_id            STRING    NOT NULL,
  version             BIGINT    NOT NULL,
  parent_version_id   STRING,
  created_at          TIMESTAMP DEFAULT current_timestamp(),
  created_by          STRING    DEFAULT current_user(),
  skill_name          STRING,
  config_json         STRING,
  config_hash         STRING,
  diff_patch          STRING,
  changed_surfaces    ARRAY<STRING>,
  etag                STRING,
  run_id              STRING,
  rollback_reference  STRING,
  change_summary      STRING
) USING DELTA TBLPROPERTIES (
  delta.enableRowTracking = true,
  'delta.feature.allowColumnDefaults' = 'supported'   -- required for the DEFAULT clauses above
)
""".strip()


def provision(w: WorkspaceClient, *, catalog: str, schema: str, warehouse_id: str) -> dict:
    """Auto-create the ``genie_space_history`` schema + one table with ``IF NOT EXISTS``.

    Proves spec §12 #6: the app SP, given only ``USE CATALOG`` + ``CREATE SCHEMA``,
    provisions the schema/table idempotently and the **catalog is never created**.
    Idempotency is shown by recording whether each object pre-existed and by running the
    table DDL twice (both must SUCCEED).
    """
    cat_sql = _ident(catalog)
    fq_sql = f"{_ident(catalog)}.{_ident(schema)}"
    fq_display = f"{catalog}.{schema}"
    out: dict[str, Any] = {
        "catalog": catalog,
        "schema": fq_display,
        "table": f"{fq_display}.config_snapshots",
        "catalog_created_by_spike": False,  # invariant: we issue no CREATE CATALOG
    }

    # 1) Confirm the catalog exists / is accessible WITHOUT creating it.
    try:
        exec_sql(w, warehouse_id, f"SHOW SCHEMAS IN {cat_sql}")
        out["catalog_accessible"] = True
    except SqlError as e:
        out["catalog_accessible"] = False
        out["catalog_error"] = str(e)
        out["ok"] = False
        out["note"] = "Catalog missing or no USE CATALOG grant; spike does NOT create catalogs."
        return out

    # 2) Did the schema / table already exist? (so we can prove first-run creation)
    out["schema_existed_before"] = bool(
        _rows(exec_sql(w, warehouse_id, f"SHOW SCHEMAS IN {cat_sql} LIKE '{schema}'"))
    )

    # 3) Create the schema (idempotent).
    exec_sql(w, warehouse_id, f"CREATE SCHEMA IF NOT EXISTS {fq_sql}")

    out["table_existed_before"] = bool(
        _rows(exec_sql(w, warehouse_id, f"SHOW TABLES IN {fq_sql} LIKE 'config_snapshots'"))
    )

    # 4) Create the table twice — both must SUCCEED to demonstrate idempotency.
    ddl = _CONFIG_SNAPSHOTS_DDL.format(fq=fq_sql)
    r1 = exec_sql(w, warehouse_id, ddl)
    r2 = exec_sql(w, warehouse_id, ddl)
    out["ddl_run_1_state"] = r1.status.state.value
    out["ddl_run_2_state"] = r2.status.state.value
    out["idempotent"] = (
        r1.status.state == StatementState.SUCCEEDED
        and r2.status.state == StatementState.SUCCEEDED
    )
    out["ok"] = out["idempotent"]
    return out


# ---------------------------------------------------------------------------
# Criterion #4 — VARIANT probe (success => usable; failure => default STRING)
# ---------------------------------------------------------------------------
def variant_probe(
    w: WorkspaceClient, *, catalog: str, schema: str, warehouse_id: str, cleanup: bool = True
) -> dict:
    """Test whether VARIANT + ``parse_json`` work on the target warehouse.

    Per spec §12 #3 the decision defaults to STRING; this probe flips it to VARIANT
    only if every step succeeds. Failure is captured (not raised) — that is the finding.
    """
    fq_sql = f"{_ident(catalog)}.{_ident(schema)}"
    tbl_sql = f"{fq_sql}.`_variant_probe`"
    tbl_display = f"{catalog}.{schema}._variant_probe"
    steps: list[dict] = []
    out: dict[str, Any] = {"table": tbl_display}

    def step(name: str, sql: str, parameters=None):
        try:
            resp = exec_sql(w, warehouse_id, sql, parameters=parameters)
            steps.append({"step": name, "state": "SUCCEEDED"})
            return resp
        except SqlError as e:
            steps.append({"step": name, "state": e.state or "FAILED", "error": str(e)})
            raise

    try:
        exec_sql(w, warehouse_id, f"CREATE SCHEMA IF NOT EXISTS {fq_sql}")
        step("create_table_variant", f"CREATE TABLE IF NOT EXISTS {tbl_sql} (id STRING, payload VARIANT)")
        step("truncate", f"TRUNCATE TABLE {tbl_sql}")
        # Literals are bound server-side (the JSON is data, not interpolated SQL).
        step(
            "insert_parse_json",
            f"INSERT INTO {tbl_sql} SELECT :id, parse_json(:payload)",
            parameters=[
                StatementParameterListItem(name="id", value="k1"),
                StatementParameterListItem(name="payload", value='{"a": 1, "b": [2, 3]}'),
            ],
        )
        rb = step("read_back_variant_path", f"SELECT id, payload:a::int AS a, to_json(payload:b) AS b FROM {tbl_sql}")
        out["variant_usable"] = True
        out["read_back"] = _rows(rb)
        out["recommendation"] = "VARIANT"
    except SqlError as e:
        out["variant_usable"] = False
        out["error"] = str(e)
        out["recommendation"] = "STRING"
    finally:
        out["steps"] = steps
        if cleanup:
            try:
                exec_sql(w, warehouse_id, f"DROP TABLE IF EXISTS {tbl_sql}")
                out["cleanup"] = "dropped"
            except SqlError as e:
                out["cleanup"] = f"drop failed: {e}"

    out["ok"] = out.get("variant_usable", False)
    return out


# ---------------------------------------------------------------------------
# Criterion #5 — Genie get/update round-trip (idempotent no-op restore)
# ---------------------------------------------------------------------------
def _hash(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _space_summary(space) -> dict:
    return {
        "space_id": space.space_id,
        "title": space.title,
        "warehouse_id": space.warehouse_id,
        "etag": space.etag,
        "has_serialized_space": space.serialized_space is not None,
        "serialized_space_len": len(space.serialized_space) if space.serialized_space else 0,
        "config_hash": _hash(space.serialized_space),
    }


def _reapply_identical(w: WorkspaceClient, space, *, etag: Optional[str]):
    """Re-apply the EXACT serialized_space + outer metadata we just read (a no-op restore).

    Safe by construction: identical payload means the Space's effective config never
    changes. ``etag`` is passed explicitly so the caller controls the optimistic lock.
    """
    kwargs = dict(
        space_id=space.space_id,
        serialized_space=space.serialized_space,
        title=space.title,
        warehouse_id=space.warehouse_id,
        etag=etag,
    )
    if space.description is not None:
        kwargs["description"] = space.description
    return w.genie.update_space(**kwargs)


def genie_roundtrip(w: WorkspaceClient, *, space_id: str, apply: bool = True) -> dict:
    """``get_space(include_serialized_space=True)`` → re-apply the identical snapshot.

    Proves spec §8 / §12 #1: the read+write mechanism works and is non-destructive.
    With ``apply=False`` it's a dry run (read only).
    """
    before = w.genie.get_space(space_id, include_serialized_space=True)
    out: dict[str, Any] = {"before": _space_summary(before), "applied": False}

    if not apply:
        out["ok"] = before.serialized_space is not None
        out["note"] = "dry_run: read only, no update issued"
        return out

    # Fail closed: never push an empty/None serialized_space over a live Space.
    if before.serialized_space is None:
        out["ok"] = False
        out["error"] = "serialized_space is None; refusing to update (fail closed)"
        return out

    updated = _reapply_identical(w, before, etag=before.etag)
    out["applied"] = True
    out["after_update_etag"] = updated.etag

    # Re-read and confirm the config is byte-identical (idempotent no-op).
    after = w.genie.get_space(space_id, include_serialized_space=True)
    out["after"] = _space_summary(after)
    out["config_unchanged"] = _hash(before.serialized_space) == _hash(after.serialized_space)
    out["etag_rotated"] = before.etag != after.etag
    out["ok"] = out["config_unchanged"]
    return out


# ---------------------------------------------------------------------------
# Criterion #6 — stale-etag update is rejected (optimistic lock)
# ---------------------------------------------------------------------------
def etag_check(w: WorkspaceClient, *, space_id: str) -> dict:
    """Prove the body ``etag`` enforces optimistic concurrency.

    What this actually tests: that a **non-matching** etag is rejected. The Genie etag is
    content-based (see FINDINGS F-5), so re-applying the identical payload with the
    just-read etag is *not* a conflict — it is accepted. To force a conflict without
    changing the live config, we submit a deliberately **non-matching** etag and expect
    rejection. (A truly *stale* etag — one that was valid before a concurrent real edit —
    would require a controlled mutation of the Space, which this no-op spike avoids.)

    Sequence (all updates re-apply the identical serialized_space, so config never changes):
      1. read  -> etag1
      2. update with etag1 (valid) -> succeeds
      3. update with etag1 again -> accepted (content identical; etag still matches)
      4. update with a non-matching etag -> must be rejected
    """
    out: dict[str, Any] = {}
    before = w.genie.get_space(space_id, include_serialized_space=True)
    etag1 = before.etag
    out["etag_initial"] = etag1

    if before.serialized_space is None:
        out["ok"] = False
        out["error"] = "serialized_space is None; refusing to update (fail closed)"
        return out

    # Step 2: a valid update with the current etag.
    updated = _reapply_identical(w, before, etag=etag1)
    etag2 = updated.etag
    out["etag_after_valid_update"] = etag2
    out["etag_rotated"] = etag1 != etag2

    def try_etag(etag_value: str, label: str):
        try:
            _reapply_identical(w, before, etag=etag_value)
            return {"label": label, "etag_used": etag_value, "rejected": False}
        except Exception as e:  # noqa: BLE001 - we want the class + message verbatim
            return {
                "label": label,
                "etag_used": etag_value,
                "rejected": True,
                "error_class": type(e).__name__,
                "error_message": str(e),
            }

    attempts = [
        try_etag(etag1, "reuse_previous_etag"),         # expected: accepted (content identical)
        try_etag("nonmatching-etag-probe-0000", "nonmatching_etag"),  # expected: rejected
    ]
    out["etag_attempts"] = attempts
    # The meaningful signal: a non-matching etag is rejected (optimistic lock present).
    out["nonmatching_etag_rejected"] = any(a["rejected"] for a in attempts if a["label"] == "nonmatching_etag")
    out["ok"] = out["nonmatching_etag_rejected"]
    return out
