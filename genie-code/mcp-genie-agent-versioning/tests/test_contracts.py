"""Complete-envelope validation, canonical hashing, and cursor behavior."""

from __future__ import annotations

import copy
import json

import pytest

from server.contracts import decode_cursor, encode_cursor, prepare_envelope
from server.errors import ToolValidationError


def test_prepared_envelope_adds_server_fields_and_preserves_unknown(complete_config):
    config = {**complete_config, "future_restore_field": {"enabled": True}}
    prepared = prepare_envelope(space_id="space-1", config=config, max_config_bytes=1_000_000)

    assert prepared.envelope["format_version"] == 1
    assert prepared.envelope["space_id"] == "space-1"
    assert prepared.envelope["future_restore_field"] == {"enabled": True}


@pytest.mark.parametrize(
    "missing",
    ["serialized_space", "title", "description", "warehouse_id", "parent_path"],
)
def test_missing_restore_field_is_rejected(complete_config, missing):
    config = dict(complete_config)
    config.pop(missing)
    with pytest.raises(ToolValidationError, match="incomplete"):
        prepare_envelope(space_id="space-1", config=config, max_config_bytes=1_000_000)


def test_serialized_space_must_be_json_object(complete_config):
    config = {**complete_config, "serialized_space": "[]"}
    with pytest.raises(ToolValidationError, match="must be an object"):
        prepare_envelope(space_id="space-1", config=config, max_config_bytes=1_000_000)


def test_current_genie_api_serialized_space_shape_is_accepted(complete_config):
    serialized_space = json.loads(complete_config["serialized_space"])
    assert set(serialized_space) == {"version", "data_sources", "instructions", "benchmarks"}

    prepared = prepare_envelope(
        space_id="space-1", config=complete_config, max_config_bytes=1_000_000
    )

    assert prepared.envelope["serialized_space"] == complete_config["serialized_space"]


@pytest.mark.parametrize(
    "serialized_space",
    [
        '{"state":"after_second_update","pass_rate":"30/39","failed":8}',
        '{"state":"after_fourth_update","pass_rate":"31/39","failed":8}',
        '{"state":"after_third_update","pass_rate":"30/39","failed":6}',
    ],
)
def test_summary_or_progress_report_is_not_a_serialized_space(complete_config, serialized_space):
    config = {**complete_config, "serialized_space": serialized_space}
    with pytest.raises(ToolValidationError, match="not a complete Genie Agent export"):
        prepare_envelope(space_id="space-1", config=config, max_config_bytes=1_000_000)


@pytest.mark.parametrize("missing", ["version", "data_sources"])
def test_serialized_space_requires_export_signature(complete_config, missing):
    serialized_space = {
        "version": 2,
        "instructions": {},
        "data_sources": {"tables": []},
    }
    serialized_space.pop(missing)
    config = {**complete_config, "serialized_space": json.dumps(serialized_space)}
    with pytest.raises(ToolValidationError, match=missing):
        prepare_envelope(space_id="space-1", config=config, max_config_bytes=1_000_000)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("version", True, "positive integer"),
        ("version", 0, "positive integer"),
        ("instructions", [], "must be a JSON object"),
        ("data_sources", [], "must be a JSON object"),
    ],
)
def test_serialized_space_export_signature_has_valid_types(complete_config, field, value, message):
    serialized_space = {
        "version": 2,
        "instructions": {},
        "data_sources": {"tables": []},
    }
    serialized_space[field] = value
    config = {**complete_config, "serialized_space": json.dumps(serialized_space)}
    with pytest.raises(ToolValidationError, match=message):
        prepare_envelope(space_id="space-1", config=config, max_config_bytes=1_000_000)


@pytest.mark.parametrize("collection", ["tables", "metric_views"])
def test_serialized_space_data_source_collections_must_be_arrays(complete_config, collection):
    serialized_space = {
        "version": 2,
        "instructions": {},
        "data_sources": {collection: {}},
    }
    config = {**complete_config, "serialized_space": json.dumps(serialized_space)}
    with pytest.raises(ToolValidationError, match="must be a JSON array"):
        prepare_envelope(space_id="space-1", config=config, max_config_bytes=1_000_000)


def test_serialized_space_accepts_legacy_config_body(complete_config):
    serialized_space = {
        "version": 2,
        "config": {"sample_questions": []},
        "data_sources": {"tables": []},
    }
    config = {**complete_config, "serialized_space": json.dumps(serialized_space)}

    prepared = prepare_envelope(space_id="space-1", config=config, max_config_bytes=1_000_000)

    assert prepared.envelope["serialized_space"] == config["serialized_space"]


def test_serialized_space_requires_instructions_or_legacy_config(complete_config):
    serialized_space = {
        "version": 2,
        "data_sources": {"tables": []},
        "benchmarks": {},
    }
    config = {**complete_config, "serialized_space": json.dumps(serialized_space)}

    with pytest.raises(ToolValidationError, match="instructions"):
        prepare_envelope(space_id="space-1", config=config, max_config_bytes=1_000_000)


def test_space_id_mismatch_is_rejected(complete_config):
    config = {**complete_config, "space_id": "other-space"}
    with pytest.raises(ToolValidationError, match="must match"):
        prepare_envelope(space_id="space-1", config=config, max_config_bytes=1_000_000)


def test_reserved_event_fields_are_rejected(complete_config):
    with pytest.raises(ToolValidationError, match="reserved"):
        prepare_envelope(
            space_id="space-1",
            config={**complete_config, "created_by": "mallory@example.com"},
            max_config_bytes=1_000_000,
        )


def test_hash_is_canonical_and_excludes_etag(complete_config):
    first = copy.deepcopy(complete_config)
    second = copy.deepcopy(complete_config)
    first["serialized_space"] = (
        '{"version":2,"instructions":{"text_instructions":[]},"data_sources":{"tables":[]}}'
    )
    second["serialized_space"] = (
        '{\n  "data_sources": {"tables": []},\n'
        '  "instructions": {"text_instructions": []},\n  "version": 2\n}'
    )
    second["etag"] = "newer-etag"

    p1 = prepare_envelope(space_id="space-1", config=first, max_config_bytes=1_000_000)
    p2 = prepare_envelope(space_id="space-1", config=second, max_config_bytes=1_000_000)
    assert p1.config_hash == p2.config_hash


def test_hash_changes_with_unknown_restore_field(complete_config):
    p1 = prepare_envelope(space_id="space-1", config=complete_config, max_config_bytes=1_000_000)
    p2 = prepare_envelope(
        space_id="space-1",
        config={**complete_config, "future_restore_field": "new"},
        max_config_bytes=1_000_000,
    )
    assert p1.config_hash != p2.config_hash


def test_payload_size_is_bounded(complete_config):
    with pytest.raises(ToolValidationError, match="maximum allowed"):
        prepare_envelope(space_id="space-1", config=complete_config, max_config_bytes=10)


def test_cursor_round_trip_and_space_binding():
    cursor = encode_cursor(
        space_id="space-1",
        created_at="2026-07-30T12:00:00Z",
        version_id="abc",
    )
    decoded = decode_cursor(cursor, expected_space_id="space-1")
    assert decoded.created_at == "2026-07-30T12:00:00Z"
    assert decoded.version_id == "abc"

    with pytest.raises(ToolValidationError, match="different"):
        decode_cursor(cursor, expected_space_id="space-2")


def test_invalid_cursor_is_rejected():
    with pytest.raises(ToolValidationError, match="invalid"):
        decode_cursor("not-base64!", expected_space_id="space-1")
