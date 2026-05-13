---
name: genie-space-diagnostics
description: "Diagnose Databricks Genie Space quality problems and produce a concrete tuning plan. Use when users ask why a Genie Space cannot answer a question consistently, gives wrong SQL, chooses wrong tables or columns, mishandles filters or joins, or needs a configuration health check before optimization. This skill is plan-only: it may fetch/read space configuration and perform bounded read-only SQL inspection, but it must not edit serialized_space, update a Genie Space, run benchmark evals, or mutate Databricks data."
---

# Genie Space Diagnostics

Diagnose Genie Space quality problems and produce a concrete tuning plan. The default workflow is **question-level tuning triage**: start from a failing user question, gather evidence from the serialized space and read-only data inspection, classify the likely failure mode, and recommend the smallest useful Genie configuration change.

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
- Local coding agents save reports to `reports/<space_id>/` in the project root.
- Databricks notebooks render the report in notebook output with `displayHTML()` or printed markdown.

## Step 1: Establish The Tuning Case

Ask for any missing inputs that materially affect diagnosis:

- Genie Space ID, a 32-character hex string from the space URL.
- Failing question, exactly as the user asks it.
- Observed bad behavior: wrong table, wrong column, wrong filter value, missing join, wrong metric, inconsistent answers, SQL error, empty answer, or unclear.
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

- `references/tuning-diagnosis.md` for failure classification and tuning-surface routing.
- `references/best-practices-checklist.md` for supporting static health checks.
- `references/space-schema.md` when field shapes, version-specific names, or validation rules matter.

## Step 4: Inspect Evidence

### 4a: Serialized Space Evidence

Use the fetched `serialized_space` to identify:

- candidate tables, columns, metric views, and descriptions related to the failing question
- relevant synonyms, `enable_format_assistance`, and `enable_entity_matching` flags
- existing join specs for tables implicated by the question
- SQL snippets for reusable measures, filters, and expressions
- example SQLs that might help or conflict with the question pattern
- text instructions that define global conventions or contain overly specific logic
- benchmark questions that cover similar intent, if any

Prefer concrete evidence: table names, column names, field values, instruction text, snippet names, and benchmark IDs.

### 4b: Read-Only SQL Inspection

Use the DBSQL MCP, Databricks SQL, or notebook SQL cells for read-only SQL only when the serialized config is insufficient to determine the likely cause. Keep inspection targeted and bounded.

Allowed SQL:

- `SELECT`
- `WITH`
- `SHOW`
- `DESCRIBE`
- `EXPLAIN`
- `information_schema` queries

Not allowed:

- `CREATE`, `ALTER`, `DROP`, `TRUNCATE`
- `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`
- table/schema/data mutation of any kind

Use read-only SQL for:

- confirming candidate column names and data types
- checking distinct categorical values and case/format mismatches
- checking null rates, row counts, and cardinality
- sampling a small number of rows with explicit `LIMIT`
- validating join keys and join grain
- understanding metric definitions when expected SQL or business rules are provided

Record the SQL purpose and findings in the report. Do not include broad exploratory dumps.

## Step 5: Classify The Failure

Choose one primary failure class, plus secondary contributors if needed:

- **Wrong table or column**: Genie selects a similarly named but incorrect source or omits a required field.
- **Wrong filter value**: Genie uses a label, code, casing, date boundary, or categorical value that does not match stored data.
- **Wrong join**: Genie misses a table, joins through the wrong key, or changes grain/cardinality.
- **Metric or business logic error**: Genie calculates the wrong numerator, denominator, aggregation, ratio, or reusable business concept.
- **Time logic error**: Genie uses the wrong period, boundary, date grain, fiscal convention, or rolling-window logic.
- **Result shape error**: Genie returns the right concept with wrong columns, aliases, granularity, ranking, ordering, or limit.
- **Instruction conflict or overload**: text instructions, examples, snippets, or benchmark SQL conflict or dilute the intended behavior.
- **Insufficient benchmark coverage**: no benchmark or only weak benchmark coverage for the question pattern.
- **Unknown from static evidence**: evidence is insufficient; state exactly what additional result SQL, expected SQL, or eval report is needed.

## Step 6: Recommend Tuning Changes

Recommend the smallest structured Genie configuration change that addresses the failure. Use this routing order:

1. Table or column descriptions, synonyms, and hidden columns for table/column ambiguity.
2. `enable_format_assistance` and `enable_entity_matching` for categorical value, formatting, or stored-value mismatch.
3. `instructions.join_specs` for missing or incorrect joins.
4. `instructions.sql_snippets` for reusable measures, filters, dimensions, and business expressions.
5. `instructions.example_question_sqls` for representative complex patterns, multi-step logic, ranking, windows, or result shape.
6. `instructions.text_instructions` only for concise global conventions that cannot be encoded structurally.

Do not recommend copying the failing question or benchmark answer verbatim into example SQL. Example SQL should teach a representative pattern, not memorize a test.

For every recommended change, include:

- the target config surface
- exact table, column, join, snippet, example, or instruction target
- the proposed wording or JSON-level intent
- why this is the smallest appropriate intervention
- how the user should validate it after implementation

## Step 7: Run Static Space Health Checks

Use `references/best-practices-checklist.md` as supporting evidence after the question-level diagnosis. Evaluate the health checks most relevant to the failure first, then summarize broader issues:

- data source scope and metadata
- column descriptions, synonyms, format assistance, entity matching, and hidden noisy columns
- text instruction focus
- example SQL coverage and diversity
- join specs and comments
- SQL snippets for reusable filters, expressions, and measures
- benchmark count, static answer shape, and pattern coverage
- sample question quality

Do not let a generic checklist item outrank a concrete finding about the failing question.

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
| Confidence | High / Medium / Low |

## Evidence From Serialized Space

- ...

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
| Benchmark count | pass/fail/warning | X questions; 30+ valid Q/A pairs recommended before benchmark-driven tuning |
| Benchmark answer shape | pass/fail/warning | X questions have exactly one SQL answer |
| Benchmark diversity | pass/warning | Coverage across tables, joins, metrics, filters, time logic, and result shapes |
| Critical static failures resolved | pass/warning | X issues should be addressed before optimization |

**Verdict:** Ready / Needs Work / Not Ready

## Handoff To Optimization

- Recommended next skill: `optimize-genie-space` when the user is ready to make versioned config edits, update the space, run evals, and compare accuracy.
- Suggested first optimization task: ...
```

## Step 9: Save Report

**Claude Code / local coding agents:**
1. Create `reports/<space_id>/` in the user's project root if needed.
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
