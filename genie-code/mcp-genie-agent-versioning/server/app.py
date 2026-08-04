"""FastAPI/FastMCP application and persistence-aware readiness endpoints."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastmcp import FastMCP

from . import auth, provisioning
from .config import Settings
from .tools import register_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-genie-agent-versioning")

settings = Settings.from_env()

# Genie Code can be served from a workspace alias that differs from the canonical
# DATABRICKS_HOST injected into the App. Restrict automatic aliases to official
# Databricks workspace domains.
TRUSTED_DATABRICKS_ORIGIN_REGEX = (
    r"^https://(?:[a-zA-Z0-9-]+\.)*"
    r"(?:cloud\.databricks\.com|cloud\.databricks\.us|"
    r"azuredatabricks\.net|gcp\.databricks\.com)$"
)

readiness: dict[str, object] = {
    "ready": False,
    "message": "startup bootstrap has not completed",
    "bootstrap": None,
}

mcp_server = FastMCP(name="mcp-genie-agent-versioning")
register_tools(mcp_server, settings)

# stateless_http=True: each request is self-contained (no mcp-session-id handshake),
# which Genie Code / horizontally-scaled Apps require. path="/mcp" is the contract.
mcp_app = mcp_server.http_app(path="/mcp", stateless_http=True)


def _set_readiness(*, ready: bool, message: str, bootstrap: object = None) -> None:
    readiness.update({"ready": ready, "message": message, "bootstrap": bootstrap})


def _run_startup_bootstrap() -> dict:
    """Provision UC objects as the app SP and update persistence readiness."""
    missing = settings.missing_required()
    if missing:
        message = "bootstrap skipped: missing required env: " + ", ".join(missing)
        logger.error(message)
        report = {"ok": False, "errors": [message]}
        _set_readiness(ready=False, message=message, bootstrap=report)
        return report
    try:
        report = provisioning.bootstrap(auth.get_app_workspace_client(), settings)
        logger.info("bootstrap report: %s", report)
        if report.get("warnings"):
            logger.warning("bootstrap warnings: %s", report["warnings"])
        if not report.get("ok"):
            logger.error(
                "bootstrap NOT ok: errors=%s — persistence or row isolation incomplete; "
                "an operator must resolve this before the App becomes ready",
                report.get("errors"),
            )
            _set_readiness(
                ready=False,
                message="configuration snapshots cannot currently be persisted",
                bootstrap=report,
            )
        else:
            _set_readiness(
                ready=True,
                message="configuration version storage is ready",
                bootstrap=report,
            )
        return report
    except Exception as exc:  # noqa: BLE001 — startup must survive bootstrap failures
        logger.exception("bootstrap failed (continuing startup): %s", exc)
        report = {"ok": False, "errors": [str(exc)]}
        _set_readiness(ready=False, message="bootstrap failed", bootstrap=report)
        return report


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run provisioning only inside a deployed App (where the SP exists) unless an
    # operator explicitly opts in; preserve FastMCP's own session-manager lifespan.
    if auth.running_in_app():
        _run_startup_bootstrap()
    else:
        logger.info("not running in a Databricks App; skipping startup bootstrap")
        _set_readiness(
            ready=False,
            message="local process: Databricks App provisioning was not run",
        )
    async with mcp_app.lifespan(app):
        yield


api = FastAPI(title="mcp-genie-agent-versioning", version="2.0.0")


@api.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "message": "Genie Agent Versioning MCP running",
        "version": "2.0.0",
        "mcp_endpoint": "/mcp",
        "ready": readiness["ready"],
    }


@api.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return {"status": "healthy", "check": "liveness"}


@api.get("/readyz", include_in_schema=False)
async def readyz() -> JSONResponse:
    ready = bool(readiness["ready"])
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "message": readiness["message"],
            "config": settings.as_public_dict(),
            "bootstrap": readiness["bootstrap"],
        },
    )


# Combine the MCP protocol routes with the custom API routes under one app.
app = FastAPI(
    title="Genie Agent Versioning MCP",
    version="2.0.0",
    routes=[*mcp_app.routes, *api.routes],
    lifespan=lifespan,
)


@app.middleware("http")
async def capture_obo_token(request: Request, call_next):
    """Stash only the OBO token for this request; reset it afterward so it never leaks."""
    reset = auth.obo_token_var.set(request.headers.get(auth.OBO_HEADER))
    try:
        return await call_next(request)
    finally:
        auth.obo_token_var.reset(reset)


def _add_cors_middleware(target: FastAPI, configured_settings: Settings) -> None:
    """Allow Genie Code's browser client from the App's Databricks workspace."""
    allowed_origins = list(
        dict.fromkeys(
            origin
            for origin in (
                configured_settings.workspace_origin,
                *configured_settings.workspace_origin_aliases,
            )
            if origin
        )
    )
    target.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=TRUSTED_DATABRICKS_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )


_add_cors_middleware(app, settings)
