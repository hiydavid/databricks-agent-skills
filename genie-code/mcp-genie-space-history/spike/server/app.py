"""FastAPI + FastMCP application for the spike MCP server.

Shape follows ``databricks/app-templates -> mcp-server-hello-world`` (the template the
design spec §10 says to start from):
  * ``mcp_server.http_app(stateless_http=True)`` -> MCP mounted at ``/mcp`` over
    streamable HTTP (Genie Code requirement, design spec §3).
  * a header-capture middleware stashes request headers in a ContextVar so tools can
    read ``X-Forwarded-Access-Token`` for OBO.
  * CORS is allow-listed to the workspace URL (Genie Code requirement, design spec §3).
"""

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP

from .tools import load_tools
from .utils import header_store

mcp_server = FastMCP(name="mcp-genie-space-history")

# Register the spike tools (mapped 1:1 to the P0 exit criteria).
load_tools(mcp_server)

# stateless_http=True: each request is self-contained (no mcp-session-id handshake),
# which is what the Databricks Assistant / Genie Code expects and what horizontally
# scaled Databricks Apps need.
mcp_app = mcp_server.http_app(stateless_http=True)

api = FastAPI(title="mcp-genie-space-history (spike)", version="0.0.1", lifespan=mcp_app.lifespan)


@api.get("/", include_in_schema=False)
async def root():
    return {"message": "Genie Space History MCP (spike) running", "mcp_endpoint": "/mcp"}


@api.get("/healthz", include_in_schema=False)
async def healthz():
    return {"status": "healthy"}


# Combine MCP protocol routes with the custom API routes.
combined_app = FastAPI(
    title="Genie Space History MCP (spike)",
    routes=[*mcp_app.routes, *api.routes],
    lifespan=mcp_app.lifespan,
)

# CORS: allow the workspace origin(s). Comma-separated env override; "*" by default for
# the spike (tighten to the workspace URL in production — design spec §3/§10).
_origins = os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",")
combined_app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@combined_app.middleware("http")
async def capture_headers(request: Request, call_next):
    """Stash request headers so OBO tools can read X-Forwarded-Access-Token."""
    header_store.set(dict(request.headers))
    return await call_next(request)
