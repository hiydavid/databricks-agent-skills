"""uvicorn entry point. Binds to DATABRICKS_APP_PORT (default 8000) per design spec §10."""

import os

import uvicorn


def main():
    port = int(os.environ.get("DATABRICKS_APP_PORT", "8000"))
    uvicorn.run("server.app:combined_app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
