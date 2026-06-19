# spike/ — throwaway P0 spike code

De-risking spike for the **Genie Space History MCP** (see `../genie-space-history-mcp-design.md`,
anchor §13 P0). **This is throwaway/learning code** — it proves mechanics, it is not
production-grade.

## Layout

```
spike/
├── config.py          # env-driven config (throwaway-spike defaults baked in)
├── spike_core.py      # the actual logic for criteria #2–#6 (shared by server + probes)
├── server/            # the MCP server (FastAPI + FastMCP, /mcp stateless)
│   ├── app.py         #   - http_app(stateless_http=True) + CORS + header-capture middleware
│   ├── tools.py       #   - MCP tools (health, whoami, provision, variant, genie_roundtrip, etag)
│   ├── utils.py       #   - OBO client (X-Forwarded-Access-Token) vs app-SP client
│   └── main.py        #   - uvicorn entry (binds DATABRICKS_APP_PORT)
├── probes/            # local runner for the scriptable criteria (#3–#6)
│   └── run_all.py     #   - python -m probes.run_all [whoami provision variant roundtrip etag]
├── app.yaml           # Databricks Apps manifest
└── requirements.txt   # pins databricks-sdk>=0.118.0 (etag support)
```

`server/` and `probes/` run the **same** `spike_core` functions; only the identity/transport
differ (deployed App + OBO header vs local CLI profile).

## Run the probes locally (criteria #3–#6)

```bash
cd spike
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt          # needs databricks-sdk>=0.118.0
# one-time: create the CLI profile the probes use
databricks auth login --host https://fevm-dhuang.cloud.databricks.com --profile fevm-dhuang
python -m probes.run_all                    # runs whoami + provision + variant + roundtrip + etag
```

Override any input via env, e.g. `SQL_WAREHOUSE_ID=... GENIE_SPACE_ID=... python -m probes.run_all`.

## Run the server locally (criterion #1 smoke)

```bash
cd spike
uvicorn server.app:combined_app --host 0.0.0.0 --port 8000
# MCP is at http://localhost:8000/mcp ; health at http://localhost:8000/healthz
```

See `../RUNBOOK.md` for the deploy + Genie-Code-connect steps (criteria #1, #2 over OBO).
