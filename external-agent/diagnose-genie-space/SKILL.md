---
name: diagnose-genie-space
description: "Diagnose Databricks Genie Space quality, feedback, and response-latency problems and produce a concrete tuning plan. Use when users ask why a Genie Space cannot answer a question consistently, gives wrong SQL, chooses wrong data sources, metric views, tables, columns, measures, dimensions, filters, or joins, shows negative Monitor feedback trends, responds slowly, or needs a configuration health check before optimization. This skill is plan-only: it may fetch/read space configuration and perform bounded read-only SQL inspection, but it must not edit serialized_space, update a Genie Space, run benchmark evals, or mutate Databricks data. For versioned edits and eval loops use optimize-genie-space; for authoring a new Space use create-genie-space."
---

# Diagnose Genie Space

Diagnose Genie Space quality problems and produce a concrete tuning plan. The default workflow is **question-level tuning triage**: start from a failing user question, gather evidence from the serialized space, Monitor feedback, and read-only data inspection, classify the likely failure mode, and recommend the smallest useful Genie configuration change.

This skill is plan-only. Do not edit local config files, patch Databricks, run benchmark evals, or change benchmark questions. If the user wants versioned edits, updates, eval runs, or accuracy comparison, hand off to `optimize-genie-space` after diagnosis.

## Prerequisites

**Databricks notebooks / Assistant:**
- The Databricks SDK is pre-installed and `WorkspaceClient()` authenticates automatically.
- Always use notebook cells for code execution and SQL inspection. Chat responses are only for questions, progress, and analysis.

**Claude Code / local coding agents:**
1. **Databricks SDK** (v0.85+): `pip install "databricks-sdk>=0.85"`
2. **Databricks CLI profile** or environment variables configured.

**Both environments:**
- **CAN EDIT permission** on the target Genie Space is required to read `serialized_space`.
- Use only bounded read-only SQL inspection when live data evidence is needed.

**Output behavior:**
- Local coding agents save reports to `reports/<space_id>/` in the user's project folder.
- Databricks notebooks render the report in notebook output with `displayHTML()` or printed markdown.

## Step 1: Establish The Case

Ask for any missing inputs that materially affect diagnosis:

- Genie Space ID, a 32-character hex string from the space URL.
- Failing question, exactly as the user asks it.
- Observed bad behavior: wrong data source, wrong metric view, wrong table, wrong column, wrong measure, wrong dimension, wrong time dimension, wrong filter scope, wrong grain, missing join, inconsistent answers, SQL error, empty answer, slow response, or unclear.
- Actual generated SQL or error text, if available.
- Expected answer, expected SQL, or business rule if available.
- Whether the issue is intermittent or consistently reproducible.

If the user only asks for a general audit, skip the question-level sections and run the static health-check workflow.

## Step 2: Fetch Space Configuration

Read `scripts/fetch_space.py` for the implementation, then execute it.

**Claude Code / local coding agents:**

```bash
python scripts/fetch_space.py <space_id>
```

Save the JSON output to `reports/<space_id>/space-config.json`. The output has:

- `title`
- `description`
- `space_id`
- `warehouse_id`
- `workspace_host`
- `serialized_space` as a parsed object

**Databricks notebook / Assistant:**
- Read `scripts/fetch_space.py`.
- Create a notebook code cell containing the function definition and call.
- Replace `sys.exit()` calls with `raise` statements so the notebook kernel is not killed.
- Keep the returned object in `space_config` for later cells.

The script uses `client.api_client.do()` against `/api/2.0/genie/spaces/{space_id}?include_serialized_space=true`; avoid raw `requests.get()` because serverless auth tokens are not directly accessible.

If fetching fails:
- `ImportError`: install `databricks-sdk>=0.85` for local agents.
- Auth failure: configure the Databricks CLI profile or environment variables for local agents.
- `403` / `PERMISSION_DENIED`: the user needs CAN EDIT on the space.
- `404` / `NOT_FOUND`: verify the space ID.

## Step 3: Load References

Read only the references needed for the case:

- `references/tuning-diagnosis.md` for failure classification, feedback routing, latency pre-routing, conflict precedence, and tuning-surface routing.
- `references/best-practices-checklist.md` for supporting static health checks and the confidence rubric.
- `references/space-schema.md` when field shapes, version-specific names, or validation rules matter.

## Step 4: Inspect Evidence

### 4a: Serialized Space Evidence

Inventory the config surfaces implicated by the failing question using the evidence list in `references/tuning-diagnosis.md` (Evidence To Gather). Prefer concrete evidence: table names, column names, field values, instruction text, snippet names, and benchmark IDs.

### 4b: Feedback And Latency Evidence

When the case involves quality trends or slow responses:

- **Monitor feedback**: ask the user for Monitor-tab exports, screenshots, or reviewable conversation details — ratings trends, negative ratings, `Fix it` / `Request review` conversations, feedback and reviewer comments, and generated SQL or error text from reviewable conversations. When conversations are private or Monitor details are unavailable, use only visible prompt, status, rating, timestamp, and trend metadata; do not use conversation APIs or audit logs to recover hidden content. Route patterns per `references/tuning-diagnosis.md` → Feedback Routing.
- **Latency complaints**: separate SQL-runtime latency from generation/thinking latency using the questions and Query History timing described in `references/tuning-diagnosis.md` → Latency Pre-Routing. If SQL runtime dominates and the generated SQL is correct, stop Space-quality diagnosis and route to query/warehouse follow-up outside Space configuration.

### 4c: Read-Only SQL Inspection

