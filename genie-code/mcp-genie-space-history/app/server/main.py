"""uvicorn entry point. Binds to ``DATABRICKS_APP_PORT`` (default 8000) — spec §10."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    port = int(os.environ.get("DATABRICKS_APP_PORT", "8000"))
    uvicorn.run("server.app:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
