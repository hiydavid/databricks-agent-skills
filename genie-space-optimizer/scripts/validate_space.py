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
from collections import Counter
from typing import Any


# Fields that must be arrays of strings (not bare strings) in v2 configs.
# Per the Genie API: https://docs.databricks.com/aws/en/genie/conversation-api
_ARRAY_STRING_FIELDS = {
    "description",
    "question",
    "content",
    "sql",
    "synonyms",
    "comment",
    "instruction",
    "usage_guidance",
}

# Regex for 32-character lowercase hex IDs
_ID_RE = re.compile(r"^[0-9a-f]{32}$")

# Valid relationship type annotations for join_specs sql[1]
_VALID_RELATIONSHIP_TYPES = {
    "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--",
    "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--",
    "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_ONE--",
    "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_MANY--",
}

# Jaccard similarity threshold for benchmark overlap detection
_OVERLAP_SIMILARITY_THRESHOLD = 0.9


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text_from_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(v).strip() for v in value if str(v).strip()).strip()
    return str(value).strip()


def _column_configs(table: dict) -> list[dict]:
    if isinstance(table.get("column_configs"), list):
        return table["column_configs"]
    if isinstance(table.get("columns"), list):
        return table["columns"]
    return []


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


def _fix_snippet_fields(config: dict) -> dict:
    """Fix common LLM mistakes in sql_snippets: wrong field names and wrapped scalars."""
    snippets = config.get("instructions", {}).get("sql_snippets", {})
    for category in ("filters", "expressions", "measures"):
        for item in snippets.get(category, []):
            # Rename 'name' -> 'display_name' (common LLM mistake)
            if "name" in item and "display_name" not in item:
                item["display_name"] = item.pop("name")
            # Unwrap scalar fields that the API expects as plain strings
            for field in ("display_name", "alias"):
                val = item.get(field)
                if isinstance(val, list) and len(val) == 1:
                    item[field] = val[0]
    return config


