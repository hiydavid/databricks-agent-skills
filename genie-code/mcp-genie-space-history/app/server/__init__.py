"""Genie Space History MCP server (P1 — write + read).

Productionizes the P0 spike (../spike/) into a real package: a FastAPI + FastMCP
server, mounted at ``/mcp`` over stateless streamable HTTP, that persists the
artifacts the ``genie-code/`` skills emit to governed Unity Catalog Delta tables.

Module map:
  * ``config``       — env-driven :class:`Settings` (spec §10).
  * ``errors``       — structured tool errors (scope_error / validation).
  * ``sql``          — ``exec_sql`` + identifier quoting + the param/result adapter (spec §11).
  * ``schema``       — DDL for the 7 UC tables + the ``only_mine`` row-filter function (spec §7.1).
  * ``auth``         — OBO (per-request user) vs app-SP WorkspaceClient builders (spec §5).
  * ``provisioning`` — idempotent bootstrap: schema/tables/filter/ownership/grants (§7.1/§10).
  * ``store``        — :class:`UCTableStore`, the UC storage adapter (spec §6/§7).
  * ``tools``        — the four P1 MCP tools (spec §6).
  * ``app``/``main`` — the FastAPI/FastMCP wiring + uvicorn entrypoint (spec §3/§10).
"""

__version__ = "0.1.0"
