"""MCP tools exposed by the spike server.

Each tool is a thin wrapper over ``spike_core`` (the shared logic also driven by the
local probes) plus the right identity:
  * ``whoami`` / ``genie_*`` run OBO (the calling user) — design spec §5.
  * ``provision_history_schema`` runs as the app SP (bootstrap) — design spec §5/§10.

These map 1:1 to the P0 exit criteria so the deployed app can be exercised from Genie
Code. (The real product's lean 6-tool surface is in design spec §6; this is spike scope.)
"""

import config
import spike_core

from . import utils


def load_tools(mcp_server):
    @mcp_server.tool
    def health() -> dict:
        """Liveness check. Returns the resolved (non-secret) spike config."""
        return {"status": "healthy", "config": config.as_dict()}

    @mcp_server.tool
    def whoami() -> dict:
        """Criterion #2 (OBO identity): return ``current_user.me()`` for the *calling*
        user via the forwarded user token. Confirms OBO is enabled + scoped."""
        try:
            return spike_core.whoami(utils.get_user_workspace_client())
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    @mcp_server.tool
    def provision_history_schema() -> dict:
        """Criterion #3 (auto-provision): as the app SP, create the
        ``genie_space_history`` schema + ``config_snapshots`` table with IF NOT EXISTS.
        Never creates the catalog."""
        try:
            return spike_core.provision(
                utils.get_app_workspace_client(),
                catalog=config.HISTORY_CATALOG,
                schema=config.HISTORY_SCHEMA,
                warehouse_id=config.SQL_WAREHOUSE_ID,
            )
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    @mcp_server.tool
    def variant_probe() -> dict:
        """Criterion #4 (VARIANT probe): CREATE TABLE(... VARIANT) + INSERT parse_json
        on the target warehouse. Reports whether VARIANT is usable or to default STRING."""
        try:
            return spike_core.variant_probe(
                utils.get_app_workspace_client(),
                catalog=config.HISTORY_CATALOG,
                schema=config.HISTORY_SCHEMA,
                warehouse_id=config.SQL_WAREHOUSE_ID,
            )
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    @mcp_server.tool
    def genie_roundtrip(dry_run: bool = True) -> dict:
        """Criterion #5 (Genie round-trip): get_space(include_serialized_space=True) then
        re-apply the IDENTICAL snapshot (no-op restore) under the calling user (OBO).
        ``dry_run=True`` reads only."""
        try:
            return spike_core.genie_roundtrip(
                utils.get_user_workspace_client(),
                space_id=config.GENIE_SPACE_ID,
                apply=not dry_run,
            )
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    @mcp_server.tool
    def genie_etag_check() -> dict:
        """Criterion #6 (etag concurrency): prove a stale-etag update is rejected."""
        try:
            return spike_core.etag_check(
                utils.get_user_workspace_client(),
                space_id=config.GENIE_SPACE_ID,
            )
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
