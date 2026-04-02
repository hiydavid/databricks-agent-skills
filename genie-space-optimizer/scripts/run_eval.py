#!/usr/bin/env python3
"""
Run benchmark evaluations against a Databricks Genie Space using the Benchmark API (Beta).

Usage:
  python run_eval.py create <space_id> [question_id1,question_id2,...]
  python run_eval.py poll <space_id> <eval_run_id>
  python run_eval.py results <space_id> <eval_run_id>
  python run_eval.py details <space_id> <eval_run_id> <result_id>

Output: JSON to stdout
Exit codes: 0 success, 1 error (message to stderr)

Requires:
  - databricks-sdk >= 0.85 (pip install "databricks-sdk>=0.85")
  - Databricks CLI profile configured (databricks configure)
  - CAN EDIT permission on the target Genie Space
"""

import json
import sys
import time


def _get_client():
    """Initialize and return a Databricks WorkspaceClient."""
    try:
        from databricks.sdk import WorkspaceClient
    except ImportError:
        print(
            'Error: databricks-sdk is not installed. Run: pip install "databricks-sdk>=0.85"',
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        return WorkspaceClient()
    except Exception as e:
        print(
            f"Error: Failed to initialize Databricks client. "
            f"Ensure your CLI profile is configured (databricks configure).\n{e}",
            file=sys.stderr,
        )
        sys.exit(1)


def _api_request(client, method: str, path: str, body: dict = None) -> dict:
    """Make an API request using the WorkspaceClient's API client."""
    try:
        if method == "GET":
            response = client.api_client.do(method, path)
        else:
            response = client.api_client.do(method, path, body=body)
        return response
    except Exception as e:
        error_msg = str(e)
        if "PERMISSION_DENIED" in error_msg or "403" in error_msg:
            print(f"Error: Permission denied.", file=sys.stderr)
        elif "NOT_FOUND" in error_msg or "404" in error_msg:
            print(f"Error: Resource not found. Check the space/run/result ID.", file=sys.stderr)
        else:
            print(f"Error: API request failed: {e}", file=sys.stderr)
        sys.exit(1)


def create_eval_run(space_id: str, question_ids: list[str] = None) -> dict:
    """Create and start an evaluation run for benchmark questions.

    Args:
        space_id: The Genie Space ID.
        question_ids: Optional list of benchmark question IDs to evaluate.
                     If None, all benchmark questions are evaluated.

    Returns:
        dict with eval_run_id, eval_run_status, num_questions, etc.
    """
    client = _get_client()
    path = f"/api/2.0/genie/spaces/{space_id}/eval-runs"
    body = {}
    if question_ids:
        body["benchmark_question_ids"] = question_ids
    return _api_request(client, "POST", path, body=body)


def poll_eval_run(space_id: str, eval_run_id: str, timeout_minutes: int = 15) -> dict:
    """Poll an evaluation run until it reaches a terminal state.

    Args:
        space_id: The Genie Space ID.
        eval_run_id: The evaluation run ID.
        timeout_minutes: Maximum time to wait before giving up.

    Returns:
        dict with final eval run status and counts.
    """
    client = _get_client()
    path = f"/api/2.0/genie/spaces/{space_id}/eval-runs/{eval_run_id}"
    terminal_states = {"DONE", "EVALUATION_FAILED", "EVALUATION_CANCELLED", "EVALUATION_TIMEOUT"}

    deadline = time.time() + (timeout_minutes * 60)
    poll_interval = 5  # seconds

    while time.time() < deadline:
        result = _api_request(client, "GET", path)
        status = result.get("eval_run_status", "")
        num_done = result.get("num_done", 0)
        num_questions = result.get("num_questions", 0)

        print(
            f"Status: {status} — {num_done}/{num_questions} questions completed",
            file=sys.stderr,
        )

        if status in terminal_states:
            return result

        time.sleep(poll_interval)
        # Increase interval for long-running evals, cap at 30s
        poll_interval = min(poll_interval + 5, 30)

    print(
        f"Error: Timed out after {timeout_minutes} minutes waiting for eval run to complete.",
        file=sys.stderr,
    )
    sys.exit(1)


def get_eval_results(space_id: str, eval_run_id: str) -> list[dict]:
    """Get all evaluation result summaries for an eval run, handling pagination.

    Args:
        space_id: The Genie Space ID.
        eval_run_id: The evaluation run ID.

    Returns:
        list of result summary dicts.
    """
    client = _get_client()
    base_path = f"/api/2.0/genie/spaces/{space_id}/eval-runs/{eval_run_id}/results"
    all_results = []
    page_token = None

    while True:
        path = base_path + f"?page_size=100"
        if page_token:
            path += f"&page_token={page_token}"

        response = _api_request(client, "GET", path)
        results = response.get("eval_results", [])
        all_results.extend(results)

        page_token = response.get("next_page_token")
        if not page_token:
            break

    return all_results


def get_result_details(space_id: str, eval_run_id: str, result_id: str) -> dict:
    """Get detailed evaluation result for a single benchmark question.

    Args:
        space_id: The Genie Space ID.
        eval_run_id: The evaluation run ID.
        result_id: The specific result ID.

    Returns:
        dict with assessment, assessment_reasons, actual_response, expected_response, etc.
    """
    client = _get_client()
    path = f"/api/2.0/genie/spaces/{space_id}/eval-runs/{eval_run_id}/results/{result_id}"
    return _api_request(client, "GET", path)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage:\n"
            "  python run_eval.py create <space_id> [question_id1,question_id2,...]\n"
            "  python run_eval.py poll <space_id> <eval_run_id>\n"
            "  python run_eval.py results <space_id> <eval_run_id>\n"
            "  python run_eval.py details <space_id> <eval_run_id> <result_id>",
            file=sys.stderr,
        )
        sys.exit(1)

    command = sys.argv[1]

    if command == "create":
        space_id = sys.argv[2]
        question_ids = sys.argv[3].split(",") if len(sys.argv) > 3 else None
        result = create_eval_run(space_id, question_ids)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif command == "poll":
        if len(sys.argv) < 4:
            print("Usage: python run_eval.py poll <space_id> <eval_run_id>", file=sys.stderr)
            sys.exit(1)
        result = poll_eval_run(sys.argv[2], sys.argv[3])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif command == "results":
        if len(sys.argv) < 4:
            print("Usage: python run_eval.py results <space_id> <eval_run_id>", file=sys.stderr)
            sys.exit(1)
        results = get_eval_results(sys.argv[2], sys.argv[3])
        print(json.dumps(results, indent=2, ensure_ascii=False))

    elif command == "details":
        if len(sys.argv) < 5:
            print(
                "Usage: python run_eval.py details <space_id> <eval_run_id> <result_id>",
                file=sys.stderr,
            )
            sys.exit(1)
        result = get_result_details(sys.argv[2], sys.argv[3], sys.argv[4])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)
