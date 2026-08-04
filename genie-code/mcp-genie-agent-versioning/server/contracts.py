"""Validation, canonical hashing, and cursor helpers for the v2 MCP contract."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .errors import ToolValidationError

FORMAT_VERSION = 1
ALLOWED_REASONS = frozenset({"before_update", "before_rollback", "manual"})
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 100
MAX_CHANGE_SUMMARY_CHARS = 200

# These fields are present in the serialized representation returned by the Genie Get
# Space API. Checking only for an arbitrary JSON object lets callers accidentally persist
# progress notes or benchmark summaries that cannot be used to restore a space.
REQUIRED_SERIALIZED_SPACE_FIELDS = ("version", "data_sources")
SERIALIZED_SPACE_BODY_FIELDS = ("instructions", "config")

# Presence is required even when the native value is null. This prevents a caller from
# accidentally saving a partial API projection and later treating it as rollback-ready.
REQUIRED_CONFIG_FIELDS = (
    "serialized_space",
    "title",
    "description",
    "warehouse_id",
    "parent_path",
)

# These belong to the stored event/envelope and must never be smuggled in as arbitrary
# restorable config fields. ``space_id`` and ``format_version`` are accepted separately
# below only so callers can pass a previously retrieved envelope back unchanged.
_RESERVED_CONFIG_FIELDS = frozenset(
    {
        "version_id",
        "created_at",
        "created_by",
        "config_hash",
        "reason",
        "change_summary",
        "parent_version_id",
        "rollback_target_version_id",
    }
)


@dataclass(frozen=True)
class PreparedEnvelope:
    envelope: dict[str, Any]
    envelope_json: str
    config_hash: str


@dataclass(frozen=True)
class VersionCursor:
    created_at: str
    version_id: str


def require_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolValidationError(f"`{name}` is required and must be a non-empty string.")
    return value


def validate_change_summary(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolValidationError("`change_summary` must be a string when provided.")
    line_breaks = ("\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")
    if any(line_break in value for line_break in line_breaks):
        raise ToolValidationError("`change_summary` must be a single line.")
    if len(value) > MAX_CHANGE_SUMMARY_CHARS:
        raise ToolValidationError(
            f"`change_summary` must be at most {MAX_CHANGE_SUMMARY_CHARS} characters."
        )
    return value


def validate_reason(value: Any) -> str:
    if not isinstance(value, str) or value not in ALLOWED_REASONS:
        allowed = ", ".join(sorted(ALLOWED_REASONS))
        raise ToolValidationError(f"`reason` must be one of: {allowed}.")
    return str(value)


def _validate_nullable_string(config: Mapping[str, Any], name: str) -> None:
    value = config[name]
    if value is not None and not isinstance(value, str):
        raise ToolValidationError(f"`config.{name}` must be a string or null.")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ToolValidationError("`config` must contain only valid JSON values.") from exc


def _validate_serialized_space(value: Any) -> dict[str, Any]:
    serialized_space = require_nonempty_string(value, "config.serialized_space")
    try:
        parsed = json.loads(serialized_space)
    except json.JSONDecodeError as exc:
        raise ToolValidationError("`config.serialized_space` must contain valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ToolValidationError("`config.serialized_space` JSON must be an object.")

    missing = [name for name in REQUIRED_SERIALIZED_SPACE_FIELDS if name not in parsed]
    body_field = next((name for name in SERIALIZED_SPACE_BODY_FIELDS if name in parsed), None)
    if body_field is None:
        missing.append("instructions")
    if missing:
        raise ToolValidationError(
            "`config.serialized_space` is not a complete Genie Agent export; missing "
            "required top-level field(s): "
            + ", ".join(missing)
            + ". Pass the exact value returned by Get Genie Agent with "
            "`include_serialized_space=true`, not a summary or progress report."
        )

    assert body_field is not None
    version = parsed["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ToolValidationError("`config.serialized_space.version` must be a positive integer.")
    for field in (body_field, "data_sources"):
        if not isinstance(parsed[field], dict):
            raise ToolValidationError(f"`config.serialized_space.{field}` must be a JSON object.")

    data_sources = parsed["data_sources"]
    for collection in ("tables", "metric_views"):
        if collection in data_sources and not isinstance(data_sources[collection], list):
            raise ToolValidationError(
                f"`config.serialized_space.data_sources.{collection}` must be a JSON array."
            )
    return parsed


def prepare_envelope(
    *, space_id: str, config: Mapping[str, Any], max_config_bytes: int
) -> PreparedEnvelope:
    """Validate and serialize a complete, forward-compatible restore envelope."""
    require_nonempty_string(space_id, "space_id")
    if not isinstance(config, Mapping):
        raise ToolValidationError("`config` must be a JSON object.")

    unknown_reserved = _RESERVED_CONFIG_FIELDS.intersection(config)
    if unknown_reserved:
        names = ", ".join(sorted(unknown_reserved))
        raise ToolValidationError(f"`config` contains reserved server field(s): {names}.")

    missing = [name for name in REQUIRED_CONFIG_FIELDS if name not in config]
    if missing:
        raise ToolValidationError(
            "`config` is incomplete; missing required field(s): " + ", ".join(missing) + "."
        )

    supplied_space_id = config.get("space_id")
    if supplied_space_id is not None and supplied_space_id != space_id:
        raise ToolValidationError("`config.space_id` must match the top-level `space_id`.")
    supplied_format = config.get("format_version")
    if supplied_format is not None and (
        isinstance(supplied_format, bool)
        or not isinstance(supplied_format, int)
        or supplied_format != FORMAT_VERSION
    ):
        raise ToolValidationError(
            f"unsupported `config.format_version`; expected {FORMAT_VERSION}."
        )

    parsed_serialized_space = _validate_serialized_space(config.get("serialized_space"))

    require_nonempty_string(config.get("title"), "config.title")
    require_nonempty_string(config.get("warehouse_id"), "config.warehouse_id")
    _validate_nullable_string(config, "description")
    _validate_nullable_string(config, "parent_path")
    if "etag" in config and config["etag"] is not None and not isinstance(config["etag"], str):
        raise ToolValidationError("`config.etag` must be a string or null.")

    # Round-trip through JSON to reject custom Python objects and detach the stored value
    # from caller-owned mutable structures while retaining unknown JSON-safe fields.
    config_json = _canonical_json(dict(config))
    envelope = json.loads(config_json)
    envelope["format_version"] = FORMAT_VERSION
    envelope["space_id"] = space_id
    envelope_json = _canonical_json(envelope)
    payload_bytes = len(envelope_json.encode("utf-8"))
    if payload_bytes > max_config_bytes:
        raise ToolValidationError(
            f"`config` is {payload_bytes} bytes; maximum allowed is {max_config_bytes} bytes."
        )

    # Hash semantic restore content. JSON whitespace/key order inside serialized_space and
    # the capture-time etag do not change the content hash.
    hash_basis = dict(envelope)
    hash_basis.pop("format_version", None)
    hash_basis.pop("space_id", None)
    hash_basis.pop("etag", None)
    hash_basis["serialized_space"] = parsed_serialized_space
    canonical_hash_basis = _canonical_json(hash_basis)
    config_hash = hashlib.sha256(canonical_hash_basis.encode("utf-8")).hexdigest()
    return PreparedEnvelope(
        envelope=envelope,
        envelope_json=envelope_json,
        config_hash=config_hash,
    )


def validate_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ToolValidationError("`limit` must be an integer.")
    if limit < 1 or limit > MAX_LIST_LIMIT:
        raise ToolValidationError(f"`limit` must be between 1 and {MAX_LIST_LIMIT}.")
    return limit


def encode_cursor(*, space_id: str, created_at: str, version_id: str) -> str:
    payload = _canonical_json(
        {"v": 1, "space_id": space_id, "created_at": created_at, "version_id": version_id}
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, *, expected_space_id: str) -> VersionCursor:
    require_nonempty_string(cursor, "cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ToolValidationError("`cursor` is invalid.") from exc
    if not isinstance(value, dict) or value.get("v") != 1:
        raise ToolValidationError("`cursor` has an unsupported format.")
    if value.get("space_id") != expected_space_id:
        raise ToolValidationError("`cursor` belongs to a different `space_id`.")
    created_at = require_nonempty_string(value.get("created_at"), "cursor.created_at")
    version_id = require_nonempty_string(value.get("version_id"), "cursor.version_id")
    return VersionCursor(created_at=created_at, version_id=version_id)
