"""Structured errors surfaced by the MCP tools.

The tools never raise raw exceptions back over MCP — they translate them into
plain JSON-serializable dicts so the calling agent (Genie Code) gets an
actionable, machine-readable result. The two shapes that matter most:

  * ``scope_error`` — the forwarded OBO token is missing or lacks the ``sql``
    scope (spec §5). The server NEVER silently falls back to the app SP for a
    user write; it returns this so the user enables the scope.
  * ``validation_error`` — the inputs violated a §7 field contract (e.g. an
    unknown ``artifact_type``, or a missing required field).
"""

from __future__ import annotations

from typing import Any, Optional


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
    "401",
)


def looks_like_scope_error(exc: Exception) -> bool:
    """Heuristic: does this SQL/auth failure look like a missing OAuth scope?

    The definitive scope signal is the absent OBO token (handled in ``auth`` via
    :class:`OBOScopeError`). This only catches the token-level authorization
    failures a deployed app hits when its OBO token defaults to identity-only
    scopes (spec §5, P0 finding F-6).
    """
    msg = str(exc).lower()
    return any(marker in msg for marker in _SCOPE_MARKERS)


def exception_to_payload(
    exc: Exception, *, default_type: str = "error"
) -> Optional[dict[str, Any]]:
    """Map a known exception type to a structured payload, or ``None`` if unknown."""
    if isinstance(exc, OBOScopeError):
        return scope_error_payload(str(exc), required_scope=exc.required_scope)
    if isinstance(exc, ToolValidationError):
        return validation_error_payload(str(exc))
    return None
