#!/usr/bin/env python3
"""
Update an existing Databricks Genie Space's serialized configuration in-place.

Uses the REST API directly (PATCH /api/2.0/genie/spaces/{space_id}) to ensure
compatibility across SDK versions — the SDK's update_space() method does not
reliably support serialized_space updates.

Usage: python update_space.py <space_id> <updated_config_path>
Output: JSON to stdout with space_id, title, status
Exit codes: 0 success, 1 error (message to stderr)

Requires:
  - databricks-sdk >= 0.85 (pip install "databricks-sdk>=0.85")
  - Databricks CLI profile configured (databricks configure)
  - CAN EDIT permission on the target Genie Space
"""

import json
import sys


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


def update_space(space_id: str, updated_serialized_space: dict) -> dict:
    """Update an existing Genie Space's serialized configuration in-place.

    Fetches the current space to preserve title, description, and warehouse_id,
    then PATCHes the space with the updated serialized_space via the REST API.

    Args:
        space_id: The Genie Space ID to update.
        updated_serialized_space: The new serialized_space dict.

    Returns:
        dict with space_id, title, and update status.
    """
    client = _get_client()

    # Fetch current space metadata to preserve title/description/warehouse_id
    try:
        space = client.genie.get_space(space_id=space_id)
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

    # PATCH the space via REST API — SDK update_space() does not reliably
    # accept serialized_space; using api_client.do() bypasses that limitation.
    path = f"/api/2.0/genie/spaces/{space_id}"
    body = {
        "title": space.title,
        "description": space.description or "",
        "warehouse_id": space.warehouse_id,
        "serialized_space": json.dumps(updated_serialized_space, ensure_ascii=False),
    }

    try:
        client.api_client.do("PATCH", path, body=body)
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
            print(f"Error: Failed to update space '{space_id}': {e}", file=sys.stderr)
        sys.exit(1)

    return {
        "space_id": space_id,
        "title": space.title,
        "status": "updated",
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python update_space.py <space_id> <updated_config_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    space_id = sys.argv[1]
    config_path = sys.argv[2]

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            updated_config = json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}", file=sys.stderr)
        sys.exit(1)

    result = update_space(space_id, updated_config)
    print(json.dumps(result, indent=2, ensure_ascii=False))
