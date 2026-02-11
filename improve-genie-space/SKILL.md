---
name: improve-genie-space
description: 'Analyze, optimize, and improve Databricks Genie Space (AI/BI Dashboard) configurations. Use when users want to: (1) evaluate a Genie Space against best practices, (2) audit space configuration quality, (3) get recommendations for improving their Genie Space, or (4) optimize Genie Space performance. Triggers on: "improve genie space", "analyze genie space", "optimize genie", "audit genie", "review genie space", "genie best practices".'
---

# Improve Genie Space

Analyze and optimize Databricks Genie Space configurations by evaluating them against best practices and providing specific, actionable recommendations.

## Prerequisites

**Databricks notebooks / Assistant:**
- The Databricks SDK is pre-installed and `WorkspaceClient()` authenticates automatically — no setup needed.
- Always use notebook cells for code execution. Chat responses are only for questions, progress, and analysis.

**Claude Code (local):**
1. **Databricks SDK** (v0.85+): `pip install "databricks-sdk>=0.85"`
2. **Databricks CLI profile**: Must be configured (`databricks configure`) or have environment variables set (`DATABRICKS_HOST`, `DATABRICKS_TOKEN`).

**Both environments:**
- **CAN EDIT permission** on the target Genie Space (required to read the serialized configuration).

**Output behavior:**
- Claude Code saves reports to `reports/<space_id>/` in the project root.
- Databricks notebooks: create and run notebook cells for all code execution and result display. Do not run code only in the chat panel.

## Step 1: Identify the Space ID

Ask the user for the Genie Space ID. It's a 32-character hex string (e.g., `01ef8a1b2c3d4e5f6a7b8c9d0e1f2a3b`). Users can find it in the URL when viewing their Genie Space: `https://<workspace>.databricks.com/spaces/<space_id>`.

## Step 2: Fetch Space Configuration

Read `scripts/fetch_space.py` for the implementation, then execute it:

- **Claude Code**: Run via bash:
  ```bash
  python scripts/fetch_space.py <space_id>
  ```
- **Databricks notebook**: Read the script to understand the implementation. Then create a new notebook code cell containing the function definition and a call to it. Replace any `sys.exit()` calls with `raise` statements so the notebook kernel is not killed. Run the cell. Example cell structure:
  ```python
  # <paste fetch_space function definition here, replacing sys.exit(1) with raise>
  space_config = fetch_space("<space_id>")
  space_config
  ```

This outputs JSON with keys: `title`, `description`, `space_id`, `warehouse_id`, `serialized_space` (parsed dict).

### Step 2b: Save Raw Config

- **Claude Code**: Save the JSON output to `reports/<space_id>/space-config.json` (create the directory if needed). Inform the user the raw config has been saved.
- **Databricks notebook**: No additional cell needed. The `space_config` variable from the previous cell is stored in the notebook kernel's memory and is available in subsequent cells.

If the code fails:
- **`ImportError`**: Prompt user to `pip install "databricks-sdk>=0.85"` (Claude Code only — SDK is pre-installed in Databricks)
- **Auth failure**: Prompt user to run `databricks configure` or check environment variables (Claude Code only — Databricks notebooks auto-authenticate)
- **Permission denied (`403` / `PERMISSION_DENIED`)**: User needs CAN EDIT on the space
- **Not found (`404` / `NOT_FOUND`)**: Verify the space ID

## Step 3: Select Workflow

Based on the user's request, select the appropriate workflow:

### Option A: Analyze with Best Practices (default)

Evaluate the space configuration against the best practices checklist. Produces a detailed report with pass/fail/warning status for each item and specific, actionable fixes. **This is the default if the user doesn't specify.**

Read `references/workflow-analyze.md` for the full workflow.

### Option B: Analyze with Benchmarks

Run the space's benchmark questions against Genie via the SDK, compare generated SQL to expected answers, and produce a detailed accuracy report with per-question verdicts and pattern analysis.

Read `references/workflow-benchmark.md` for the full workflow.

### Option C: Optimize Genie Space

Create a **new** optimized Genie Space by applying findings from both the best practices analysis and benchmark analysis. The original space is preserved — only a new copy is created with improvements applied.

**Prerequisites:** Both Option A (config analysis) and Option B (benchmark analysis) must be completed first.

Read `references/workflow-optimize.md` for the full workflow.

## Report Files

All reports are written to `reports/<space_id>/` in the project root (Claude Code) or displayed in notebook cells (Databricks).

| File | Written by | Used by |
|------|-----------|---------|
| `space-config.json` | Step 2 | Options A, B, C |
| `config-analysis.md` | Option A | Option C (prerequisite) |
| `benchmark-analysis.md` | Option B | Option C (prerequisite) |
| `optimized-space-config.json` | Option C | Option C (script input) |
| `optimization-report.md` | Option C | — |
