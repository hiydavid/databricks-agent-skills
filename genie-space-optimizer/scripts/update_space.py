#!/usr/bin/env python3
"""
Update an existing Databricks Genie Space's serialized configuration in-place.

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


def update_space(space_id: str, updated_serialized_space: dict) -> dict:
    """Update an existing Genie Space's serialized configuration.

    The space's title, description, and warehouse_id are preserved.
    Only the serialized_space (config, data_sources, instructions, benchmarks)
    is replaced with the updated version.

    Args:
        space_id: The Genie Space ID to update.
        updated_serialized_space: The new serialized_space dict.

    Returns:
        dict with space_id, title, and update status.
    """
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

    # Update the space with the new serialized config
    try:
        updated_space = client.genie.update_space(
            space_id=space_id,
            serialized_space=json.dumps(updated_serialized_space, ensure_ascii=False),
        )
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
        "title": updated_space.title,
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
