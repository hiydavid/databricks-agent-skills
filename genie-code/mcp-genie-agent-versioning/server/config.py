"""Environment-driven settings for the v2 configuration version store."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional
from urllib.parse import urlsplit

DEFAULT_HISTORY_SCHEMA = "genie_agent_versioning"
DEFAULT_MAX_CONFIG_BYTES = 5 * 1024 * 1024


def _as_bool(value: Optional[str], *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _as_positive_int(value: Optional[str], *, default: int) -> int:
    if value is None or not value.strip():
        return default
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("MAX_CONFIG_BYTES must be a positive integer")
    return parsed


def _as_workspace_origin(value: Optional[str]) -> str:
    origin = (value or "").strip().rstrip("/")
    if origin and "://" not in origin:
        origin = f"https://{origin}"
    return origin


def _as_origin_aliases(value: Optional[str]) -> tuple[str, ...]:
    aliases: list[str] = []
    for raw_alias in (value or "").split(","):
        alias = raw_alias.strip().rstrip("/")
        if not alias:
            continue
        parsed = urlsplit(alias)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("DATABRICKS_ORIGIN_ALIASES must contain comma-separated HTTPS origins")
        if alias not in aliases:
            aliases.append(alias)
    return tuple(aliases)


@dataclass(frozen=True)
class Settings:
    """Resolved, immutable server configuration.

    ``HISTORY_SCHEMA`` is deliberately configurable. Fresh deployments default to
    ``genie_agent_versioning``; an existing v1 deployment can explicitly keep using
    ``genie_space_history`` while the v2 table is added alongside its legacy tables.
    """

    history_catalog: str
    history_grantee: str
    sql_warehouse_id: str
    history_schema: str = DEFAULT_HISTORY_SCHEMA
    history_owner_group: str = ""
    transfer_ownership: bool = False
    grantee_use_catalog_confirmed: bool = False
    max_config_bytes: int = DEFAULT_MAX_CONFIG_BYTES
    workspace_origin: str = ""
    workspace_origin_aliases: tuple[str, ...] = ()

    @property
    def fq_schema(self) -> str:
        return f"{self.history_catalog}.{self.history_schema}"

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        env = env if env is not None else os.environ
        return cls(
            history_catalog=env.get("HISTORY_CATALOG", "").strip(),
            history_schema=(
                env.get("HISTORY_SCHEMA", DEFAULT_HISTORY_SCHEMA).strip() or DEFAULT_HISTORY_SCHEMA
            ),
            history_owner_group=env.get("HISTORY_OWNER_GROUP", "").strip(),
            history_grantee=env.get("HISTORY_GRANTEE", "").strip(),
            sql_warehouse_id=env.get("SQL_WAREHOUSE_ID", "").strip(),
            transfer_ownership=_as_bool(env.get("TRANSFER_OWNERSHIP"), default=False),
            grantee_use_catalog_confirmed=_as_bool(
                env.get("HISTORY_GRANTEE_USE_CATALOG_CONFIRMED"), default=False
            ),
            max_config_bytes=_as_positive_int(
                env.get("MAX_CONFIG_BYTES"), default=DEFAULT_MAX_CONFIG_BYTES
            ),
            workspace_origin=_as_workspace_origin(env.get("DATABRICKS_HOST")),
            workspace_origin_aliases=_as_origin_aliases(env.get("DATABRICKS_ORIGIN_ALIASES")),
        )

    def missing_required(self) -> list[str]:
        required = {
            "HISTORY_CATALOG": self.history_catalog,
            "HISTORY_SCHEMA": self.history_schema,
            "HISTORY_GRANTEE": self.history_grantee,
            "SQL_WAREHOUSE_ID": self.sql_warehouse_id,
            "DATABRICKS_HOST": self.workspace_origin,
        }
        missing = [name for name, value in required.items() if not value]
        if self.transfer_ownership and not self.history_owner_group:
            missing.append("HISTORY_OWNER_GROUP (required when TRANSFER_OWNERSHIP=true)")
        if not self.grantee_use_catalog_confirmed:
            missing.append("HISTORY_GRANTEE_USE_CATALOG_CONFIRMED=true")
        return missing

    def as_public_dict(self) -> dict[str, object]:
        return {
            "history_catalog": self.history_catalog,
            "history_schema": self.history_schema,
            "history_owner_group": self.history_owner_group,
            "history_grantee": self.history_grantee,
            "sql_warehouse_id": self.sql_warehouse_id,
            "transfer_ownership": self.transfer_ownership,
            "grantee_use_catalog_confirmed": self.grantee_use_catalog_confirmed,
            "max_config_bytes": self.max_config_bytes,
            "workspace_origin": self.workspace_origin,
            "workspace_origin_aliases": self.workspace_origin_aliases,
        }
