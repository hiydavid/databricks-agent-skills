"""Auth helpers — OBO (per-request user token) vs the app service principal.

Mirrors the ``databricks/app-templates -> mcp-server-hello-world`` pattern: an HTTP
middleware stashes the request headers in a ContextVar, and tools build a per-request
WorkspaceClient from ``X-Forwarded-Access-Token`` (OBO). The app SP client is used only
for bootstrap/admin (schema + table creation), per design spec §5.
"""

import contextvars
import os

from databricks.sdk import WorkspaceClient

# Populated per-request by the header-capture middleware in app.py.
header_store: contextvars.ContextVar = contextvars.ContextVar("header_store")

OBO_HEADER = "x-forwarded-access-token"


def _running_in_app() -> bool:
    return "DATABRICKS_APP_NAME" in os.environ


def get_app_workspace_client() -> WorkspaceClient:
    """App service-principal client (auto-injected DATABRICKS_CLIENT_ID/SECRET).

    Used for bootstrap/admin only: creating the schema + tables. Locally this falls
    back to the developer's default credentials.
    """
    return WorkspaceClient()


def get_user_workspace_client() -> WorkspaceClient:
    """On-Behalf-Of-user client built from the forwarded user token.

    Raises a clear error if the OBO header is absent inside the App — that means OBO
    isn't enabled or the required scopes (``sql`` + Genie/dashboards) aren't granted
    (design spec §5 failure mode). Locally, returns the developer identity.
    """
    if not _running_in_app():
        return WorkspaceClient()

    headers = header_store.get({})
    token = headers.get(OBO_HEADER)
    if not token:
        raise ValueError(
            f"OBO token missing: no '{OBO_HEADER}' header. Confirm OBO is enabled in "
            "the Previews portal and the app's OAuth scopes include 'sql' + the "
            "Genie/dashboards scope."
        )
    return WorkspaceClient(token=token, auth_type="pat")
