"""Shared spike configuration (env-driven, with throwaway-spike defaults).

The defaults below are the *non-secret* identifiers the human provided for the P0
de-risking spike (a throwaway Genie Space, a pre-existing catalog, a SQL warehouse).
Every value is overridable via an environment variable so the same code runs both
locally (probes) and inside the Databricks App (MCP tools).

NOTE: this is throwaway spike code — it prioritizes proving mechanics over
production hardening (see the design spec §13 P0).
"""

import os

# ---------------------------------------------------------------------------
# Local-run only: the Databricks CLI profile the probes authenticate with.
# Create it once with:
#   databricks auth login --host https://fevm-dhuang.cloud.databricks.com \
#       --profile fevm-dhuang
# Ignored inside the deployed App (which uses the injected SP / OBO token).
# ---------------------------------------------------------------------------
SPIKE_PROFILE = os.environ.get("SPIKE_PROFILE", "fevm-dhuang")

# Pre-existing UC catalog. The app/spike NEVER creates this (design §7.1/§12 #6).
# The app SP is granted USE CATALOG + CREATE SCHEMA on it out-of-band.
HISTORY_CATALOG = os.environ.get("HISTORY_CATALOG", "dhuang_catalog")

# Schema name is fixed by the design spec (§7.1).
HISTORY_SCHEMA = os.environ.get("HISTORY_SCHEMA", "genie_space_history")

# SQL warehouse used for all UC DDL/DML probes.
SQL_WAREHOUSE_ID = os.environ.get("SQL_WAREHOUSE_ID", "78e36e2b033b2d06")

# Throwaway Genie Space used for the get/update round-trip + etag probes.
GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID", "01f16b396b3419ba8462d5efe167d947")


def fq_schema() -> str:
    return f"{HISTORY_CATALOG}.{HISTORY_SCHEMA}"


def as_dict() -> dict:
    """Echo the resolved config (no secrets) for logging / findings."""
    return {
        "history_catalog": HISTORY_CATALOG,
        "history_schema": HISTORY_SCHEMA,
        "sql_warehouse_id": SQL_WAREHOUSE_ID,
        "genie_space_id": GENIE_SPACE_ID,
        "spike_profile": SPIKE_PROFILE,
    }