Use the DBSQL MCP, Databricks SQL, or notebook SQL cells for read-only SQL only when the serialized config is insufficient to determine the likely cause. Keep inspection targeted and bounded.

Allowed SQL: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema` queries. Not allowed: `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, or any table/schema/data mutation.

Record the SQL purpose and findings in the report. Do not include broad exploratory dumps.

## Step 5: Classify The Failure

Choose one primary failure class, plus secondary contributors if needed, using the failure classes in `references/tuning-diagnosis.md`: wrong data source / metric view / field, wrong metric view measure or dimension, wrong metric view scope / time dimension / grain, wrong filter value, wrong join, metric or business logic error, time logic error, result shape error, instruction conflict or overload, generation latency or context overload, permission / governance / data visibility limitation, or unknown from static evidence (state exactly what additional result SQL, expected SQL, or eval report is needed).

For conflicting or ignored guidance, name the precedence mechanism (bindingness, relevance selection, or budget crowding) per `references/tuning-diagnosis.md` → Conflict Resolution And Precedence. Assign High / Medium / Low confidence using the canonical rubric in `references/best-practices-checklist.md` → No-Query Diagnosis Mode.

## Step 6: Recommend Tuning Changes

Recommend the smallest structured Genie configuration change that addresses the failure, using the routing order in `references/tuning-diagnosis.md` (structured surfaces first, text instructions last).

Never recommend copying benchmark questions, benchmark answer SQL, or evaluation notes into sample questions, snippets, example SQL, or any other config surface (benchmark leakage). Example SQL should teach a representative pattern, not memorize a test.

For every recommended change, include:

- the target config surface
- exact table, column, join, snippet, example, or instruction target
- the proposed wording or JSON-level intent
- why this is the smallest appropriate intervention
- how the user should validate it after implementation

## Step 7: Run Static Space Health Checks

Use `references/best-practices-checklist.md` as supporting evidence after the question-level diagnosis. Evaluate the health checks most relevant to the failure first, then summarize broader issues. Do not let a generic checklist item outrank a concrete finding about the failing question.

## Step 8: Generate Diagnostics Report

Present the report in this format:

```markdown
# Genie Space Diagnostics: <space_title>

**Space ID:** `<space_id>`
**Date:** <YYYY-MM-DD>
**Workspace:** `<workspace_host>`

## Question-Level Tuning Diagnosis

**Failing question:** <question>
**Observed behavior:** <what the user reported>
**Expected behavior:** <expected answer, SQL, or business rule; say "not provided" if absent>

| Finding | Details |
|---------|---------|
| Primary failure class | ... |
| Secondary contributors | ... |
| Likely root cause | ... |
| Confidence | High / Medium / Low (rubric: best-practices-checklist.md) |

## Evidence From Serialized Space

- ...

## Feedback And Latency Evidence

- Monitor trends / reviewable conversations inspected: Yes / No / Unavailable
- Latency split (generation vs SQL runtime), if applicable: ...
- Privacy limitations: ...

## Read-Only Inspection Notes

- SQL inspection performed: Yes / No
- Findings: ...
- Limitations: ...

## Recommended Genie Tuning Changes

Rank by expected impact on the failing question.

| Priority | Config surface | Recommendation | Rationale | Validation |
|----------|----------------|----------------|-----------|------------|
| 1 | ... | ... | ... | ... |

## Static Space Health Checks

| Category | Pass | Fail | Warning | N/A |
|----------|------|------|---------|-----|
| Data Sources | X | X | X | X |
| Instructions | X | X | X | X |
| Benchmarks | X | X | X | X |
| Config | X | X | X | X |
| **Total** | **X** | **X** | **X** | **X** |

### Notable Static Findings

| Item | Status | Explanation | Suggested fix |
|------|--------|-------------|---------------|
| ... | ... | ... | ... |

## Optimizer Readiness

| Criterion | Status | Details |
|-----------|--------|---------|
| Benchmarks exist | pass/fail | X benchmark questions found |
| Benchmark count | pass/fail/warning | X questions; 30+ valid Q/A pairs recommended before benchmark-driven tuning (skill convention) |
| Benchmark answer shape | pass/fail/warning | X questions have exactly one SQL answer |
| Benchmark diversity | pass/warning | Coverage across data sources, metric views, measures, dimensions, joins, filters, time logic, and result shapes |
| Critical static failures resolved | pass/warning | X issues should be addressed before optimization |

**Verdict:** Ready / Needs Work / Not Ready

## Handoff

- For versioned edits, eval runs, and accuracy comparison: `optimize-genie-space`. Suggested first optimization task: ...
- For SQL-runtime-dominated latency with correct generated SQL: query/warehouse follow-up outside Space configuration (for example a query-optimization skill when available).
- For wrong or missing Metric View definitions: upstream semantic-layer fix (for example a metric-view authoring skill when available).
```

## Step 9: Save Report

**Claude Code / local coding agents:**
1. Create `reports/<space_id>/` in the user's project folder if needed.
2. Save the raw config to `reports/<space_id>/space-config.json`.
3. Save the diagnostics markdown to `reports/<space_id>/diagnostics-report.md`.
4. Tell the user the saved paths and the highest-impact recommended tuning change.

**Databricks notebook / Assistant:**
- Create a notebook cell that renders the diagnostics report with `displayHTML()` or prints the markdown string.
- Do not display the report only in chat.

## Boundaries

- Do not edit `serialized_space`.
- Do not create candidate config versions.
- Do not patch or update the Genie Space.
- Do not run benchmark evals.
- Do not change benchmark questions or benchmark answers.
- Do not mutate Databricks tables, data, schemas, functions, or views.
