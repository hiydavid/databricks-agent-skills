"""Identity & auth — OBO (per-request user) vs the app service principal (spec §5).

  * **OBO** — every Genie read and artifact read/write runs as the *calling user*. We build a
    fresh ``WorkspaceClient`` from the ``X-Forwarded-Access-Token`` header on each
    request and NEVER cache it. UC row filters then isolate per user.
  * **App SP** — used ONLY for bootstrap/admin (schema + table provisioning).
    Never the write actor for user artifacts; we never silently fall back to it
    for a user write (spec §5).

The middleware in ``app.py`` stashes the OBO token in a ``ContextVar``; tools read
it here. On a missing token, :func:`get_user_workspace_client` raises
:class:`OBOScopeError` so the tool can return a structured ``scope_error``.
"""

from __future__ import annotations

import contextvars
import os

from databricks.sdk import WorkspaceClient

from .errors import OBOScopeError

OBO_HEADER = "x-forwarded-access-token"

# Populated per-request by the middleware in app.py (only the OBO token, nothing else).
obo_token_var: contextvars.ContextVar = contextvars.ContextVar("obo_token", default=None)


def running_in_app() -> bool:
    """True when executing inside a deployed Databricks App (SP + OBO are available)."""
    return "DATABRICKS_APP_NAME" in os.environ


def get_app_workspace_client() -> WorkspaceClient:
    """App service-principal client (auto-injected ``DATABRICKS_CLIENT_ID``/``SECRET``).

    Bootstrap/admin only — schema + table provisioning, ownership, grants (spec §5).
    Locally this falls back to the developer's default credentials.
    """
    return WorkspaceClient()


def get_user_workspace_client() -> WorkspaceClient:
    """On-Behalf-Of-User client built from the forwarded user token (spec §5).

    Raises :class:`OBOScopeError` when the token is absent. The tool turns that into
    a ``scope_error`` for the user; it does NOT fall back to the app SP for a
    user-scoped write.

    Outside a deployed App (local dev / tests), returns the developer identity so
    the same code path is exercisable without the forwarded header.
    """
    if not running_in_app():
        return WorkspaceClient()

    token = obo_token_var.get()
    if not token:
        raise OBOScopeError(
            f"OBO token missing: no '{OBO_HEADER}' header on the request. Confirm OBO is "
            "enabled in the Previews portal and the app declares the required `sql` and "
            "`genie` user scopes.",
        )
    return WorkspaceClient(token=token, auth_type="pat")
