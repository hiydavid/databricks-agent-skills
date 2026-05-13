---
name: genie-space-diagnostics
description: 'Audit a Databricks Genie Space configuration against best practices and produce a prioritized remediation plan. Static analysis only — no queries are sent to Genie. Use when users want to: (1) evaluate a Genie Space against best practices, (2) audit space configuration quality, (3) get a checklist of improvements, (4) understand why Genie answers may be inaccurate, (5) review space setup before optimization or deployment. Triggers on: "diagnose genie space", "audit genie space", "genie space checklist", "review genie space", "genie best practices", "genie configuration audit", "genie setup review", "genie space health check", "why is genie giving wrong answers", "genie not working correctly".'
---

# Genie Space Diagnostics

Audit a Databricks Genie Space configuration against best practices and produce a prioritized remediation plan. This is a **static analysis** — no queries are sent to Genie.

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

**Databricks notebook notes:**
- The script uses the REST API (`client.api_client.do()`) rather than the SDK's `genie.get_space()` — this works reliably across all SDK versions and compute types, including serverless.
- On serverless compute, `client.config.token` is not directly accessible — `api_client.do()` handles authentication automatically, so avoid raw `requests.get()` calls.

This outputs JSON with keys: `title`, `description`, `space_id`, `warehouse_id`, `workspace_host`, `serialized_space` (parsed dict).

### Step 2b: Save Raw Config

- **Claude Code**: Save the JSON output to `reports/<space_id>/space-config.json` (create the directory if needed). Inform the user the raw config has been saved.
- **Databricks notebook**: No additional cell needed. The `space_config` variable from the previous cell is stored in the notebook kernel's memory and is available in subsequent cells.

If the code fails:
- **`ImportError`**: Prompt user to `pip install "databricks-sdk>=0.85"` (Claude Code only — SDK is pre-installed in Databricks)
- **Auth failure**: Prompt user to run `databricks configure` or check environment variables (Claude Code only — Databricks notebooks auto-authenticate)
- **Permission denied (`403` / `PERMISSION_DENIED`)**: User needs CAN EDIT on the space
- **Not found (`404` / `NOT_FOUND`)**: Verify the space ID

## Step 3: Run Diagnostics Audit

### Step 3a: Load Checklist

Read `references/best-practices-checklist.md` for the full evaluation criteria.

### Step 3b: Load Schema Reference (if needed)

If you need to understand specific fields in the serialized space JSON, read `references/space-schema.md`.

### Step 3c: Evaluate Each Checklist Item

For each item in the checklist, examine the fetched space configuration and determine:

- **Status**: `pass`, `fail`, `warning`, or `na`
- **Explanation**: Why this assessment was made, referencing specific data from the space
- **Fix** (for fail/warning only): A specific, actionable recommendation

Be concrete — reference actual table names, column names, instruction text, and field values from the space. Don't give generic advice.

Examples of specific fixes:
- "Add a description to column `unit_price` in table `catalog.schema.orders` — e.g., `'Unit price in USD for a single item'`"
- "Add synonyms `['revenue', 'sales amount']` to column `total_sales` in table `catalog.schema.transactions`"
- "Enable `enable_format_assistance: true` (v2) or `get_example_values: true` (v1) on column `region` in table `catalog.schema.stores` — this column appears filterable"
- "Add a join spec between `catalog.schema.orders` and `catalog.schema.customers` on `orders.customer_id = customers.id`"

## Step 4: Generate Diagnostics Report

Present the diagnostics report in this format:

```markdown
# Genie Space Diagnostics: <space_title>

**Space ID:** `<space_id>`
**Date:** <YYYY-MM-DD>
**Workspace:** `<workspace_host>`

## Summary

| Category | Pass | Fail | Warning | N/A |
|----------|------|------|---------|-----|
| Data Sources | X | X | X | X |
| Instructions | X | X | X | X |
| Benchmarks | X | X | X | X |
| Config | X | X | X | X |
| **Total** | **X** | **X** | **X** | **X** |

## Data Sources

| Item | Status | Explanation |
|------|--------|-------------|
| ... | ... | ... |

Fixes:
1. ...

## Instructions

| Item | Status | Explanation |
|------|--------|-------------|
| ... | ... | ... |

Fixes:
1. ...

## Benchmarks

| Item | Status | Explanation |
|------|--------|-------------|
| ... | ... | ... |

Fixes:
1. ...

## Config

| Item | Status | Explanation |
|------|--------|-------------|
| ... | ... | ... |

Fixes:
1. ...

## Prioritized Remediation Plan

Rank all fixes into three tiers, ordered by expected impact on Genie accuracy:

### Critical (must fix)
All items with `fail` status. These are the most likely causes of incorrect answers.
1. ...

### Recommended (should fix)
Items with `warning` status that affect answer accuracy — descriptions, synonyms, example values, join specs, example SQLs.
1. ...

### Nice-to-Have
Items with `warning` status that affect user experience but not accuracy — sample questions, instruction verbosity, usage guidance.
1. ...

## Optimizer Readiness Assessment

Evaluate whether the space is ready for benchmark-driven optimization via `genie-space-optimizer`:

| Criterion | Status | Details |
|-----------|--------|---------|
| Benchmarks exist | pass/fail | X benchmark questions found |
| Benchmark count >= 10 | pass/fail/warning | X questions (minimum 10, recommended 20+) |
| Benchmark diversity | pass/warning | Coverage across X of Y tables |
| Critical failures resolved | pass/warning | X critical issues should be fixed first |

**Verdict:** Ready / Needs Work / Not Ready

<If not ready, explain what needs to happen before running the optimizer.>
```

## Step 5: Save Report

**Claude Code (local):**
1. Create a `reports/<space_id>/` directory in the user's project root if it doesn't already exist.
2. Save the full diagnostics markdown to `reports/<space_id>/diagnostics-report.md` in the project root.
3. Inform the user of the saved file path.

**Databricks notebook:**
Create a new notebook code cell that renders the diagnostics report as cell output using `displayHTML()` or by printing the markdown string. Do not display the report only in the chat panel.
