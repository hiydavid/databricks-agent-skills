# (WIP) mcp-genie-space-history

Home of the **Genie Space History MCP** server. Design lives one level up in
`../genie-space-history-mcp-design.md`.

> **Status: P0 de-risking spike.** Everything here is throwaway/learning code whose job
> is to settle the spec's runtime unknowns (§12 residuals) and prove the end-to-end
> mechanics on a throwaway Space — **not** to be the production server.

## Contents

| Path | What |
|---|---|
| `spike/` | Runnable spike: MCP server (`server/`) + local probes (`probes/`) sharing `spike_core.py`. |
| `RUNBOOK.md` | Copy-pasteable, per-criterion commands (scriptable #3–#6 + deploy/UI #1–#2). |
| `FINDINGS.md` | What actually ran, real output, and the resolved value for each §12 residual. |

## The six P0 exit criteria (design spec §13)

| # | Criterion | How it's covered here |
|---|---|---|
| 1 | Hosting: hello-world MCP on Apps, reachable at `/mcp`, connectable from Genie Code | `spike/server/` + RUNBOOK §1 (deploy + UI) |
| 2 | OBO `current_user.me()` returns the calling user | `whoami` tool / `probes ... whoami`; OBO-over-header is RUNBOOK §2 |
| 3 | App SP auto-creates schema + table (`IF NOT EXISTS`); catalog NOT created | `provision` probe / `provision_history_schema` tool |
| 4 | VARIANT probe → usable or default STRING | `variant` probe / `variant_probe` tool |
| 5 | Genie `get_space` → `update_space` round-trip; record min permission | `roundtrip` probe / `genie_roundtrip` tool |
| 6 | Stale-etag update rejected (optimistic lock) | `etag` probe / `genie_etag_check` tool |

See `RUNBOOK.md` for the full sequence and `FINDINGS.md` for results.
