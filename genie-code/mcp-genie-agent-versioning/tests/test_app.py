"""Liveness is separate from persistence-aware readiness."""

from __future__ import annotations

import asyncio
import dataclasses
import json

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

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


@pytest.mark.parametrize(
    "origin",
    [
        "https://fevm-dhuang.cloud.databricks.com",
        "https://adb-1234567890123456.7.azuredatabricks.net",
        "https://1234567890123456.7.gcp.databricks.com",
    ],
)
def test_mcp_cors_preflight_allows_official_workspace_alias(settings: Settings, origin: str):
    cors_app = FastAPI()
    app_module._add_cors_middleware(cors_app, settings)

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


def test_mcp_cors_preflight_allows_explicit_nonstandard_alias(settings: Settings):
    origin = "https://genie-code.internal.example.com"
    settings = dataclasses.replace(settings, workspace_origin_aliases=(origin,))
    cors_app = FastAPI()
    app_module._add_cors_middleware(cors_app, settings)

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


def test_mcp_cors_preflight_rejects_untrusted_origin(settings: Settings):
    cors_app = FastAPI()
    app_module._add_cors_middleware(cors_app, settings)

    response = TestClient(cors_app).options(
        "/mcp",
        headers={
            "Origin": "https://cloud.databricks.com.attacker.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_shipped_app_has_cors_outside_obo_token_capture():
    middleware = app_module.app.user_middleware
    cors_index = next(i for i, item in enumerate(middleware) if item.cls is CORSMiddleware)
    obo_index = next(i for i, item in enumerate(middleware) if item.cls is BaseHTTPMiddleware)

    assert cors_index < obo_index
    assert middleware[cors_index].kwargs["allow_origins"] == [
        *filter(
            None,
            (
                app_module.settings.workspace_origin,
                *app_module.settings.workspace_origin_aliases,
            ),
        )
    ]
    assert (
        middleware[cors_index].kwargs["allow_origin_regex"]
        == app_module.TRUSTED_DATABRICKS_ORIGIN_REGEX
    )

    response = TestClient(app_module.app).options(
        "/mcp",
        headers={
            "Origin": "https://cloud.databricks.com.attacker.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
