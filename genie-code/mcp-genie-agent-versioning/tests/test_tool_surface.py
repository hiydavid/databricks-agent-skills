"""The public MCP surface is exactly the three v2 tools."""

from __future__ import annotations

import asyncio
import inspect
import threading
from typing import Any, cast

from fastmcp import FastMCP

from server import tools as tools_module
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
    assert "include_serialized_space=true" in save.description
    config_property = save.parameters["properties"]["config"]
    assert "exact serialized configuration" in config_property["description"]
    config_schema = save.parameters["$defs"]["AgentConfigInput"]
    assert config_schema["required"] == [
        "serialized_space",
        "title",
        "description",
        "warehouse_id",
        "parent_path",
    ]
    assert "Exact string returned" in config_schema["properties"]["serialized_space"]["description"]


def test_get_description_warns_about_historical_etag(settings):
    server = FastMCP(name="test")
    register_tools(server, settings)
    get = _registered_tools(server)["get_agent_version"]
    assert "historical provenance only" in get.description
    assert "fresh etag" in get.description


def test_registered_tools_offload_blocking_work_and_can_overlap(monkeypatch, settings):
    server = FastMCP(name="test")
    register_tools(server, settings)
    get = _registered_tools(server)["get_agent_version"]
    assert inspect.iscoroutinefunction(get.fn)

    main_thread = threading.get_ident()
    worker_threads: list[int] = []
    barrier = threading.Barrier(2, timeout=2)

    def blocking_run_tool(_settings, _tool_name, _core):
        worker_threads.append(threading.get_ident())
        barrier.wait()
        return {"ok": True}

    monkeypatch.setattr(tools_module, "_run_tool", blocking_run_tool)

    async def invoke_twice():
        return await asyncio.gather(
            get.fn(space_id="space-1", version_id="one"),
            get.fn(space_id="space-1", version_id="two"),
        )

    assert asyncio.run(invoke_twice()) == [{"ok": True}, {"ok": True}]
    assert len(set(worker_threads)) == 2
    assert main_thread not in worker_threads
