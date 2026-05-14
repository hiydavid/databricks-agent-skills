#!/usr/bin/env python3
"""Helpers for repo-local Databricks Genie config and benchmark loops."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable


DEFAULT_PROFILE = "fevm-test"
DEFAULT_EVAL_POLL_INTERVAL_SECONDS = 60
DEFAULT_EVAL_WAIT_TIMEOUT_SECONDS = 3600
ID_RE = re.compile(r"^[0-9a-f]{32}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
RUN_ID_LIKE_RE = re.compile(r"^[0-9a-f]{32}$")
VALID_JOIN_RELATIONSHIPS = {
    "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--",
    "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--",
    "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_ONE--",
    "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_MANY--",
}


class ValidationError(Exception):
    """Raised when a config or report is not valid for this workflow."""


def load_json_file(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON: {exc}") from exc
    except OSError as exc:
        raise ValidationError(f"{path}: could not read file: {exc}") from exc


def write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=True))


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def path_text(parts: tuple[Any, ...]) -> str:
    out = "$"
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}"
    return out


def string_leaves(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        leaves: list[str] = []
        for item in value:
            leaves.extend(string_leaves(item))
        return leaves
    if isinstance(value, dict):
        leaves = []
        for item in value.values():
            leaves.extend(string_leaves(item))
        return leaves
    return []


def joined_text(value: Any) -> str:
    return "".join(string_leaves(value))


def normalized_for_match(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


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


def validate_version_name(version: str) -> None:
    if not VERSION_RE.match(version):
        raise ValidationError(
            f"version must contain only letters, numbers, underscore, dot, or dash: {version!r}"
        )
    if RUN_ID_LIKE_RE.match(version):
        raise ValidationError(
            "version looks like an eval run ID; use a simple version name such as v0 or v1"
        )


def run_cli(argv: list[str]) -> str:
    command = ["databricks", *argv]
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        if completed.stdout:
            sys.stderr.write(completed.stdout)
        if completed.stderr:
            sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)
    return completed.stdout


def run_cli_json(argv: list[str]) -> Any:
    stdout = run_cli(argv)
    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"databricks command did not return JSON: {exc}\n{stdout}") from exc


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"must be an integer: {value!r}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


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
    snippets = as_dict(instructions.get("sql_snippets"))
    for snippet_group in snippets.values():
        objects.extend(item for item in as_list(snippet_group) if isinstance(item, dict))
    return objects


def object_ids(items: list[Any]) -> list[str]:
    ids: list[str] = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.append(item["id"])
    return ids


def benchmark_questions_by_id(config: dict[str, Any]) -> list[dict[str, Any]]:
    questions = as_list(as_dict(config.get("benchmarks")).get("questions"))
    return sorted((question for question in questions if isinstance(question, dict)), key=lambda q: q.get("id", ""))


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


def require_ids(errors: list[str], label: str, items: list[Any]) -> None:
    for index, item in enumerate(items):
        if not isinstance(item, dict) or "id" not in item:
            errors.append(f"{label}[{index}].id is required")


def validate_config_data(
    config: dict[str, Any],
    previous_config: dict[str, Any] | None = None,
    allow_benchmark_changes: bool = False,
) -> list[str]:
    errors: list[str] = []
    config_section, data_sources, instructions = config_sections(config)

    if "version" not in config:
        errors.append("$.version is required")

    for path, obj in iter_objects_with_id(config):
        value = obj.get("id")
        if not isinstance(value, str) or not ID_RE.match(value):
            errors.append(f"{path_text(path)}.id must be a 32-character lowercase hex string")

    tables = as_list(data_sources.get("tables"))
    metric_views = as_list(data_sources.get("metric_views"))
    check_sorted(errors, "$.data_sources.tables", tables, lambda item: as_dict(item).get("identifier", ""))
    check_sorted(
        errors,
        "$.data_sources.metric_views",
        metric_views,
        lambda item: as_dict(item).get("identifier", ""),
    )

    for collection_name, collection in (("tables", tables), ("metric_views", metric_views)):
        for index, source in enumerate(collection):
            source_obj = as_dict(source)
            identifier = source_obj.get("identifier")
            label = f"$.data_sources.{collection_name}[{index}]"
            if not isinstance(identifier, str) or len(identifier.split(".")) != 3:
                errors.append(f"{label}.identifier must use catalog.schema.table")
            column_configs = as_list(source_obj.get("column_configs"))
            check_sorted(
                errors,
                f"{label}.column_configs",
                column_configs,
                lambda item: as_dict(item).get("column_name", ""),
            )
            seen_columns: set[tuple[str, str]] = set()
            for column in column_configs:
                column_name = as_dict(column).get("column_name")
                if isinstance(identifier, str) and isinstance(column_name, str):
                    key = (identifier, column_name)
                    if key in seen_columns:
                        errors.append(f"{label}.column_configs has duplicate column_name {column_name!r}")
                    seen_columns.add(key)

    sample_questions = as_list(config_section.get("sample_questions"))
    benchmark_questions = as_list(as_dict(config.get("benchmarks")).get("questions"))
    text_instructions = as_list(instructions.get("text_instructions"))
    example_sqls = as_list(instructions.get("example_question_sqls"))
    join_specs = as_list(instructions.get("join_specs"))
    sql_functions = as_list(instructions.get("sql_functions"))

    require_ids(errors, "$.config.sample_questions", sample_questions)
    require_ids(errors, "$.benchmarks.questions", benchmark_questions)
    require_ids(errors, "$.instructions.text_instructions", text_instructions)
    require_ids(errors, "$.instructions.example_question_sqls", example_sqls)
    require_ids(errors, "$.instructions.join_specs", join_specs)
    require_ids(errors, "$.instructions.sql_functions", sql_functions)

    check_sorted(errors, "$.config.sample_questions", sample_questions, lambda item: as_dict(item).get("id", ""))
    check_sorted(errors, "$.benchmarks.questions", benchmark_questions, lambda item: as_dict(item).get("id", ""))
    check_sorted(
        errors,
        "$.instructions.text_instructions",
        text_instructions,
        lambda item: as_dict(item).get("id", ""),
    )
    check_sorted(
        errors,
        "$.instructions.example_question_sqls",
        example_sqls,
        lambda item: as_dict(item).get("id", ""),
    )
    check_sorted(errors, "$.instructions.join_specs", join_specs, lambda item: as_dict(item).get("id", ""))
    check_sorted(
        errors,
        "$.instructions.sql_functions",
        sql_functions,
        lambda item: (as_dict(item).get("id", ""), as_dict(item).get("identifier", "")),
    )

    snippets = as_dict(instructions.get("sql_snippets"))
    for snippet_name, snippet_items in snippets.items():
        items = as_list(snippet_items)
        require_ids(errors, f"$.instructions.sql_snippets.{snippet_name}", items)
        check_sorted(
            errors,
            f"$.instructions.sql_snippets.{snippet_name}",
            items,
            lambda item: as_dict(item).get("id", ""),
        )
        for index, snippet in enumerate(items):
            sql_text = joined_text(as_dict(snippet).get("sql")).strip()
            if not sql_text:
                errors.append(f"$.instructions.sql_snippets.{snippet_name}[{index}].sql cannot be empty")

    check_duplicates(
        errors,
        "sample question and benchmark question collections",
        object_ids(sample_questions) + object_ids(benchmark_questions),
    )
    check_duplicates(errors, "instruction collections", object_ids(instruction_objects(instructions)))

    if len(text_instructions) > 1:
        errors.append("$.instructions.text_instructions allows at most one text instruction")

    for index, join in enumerate(join_specs):
        sql_parts = as_dict(join).get("sql")
        if not isinstance(sql_parts, list) or len(sql_parts) != 2:
            errors.append(f"$.instructions.join_specs[{index}].sql must have exactly two elements")
            continue
        if sql_parts[1] not in VALID_JOIN_RELATIONSHIPS:
            errors.append(f"$.instructions.join_specs[{index}].sql[1] has invalid relationship annotation")

    for index, question in enumerate(benchmark_questions):
        answers = as_list(as_dict(question).get("answer"))
        if len(answers) != 1:
            errors.append(f"$.benchmarks.questions[{index}].answer must have exactly one answer")
            continue
        answer = as_dict(answers[0])
        if answer.get("format") != "SQL":
            errors.append(f"$.benchmarks.questions[{index}].answer[0].format must be SQL")

    if previous_config is not None and not allow_benchmark_changes:
        current_benchmarks = benchmark_questions_by_id(config)
        previous_benchmarks = benchmark_questions_by_id(previous_config)
        if current_benchmarks != previous_benchmarks:
            errors.append(
                "benchmark questions and answers changed relative to --previous-config; "
                "use --allow-benchmark-changes only for benchmark bootstrap or repair"
            )

    for path, value in iter_paths(config):
        if isinstance(value, str) and len(value) > 25000:
            errors.append(f"{path_text(path)} exceeds the 25,000 character string limit")
        elif isinstance(value, list) and len(value) > 10000:
            errors.append(f"{path_text(path)} exceeds the 10,000 item repeated-field limit")

    benchmark_texts: list[tuple[str, str, str]] = []
    for index, question in enumerate(benchmark_questions):
        question_obj = as_dict(question)
        question_id = question_obj.get("id", f"index {index}")
        question_text = normalized_for_match(joined_text(question_obj.get("question")))
        if len(question_text) >= 20:
            benchmark_texts.append((str(question_id), "question", question_text))
        for answer in as_list(question_obj.get("answer")):
            answer_text = normalized_for_match(joined_text(as_dict(answer).get("content")))
            if len(answer_text) >= 40:
                benchmark_texts.append((str(question_id), "answer", answer_text))

    example_text = normalized_for_match(joined_text(example_sqls))
    if example_text:
        for question_id, kind, benchmark_text in benchmark_texts:
            if benchmark_text and benchmark_text in example_text:
                errors.append(
                    f"$.instructions.example_question_sqls appears to copy benchmark {kind} from {question_id}"
                )

    return errors


def cmd_save_config(args: argparse.Namespace) -> None:
    validate_version_name(args.version)
    response = run_cli_json(
        [
            "api",
            "get",
            f"/api/2.0/genie/spaces/{args.space_id}?include_serialized_space=true",
            "-p",
            args.profile,
            "-o",
            "json",
        ]
    )
    if not isinstance(response, dict) or "serialized_space" not in response:
        raise SystemExit("response did not include serialized_space")

    serialized_space = response["serialized_space"]
    if isinstance(serialized_space, str):
        try:
            config = json.loads(serialized_space)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"serialized_space was not valid JSON: {exc}") from exc
    elif isinstance(serialized_space, dict):
        config = serialized_space
    else:
        raise SystemExit("serialized_space was neither a JSON string nor an object")

    out_path = Path(args.config_dir) / f"{args.space_id}_{args.version}.json"
    write_json_file(out_path, config)
    print(f"saved decoded serialized_space to {out_path}")


def cmd_validate_config(args: argparse.Namespace) -> None:
    try:
        config = load_json_file(Path(args.config))
        if not isinstance(config, dict):
            raise ValidationError(f"{args.config}: top-level JSON must be an object")
        previous_config = None
        if args.previous_config:
            previous_config = load_json_file(Path(args.previous_config))
            if not isinstance(previous_config, dict):
                raise ValidationError(f"{args.previous_config}: top-level JSON must be an object")
        errors = validate_config_data(config, previous_config, args.allow_benchmark_changes)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"OK: {args.config} passed validation")


def cmd_update_space(args: argparse.Namespace) -> None:
    config_path = Path(args.config)
    try:
        config = load_json_file(config_path)
        if not isinstance(config, dict):
            raise ValidationError(f"{args.config}: top-level JSON must be an object")
        errors = validate_config_data(config)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

    serialized_space = config_path.read_text(encoding="utf-8")
    body = {"serialized_space": serialized_space}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(body, handle)
        request_path = Path(handle.name)

    try:
        response = run_cli_json(
            [
                "api",
                "patch",
                f"/api/2.0/genie/spaces/{args.space_id}",
                "-p",
                args.profile,
                "--json",
                f"@{request_path}",
                "-o",
                "json",
            ]
        )
    finally:
        request_path.unlink(missing_ok=True)
    print_json(response)


def cmd_create_eval_run(args: argparse.Namespace) -> None:
    command = [
        "genie",
        "genie-create-eval-run",
        args.space_id,
        "-p",
        args.profile,
        "-o",
        "json",
    ]
    request_path: Path | None = None
    if args.benchmark_question_id:
        body = {"benchmark_question_ids": args.benchmark_question_id}
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(body, handle)
            request_path = Path(handle.name)
        command.extend(["--json", f"@{request_path}"])

    try:
        response = run_cli_json(command)
    finally:
        if request_path is not None:
            request_path.unlink(missing_ok=True)
    print_json(response)


def eval_results_from_response(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict):
        values = response.get("eval_results") or response.get("results") or []
    else:
        values = response
    return [item for item in as_list(values) if isinstance(item, dict)]


def list_eval_results(space_id: str, eval_run_id: str, profile: str) -> Any:
    command = [
        "genie",
        "genie-list-eval-results",
        space_id,
        eval_run_id,
        "-p",
        profile,
        "--page-size",
        "100",
        "-o",
        "json",
    ]
    all_results: list[dict[str, Any]] = []
    combined_response: dict[str, Any] | None = None
    page_token: str | None = None

    while True:
        page_command = list(command)
        if page_token:
            page_command.extend(["--page-token", page_token])
        response = run_cli_json(page_command)
        page_results = eval_results_from_response(response)
        all_results.extend(page_results)

        if isinstance(response, dict):
            if combined_response is None:
                combined_response = dict(response)
            page_token = response.get("next_page_token")
        else:
            page_token = None
        if not page_token:
            break

    if combined_response is not None:
        combined_response["eval_results"] = all_results
        combined_response.pop("next_page_token", None)
        return combined_response
    return all_results


def get_eval_run(space_id: str, eval_run_id: str, profile: str) -> dict[str, Any]:
    response = run_cli_json(
        [
            "genie",
            "genie-get-eval-run",
            space_id,
            eval_run_id,
            "-p",
            profile,
            "-o",
            "json",
        ]
    )
    return response if isinstance(response, dict) else {}


def wait_for_eval_results(args: argparse.Namespace) -> tuple[Any, list[dict[str, Any]]]:
    deadline = time.monotonic() + args.wait_timeout_seconds
    while True:
        eval_run = get_eval_run(args.space_id, args.eval_run_id, args.profile)
        response = list_eval_results(args.space_id, args.eval_run_id, args.profile)
        eval_results = eval_results_from_response(response)
        status = str(eval_run.get("eval_run_status") or "").upper()
        num_questions = eval_run.get("num_questions")
        num_done = eval_run.get("num_done")
        expected_count = num_questions if isinstance(num_questions, int) and num_questions > 0 else None
        done_count = num_done if isinstance(num_done, int) and num_done >= 0 else None
        terminal = status and status not in {"PENDING", "QUEUED", "RUNNING"}
        failed = status in {"FAILED", "CANCELED", "CANCELLED"}

        if failed:
            raise SystemExit(f"eval run ended with status {status}")

        if eval_results and terminal and (
            expected_count is None
            or len(eval_results) >= expected_count
            or (done_count is not None and done_count >= expected_count)
        ):
            return response, eval_results

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SystemExit(
                "eval run returned zero results after waiting "
                f"{args.wait_timeout_seconds} seconds. Benchmark eval runs are asynchronous; "
                "zero results usually means the run is still in progress or the space has no "
                "benchmark questions. Check the run with genie-get-eval-run, or rerun "
                "pull-report with a longer --wait-timeout-seconds."
            )

        sleep_seconds = min(args.poll_interval_seconds, remaining)
        progress = ""
        if expected_count is not None:
            progress = f" ({len(eval_results)}/{expected_count} result rows"
            if done_count is not None:
                progress += f", {done_count}/{expected_count} done"
            progress += ")"
        print(
            "eval run is not complete"
            f"{progress}; benchmark is likely still running. "
            f"polling again in {sleep_seconds:.0f}s...",
            file=sys.stderr,
        )
        time.sleep(sleep_seconds)


def simplified_responses(value: Any) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    for item in as_list(value):
        if not isinstance(item, dict):
            continue
        responses.append(
            {
                "response_type": item.get("response_type"),
                "response": item.get("response"),
            }
        )
    return responses


def make_report(
    space_id: str,
    eval_run_id: str,
    eval_results: list[dict[str, Any]],
    detail_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    result_by_id = {row.get("result_id"): row for row in eval_results if row.get("result_id")}
    questions: list[dict[str, Any]] = []
    for details in detail_rows:
        result_id = details.get("result_id")
        result_row = result_by_id.get(result_id, {})
        benchmark_question_id = details.get("benchmark_question_id") or result_row.get("benchmark_question_id")
        question_text = result_row.get("question") or details.get("benchmark_question") or details.get("question")
        questions.append(
            {
                "benchmark_question_id": benchmark_question_id,
                "result_id": result_id,
                "benchmark_question": question_text,
                "genie_response": simplified_responses(
                    details.get("actual_response") or details.get("genie_response") or []
                ),
                "expected_response": simplified_responses(details.get("expected_response") or []),
                "assessment": details.get("assessment") or result_row.get("assessment"),
                "assessment_reasons": details.get("assessment_reasons") or [],
            }
        )

    questions.sort(key=lambda row: row.get("benchmark_question_id") or "")
    return {
        "space_id": space_id,
        "eval_run_id": eval_run_id,
        "result_count": len(questions),
        "questions": questions,
    }


def cmd_pull_report(args: argparse.Namespace) -> None:
    validate_version_name(args.version)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    if args.wait and not args.allow_empty:
        eval_results_response, eval_results = wait_for_eval_results(args)
    else:
        eval_results_response = list_eval_results(args.space_id, args.eval_run_id, args.profile)
        eval_results = eval_results_from_response(eval_results_response)

    if not eval_results and not args.allow_empty:
        raise SystemExit(
            "eval run returned zero results. Benchmark eval runs are asynchronous; "
            "do not save or compare a zero-result report as a completed benchmark. "
            "Rerun pull-report with default waiting enabled, or use --allow-empty only for debugging."
        )

    eval_results_path = results_dir / f"{args.version}_eval_results.json"
    details_path = results_dir / f"{args.version}_eval_result_details.jsonl"
    report_path = results_dir / f"{args.version}_benchmark_report.json"
    write_json_file(eval_results_path, eval_results_response)

    detail_rows: list[dict[str, Any]] = []
    with details_path.open("w", encoding="utf-8") as handle:
        for result in eval_results:
            result_id = result.get("result_id") or result.get("id")
            if not result_id:
                continue
            details = run_cli_json(
                [
                    "genie",
                    "genie-get-eval-result-details",
                    args.space_id,
                    args.eval_run_id,
                    str(result_id),
                    "-p",
                    args.profile,
                    "-o",
                    "json",
                ]
            )
            if isinstance(details, dict):
                detail_rows.append(details)
                handle.write(json.dumps(details, ensure_ascii=True))
                handle.write("\n")

    report = make_report(args.space_id, args.eval_run_id, eval_results, detail_rows)
    if not report_questions(report) and not args.allow_empty:
        raise SystemExit(
            "eval results were returned, but no normalized question details could be saved. "
            "Do not compare this as a completed benchmark report; inspect the eval run and retry."
        )
    write_json_file(report_path, report)
    print(f"saved {eval_results_path}")
    print(f"saved {details_path}")
    print(f"saved {report_path}")


def report_label(path: Path, fallback: str) -> str:
    name = path.name
    suffix = "_benchmark_report.json"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return fallback


def report_questions(report: Any) -> list[dict[str, Any]]:
    if isinstance(report, dict):
        values = report.get("questions") or report.get("results") or []
    else:
        values = report
    return [item for item in as_list(values) if isinstance(item, dict)]


def assessment_summary(questions: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(question.get("assessment") or "").upper() for question in questions)
    total = len(questions)
    good = counts.get("GOOD", 0)
    return {
        "total": total,
        "good": good,
        "bad": counts.get("BAD", 0),
        "needs_review": counts.get("NEEDS_REVIEW", 0),
        "accuracy_pct": round((good / total * 100) if total else 0.0, 2),
    }


def cmd_compare_reports(args: argparse.Namespace) -> None:
    baseline_path = Path(args.baseline)
    candidate_path = Path(args.candidate)
    baseline_report = load_json_file(baseline_path)
    candidate_report = load_json_file(candidate_path)

    baseline_label = report_label(baseline_path, "baseline")
    candidate_label = report_label(candidate_path, "candidate")
    if baseline_label == candidate_label:
        baseline_label = "baseline"
        candidate_label = "candidate"

    baseline_questions = report_questions(baseline_report)
    candidate_questions = report_questions(candidate_report)
    if not baseline_questions:
        raise SystemExit(
            f"{baseline_path}: benchmark report has zero questions. "
            "The eval run may not have completed before the report was pulled."
        )
    if not candidate_questions:
        raise SystemExit(
            f"{candidate_path}: benchmark report has zero questions. "
            "The eval run may not have completed before the report was pulled."
        )
    baseline_summary = assessment_summary(baseline_questions)
    candidate_summary = assessment_summary(candidate_questions)

    baseline_by_id = {question.get("benchmark_question_id"): question for question in baseline_questions}
    candidate_by_id = {question.get("benchmark_question_id"): question for question in candidate_questions}
    changed_questions: list[dict[str, Any]] = []
    for question_id in sorted(set(baseline_by_id) | set(candidate_by_id)):
        if question_id is None:
            continue
        baseline_question = baseline_by_id.get(question_id, {})
        candidate_question = candidate_by_id.get(question_id, {})
        baseline_assessment = baseline_question.get("assessment")
        candidate_assessment = candidate_question.get("assessment")
        if baseline_assessment == candidate_assessment:
            continue
        changed_questions.append(
            {
                "benchmark_question_id": question_id,
                "question": candidate_question.get("benchmark_question")
                or baseline_question.get("benchmark_question"),
                baseline_label: baseline_assessment,
                candidate_label: candidate_assessment,
            }
        )

    comparison = {
        f"{baseline_label}_report": str(baseline_path),
        f"{candidate_label}_report": str(candidate_path),
        baseline_label: baseline_summary,
        candidate_label: candidate_summary,
        "delta_good": candidate_summary["good"] - baseline_summary["good"],
        "delta_accuracy_pct_points": round(
            candidate_summary["accuracy_pct"] - baseline_summary["accuracy_pct"],
            2,
        ),
        "changed_questions": changed_questions,
    }
    write_json_file(Path(args.out), comparison)
    print(f"saved {args.out}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repo-local helpers for Databricks Genie config, eval, and report loops."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    save = subparsers.add_parser("save-config", help="Fetch and save decoded serialized_space JSON.")
    save.add_argument("--space-id", required=True)
    save.add_argument("--version", required=True)
    save.add_argument("--profile", default=DEFAULT_PROFILE)
    save.add_argument("--config-dir", default="genie_configs")
    save.set_defaults(func=cmd_save_config)

    validate = subparsers.add_parser("validate-config", help="Validate a local serialized_space JSON file.")
    validate.add_argument("--config", required=True)
    validate.add_argument("--previous-config")
    validate.add_argument(
        "--allow-benchmark-changes",
        action="store_true",
        help="Allow intentional benchmark question/answer changes during benchmark bootstrap or repair.",
    )
    validate.set_defaults(func=cmd_validate_config)

    update = subparsers.add_parser("update-space", help="Validate and patch a Genie space with local config.")
    update.add_argument("--space-id", required=True)
    update.add_argument("--config", required=True)
    update.add_argument("--profile", default=DEFAULT_PROFILE)
    update.set_defaults(func=cmd_update_space)

    eval_run = subparsers.add_parser("create-eval-run", help="Create a Genie benchmark eval run.")
    eval_run.add_argument("--space-id", required=True)
    eval_run.add_argument("--profile", default=DEFAULT_PROFILE)
    eval_run.add_argument(
        "--benchmark-question-id",
        action="append",
        help="Optional benchmark question ID. Repeat to evaluate a subset.",
    )
    eval_run.set_defaults(func=cmd_create_eval_run)

    pull = subparsers.add_parser("pull-report", help="Pull eval results and save normalized versioned reports.")
    pull.add_argument("--space-id", required=True)
    pull.add_argument("--eval-run-id", required=True)
    pull.add_argument("--version", required=True)
    pull.add_argument("--profile", default=DEFAULT_PROFILE)
    pull.add_argument("--results-dir", default="results")
    pull.add_argument(
        "--no-wait",
        dest="wait",
        action="store_false",
        help="Do not poll for eval results before pulling the report.",
    )
    pull.add_argument(
        "--wait-timeout-seconds",
        type=positive_int,
        default=DEFAULT_EVAL_WAIT_TIMEOUT_SECONDS,
        help="Maximum time to wait for eval results before failing.",
    )
    pull.add_argument(
        "--poll-interval-seconds",
        type=positive_int,
        default=DEFAULT_EVAL_POLL_INTERVAL_SECONDS,
        help="Seconds between eval result polling attempts.",
    )
    pull.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow saving a zero-result report for debugging only; implies no waiting.",
    )
    pull.set_defaults(wait=True)
    pull.set_defaults(func=cmd_pull_report)

    compare = subparsers.add_parser("compare-reports", help="Compare GOOD accuracy across two reports.")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--out", required=True)
    compare.set_defaults(func=cmd_compare_reports)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
