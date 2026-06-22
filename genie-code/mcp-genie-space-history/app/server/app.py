"""FastAPI + FastMCP application (spec §3 / §10).

* ``mcp_server.http_app(path="/mcp", stateless_http=True)`` → the MCP server
  mounted at ``/mcp`` over stateless streamable HTTP (Genie Code requirement).
* A middleware captures ``X-Forwarded-Access-Token`` into a ContextVar for OBO;
  it is reset after each request so it never leaks across requests.
* CORS is allow-listed to the workspace origin(s) from ``CORS_ALLOW_ORIGINS``.
* On startup the app SP runs the idempotent bootstrap (schema/tables/filter/
  ownership/grants); failures are logged but never crash startup (spec §7.1).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP

from . import auth, provisioning
from .config import Settings
from .tools import register_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-genie-space-history")

settings = Settings.from_env()

mcp_server = FastMCP(name="mcp-genie-space-history")
register_tools(mcp_server, settings)

# stateless_http=True: each request is self-contained (no mcp-session-id handshake),
# which Genie Code / horizontally-scaled Apps require. path="/mcp" is the contract.
mcp_app = mcp_server.http_app(path="/mcp", stateless_http=True)


def _run_startup_bootstrap() -> None:
    """Provision UC objects as the app SP (best-effort; never raises)."""
    missing = settings.missing_required()
    if missing:
        logger.warning("bootstrap skipped: missing required env: %s", ", ".join(missing))
        return
    try:
        report = provisioning.bootstrap(auth.get_app_workspace_client(), settings)
        logger.info("bootstrap report: %s", report)
        if report.get("warnings"):
            logger.warning("bootstrap warnings: %s", report["warnings"])
        if not report.get("ok"):
            # Row isolation / table creation incomplete — grantee access may be withheld.
            logger.error(
                "bootstrap NOT ok: errors=%s grants_withheld=%s — row isolation incomplete; "
                "an operator must resolve before relying on per-user history",
                report.get("errors"),
                report.get("grants_withheld"),
            )
    except Exception as exc:  # noqa: BLE001 — startup must survive bootstrap failures
        logger.exception("bootstrap failed (continuing startup): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run provisioning only inside a deployed App (where the SP exists) unless an
    # operator explicitly opts in; preserve FastMCP's own session-manager lifespan.
    if auth.running_in_app():
        _run_startup_bootstrap()
    else:
        logger.info("not running in a Databricks App; skipping startup bootstrap")
    async with mcp_app.lifespan(app):
        yield


api = FastAPI(title="mcp-genie-space-history", version="0.1.0")


@api.get("/", include_in_schema=False)
async def root() -> dict:
    return {"message": "Genie Space History MCP running", "mcp_endpoint": "/mcp"}


@api.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return {"status": "healthy", "config": settings.as_public_dict()}


# Combine the MCP protocol routes with the custom API routes under one app.
app = FastAPI(
    title="Genie Space History MCP",
    version="0.1.0",
    routes=[*mcp_app.routes, *api.routes],
    lifespan=lifespan,
)

# CORS: allow only the configured workspace origin(s) (spec §3/§10). When unset,
# no cross-origin browser access is permitted (fail-closed).
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allow_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def capture_obo_token(request: Request, call_next):
    """Stash only the OBO token for this request; reset it afterward so it never leaks."""
    reset = auth.obo_token_var.set(request.headers.get(auth.OBO_HEADER))
    try:
        return await call_next(request)
    finally:
        auth.obo_token_var.reset(reset)
