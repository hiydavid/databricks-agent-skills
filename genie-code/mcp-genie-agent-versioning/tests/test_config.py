"""Deployment configuration and explicit schema cutover behavior."""

from __future__ import annotations

import pytest

from server.config import DEFAULT_HISTORY_SCHEMA, Settings


def test_fresh_deployment_defaults_to_v2_schema():
    settings = Settings.from_env(
        {
            "HISTORY_CATALOG": "catalog",
            "HISTORY_GRANTEE": "group",
            "HISTORY_GRANTEE_USE_CATALOG_CONFIRMED": "true",
            "SQL_WAREHOUSE_ID": "warehouse",
            "DATABRICKS_HOST": "example.cloud.databricks.com/",
        }
    )
    assert settings.history_schema == DEFAULT_HISTORY_SCHEMA == "genie_agent_versioning"
    assert settings.workspace_origin == "https://example.cloud.databricks.com"


def test_existing_deployment_can_explicitly_reuse_v1_schema():
    settings = Settings.from_env(
        {
            "HISTORY_CATALOG": "catalog",
            "HISTORY_SCHEMA": "genie_space_history",
            "HISTORY_GRANTEE": "group",
            "HISTORY_GRANTEE_USE_CATALOG_CONFIRMED": "true",
            "SQL_WAREHOUSE_ID": "warehouse",
        }
    )
    assert settings.history_schema == "genie_space_history"


def test_ownership_group_required_only_when_transfer_enabled():
    base = {
        "HISTORY_CATALOG": "catalog",
        "HISTORY_GRANTEE": "group",
        "HISTORY_GRANTEE_USE_CATALOG_CONFIRMED": "true",
        "SQL_WAREHOUSE_ID": "warehouse",
        "DATABRICKS_HOST": "https://example.cloud.databricks.com",
    }
    assert Settings.from_env(base).missing_required() == []
    enabled = Settings.from_env({**base, "TRANSFER_OWNERSHIP": "true"})
    assert any("HISTORY_OWNER_GROUP" in item for item in enabled.missing_required())


def test_max_payload_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        Settings.from_env({"MAX_CONFIG_BYTES": "0"})


def test_workspace_origin_aliases_are_exact_https_origins():
    settings = Settings.from_env(
        {
            "DATABRICKS_ORIGIN_ALIASES": (
                "https://alias.cloud.databricks.com/, https://adb-123.4.azuredatabricks.net"
            )
        }
    )
    assert settings.workspace_origin_aliases == (
        "https://alias.cloud.databricks.com",
        "https://adb-123.4.azuredatabricks.net",
    )


@pytest.mark.parametrize(
    "alias",
    ["http://alias.cloud.databricks.com", "https://alias.cloud.databricks.com/path"],
)
def test_workspace_origin_aliases_reject_non_https_origins(alias):
    with pytest.raises(ValueError, match="HTTPS origins"):
        Settings.from_env({"DATABRICKS_ORIGIN_ALIASES": alias})
