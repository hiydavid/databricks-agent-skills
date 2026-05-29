#!/usr/bin/env python3
"""Validate a Databricks Genie decoded serialized_space JSON file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable


ID_RE = re.compile(r"^[0-9a-f]{32}$")
VALID_JOIN_RELATIONSHIPS = {
    "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--",
    "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--",
    "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_ONE--",
    "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_MANY--",
}
V1_COLUMN_FIELDS = {"get_example_values", "build_value_dictionary"}
V2_COLUMN_FIELDS = {"enable_format_assistance", "enable_entity_matching"}
MAX_DATA_SOURCES = 30
MAX_INSTRUCTION_OBJECTS = 100
MAX_ENTITY_MATCHING_COLUMNS = 120
MAX_TEXT_INSTRUCTION_CHARS = 2000
SUMMARY_INSTRUCTION_HEADER = "Instructions you must follow when providing summaries"
CANONICAL_GSL_HEADERS = [
    "PURPOSE",
    "DISAMBIGUATION",
    "DATA QUALITY NOTES",
    "CONSTRAINTS",
    SUMMARY_INSTRUCTION_HEADER,
]
PARAM_RE = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)\b")
HEADER_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")
SQL_IN_PROSE_RE = re.compile(
    r"\bselect\b.+\bfrom\b|\bwhere\s+[`A-Za-z_][\w.`]*\s*(=|<>|!=|>|<|>=|<=|in\b|like\b)"
    r"|\bjoin\s+[`A-Za-z_][\w.`]*\s+\bon\b|\bgroup\s+by\b|\border\s+by\b|\bhaving\b",
    re.I | re.S,
)


class ValidationError(Exception):
    """Raised when the input file cannot be parsed as a space config."""


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def joined_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(joined_text(item) for item in value)
    if isinstance(value, dict):
        return "".join(joined_text(item) for item in value.values())
    return ""


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def path_text(parts: tuple[Any, ...]) -> str:
    out = "$"
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def iter_paths(value: Any, path: tuple[Any, ...] = ()) -> Any:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_paths(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_paths(child, path + (index,))


def iter_objects_with_id(value: Any, path: tuple[Any, ...] = ()) -> Any:
    if isinstance(value, dict):
        if "id" in value:
            yield path, value
        for key, child in value.items():
            yield from iter_objects_with_id(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_objects_with_id(child, path + (index,))


def load_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON: {exc}") from exc
    except OSError as exc:
        raise ValidationError(f"{path}: could not read file: {exc}") from exc

    if not isinstance(data, dict):
        raise ValidationError(f"{path}: top-level JSON must be an object")

    if "serialized_space" in data:
        serialized = data["serialized_space"]
        if isinstance(serialized, str):
            try:
                data = json.loads(serialized)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"{path}: serialized_space string is not valid JSON: {exc}") from exc
        elif isinstance(serialized, dict):
            data = serialized
        else:
            raise ValidationError(f"{path}: serialized_space must be a JSON string or object")

    if not isinstance(data, dict):
        raise ValidationError(f"{path}: decoded serialized_space must be an object")
    return data


def object_ids(items: list[Any]) -> list[str]:
    return [item["id"] for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)]


def check_sorted(
    errors: list[str],
    label: str,
    items: list[Any],
    key_func: Callable[[Any], Any],
) -> None:
    keys = [key_func(item) for item in items]
    if keys != sorted(keys):
        errors.append(f"{label} must be sorted")


def check_duplicates(errors: list[str], label: str, ids: list[str]) -> None:
    duplicates = sorted(value for value, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append(f"{label} has duplicate IDs: {', '.join(duplicates)}")


def require_id(errors: list[str], path: str, item: Any) -> None:
    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
        errors.append(f"{path}.id is required")
    elif not ID_RE.match(item["id"]):
        errors.append(f"{path}.id must be a 32-character lowercase hex string")


def check_string_array(warnings: list[str], path: str, value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        warnings.append(f"{path} should be an array of strings")


def canonical_gsl_header(header: str) -> str | None:
    normalized_header = re.sub(r"\s+", " ", header.strip()).lower()
    for canonical in CANONICAL_GSL_HEADERS:
        if normalized_header == canonical.lower():
            return canonical
    return None


def has_default_value(param: dict[str, Any]) -> bool:
    if "default_value" not in param:
        return False
    value = param.get("default_value")
    if isinstance(value, dict):
        values = value.get("values")
        return isinstance(values, list) and any(str(item).strip() for item in values)
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return value is not None and str(value).strip() != ""


def looks_placeholderish(value: Any) -> bool:
    text = normalized(joined_text(value))
    return bool(re.search(r"\b(example|placeholder|sample|test|todo|tbd|unknown|value)\b", text))


def check_gsl_text_instruction(warnings: list[str], label: str, content: str) -> None:
    if len(content) > MAX_TEXT_INSTRUCTION_CHARS:
        warnings.append(
            f"{label} is over {MAX_TEXT_INSTRUCTION_CHARS} characters; keep global instructions concise"
        )
    if len(content.split()) > 500:
        warnings.append(f"{label} is long; keep global instructions concise")
    if SQL_IN_PROSE_RE.search(content):
        warnings.append(f"{label} appears to contain SQL; prefer snippets, joins, or examples")

    matches = list(HEADER_RE.finditer(content))
    if not matches:
        warnings.append(f"{label} should use canonical GSL markdown sections")
        return

    seen_positions: list[int] = []
    for match in matches:
        raw_header = match.group(1).strip()
        canonical = canonical_gsl_header(raw_header)
        if canonical is None:
            warnings.append(f"{label} has non-canonical GSL header {raw_header!r}")
            continue
        if canonical == SUMMARY_INSTRUCTION_HEADER and raw_header != SUMMARY_INSTRUCTION_HEADER:
            warnings.append(
                f"{label} should use exact summary heading '## {SUMMARY_INSTRUCTION_HEADER}'"
            )
        seen_positions.append(CANONICAL_GSL_HEADERS.index(canonical))

    if seen_positions and seen_positions != sorted(seen_positions):
        warnings.append(f"{label} GSL sections should appear in canonical order")

    present = {canonical_gsl_header(match.group(1).strip()) for match in matches}
    if "PURPOSE" not in present:
        warnings.append(f"{label} should include a PURPOSE section for space scope and audience")


def sql_contains_table_reference(sql_text: str, identifier: str, short_name: str) -> bool:
    lowered = sql_text.lower()
    identifier_l = identifier.lower()
    short_l = short_name.lower()
    return identifier_l in lowered or re.search(rf"\b{re.escape(short_l)}\b", lowered) is not None


def config_sections(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        as_dict(config.get("config")),
        as_dict(config.get("data_sources")),
        as_dict(config.get("instructions")),
    )


def instruction_objects(instructions: dict[str, Any]) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for key in ("text_instructions", "example_question_sqls", "join_specs", "sql_functions"):
        objects.extend(item for item in as_list(instructions.get(key)) if isinstance(item, dict))
    for snippet_group in as_dict(instructions.get("sql_snippets")).values():
        objects.extend(item for item in as_list(snippet_group) if isinstance(item, dict))
    return objects


def sql_texts_with_label(instructions: dict[str, Any], config: dict[str, Any]) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for index, example in enumerate(as_list(instructions.get("example_question_sqls"))):
        sql_text = joined_text(as_dict(example).get("sql")).strip()
        if sql_text:
            texts.append((f"$.instructions.example_question_sqls[{index}].sql", sql_text))
    for index, question in enumerate(as_list(as_dict(config.get("benchmarks")).get("questions"))):
        for answer_index, answer in enumerate(as_list(as_dict(question).get("answer"))):
            sql_text = joined_text(as_dict(answer).get("content")).strip()
            if sql_text:
                texts.append((f"$.benchmarks.questions[{index}].answer[{answer_index}].content", sql_text))
    return texts


def validate(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    config_section, data_sources, instructions = config_sections(config)

    version = config.get("version")
    if version not in (1, 2):
        errors.append("$.version must be 1 or 2; use 2 for new spaces")
    elif version != 2:
        warnings.append("$.version is 1; new Genie spaces should usually use version 2")

    for path, obj in iter_objects_with_id(config):
        value = obj.get("id")
        if not isinstance(value, str) or not ID_RE.match(value):
            errors.append(f"{path_text(path)}.id must be a 32-character lowercase hex string")

    for path, value in iter_paths(config):
        if isinstance(value, str) and len(value) > 25000:
            errors.append(f"{path_text(path)} exceeds the 25,000 character string limit")
        elif isinstance(value, list) and len(value) > 10000:
            errors.append(f"{path_text(path)} exceeds the 10,000 item repeated-field limit")

    tables = as_list(data_sources.get("tables"))
    metric_views = as_list(data_sources.get("metric_views"))
    total_data_sources = len(tables) + len(metric_views)
    entity_matching_columns = 0
    if not tables and not metric_views:
        errors.append("$.data_sources.tables or $.data_sources.metric_views must include at least one data source")
    if total_data_sources > MAX_DATA_SOURCES:
        errors.append(
            "$.data_sources should not contain more than "
            f"{MAX_DATA_SOURCES} total tables, views, and Metric Views"
        )
    elif total_data_sources > 10:
        warnings.append("$.data_sources has more than 10 data objects; start with a smaller focused scope if possible")

    check_sorted(errors, "$.data_sources.tables", tables, lambda item: as_dict(item).get("identifier", ""))
    check_sorted(
        errors,
        "$.data_sources.metric_views",
        metric_views,
        lambda item: as_dict(item).get("identifier", ""),
    )

    for collection_name, collection in (("tables", tables), ("metric_views", metric_views)):
        for index, source in enumerate(collection):
            label = f"$.data_sources.{collection_name}[{index}]"
            source_obj = as_dict(source)
            require_id(errors, label, source)
            identifier = source_obj.get("identifier")
            if not isinstance(identifier, str) or len(identifier.split(".")) != 3:
                errors.append(f"{label}.identifier must use catalog.schema.object")
            if collection_name == "tables":
                desc = joined_text(source_obj.get("description")).strip()
                check_string_array(warnings, f"{label}.description", source_obj.get("description"))
                if not desc or desc.lower() in {"table", str(identifier).split(".")[-1].lower()}:
                    warnings.append(f"{label}.description should explain table grain and business purpose")
            else:
                desc = joined_text(source_obj.get("description")).strip()
                check_string_array(warnings, f"{label}.description", source_obj.get("description"))
                if not desc or desc.lower() in {"metric view", str(identifier).split(".")[-1].lower()}:
                    warnings.append(f"{label}.description should explain Metric View measures, dimensions, and scope")

            column_configs = as_list(source_obj.get("column_configs"))
            if collection_name == "tables" and not column_configs:
                warnings.append(f"{label}.column_configs is empty; add column metadata for Genie quality")
            check_sorted(
                errors,
                f"{label}.column_configs",
                column_configs,
                lambda item: as_dict(item).get("column_name", ""),
            )
            seen_columns: set[tuple[str, str]] = set()
            for column_index, column in enumerate(column_configs):
                column_label = f"{label}.column_configs[{column_index}]"
                column_obj = as_dict(column)
                require_id(errors, column_label, column)
                column_name = column_obj.get("column_name")
                if not isinstance(column_name, str) or not column_name:
                    errors.append(f"{column_label}.column_name is required")
                elif isinstance(identifier, str):
                    key = (identifier, column_name)
                    if key in seen_columns:
                        errors.append(f"{label}.column_configs has duplicate column_name {column_name!r}")
                    seen_columns.add(key)

                if version == 2:
                    for field in V1_COLUMN_FIELDS:
                        if field in column_obj:
                            errors.append(f"{column_label}.{field} is v1-only; use v2 fields for version 2 spaces")
                    if column_obj.get("enable_entity_matching") is True and column_obj.get("enable_format_assistance") is not True:
                        errors.append(f"{column_label}.enable_entity_matching requires enable_format_assistance")
                    if column_obj.get("enable_entity_matching") is True:
                        entity_matching_columns += 1
                elif version == 1:
                    for field in V2_COLUMN_FIELDS:
                        if field in column_obj:
                            errors.append(f"{column_label}.{field} is v2-only; use v1 fields for version 1 spaces")

                check_string_array(warnings, f"{column_label}.description", column_obj.get("description"))
                desc = joined_text(column_obj.get("description")).strip()
                if column_obj.get("exclude") is not True and not desc:
                    warnings.append(f"{column_label}.description should explain the column meaning")
                if column_obj.get("exclude") is not True and column_name and not as_list(column_obj.get("synonyms")):
                    if not re.search(r"(^id$|_id$|uuid|timestamp|created_|updated_|deleted_|etl|ingest)", column_name, re.I):
                        warnings.append(f"{column_label}.synonyms is empty for a visible business column")

    if entity_matching_columns > MAX_ENTITY_MATCHING_COLUMNS:
        warnings.append(
            f"entity matching is enabled for {entity_matching_columns} columns; "
            f"keep it at or below {MAX_ENTITY_MATCHING_COLUMNS} focused categorical columns"
        )

    sample_questions = as_list(config_section.get("sample_questions"))
    benchmark_questions = as_list(as_dict(config.get("benchmarks")).get("questions"))
    text_instructions = as_list(instructions.get("text_instructions"))
    example_sqls = as_list(instructions.get("example_question_sqls"))
    join_specs = as_list(instructions.get("join_specs"))
    sql_functions = as_list(instructions.get("sql_functions"))

    for label, items in (
        ("$.config.sample_questions", sample_questions),
        ("$.benchmarks.questions", benchmark_questions),
        ("$.instructions.text_instructions", text_instructions),
        ("$.instructions.example_question_sqls", example_sqls),
        ("$.instructions.join_specs", join_specs),
        ("$.instructions.sql_functions", sql_functions),
    ):
        for index, item in enumerate(items):
            require_id(errors, f"{label}[{index}]", item)
        check_sorted(errors, label, items, lambda item: as_dict(item).get("id", ""))

    check_sorted(
        errors,
        "$.instructions.sql_functions",
        sql_functions,
        lambda item: (as_dict(item).get("id", ""), as_dict(item).get("identifier", "")),
    )

    snippets = as_dict(instructions.get("sql_snippets"))
    for snippet_name in ("filters", "expressions", "measures"):
        items = as_list(snippets.get(snippet_name))
        check_sorted(
            errors,
            f"$.instructions.sql_snippets.{snippet_name}",
            items,
            lambda item: as_dict(item).get("id", ""),
        )
        for index, snippet in enumerate(items):
            label = f"$.instructions.sql_snippets.{snippet_name}[{index}]"
            require_id(errors, label, snippet)
            if not joined_text(as_dict(snippet).get("sql")).strip():
                errors.append(f"{label}.sql cannot be empty")

    instruction_count = len(instruction_objects(instructions))
    if instruction_count > MAX_INSTRUCTION_OBJECTS:
        warnings.append(
            f"instruction collections contain {instruction_count} objects; "
            f"keep total instructions at or below {MAX_INSTRUCTION_OBJECTS}"
        )

    all_ids = [obj["id"] for _, obj in iter_objects_with_id(config) if isinstance(obj.get("id"), str)]
    check_duplicates(errors, "all serialized_space objects", all_ids)
    check_duplicates(
        errors,
        "sample question and benchmark question collections",
        object_ids(sample_questions) + object_ids(benchmark_questions),
    )
    check_duplicates(errors, "instruction collections", object_ids(instruction_objects(instructions)))

    if len(text_instructions) > 1:
        errors.append("$.instructions.text_instructions allows at most one text instruction")
    for index, instruction in enumerate(text_instructions):
        content = joined_text(as_dict(instruction).get("content"))
        check_gsl_text_instruction(warnings, f"$.instructions.text_instructions[{index}]", content)

    if len(tables) > 1 and not join_specs:
        warnings.append("multiple tables/views are configured but $.instructions.join_specs is empty")

    for index, join in enumerate(join_specs):
        label = f"$.instructions.join_specs[{index}]"
        join_obj = as_dict(join)
        sql_parts = join_obj.get("sql")
        if not isinstance(sql_parts, list) or len(sql_parts) != 2:
            errors.append(f"{label}.sql must have exactly two elements")
            continue
        if sql_parts[1] not in VALID_JOIN_RELATIONSHIPS:
            errors.append(f"{label}.sql[1] has invalid relationship annotation")
        if isinstance(sql_parts[0], str) and re.search(r"\b(and|or)\b", sql_parts[0], re.I):
            warnings.append(f"{label}.sql[0] should contain one equality condition; split compound joins")
        if not joined_text(join_obj.get("comment")).strip():
            warnings.append(f"{label}.comment should explain the business relationship")

    for index, example in enumerate(example_sqls):
        label = f"$.instructions.example_question_sqls[{index}]"
        example_obj = as_dict(example)
        sql_text = joined_text(example_obj.get("sql"))
        usage_guidance = joined_text(example_obj.get("usage_guidance")).strip()
        if not usage_guidance:
            warnings.append(f"{label}.usage_guidance should explain when to apply the example")

        placeholders = set(PARAM_RE.findall(sql_text))
        params = as_list(example_obj.get("parameters"))
        param_by_name = {
            as_dict(param).get("name"): as_dict(param)
            for param in params
            if isinstance(as_dict(param).get("name"), str)
        }
        for name in sorted(placeholders):
            if name not in param_by_name:
                warnings.append(f"{label}.sql uses :{name} but parameters has no matching entry")
        for param_index, param in enumerate(params):
            param_label = f"{label}.parameters[{param_index}]"
            param_obj = as_dict(param)
            name = param_obj.get("name")
            if not isinstance(name, str) or not name:
                warnings.append(f"{param_label}.name is required")
                continue
            if name not in placeholders:
                warnings.append(f"{param_label}.name {name!r} is not used by the SQL")
            if not joined_text(param_obj.get("description")).strip():
                warnings.append(f"{param_label}.description should describe the parameter and real values")
            if not param_obj.get("type_hint"):
                warnings.append(f"{param_label}.type_hint should be set")
            if not has_default_value(param_obj):
                warnings.append(f"{param_label}.default_value should contain a real profiled value")
            elif looks_placeholderish(param_obj.get("default_value")):
                warnings.append(f"{param_label}.default_value looks like a placeholder; use a real profiled value")

    if not sample_questions:
        warnings.append("$.config.sample_questions is empty; add representative UI starter questions")
    elif len(sample_questions) < 5:
        warnings.append("$.config.sample_questions has fewer than 5 questions")

    if not benchmark_questions:
        warnings.append("$.benchmarks.questions is empty; eval-ready spaces should include validated SQL benchmarks")
    elif len(benchmark_questions) < 10:
        warnings.append("$.benchmarks.questions has fewer than 10 questions")
    elif len(benchmark_questions) < 30:
        warnings.append("$.benchmarks.questions has fewer than 30 questions; target 30+ for optimization readiness")

    for index, question in enumerate(benchmark_questions):
        label = f"$.benchmarks.questions[{index}]"
        answers = as_list(as_dict(question).get("answer"))
        if len(answers) != 1:
            errors.append(f"{label}.answer must have exactly one answer")
            continue
        answer = as_dict(answers[0])
        if answer.get("format") != "SQL":
            errors.append(f"{label}.answer[0].format must be SQL")
        answer_sql = joined_text(answer.get("content"))
        placeholders = sorted(set(PARAM_RE.findall(answer_sql)))
        if placeholders:
            warnings.append(
                f"{label}.answer[0].content uses parameter placeholder(s) "
                f":{', :'.join(placeholders)}; benchmark SQL should be concrete"
            )

    benchmark_texts: list[tuple[str, str, str]] = []
    for index, question in enumerate(benchmark_questions):
        question_obj = as_dict(question)
        question_id = str(question_obj.get("id", f"index {index}"))
        question_text = normalized(joined_text(question_obj.get("question")))
        if len(question_text) >= 20:
            benchmark_texts.append((question_id, "question", question_text))
        for answer in as_list(question_obj.get("answer")):
            answer_text = normalized(joined_text(as_dict(answer).get("content")))
            if len(answer_text) >= 40:
                benchmark_texts.append((question_id, "answer", answer_text))

    example_text = normalized(joined_text(example_sqls))
    sample_text = normalized(joined_text(sample_questions))
    snippet_text = normalized(joined_text(snippets))
    for question_id, kind, benchmark_text in benchmark_texts:
        if not benchmark_text:
            continue
        if benchmark_text in example_text:
            errors.append(f"$.instructions.example_question_sqls appears to copy benchmark {kind} from {question_id}")
        if kind == "question" and benchmark_text in sample_text:
            warnings.append(f"$.config.sample_questions appears to duplicate benchmark question from {question_id}")
        if kind == "answer" and benchmark_text in snippet_text:
            errors.append(f"$.instructions.sql_snippets appears to copy benchmark answer from {question_id}")

    metric_identifiers = [
        as_dict(metric_view).get("identifier")
        for metric_view in metric_views
        if isinstance(as_dict(metric_view).get("identifier"), str)
    ]
    metric_names = [(identifier, identifier.split(".")[-1]) for identifier in metric_identifiers]
    for label, sql_text in sql_texts_with_label(instructions, config):
        lowered = sql_text.lower()
        for identifier, name in metric_names:
            identifier_l = identifier.lower()
            name_l = name.lower()
            mentions_metric_view = sql_contains_table_reference(sql_text, identifier, name)
            if not mentions_metric_view:
                continue
            if re.search(r"\bselect\s+\*", lowered):
                errors.append(f"{label} appears to use SELECT * against Metric View {identifier}")
            if "measure(" not in lowered:
                warnings.append(f"{label} mentions Metric View {identifier} but does not use MEASURE()")
            direct_join_pattern = (
                rf"\bfrom\s+`?{re.escape(identifier_l)}`?(?:(?!\)).)*?\bjoin\b"
                rf"|\bjoin\s+`?{re.escape(identifier_l)}`?\b"
                rf"|\bfrom\s+`?{re.escape(name_l)}`?(?:(?!\)).)*?\bjoin\b"
                rf"|\bjoin\s+`?{re.escape(name_l)}`?\b"
            )
            if re.search(direct_join_pattern, lowered, re.S):
                warnings.append(
                    f"{label} appears to join Metric View {identifier} directly; "
                    "use a CTE for mixed Metric View plus table/view SQL"
                )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to decoded serialized_space JSON or create-space request JSON")
    parser.add_argument("--warnings-as-errors", action="store_true", help="Exit non-zero when warnings are present")
    args = parser.parse_args()

    try:
        config = load_config(Path(args.path))
        errors, warnings = validate(config)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    for warning in warnings:
        print(f"WARN: {warning}", file=sys.stderr)

    if errors or (warnings and args.warnings_as_errors):
        return 1

    print(f"OK: {args.path} passed structural validation")
    if warnings:
        print(f"OK: {len(warnings)} best-practice warning(s) reported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
