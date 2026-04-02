#!/usr/bin/env python3
"""
Local version management for Genie Space configurations.

Saves snapshots of serialized_space JSON before each mutation, enabling
rollback and diff capabilities since Genie has no native versioning.

Usage:
  python snapshot_space.py save <space_id> <version_name> [--accuracy SCORE] [--summary TEXT]
  python snapshot_space.py list <space_id>
  python snapshot_space.py restore <space_id> <version_name>
  python snapshot_space.py diff <space_id> <version_a> <version_b>

Snapshots are stored in: reports/<space_id>/versions/

Requires:
  - databricks-sdk >= 0.85 (for restore command only)
  - Databricks CLI profile configured (for restore command only)
"""

import json
import os
import sys
from datetime import datetime, timezone


def _versions_dir(space_id: str) -> str:
    """Get the versions directory path for a space."""
    return os.path.join("reports", space_id, "versions")


def _manifest_path(space_id: str) -> str:
    """Get the manifest file path for a space."""
    return os.path.join(_versions_dir(space_id), "manifest.json")


def _load_manifest(space_id: str) -> list[dict]:
    """Load the version manifest, creating it if it doesn't exist."""
    path = _manifest_path(space_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_manifest(space_id: str, manifest: list[dict]) -> None:
    """Save the version manifest."""
    path = _manifest_path(space_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def save_snapshot(
    space_id: str,
    version_name: str,
    config: dict,
    accuracy_score: float = None,
    changes_summary: str = None,
) -> dict:
    """Save a snapshot of the current space configuration.

    Args:
        space_id: The Genie Space ID.
        version_name: Name for this version (e.g., "v0_baseline", "v1_uc_metadata").
        config: The serialized_space dict to snapshot.
        accuracy_score: Optional accuracy percentage from the last eval run.
        changes_summary: Optional description of changes applied in this version.

    Returns:
        dict with version_name, file_path, and timestamp.
    """
    versions_dir = _versions_dir(space_id)
    os.makedirs(versions_dir, exist_ok=True)

    # Save the config snapshot
    snapshot_path = os.path.join(versions_dir, f"{version_name}.json")
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    # Update manifest
    manifest = _load_manifest(space_id)
    timestamp = datetime.now(timezone.utc).isoformat()

    entry = {
        "version": version_name,
        "timestamp": timestamp,
        "file": f"{version_name}.json",
    }
    if accuracy_score is not None:
        entry["accuracy"] = accuracy_score
    if changes_summary:
        entry["changes"] = changes_summary

    manifest.append(entry)
    _save_manifest(space_id, manifest)

    return {
        "version": version_name,
        "file_path": snapshot_path,
        "timestamp": timestamp,
    }


def list_snapshots(space_id: str) -> list[dict]:
    """List all version snapshots for a space.

    Returns:
        list of version entries from the manifest.
    """
    return _load_manifest(space_id)


def restore_snapshot(space_id: str, version_name: str) -> dict:
    """Restore a space to a previous version by updating it with the saved config.

    Args:
        space_id: The Genie Space ID.
        version_name: The version to restore.

    Returns:
        dict with restore status.
    """
    versions_dir = _versions_dir(space_id)
    snapshot_path = os.path.join(versions_dir, f"{version_name}.json")

    if not os.path.exists(snapshot_path):
        print(f"Error: Snapshot '{version_name}' not found at {snapshot_path}", file=sys.stderr)
        sys.exit(1)

    with open(snapshot_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Import and use update_space to apply the restore
    from update_space import update_space

    result = update_space(space_id, config)

    # Record the restore in the manifest
    manifest = _load_manifest(space_id)
    manifest.append({
        "version": f"restore_{version_name}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file": f"{version_name}.json",
        "changes": f"Restored from {version_name}",
    })
    _save_manifest(space_id, manifest)

    return {
        "status": "restored",
        "restored_version": version_name,
        "space_id": space_id,
        "title": result.get("title"),
    }


def diff_snapshots(space_id: str, version_a: str, version_b: str) -> dict:
    """Compare two version snapshots and report differences.

    Args:
        space_id: The Genie Space ID.
        version_a: First version name.
        version_b: Second version name.

    Returns:
        dict summarizing the differences between the two versions.
    """
    versions_dir = _versions_dir(space_id)

    path_a = os.path.join(versions_dir, f"{version_a}.json")
    path_b = os.path.join(versions_dir, f"{version_b}.json")

    for path, name in [(path_a, version_a), (path_b, version_b)]:
        if not os.path.exists(path):
            print(f"Error: Snapshot '{name}' not found at {path}", file=sys.stderr)
            sys.exit(1)

    with open(path_a, "r", encoding="utf-8") as f:
        config_a = json.load(f)
    with open(path_b, "r", encoding="utf-8") as f:
        config_b = json.load(f)

    diff = {
        "version_a": version_a,
        "version_b": version_b,
        "sections": {},
    }

    # Compare top-level sections
    for section in ["config", "data_sources", "instructions", "benchmarks"]:
        a_section = json.dumps(config_a.get(section, {}), sort_keys=True)
        b_section = json.dumps(config_b.get(section, {}), sort_keys=True)
        if a_section != b_section:
            diff["sections"][section] = "changed"
        else:
            diff["sections"][section] = "unchanged"

    # Detailed counts for changed sections
    if diff["sections"].get("data_sources") == "changed":
        tables_a = {t.get("identifier", t.get("id")): t for t in config_a.get("data_sources", {}).get("tables", [])}
        tables_b = {t.get("identifier", t.get("id")): t for t in config_b.get("data_sources", {}).get("tables", [])}
        added = set(tables_b.keys()) - set(tables_a.keys())
        removed = set(tables_a.keys()) - set(tables_b.keys())
        modified = {k for k in tables_a.keys() & tables_b.keys() if json.dumps(tables_a[k], sort_keys=True) != json.dumps(tables_b[k], sort_keys=True)}
        diff["data_sources_detail"] = {
            "tables_added": list(added),
            "tables_removed": list(removed),
            "tables_modified": list(modified),
        }

    if diff["sections"].get("instructions") == "changed":
        instr_a = config_a.get("instructions", {})
        instr_b = config_b.get("instructions", {})
        detail = {}
        for key in ["text_instructions", "example_question_sqls", "join_specs", "sql_functions"]:
            count_a = len(instr_a.get(key, []))
            count_b = len(instr_b.get(key, []))
            if count_a != count_b:
                detail[key] = f"{count_a} → {count_b}"
        snippets_a = instr_a.get("sql_snippets", {})
        snippets_b = instr_b.get("sql_snippets", {})
        for snippet_type in ["filters", "expressions", "measures"]:
            count_a = len(snippets_a.get(snippet_type, []))
            count_b = len(snippets_b.get(snippet_type, []))
            if count_a != count_b:
                detail[f"snippets_{snippet_type}"] = f"{count_a} → {count_b}"
        if detail:
            diff["instructions_detail"] = detail

    if diff["sections"].get("benchmarks") == "changed":
        q_a = len(config_a.get("benchmarks", {}).get("questions", []))
        q_b = len(config_b.get("benchmarks", {}).get("questions", []))
        diff["benchmarks_detail"] = {"questions": f"{q_a} → {q_b}"}

    return diff


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage:\n"
            "  python snapshot_space.py save <space_id> <version_name> [--accuracy SCORE] [--summary TEXT]\n"
            "  python snapshot_space.py list <space_id>\n"
            "  python snapshot_space.py restore <space_id> <version_name>\n"
            "  python snapshot_space.py diff <space_id> <version_a> <version_b>",
            file=sys.stderr,
        )
        sys.exit(1)

    command = sys.argv[1]

    if command == "save":
        if len(sys.argv) < 4:
            print("Usage: python snapshot_space.py save <space_id> <version_name> [--accuracy SCORE] [--summary TEXT]", file=sys.stderr)
            sys.exit(1)

        space_id = sys.argv[2]
        version_name = sys.argv[3]

        # Read config from stdin
        print("Reading serialized_space JSON from stdin...", file=sys.stderr)
        config = json.load(sys.stdin)

        # Parse optional flags
        accuracy = None
        summary = None
        i = 4
        while i < len(sys.argv):
            if sys.argv[i] == "--accuracy" and i + 1 < len(sys.argv):
                accuracy = float(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--summary" and i + 1 < len(sys.argv):
                summary = sys.argv[i + 1]
                i += 2
            else:
                i += 1

        result = save_snapshot(space_id, version_name, config, accuracy, summary)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif command == "list":
        space_id = sys.argv[2]
        snapshots = list_snapshots(space_id)
        print(json.dumps(snapshots, indent=2, ensure_ascii=False))

    elif command == "restore":
        if len(sys.argv) < 4:
            print("Usage: python snapshot_space.py restore <space_id> <version_name>", file=sys.stderr)
            sys.exit(1)
        result = restore_snapshot(sys.argv[2], sys.argv[3])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif command == "diff":
        if len(sys.argv) < 5:
            print("Usage: python snapshot_space.py diff <space_id> <version_a> <version_b>", file=sys.stderr)
            sys.exit(1)
        result = diff_snapshots(sys.argv[2], sys.argv[3], sys.argv[4])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)
