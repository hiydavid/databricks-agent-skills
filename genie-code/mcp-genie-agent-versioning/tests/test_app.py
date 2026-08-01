"""Liveness is separate from persistence-aware readiness."""

from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import app as app_module
from server.config import Settings


def test_successful_bootstrap_marks_ready(monkeypatch, settings):
    monkeypatch.setattr(app_module, "settings", settings)
    monkeypatch.setattr(app_module.auth, "get_app_workspace_client", lambda: object())
    monkeypatch.setattr(
        app_module.provisioning,
        "bootstrap",
        lambda _workspace, _settings: {"ok": True, "errors": [], "warnings": []},
    )
    app_module._run_startup_bootstrap()
    response = asyncio.run(app_module.readyz())
    payload = json.loads(bytes(response.body))
    assert response.status_code == 200
    assert payload["status"] == "ready"


def test_failed_bootstrap_marks_not_ready(monkeypatch, settings):
    monkeypatch.setattr(app_module, "settings", settings)
    monkeypatch.setattr(app_module.auth, "get_app_workspace_client", lambda: object())
    monkeypatch.setattr(
        app_module.provisioning,
        "bootstrap",
        lambda _workspace, _settings: {
            "ok": False,
            "errors": ["grant failed"],
            "warnings": [],
        },
    )
    app_module._run_startup_bootstrap()
    response = asyncio.run(app_module.readyz())
    payload = json.loads(bytes(response.body))
    assert response.status_code == 503
    assert payload["status"] == "not_ready"


def test_healthz_is_liveness_only():
    result = asyncio.run(app_module.healthz())
    assert result == {"status": "healthy", "check": "liveness"}


def test_mcp_cors_preflight_allows_configured_workspace_origin(settings: Settings):
    cors_app = FastAPI()
    app_module._add_cors_middleware(cors_app, settings)
    origin = settings.workspace_origin

    response = TestClient(cors_app).options(
        "/mcp",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,mcp-protocol-version",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_mcp_cors_preflight_rejects_unconfigured_origin(settings: Settings):
    cors_app = FastAPI()
    app_module._add_cors_middleware(cors_app, settings)

    response = TestClient(cors_app).options(
        "/mcp",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
