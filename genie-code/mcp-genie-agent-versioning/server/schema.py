"""Unity Catalog schema for the v2 Genie Agent configuration version store."""

from __future__ import annotations

AGENT_CONFIG_VERSIONS = "agent_config_versions"
ROW_FILTER_FUNCTION = "only_mine"

_TBLPROPERTIES = (
    "TBLPROPERTIES (\n"
    "  delta.enableRowTracking = true,\n"
    "  'delta.feature.allowColumnDefaults' = 'supported'\n"
    ")"
)


def agent_config_versions_ddl(fq: str) -> str:
    """Create the sole user-data table.

    The two nullable reference columns resolve the design's lineage requirement:
    ``parent_version_id`` connects related snapshots, while
    ``rollback_target_version_id`` records the target of a ``before_rollback`` event.
    """
    return f"""
CREATE TABLE IF NOT EXISTS {fq}.{AGENT_CONFIG_VERSIONS} (
  version_id                 STRING    NOT NULL,
  space_id                   STRING    NOT NULL,
  reason                     STRING    NOT NULL,
  config_envelope            STRING    NOT NULL,
  config_hash                STRING    NOT NULL,
  change_summary             STRING,
  parent_version_id          STRING,
  rollback_target_version_id STRING,
  created_at                 TIMESTAMP NOT NULL DEFAULT current_timestamp(),
  created_by                 STRING    NOT NULL DEFAULT SESSION_USER()
) USING DELTA {_TBLPROPERTIES}
""".strip()


def only_mine_function_ddl(fq: str) -> str:
    return (
        f"CREATE FUNCTION IF NOT EXISTS {fq}.{ROW_FILTER_FUNCTION}(owner STRING)\n"
        "  RETURN owner = SESSION_USER()"
    )
