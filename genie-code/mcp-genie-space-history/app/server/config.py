"""Env-driven configuration (spec §10).

All deployment knobs come from environment variables set in ``app.yaml``:

  * ``HISTORY_CATALOG``     — a **pre-existing** UC catalog. The app NEVER creates it.
  * ``HISTORY_OWNER_GROUP`` — durable account group that OWNS the schema/tables
                              (survives app/SP deletion — spec §7.1).
  * ``HISTORY_GRANTEE``     — user group granted SELECT/MODIFY for OBO reads/writes.
  * ``SQL_WAREHOUSE_ID``    — warehouse all UC SQL runs on.
  * ``CORS_ALLOW_ORIGINS``  — comma-separated workspace origin allowlist (spec §3).
  * ``HISTORY_USE_VARIANT`` — opt-in VARIANT JSON columns (default STRING — spec §7.1/§12 #3).
  * ``OBO_ENABLED``         — OBO feature flag for graceful degradation (spec §5/§12 #2).

The schema name is fixed at ``genie_space_history`` (spec §7.1).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional

# Fixed by the design spec §7.1 — never configurable.
HISTORY_SCHEMA = "genie_space_history"


def _as_bool(value: Optional[str], *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    """Resolved, immutable server configuration."""

    history_catalog: str
    history_owner_group: str
    history_grantee: str
    sql_warehouse_id: str
    history_schema: str = HISTORY_SCHEMA
    cors_allow_origins: tuple[str, ...] = field(default_factory=tuple)
    use_variant: bool = False
    obo_enabled: bool = True

    @property
    def fq_schema(self) -> str:
        """``catalog.schema`` for logging/display (NOT pre-quoted)."""
        return f"{self.history_catalog}.{self.history_schema}"

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        """Build settings from the process environment (or an injected mapping for tests)."""
        env = env if env is not None else os.environ
        origins = tuple(
            o.strip() for o in env.get("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()
        )
        return cls(
            history_catalog=env.get("HISTORY_CATALOG", "").strip(),
            history_owner_group=env.get("HISTORY_OWNER_GROUP", "").strip(),
            history_grantee=env.get("HISTORY_GRANTEE", "").strip(),
            sql_warehouse_id=env.get("SQL_WAREHOUSE_ID", "").strip(),
            cors_allow_origins=origins,
            use_variant=_as_bool(env.get("HISTORY_USE_VARIANT"), default=False),
            obo_enabled=_as_bool(env.get("OBO_ENABLED"), default=True),
        )

    def missing_required(self) -> list[str]:
        """Names of required env vars that are unset (for a fail-fast startup check)."""
        required = {
            "HISTORY_CATALOG": self.history_catalog,
            "HISTORY_OWNER_GROUP": self.history_owner_group,
            "HISTORY_GRANTEE": self.history_grantee,
            "SQL_WAREHOUSE_ID": self.sql_warehouse_id,
        }
        return [name for name, value in required.items() if not value]

    def as_public_dict(self) -> dict[str, object]:
        """Non-secret config echo for ``/healthz`` / structured logs."""
        return {
            "history_catalog": self.history_catalog,
            "history_schema": self.history_schema,
            "history_owner_group": self.history_owner_group,
            "history_grantee": self.history_grantee,
            "sql_warehouse_id": self.sql_warehouse_id,
            "cors_allow_origins": list(self.cors_allow_origins),
            "use_variant": self.use_variant,
            "obo_enabled": self.obo_enabled,
        }
