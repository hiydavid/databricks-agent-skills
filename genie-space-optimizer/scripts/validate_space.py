#!/usr/bin/env python3
"""
Normalize and validate a Databricks Genie Space serialized_space configuration.

Normalization wraps bare string fields into single-element arrays and sorts
collections by their id/identifier field. Validation enforces schema constraints
before the config is pushed to Databricks.

Usage:
  python validate_space.py <config_path>                   # validate only
  python validate_space.py <config_path> --normalize       # normalize then validate

Input:  serialized_space JSON file (just the serialized_space dict, not the full fetch output)
Output: JSON to stdout with {is_valid, errors, warnings} or {is_valid, errors, warnings, normalized_config}
Exit codes: 0 valid, 1 invalid or error (message to stderr)

Requires no external dependencies beyond Python stdlib.
"""

import json
import re
import sys


# Fields that must be arrays of strings (not bare strings) in v2 configs
_ARRAY_STRING_FIELDS = {"description", "synonyms", "content"}

# Regex for 32-character lowercase hex IDs
_ID_RE = re.compile(r"^[0-9a-f]{32}$")


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _wrap_string_fields(obj):
    """Recursively wrap bare string values for known array-string fields."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if k in _ARRAY_STRING_FIELDS and isinstance(v, str):
                result[k] = [v]
            else:
                result[k] = _wrap_string_fields(v)
        return result
    elif isinstance(obj, list):
        return [_wrap_string_fields(item) for item in obj]
    return obj


def _sort_by_id(obj):
    """Recursively sort lists whose elements have an 'id' or 'identifier' key."""
    if isinstance(obj, dict):
        return {k: _sort_by_id(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        processed = [_sort_by_id(item) for item in obj]
        if processed and isinstance(processed[0], dict):
            sort_key = None
            if "id" in processed[0]:
                sort_key = "id"
            elif "identifier" in processed[0]:
                sort_key = "identifier"
            if sort_key:
                try:
                    processed = sorted(processed, key=lambda x: x.get(sort_key, ""))
                except TypeError:
                    pass
        return processed
    return obj


def normalize_serialized_space(config: dict) -> dict:
    """Normalize a serialized_space dict.

    - Wraps bare string description/synonyms/content fields into arrays
    - Sorts collections with id/identifier fields alphabetically

    Args:
        config: The serialized_space dict (parsed JSON).

    Returns:
        Normalized copy of config.
    """
    config = _wrap_string_fields(config)
    config = _sort_by_id(config)
    return config


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _is_valid_id(value) -> bool:
    return isinstance(value, str) and bool(_ID_RE.match(value))


def _collect_ids(obj, ids: set, path: str = ""):
    """Recursively collect all 'id' field values."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{path}.{k}" if path else k
            if k == "id":
                ids.add((v, child_path))
            else:
                _collect_ids(v, ids, child_path)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _collect_ids(item, ids, f"{path}[{i}]")


