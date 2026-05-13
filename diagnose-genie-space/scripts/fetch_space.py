#!/usr/bin/env python3
"""
Fetch a Databricks Genie Space's serialized configuration.

Uses the REST API directly (GET /api/2.0/genie/spaces/{space_id}) to ensure
compatibility across all compute types (serverless, classic, interactive)
and SDK versions.

Usage: python fetch_space.py <space_id>
Output: JSON to stdout
Exit codes: 0 success, 1 error (message to stderr)

Requires:
  - databricks-sdk >= 0.85 (pip install "databricks-sdk>=0.85")
  - Databricks CLI profile configured (databricks configure)
  - CAN EDIT permission on the target Genie Space
"""

import json
import sys


def fetch_space(space_id: str) -> dict:
    """Fetch a Genie Space with its serialized configuration."""
    try:
        from databricks.sdk import WorkspaceClient
    except ImportError:
        print(
            'Error: databricks-sdk is not installed. Run: pip install "databricks-sdk>=0.85"',
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        client = WorkspaceClient()
    except Exception as e:
        print(
            f"Error: Failed to initialize Databricks client. "
            f"Ensure your CLI profile is configured (databricks configure).\n{e}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Use REST API directly — works across all compute types and SDK versions.
    # The SDK's genie.get_space() may not support include_serialized_space on
    # older SDK versions bundled with some Databricks notebook runtimes.
    path = f"/api/2.0/genie/spaces/{space_id}?include_serialized_space=true"
    try:
        response = client.api_client.do("GET", path)
    except Exception as e:
        error_msg = str(e)
        if "PERMISSION_DENIED" in error_msg or "403" in error_msg:
            print(
                f"Error: Permission denied. You need CAN EDIT permission on space '{space_id}'.",
                file=sys.stderr,
            )
        elif "NOT_FOUND" in error_msg or "404" in error_msg:
            print(
                f"Error: Genie Space '{space_id}' not found. Check the space ID.",
                file=sys.stderr,
            )
        else:
            print(f"Error: Failed to fetch space '{space_id}': {e}", file=sys.stderr)
        sys.exit(1)

    serialized_space = response.get("serialized_space")
    if not serialized_space:
        print(
            "Error: Could not retrieve serialized_space. "
            "Ensure you have CAN EDIT permission on the Genie Space.",
            file=sys.stderr,
        )
        sys.exit(1)

    return {
        "title": response.get("title"),
        "description": response.get("description"),
        "space_id": space_id,
        "warehouse_id": response.get("warehouse_id"),
        "workspace_host": client.config.host,
        "serialized_space": json.loads(serialized_space),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fetch_space.py <space_id>", file=sys.stderr)
        sys.exit(1)

    result = fetch_space(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
