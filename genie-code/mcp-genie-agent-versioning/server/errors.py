"""Structured errors surfaced by the MCP tools.

The tools never raise raw exceptions back over MCP — they translate them into
plain JSON-serializable dicts so the calling agent (Genie Code) gets an
actionable, machine-readable result. The two shapes that matter most:

  * ``scope_error`` — the forwarded OBO token is missing or lacks a required
    ``sql`` or ``genie`` scope (spec §5). The server NEVER silently
    falls back to the app SP for a user operation; it returns this so the user
    enables the scope.
  * ``validation_error`` — the inputs violated a §7 field contract (e.g. an
    unknown ``artifact_type``, or a missing required field).
"""

from __future__ import annotations

import re
from typing import Any


class ToolValidationError(ValueError):
    """An input failed validation against the §7 field contracts."""


class OBOScopeError(RuntimeError):
    """The OBO token is absent / OBO is disabled / a required scope is missing.

    Carries the scope the user must enable so the tool can render an actionable
    ``scope_error`` payload (spec §5).
    """

    def __init__(self, message: str, *, required_scope: str = "sql"):
        super().__init__(message)
        self.required_scope = required_scope


def scope_error_payload(message: str, *, required_scope: str = "sql") -> dict[str, Any]:
    """Build the structured ``scope_error`` result returned by a tool (spec §5)."""
    return {
        "ok": False,
        "error_type": "scope_error",
        "required_scope": required_scope,
        "message": message,
        "remediation": (
            f"Enable On-Behalf-Of-User auth in the Previews portal and ensure the app's "
            f"`user_api_scopes` includes `{required_scope}`, then reconnect the MCP server."
        ),
    }


def validation_error_payload(message: str) -> dict[str, Any]:
    """Build the structured ``validation_error`` result returned by a tool."""
    return {"ok": False, "error_type": "validation_error", "message": message}


def error_payload(error_type: str, message: str) -> dict[str, Any]:
    """Build a generic structured error result."""
    return {"ok": False, "error_type": error_type, "message": message}


# Lower-cased substrings that mark an OAuth-scope / token-authorization failure
# (as opposed to an ordinary UC grant denial). Kept conservative so a plain
# "user does not have SELECT on table" grant issue is NOT mislabeled a scope error.
_SCOPE_MARKERS = (
    "insufficient_scope",
    "insufficient scope",
    "invalid_token",
    "invalid access token",
    "missing scope",
    "unauthorized",
    "unauthenticated",
)

_HTTP_401_RE = re.compile(r"(?:\bhttp(?: status)?|\bstatus(?: code)?\s*[:=]?)\s*401\b", re.I)

# SDK exception class names that are unambiguously token/identity-auth failures
# (401-class). ``PermissionDenied`` (403, a UC grant issue) is deliberately EXCLUDED
# so it is never relabeled a scope error.
_SCOPE_EXCEPTION_NAMES = ("Unauthenticated",)


def looks_like_scope_error(exc: Exception) -> bool:
    """Heuristic: does this SQL/auth failure look like a missing OAuth scope?

    The definitive scope signal is the absent OBO token (handled in ``auth`` via
    :class:`OBOScopeError`). This also catches the token-level authorization
    failures raised by SQL when a deployed app receives a token without the required
    scope. ``PermissionDenied`` (403, a UC grant denial) is intentionally NOT treated
    as a scope error.
    """
    if type(exc).__name__ in _SCOPE_EXCEPTION_NAMES:
        return True
    msg = str(exc).lower()
    return any(marker in msg for marker in _SCOPE_MARKERS) or bool(_HTTP_401_RE.search(msg))