def validate_serialized_space(config: dict) -> dict:
    """Validate a serialized_space dict against Genie schema constraints.

    Args:
        config: The serialized_space dict (parsed JSON, ideally already normalized).

    Returns:
        dict with:
          - is_valid (bool): True if no errors
          - errors (list[str]): Blocking issues that must be fixed
          - warnings (list[str]): Non-blocking issues to review
    """
    errors = []
    warnings = []

    config_version = config.get("config", {}).get("version", 1)

    # ------------------------------------------------------------------
    # 1. ID format — all 'id' fields must be 32-char lowercase hex
    # ------------------------------------------------------------------
    id_values = set()
    _collect_ids(config, id_values)
    for id_val, path in id_values:
        if not _is_valid_id(id_val):
            errors.append(
                f"Invalid ID at '{path}': '{id_val}' — must be 32-char lowercase hex "
                f"(e.g. python -c \"import secrets; print(secrets.token_hex(16))\")"
            )

    # ------------------------------------------------------------------
    # 2. Array length limit — max 10,000 elements per list
    # ------------------------------------------------------------------
    def _check_array_lengths(obj, path=""):
        if isinstance(obj, list):
            if len(obj) > 10_000:
                errors.append(
                    f"Array at '{path}' has {len(obj)} elements — max allowed is 10,000"
                )
            for i, item in enumerate(obj):
                _check_array_lengths(item, f"{path}[{i}]")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _check_array_lengths(v, f"{path}.{k}" if path else k)

    _check_array_lengths(config)

    # ------------------------------------------------------------------
    # 3. String length limit — max 25,000 characters
    # ------------------------------------------------------------------
    def _check_string_lengths(obj, path=""):
        if isinstance(obj, str):
            if len(obj) > 25_000:
                errors.append(
                    f"String at '{path}' is {len(obj)} characters — max allowed is 25,000"
                )
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _check_string_lengths(item, f"{path}[{i}]")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _check_string_lengths(v, f"{path}.{k}" if path else k)

    _check_string_lengths(config)

    # ------------------------------------------------------------------
    # 4. Version-specific constraints (v2+)
    # ------------------------------------------------------------------
    if config_version >= 2:
        tables = config.get("data_sources", {}).get("tables", [])
        for table in tables:
            identifier = table.get("identifier", "?")
            for col in table.get("column_configs", []):
                col_id = col.get("id", "?")
                if col.get("get_example_values"):
                    errors.append(
                        f"Table '{identifier}' column '{col_id}': 'get_example_values' is "
                        f"not allowed in v2+ configs — remove it"
                    )
                if col.get("build_value_dictionary"):
                    errors.append(
                        f"Table '{identifier}' column '{col_id}': 'build_value_dictionary' is "
                        f"not allowed in v2+ configs — use 'enable_entity_matching' instead"
                    )

    # ------------------------------------------------------------------
    # 5. Table identifiers — must be catalog.schema.table (3 parts)
    # ------------------------------------------------------------------
    tables = config.get("data_sources", {}).get("tables", [])
    for table in tables:
        identifier = table.get("identifier", "")
        if identifier:
            parts = identifier.split(".")
            if len(parts) != 3:
                errors.append(
                    f"Table identifier '{identifier}' must have exactly 3 parts "
                    f"(catalog.schema.table), got {len(parts)}"
                )

    # ------------------------------------------------------------------
    # 6. Max 1 text_instruction entry
    # ------------------------------------------------------------------
    text_instructions = config.get("instructions", {}).get("text_instructions", [])
    if len(text_instructions) > 1:
        errors.append(
            f"instructions.text_instructions has {len(text_instructions)} entries — "
            f"max allowed is 1. Merge all content into a single entry."
        )

    # ------------------------------------------------------------------
    # 7. Unique question IDs across sample and benchmark questions
    # ------------------------------------------------------------------
    seen_question_ids = {}
    for section_name, section_key in [
        ("benchmarks", "questions"),
        ("instructions", "example_question_sqls"),
    ]:
        section = config.get(section_name, {})
        for q in section.get(section_key, []):
            qid = q.get("id")
            if qid:
                if qid in seen_question_ids:
                    errors.append(
                        f"Duplicate question ID '{qid}' found in both "
                        f"'{seen_question_ids[qid]}' and '{section_name}.{section_key}'"
                    )
                else:
                    seen_question_ids[qid] = f"{section_name}.{section_key}"

    # ------------------------------------------------------------------
    # 8. Join spec structure
    # ------------------------------------------------------------------
    join_specs = config.get("instructions", {}).get("join_specs", [])
    for i, spec in enumerate(join_specs):
        spec_id = spec.get("id", f"[{i}]")
        sql_parts = spec.get("sql", [])

        if len(sql_parts) != 2:
            errors.append(
                f"join_specs['{spec_id}'].sql must have exactly 2 elements, "
                f"got {len(sql_parts)}"
            )
        elif sql_parts:
            first = sql_parts[0]
            if re.search(r"\bAND\b|\bOR\b", first, re.IGNORECASE):
                errors.append(
                    f"join_specs['{spec_id}'].sql[0] must be a single equality expression "
                    f"— remove AND/OR: '{first[:100]}'"
                )
            if "=" not in first:
                warnings.append(
                    f"join_specs['{spec_id}'].sql[0] should contain an equality expression: "
                    f"'{first[:100]}'"
                )

    # ------------------------------------------------------------------
    # 9. description fields should be arrays in v2 (warn if bare string)
    # ------------------------------------------------------------------
    if config_version >= 2:
        def _check_descriptions(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    child_path = f"{path}.{k}" if path else k
                    if k == "description" and isinstance(v, str):
                        warnings.append(
                            f"'{child_path}' is a bare string — in v2 configs it should be "
                            f"an array: [\"{v[:50]}\"]"
                        )
                    else:
                        _check_descriptions(v, child_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _check_descriptions(item, f"{path}[{i}]")

        _check_descriptions(config)

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  python validate_space.py <config_path>              # validate only\n"
            "  python validate_space.py <config_path> --normalize  # normalize then validate",
            file=sys.stderr,
        )
        sys.exit(1)

    config_path = sys.argv[1]
    do_normalize = "--normalize" in sys.argv

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {config_path}: {e}", file=sys.stderr)
        sys.exit(1)

    if do_normalize:
        config = normalize_serialized_space(config)

    result = validate_serialized_space(config)

    if do_normalize:
        result["normalized_config"] = config

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if not result["is_valid"]:
        print(
            f"\nValidation failed: {len(result['errors'])} error(s), "
            f"{len(result['warnings'])} warning(s)",
            file=sys.stderr,
        )
        sys.exit(1)
    elif result["warnings"]:
        print(
            f"\nValidation passed with {len(result['warnings'])} warning(s)",
            file=sys.stderr,
        )
