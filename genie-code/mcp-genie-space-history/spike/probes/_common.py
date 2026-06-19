"""Shared helpers for the local probe runner.

The probes authenticate with a normal Databricks CLI profile (``config.SPIKE_PROFILE``)
and run the SAME ``spike_core`` logic the deployed MCP tools run. Locally there is no
``X-Forwarded-Access-Token``, so "OBO" == the developer's own identity — which is exactly
what we want for the scriptable criteria (#3–#6): they prove the API mechanics under a
real user, independent of the App's request path.
"""

import json
import os
import sys

# Put the spike/ dir on the path so ``import config`` / ``import spike_core`` work whether
# invoked as ``python -m probes.run_all`` or ``python probes/run_all.py``.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from databricks.sdk import WorkspaceClient  # noqa: E402


def build_client() -> WorkspaceClient:
    profile = config.SPIKE_PROFILE or None
    w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
    return w


def banner(title: str):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def show(result: dict):
    print(json.dumps(result, indent=2, default=str))
