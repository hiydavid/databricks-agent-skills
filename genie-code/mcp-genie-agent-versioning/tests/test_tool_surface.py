"""The public MCP surface is exactly the three v2 tools."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from fastmcp import FastMCP

from server.tools import register_tools


def _registered_tools(server: FastMCP):
    # FastMCP 3.x exposes this runtime API, but its published type surface omits it.
    return asyncio.run(cast(Any, server).get_tools())


def test_exact_v2_tool_surface(settings):
    server = FastMCP(name="test")
    register_tools(server, settings)
    registered = _registered_tools(server)
    assert set(registered) == {
        "save_agent_config_version",
        "list_agent_versions",
        "get_agent_version",
    }


def test_save_schema_and_blocking_instruction(settings):
    server = FastMCP(name="test")
    register_tools(server, settings)
    save = _registered_tools(server)["save_agent_config_version"]
    assert save.parameters["required"] == ["space_id", "config", "reason"]
    assert "stop without editing" in save.description


def test_get_description_warns_about_historical_etag(settings):
    server = FastMCP(name="test")
    register_tools(server, settings)
    get = _registered_tools(server)["get_agent_version"]
    assert "historical provenance only" in get.description
    assert "fresh etag" in get.description
