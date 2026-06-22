"""UC Delta schema — the 7 per-artifact tables + the ``only_mine`` row filter (spec §7.1).

This module is the single source of truth for:
  * the DDL of every table (exactly per spec §7.1, with the F-4 TBLPROPERTIES);
  * which logical-PK column identifies each table (for ``get_artifact``);
  * how each table projects onto the normalized ``list_history`` columns
    (``{id, type, version, created_at, created_by, summary, decision}``).

JSON columns default to ``STRING``; ``VARIANT`` is opt-in behind
``Settings.use_variant`` (spec §7.1/§12 #3) — never hard-required.
"""

from __future__ import annotations

from dataclasses import dataclass

ROW_FILTER_FUNCTION = "only_mine"

# Required on every table because of the DEFAULT current_timestamp()/current_user()
# columns (P0 finding F-4) — alongside row tracking.
_TBLPROPERTIES = (
    "TBLPROPERTIES (\n"
    "  delta.enableRowTracking = true,\n"
    "  'delta.feature.allowColumnDefaults' = 'supported'\n"
    ")"
)


def _json_type(use_variant: bool) -> str:
    """JSON column type: ``STRING`` by default, ``VARIANT`` only when opted-in (§12 #3)."""
    return "VARIANT" if use_variant else "STRING"


# --- table names ------------------------------------------------------------
CONFIG_SNAPSHOTS = "config_snapshots"
OPTIMIZATION_RUNS = "optimization_runs"
EVAL_RESULTS = "eval_results"
DIAGNOSE_REPORTS = "diagnose_reports"
QUERY_REPORTS = "query_reports"
DESIGN_PROPOSALS = "design_proposals"
METRIC_VIEW_ARTIFACTS = "metric_view_artifacts"

REPORT_TABLES = (DIAGNOSE_REPORTS, QUERY_REPORTS, DESIGN_PROPOSALS, METRIC_VIEW_ARTIFACTS)


# ``save_report`` routes an ``artifact_type`` to its report table (spec §6).
# Unknown artifact_types are rejected by the tool layer.
ARTIFACT_TYPE_TO_REPORT_TABLE: dict[str, str] = {
    "diagnose_report": DIAGNOSE_REPORTS,
    "query_report": QUERY_REPORTS,
    "design_proposal": DESIGN_PROPOSALS,
    "metric_view_ddl": METRIC_VIEW_ARTIFACTS,
}


@dataclass(frozen=True)
class TableSpec:
    """How one artifact table participates in ``list_history`` / ``get_artifact``."""

    name: str
    id_column: str  # logical PK — what get_artifact resolves an id against
    type_label: str  # the value surfaced as list_history.type / get_artifact.type
    # SQL expressions projecting this table onto the normalized list_history columns.
    version_expr: str
    summary_expr: str
    decision_expr: str


# Resolution order for get_artifact (config first — the rollback-critical table).
TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        name=CONFIG_SNAPSHOTS,
        id_column="config_version_id",
        type_label="config_snapshot",
        version_expr="version",
        summary_expr="change_summary",
        decision_expr="CAST(NULL AS STRING)",
    ),
    TableSpec(
        name=OPTIMIZATION_RUNS,
        id_column="run_id",
        type_label="optimization_run",
        version_expr="CAST(NULL AS BIGINT)",
        summary_expr="change_summary",
        decision_expr="decision",
    ),
    TableSpec(
        name=EVAL_RESULTS,
        id_column="eval_run_id",
        type_label="eval_result",
        version_expr="CAST(NULL AS BIGINT)",
        summary_expr="primary_failure",
        decision_expr="assessment",
    ),
    TableSpec(
        name=DIAGNOSE_REPORTS,
        id_column="artifact_id",
        type_label="diagnose_report",
        version_expr="CAST(NULL AS BIGINT)",
        summary_expr="summary",
        decision_expr="CAST(NULL AS STRING)",
    ),
    TableSpec(
        name=QUERY_REPORTS,
        id_column="artifact_id",
        type_label="query_report",
        version_expr="CAST(NULL AS BIGINT)",
        summary_expr="summary",
        decision_expr="CAST(NULL AS STRING)",
    ),
    TableSpec(
        name=DESIGN_PROPOSALS,
        id_column="artifact_id",
        type_label="design_proposal",
        version_expr="CAST(NULL AS BIGINT)",
        summary_expr="summary",
        decision_expr="CAST(NULL AS STRING)",
    ),
    TableSpec(
        name=METRIC_VIEW_ARTIFACTS,
        id_column="artifact_id",
        type_label="metric_view_ddl",
        version_expr="CAST(NULL AS BIGINT)",
        summary_expr="summary",
        decision_expr="CAST(NULL AS STRING)",
    ),
)