def _sort_by_id(obj):
    """Recursively sort lists whose elements have an 'id', 'identifier', or 'column_name' key."""
    if isinstance(obj, dict):
        return {k: _sort_by_id(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        processed = [_sort_by_id(item) for item in obj]
        if processed and isinstance(processed[0], dict):
            sort_key = None
            if all("id" in item for item in processed):
                sort_key = "id"
            elif all("identifier" in item for item in processed):
                sort_key = "identifier"
            elif all("column_name" in item for item in processed):
                sort_key = "column_name"
            if sort_key:
                try:
                    processed = sorted(processed, key=lambda x: str(x.get(sort_key, "")))
                except TypeError:
                    pass
        return processed
    return obj


def normalize_serialized_space(config: dict) -> dict:
    """Normalize a serialized_space dict.

    - Fixes common LLM mistakes in sql_snippets (name -> display_name, unwrap scalars)
    - Wraps bare string fields into single-element arrays where the API expects arrays
    - Sorts collections with id/identifier/column_name fields alphabetically

    Args:
        config: The serialized_space dict (parsed JSON).

    Returns:
        Normalized copy of config.
    """
    import copy
    config = copy.deepcopy(config)
    config = _fix_snippet_fields(config)
    config = _wrap_string_fields(config)
    config = _sort_by_id(config)
    return config


# ---------------------------------------------------------------------------
# Benchmark overlap detection
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    """Lowercase and split into word tokens for similarity comparison."""
    return set(re.findall(r"\b\w+\b", text.lower()))


def _jaccard_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity between two text strings."""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def validate_no_benchmark_overlap(config: dict) -> dict:
    """Check that example_question_sqls don't near-exactly copy benchmark questions.

    Returns dict with 'has_overlap' (bool) and 'violations' (list of dicts).
    """
    benchmarks = config.get("benchmarks", {}).get("questions", [])
    examples = config.get("instructions", {}).get("example_question_sqls", [])

    if not benchmarks or not examples:
        return {"has_overlap": False, "violations": []}

    benchmark_texts = [
        (_text_from_value(bq.get("question")), _text_from_value(bq.get("sql")))
        for bq in benchmarks
    ]

    violations = []
    for ex_idx, example in enumerate(examples):
        ex_question = _text_from_value(example.get("question"))
        ex_sql = _text_from_value(example.get("sql"))

        for bq_idx, (bq_text, bq_sql) in enumerate(benchmark_texts):
            q_sim = _jaccard_similarity(ex_question, bq_text)
            if q_sim >= _OVERLAP_SIMILARITY_THRESHOLD:
                violations.append({
                    "example_idx": ex_idx,
                    "example_id": example.get("id", "?"),
                    "benchmark_idx": bq_idx,
                    "type": "question_overlap",
                    "similarity": round(q_sim, 3),
                    "example_text": ex_question[:80],
                    "benchmark_text": bq_text[:80],
                })

            sql_sim = _jaccard_similarity(ex_sql, bq_sql) if ex_sql and bq_sql else 0.0
            if sql_sim >= _OVERLAP_SIMILARITY_THRESHOLD:
                violations.append({
                    "example_idx": ex_idx,
                    "example_id": example.get("id", "?"),
                    "benchmark_idx": bq_idx,
                    "type": "sql_overlap",
                    "similarity": round(sql_sim, 3),
                })

    return {"has_overlap": len(violations) > 0, "violations": violations}


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
    tables = config.get("data_sources", {}).get("tables", [])

    if config_version >= 2:
        for t_idx, table in enumerate(tables):
            identifier = table.get("identifier", "?")
            for c_idx, column in enumerate(_column_configs(table)):
                if "get_example_values" in column:
                    errors.append(
                        f"Table '{identifier}' column_configs[{c_idx}]: "
                        f"'get_example_values' is v1-only and not allowed in v2 — remove it"
                    )
                if "build_value_dictionary" in column:
                    errors.append(
                        f"Table '{identifier}' column_configs[{c_idx}]: "
                        f"'build_value_dictionary' is v1-only — use 'enable_entity_matching' instead"
                    )

    # ------------------------------------------------------------------
    # 5. Table identifiers — must be catalog.schema.table (3 parts)
    # ------------------------------------------------------------------
    for t_idx, table in enumerate(tables):
        identifier = table.get("identifier", "")
        if identifier and len(identifier.split(".")) != 3:
            errors.append(
                f"data_sources.tables[{t_idx}].identifier '{identifier}' "
                f"must be three-level namespace (catalog.schema.table)"
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
    sample_ids = [
        q.get("id")
        for q in config.get("config", {}).get("sample_questions", [])
        if isinstance(q, dict)
    ]
    benchmark_ids = [
        q.get("id")
        for q in config.get("benchmarks", {}).get("questions", [])
        if isinstance(q, dict)
    ]
    all_question_ids = [i for i in sample_ids + benchmark_ids if i]
    qid_counts = Counter(all_question_ids)
    dup_qids = sorted(qid for qid, cnt in qid_counts.items() if cnt > 1)
    if dup_qids:
        errors.append(
            "Question IDs must be unique across config.sample_questions and "
            "benchmarks.questions: " + ", ".join(dup_qids[:5])
        )

    # ------------------------------------------------------------------
    # 8. Instruction ID uniqueness across all instruction types
    # ------------------------------------------------------------------
    instruction_ids = []
    instr = config.get("instructions", {})
    for collection_name in (
        "text_instructions", "example_question_sqls", "sql_functions", "join_specs",
    ):
        for item in instr.get(collection_name, []):
            if isinstance(item, dict) and item.get("id"):
                instruction_ids.append(item["id"])
    for snippet_cat in ("filters", "expressions", "measures"):
        for item in instr.get("sql_snippets", {}).get(snippet_cat, []):
            if isinstance(item, dict) and item.get("id"):
                instruction_ids.append(item["id"])
    instr_id_counts = Counter(instruction_ids)
    dup_instr_ids = sorted(id_ for id_, cnt in instr_id_counts.items() if cnt > 1)
    if dup_instr_ids:
        errors.append(
            "Instruction IDs must be unique across all instruction types: "
            + ", ".join(dup_instr_ids[:5])
        )

    # ------------------------------------------------------------------
    # 9. Join spec structure and relationship type annotations
    # ------------------------------------------------------------------
    join_specs = config.get("instructions", {}).get("join_specs", [])
    for i, spec in enumerate(join_specs):
        spec_id = spec.get("id", f"[{i}]")
        sql_parts = _as_list(spec.get("sql"))

        if len(sql_parts) != 2:
            errors.append(
                f"join_specs['{spec_id}'].sql must have exactly 2 elements "
                f"(equality expression + relationship type annotation), "
                f"got {len(sql_parts)}"
            )
        else:
            # Validate first element: single equality expression
            first = _text_from_value(sql_parts[0])
            if first:
                if re.search(r"\bAND\b|\bOR\b", first, re.IGNORECASE):
                    errors.append(
                        f"join_specs['{spec_id}'].sql[0] contains AND/OR; "
                        f"use one equality expression per element"
                    )
                if first.count("=") != 1:
                    warnings.append(
                        f"join_specs['{spec_id}'].sql[0] should contain "
                        f"exactly one '=' expression"
                    )
            else:
                warnings.append(f"join_specs['{spec_id}'].sql[0] is empty")

            # Validate second element: relationship type annotation
            second = _text_from_value(sql_parts[1])
            if second and second not in _VALID_RELATIONSHIP_TYPES:
                errors.append(
                    f"join_specs['{spec_id}'].sql[1] has invalid relationship type "
                    f"'{second}'; must be one of: "
                    + ", ".join(sorted(_VALID_RELATIONSHIP_TYPES))
                )

    # ------------------------------------------------------------------
    # 10. Column config uniqueness per (table, column_name)
    # ------------------------------------------------------------------
    col_keys: list[str] = []
    for table in tables:
        table_id = table.get("identifier", "")
        for col in _column_configs(table):
            col_name = col.get("column_name", "")
            if col_name:
                col_keys.append(f"{table_id}.{col_name}")
    col_key_counts = Counter(col_keys)
    dup_cols = sorted(k for k, cnt in col_key_counts.items() if cnt > 1)
    if dup_cols:
        errors.append(
            "Column configs must be unique per (table, column_name): "
            + ", ".join(dup_cols[:5])
        )

    # ------------------------------------------------------------------
    # 11. SQL snippet sql fields must not be empty
    # ------------------------------------------------------------------
    for snippet_cat in ("filters", "expressions", "measures"):
        for s_idx, item in enumerate(instr.get("sql_snippets", {}).get(snippet_cat, [])):
            sql_text = _text_from_value(item.get("sql"))
            if not sql_text:
                errors.append(
                    f"instructions.sql_snippets.{snippet_cat}[{s_idx}].sql must not be empty"
                )

    # ------------------------------------------------------------------
    # 12. Benchmark answer format (exactly 1 answer with format "SQL")
    # ------------------------------------------------------------------
    for b_idx, bq in enumerate(config.get("benchmarks", {}).get("questions", [])):
        answers = bq.get("answer", [])
        if len(answers) != 1:
            errors.append(
                f"benchmarks.questions[{b_idx}] must have exactly 1 answer, "
                f"found {len(answers)}"
            )
        for a_idx, ans in enumerate(answers):
            if ans.get("format") != "SQL":
                errors.append(
                    f"benchmarks.questions[{b_idx}].answer[{a_idx}].format "
                    f"must be 'SQL', found '{ans.get('format')}'"
                )

    # ------------------------------------------------------------------
    # 13. Array-string field types — warn if bare strings in v2
    # ------------------------------------------------------------------
    if config_version >= 2:
        def _check_array_string_fields(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    child_path = f"{path}.{k}" if path else k
                    if k in _ARRAY_STRING_FIELDS and isinstance(v, str):
                        warnings.append(
                            f"'{child_path}' is a bare string — in v2 configs it should be "
                            f"an array: [\"{v[:50]}\"]"
                        )
                    else:
                        _check_array_string_fields(v, child_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _check_array_string_fields(item, f"{path}[{i}]")

        _check_array_string_fields(config)

    # ------------------------------------------------------------------
    # 14. Benchmark overlap check (example_question_sqls vs benchmarks)
    # ------------------------------------------------------------------
    overlap = validate_no_benchmark_overlap(config)
    if overlap["has_overlap"]:
        for v in overlap["violations"]:
            if v["type"] == "question_overlap":
                warnings.append(
                    f"instructions.example_question_sqls[{v['example_idx']}] "
                    f"question has {v['similarity']:.0%} similarity with benchmark "
                    f"question #{v['benchmark_idx']} — possible overfitting. "
                    f"Example: \"{v['example_text']}\" vs "
                    f"Benchmark: \"{v['benchmark_text']}\""
                )
            elif v["type"] == "sql_overlap":
                warnings.append(
                    f"instructions.example_question_sqls[{v['example_idx']}] "
                    f"SQL has {v['similarity']:.0%} similarity with benchmark "
                    f"question #{v['benchmark_idx']} SQL — possible overfitting"
                )

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