# Lookup of type_label -> spec, for the optional list_history artifact_type filter.
TYPE_LABEL_TO_SPEC: dict[str, TableSpec] = {s.type_label: s for s in TABLE_SPECS}

# JSON columns per table (STRING by default, VARIANT opt-in).
JSON_COLUMNS: dict[str, tuple[str, ...]] = {
    CONFIG_SNAPSHOTS: ("config_json", "diff_patch"),
    **{t: ("scores_findings",) for t in REPORT_TABLES},
}


# ---------------------------------------------------------------------------
# DDL builders — each takes a pre-quoted ``fq`` schema prefix (``cat`.`schema``).
# ---------------------------------------------------------------------------
def config_snapshots_ddl(fq: str, *, use_variant: bool) -> str:
    j = _json_type(use_variant)
    return f"""
CREATE TABLE IF NOT EXISTS {fq}.{CONFIG_SNAPSHOTS} (
  config_version_id   STRING    NOT NULL,
  space_id            STRING    NOT NULL,
  version             BIGINT    NOT NULL,
  parent_version_id   STRING,
  created_at          TIMESTAMP DEFAULT current_timestamp(),
  created_by          STRING    DEFAULT current_user(),
  skill_name          STRING,
  config_json         {j},
  config_hash         STRING,
  diff_patch          {j},
  changed_surfaces    ARRAY<STRING>,
  etag                STRING,
  run_id              STRING,
  rollback_reference  STRING,
  change_summary      STRING
) USING DELTA {_TBLPROPERTIES}
""".strip()


def optimization_runs_ddl(fq: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {fq}.{OPTIMIZATION_RUNS} (
  run_id                   STRING NOT NULL,
  space_id                 STRING NOT NULL,
  created_at               TIMESTAMP DEFAULT current_timestamp(),
  created_by               STRING DEFAULT current_user(),
  baseline_score           DOUBLE,
  candidate_score          DOUBLE,
  score_delta              DOUBLE,
  fixed_count              INT,
  regressed_count          INT,
  unchanged_count          INT,
  excluded_count           INT,
  decision                 STRING,
  parent_config_version_id STRING,
  result_config_version_id STRING,
  change_summary           STRING
) USING DELTA {_TBLPROPERTIES}
""".strip()


def eval_results_ddl(fq: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {fq}.{EVAL_RESULTS} (
  eval_run_id             STRING NOT NULL,
  run_id                  STRING NOT NULL,
  space_id                STRING NOT NULL,
  created_at              TIMESTAMP DEFAULT current_timestamp(),
  created_by              STRING DEFAULT current_user(),
  question_id             STRING,
  assessment              STRING,
  primary_failure         STRING,
  baseline_sql_hash       STRING,
  candidate_sql_hash      STRING,
  baseline_result_digest  STRING,
  candidate_result_digest STRING,
  latency_ms              BIGINT
) USING DELTA {_TBLPROPERTIES}
""".strip()


def report_table_ddl(fq: str, table_name: str, *, use_variant: bool) -> str:
    j = _json_type(use_variant)
    return f"""
CREATE TABLE IF NOT EXISTS {fq}.{table_name} (
  artifact_id         STRING    NOT NULL,
  space_id            STRING    NOT NULL,
  created_at          TIMESTAMP DEFAULT current_timestamp(),
  created_by          STRING    DEFAULT current_user(),
  skill_name          STRING,
  title               STRING,
  content_md          STRING,
  summary             STRING,
  scores_findings     {j},
  run_id              STRING,
  config_version_id   STRING,
  redacted            BOOLEAN   DEFAULT true
) USING DELTA {_TBLPROPERTIES}
""".strip()


def only_mine_function_ddl(fq: str) -> str:
    """The per-user row-filter function (spec §7.1)."""
    return (
        f"CREATE FUNCTION IF NOT EXISTS {fq}.{ROW_FILTER_FUNCTION}(owner STRING)\n"
        f"  RETURN owner = SESSION_USER()"
    )


def all_table_ddls(fq: str, *, use_variant: bool) -> list[tuple[str, str]]:
    """``(table_name, ddl)`` for every one of the 7 tables, in creation order."""
    return [
        (CONFIG_SNAPSHOTS, config_snapshots_ddl(fq, use_variant=use_variant)),
        (OPTIMIZATION_RUNS, optimization_runs_ddl(fq)),
        (EVAL_RESULTS, eval_results_ddl(fq)),
        *[(t, report_table_ddl(fq, t, use_variant=use_variant)) for t in REPORT_TABLES],
    ]


ALL_TABLE_NAMES: tuple[str, ...] = (
    CONFIG_SNAPSHOTS,
    OPTIMIZATION_RUNS,
    EVAL_RESULTS,
    *REPORT_TABLES,
)
