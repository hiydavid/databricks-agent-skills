---
name: genie-space-optimizer
description: 'Optimize a Databricks Genie Space using benchmark-driven iterative improvement. Uses the Benchmark API to run evaluations, classify errors, apply targeted fixes, and re-benchmark until accuracy targets are met. Updates the existing space in-place with local version snapshots for rollback. Use when users want to: (1) improve Genie accuracy, (2) run benchmark evaluations, (3) fix SQL generation errors, (4) iterate on space config until accuracy targets are met, (5) optimize a Genie Space after diagnostics. Triggers on: "optimize genie space", "improve genie accuracy", "run genie benchmarks", "genie eval", "genie benchmark results", "fix genie SQL errors", "genie accuracy score", "genie optimization loop", "genie not generating correct SQL".'
---

# Genie Space Optimizer

Optimize a Databricks Genie Space using benchmark-driven iterative improvement. Runs evaluations via the Benchmark API, classifies errors, applies targeted config fixes in priority order, and re-benchmarks until the accuracy target is met. The existing space is updated in-place with local version snapshots for rollback.

## Prerequisites

**Databricks notebooks / Assistant:**
- The Databricks SDK is pre-installed and `WorkspaceClient()` authenticates automatically — no setup needed.
- Always use notebook cells for code execution. Chat responses are only for questions, progress, and analysis.

**Claude Code (local):**
1. **Databricks SDK** (v0.85+): `pip install "databricks-sdk>=0.85"`
2. **Databricks CLI profile**: Must be configured (`databricks configure`) or have environment variables set (`DATABRICKS_HOST`, `DATABRICKS_TOKEN`).

**Both environments:**
- **CAN EDIT permission** on the target Genie Space.
- **Benchmark questions** must be configured in the space (minimum 10 recommended). Run `genie-space-diagnostics` first to check.

**Output behavior:**
- Claude Code saves reports and version snapshots to `reports/<space_id>/` in the project root.
- Databricks notebooks: create and run notebook cells for all code execution and result display.

---

## Phase 1: Setup & Baseline

### Step 1: Identify the Space ID

Ask the user for the Genie Space ID — a 32-character hex string from the URL: `https://<workspace>.databricks.com/spaces/<space_id>`.

Also ask for the accuracy target (default: 80%).

### Step 2: Fetch Space Configuration

Read `scripts/fetch_space.py` for the implementation, then execute it:

- **Claude Code**: Run via bash:
  ```bash
  python scripts/fetch_space.py <space_id>
  ```
- **Databricks notebook**: Read the script, create a notebook cell with the function definition (replace `sys.exit()` with `raise`), call it, and run the cell.

Save the JSON output to `reports/<space_id>/space-config.json` (Claude Code) or keep in kernel memory (notebook).

If the code fails, check the error handling guidance in the script's docstring.

### Step 3: Save Baseline Snapshot

Save the current space config as the baseline version using `scripts/snapshot_space.py`:

- **Claude Code**:
  ```bash
  cat reports/<space_id>/space-config.json | python -c "import json,sys; config=json.load(sys.stdin); json.dump(config['serialized_space'], sys.stdout)" | python scripts/snapshot_space.py save <space_id> v0_baseline --summary "Original configuration before optimization"
  ```
- **Databricks notebook**: Read the script and create a cell that calls `save_snapshot(space_id, "v0_baseline", space_config["serialized_space"], changes_summary="Original configuration before optimization")`.

This creates `reports/<space_id>/versions/v0_baseline.json` as the rollback point.

### Step 4: Check for Diagnostics Report

Look for `reports/<space_id>/diagnostics-report.md` (Claude Code) or ask the user (notebook).

- **If found**: Load it and note the prioritized remediation items and optimizer readiness assessment. These inform which fixes to prioritize.
- **If not found**: Recommend the user run `genie-space-diagnostics` first, but continue without it.

### Step 5: Check Benchmark Count

From the fetched space config, count `serialized_space.benchmarks.questions`:

- **>= 10 questions**: Proceed to baseline eval.
- **< 10 questions**: Warn the user:
  > "This space has only X benchmark questions. For reliable optimization, 10+ diverse benchmarks are recommended (covering different tables, query patterns, and business questions). Would you like guidance on creating additional benchmarks before proceeding?"

  If the user wants to add benchmarks, help them craft question-SQL pairs based on the space's tables, existing example SQLs, and business context. The user must add these to the space manually via the Genie UI or API before continuing.

### Step 6: Run Baseline Evaluation

Read `scripts/run_eval.py` and `references/benchmark-api.md` for the implementation and API details. Execute the full eval workflow:

1. **Create eval run** — evaluate all benchmark questions:
   - **Claude Code**: `python scripts/run_eval.py create <space_id>`
   - **Notebook**: Call `create_eval_run(space_id)`.
   - Record the `eval_run_id` from the response.

2. **Poll for completion**:
   - **Claude Code**: `python scripts/run_eval.py poll <space_id> <eval_run_id>`
   - **Notebook**: Call `poll_eval_run(space_id, eval_run_id)`.
   - Report progress as it polls: "Eval running: X/Y questions completed..."
   - If status is `EVALUATION_FAILED`, `EVALUATION_CANCELLED`, or `EVALUATION_TIMEOUT`, report the error and stop.

3. **Get result summaries**:
   - **Claude Code**: `python scripts/run_eval.py results <space_id> <eval_run_id>`
   - **Notebook**: Call `get_eval_results(space_id, eval_run_id)`.

4. **Get details for failed results** — for each result where assessment is not `GOOD`:
   - **Claude Code**: `python scripts/run_eval.py details <space_id> <eval_run_id> <result_id>`
   - **Notebook**: Call `get_result_details(space_id, eval_run_id, result_id)`.

5. **Calculate baseline accuracy**:
   ```
   accuracy = num_correct / num_questions * 100
   ```
   Report: "Baseline accuracy: X% (Y/Z correct, W need review)"

Update the baseline snapshot with the accuracy score:
- Read `reports/<space_id>/versions/manifest.json`, update the `v0_baseline` entry with `"accuracy": X`, save.

---

## Phase 2: Error Classification

### Step 7: Classify Failures

Read `references/fix-taxonomy.md` for the full mapping of `assessment_reasons` to fix categories.

For each `BAD` or `NEEDS_REVIEW` result, read its `assessment_reasons` and classify into:

1. **UC Metadata errors** — wrong table/column selection, missing/wrong joins
   - Triggered by: `LLM_JUDGE_INCORRECT_TABLE_OR_FIELD_USAGE`, `LLM_JUDGE_MISSING_OR_INCORRECT_JOIN`, `RESULT_MISSING_COLUMNS`, `RESULT_EXTRA_COLUMNS`, `COLUMN_TYPE_DIFFERENCE`

2. **SQL Example errors** — wrong aggregation, function usage, incomplete output
   - Triggered by: `LLM_JUDGE_MISSING_OR_INCORRECT_AGGREGATION`, `LLM_JUDGE_INCORRECT_FUNCTION_USAGE`, `LLM_JUDGE_INCOMPLETE_OR_PARTIAL_OUTPUT`, `LLM_JUDGE_FORMATTING_ERROR`, `EMPTY_RESULT`, `RESULT_MISSING_ROWS`, `RESULT_EXTRA_ROWS`

3. **Instruction / Business Logic errors** — misinterpretation, missing business rules, wrong filters/metrics
   - Triggered by: `LLM_JUDGE_MISINTERPRETATION_OF_USER_REQUEST`, `LLM_JUDGE_INSTRUCTION_COMPLIANCE_OR_MISSING_BUSINESS_LOGIC`, `LLM_JUDGE_MISSING_OR_INCORRECT_FILTER`, `LLM_JUDGE_INCORRECT_METRIC_CALCULATION`, `LLM_JUDGE_OTHER`, `SINGLE_CELL_DIFFERENCE`

**Benchmark quality signal:** If a result has `EMPTY_GOOD_SQL`, the benchmark's expected SQL returned no rows — the benchmark itself is broken. Flag it to the user for review/removal and exclude it from fix analysis.

A single result may have reasons in multiple categories. Assign it to the **most upstream** category (UC metadata > SQL examples > Instructions).

### Step 8: Present Error Summary

Show the user a summary:

```
## Error Classification Summary

Baseline accuracy: X% (Y/Z correct)

| Category | Failed Questions | Assessment Reasons |
|----------|-----------------|-------------------|
| UC Metadata | Q3, Q7, Q12 | INCORRECT_TABLE_OR_FIELD_USAGE (2), MISSING_JOIN (1) |
| SQL Examples | Q5, Q9 | WRONG_AGGREGATION (1), INCOMPLETE_OUTPUT (1) |
| Instructions | Q1, Q15 | MISINTERPRETATION (1), MISSING_BUSINESS_LOGIC (1) |

Fix order: UC Metadata → SQL Examples → Instructions
```

If the accuracy already meets the target, inform the user and skip to Phase 4.

---

## Phase 3: Iterative Fix Loop

For each fix category **in order** (UC Metadata → SQL Examples → Instructions), if there are failures in that category:

### Step 9: Generate Config Changes

Based on the failed results in the current category, generate specific config changes. Read `references/fix-taxonomy.md` for guidance on which config paths to modify.

**Be specific** — generate actual values, not generic recommendations:
- For descriptions: write the actual description text based on the table/column context
- For synonyms: list the actual synonym values based on how users refer to the data
- For example SQLs: write the actual SQL based on the benchmark's expected SQL (but generalized)
- For instructions: write the actual instruction text addressing the specific business logic gap
- For join specs: write the actual join definition with comment and instruction

Use the expected SQL from the benchmark results as the primary source for generating fixes. The expected SQL shows exactly what Genie should have produced — reverse-engineer what config changes would guide Genie to that output.

**Config generation rules (must follow all of these):**

1. **Preserve all existing IDs** — never change or remove `id` fields already in the config.
2. **New items need 32-char lowercase hex IDs** — generate with:
   ```python
   import secrets; print(secrets.token_hex(16))
   ```
3. **These fields MUST always be arrays of strings, never bare strings:** `description`, `question`, `content`, `sql`, `synonyms`, `comment`, `instruction`, `usage_guidance`. For example: `"description": ["Some text"]`, not `"description": "Some text"`.
4. **Collections with `id`, `identifier`, or `column_name` fields must be sorted alphabetically** — this applies to tables, column_configs, join_specs, example_question_sqls, sql_snippets arrays, etc.
5. **`text_instructions`: max 1 entry** — if one already exists, append new content to its `content` array rather than creating a second entry.
6. **Never modify the `benchmarks` section** — do not add, edit, or remove benchmark questions.
7. **`config.version` must remain `2`** — do not downgrade it.
8. **Join spec `sql` must have exactly 2 elements** — `[equality_expression, relationship_type_annotation]`. The first must be a single equality expression (no `AND`/`OR`). The second must be a relationship type annotation. Example: `["orders.customer_id = customers.id", "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--"]`. Valid annotations: `--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--`, `--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--`, `--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_ONE--`, `--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_MANY--`. For multi-column joins, create separate join_spec entries.
9. **`example_question_sqls` must teach generalizable SQL patterns** — each example should demonstrate a reusable technique (e.g., window functions for ranking, CASE expressions for categorization). The `question` field should be a generic template (e.g., "What is the top N [metric] by [dimension]?"), not a specific business question.
10. **Never create examples that echo benchmarks** — do not create `example_question_sqls` whose `question` or `sql` closely matches any benchmark question or SQL. Generalize both the question AND the SQL pattern.
11. **Prefer `sql_snippets` and `text_instructions` over `example_question_sqls`** when the fix only requires teaching a specific calculation, filter pattern, or business rule. Use `example_question_sqls` only when the fix requires demonstrating a multi-step SQL pattern that cannot be captured in a snippet.

### Step 10: Present Changes for User Approval

Show proposed changes grouped by type:

```
## Proposed Changes: UC Metadata (Iteration 1)

### Data Source Changes
1. [table: catalog.schema.orders] Update description: "Daily order transactions..." (was: "orders table")
2. [column: orders.customer_id] Add synonyms: ["client ID", "buyer ID"] (was: none)
3. [column: orders.region] Enable enable_entity_matching (was: false)

### Join Spec Changes
1. Add join spec: orders ↔ customers on orders.customer_id = customers.id (MANY_TO_ONE)
   Comment: "Link orders to customer details"
   Instruction: "Use when question involves customer attributes"

Total: X changes

Approve all, modify, or skip?
```

Wait for user approval. Apply any modifications the user requests.

### Step 11: Save Pre-Change Snapshot

Before applying changes, save the current config:

```bash
# Claude Code example:
python scripts/snapshot_space.py save <space_id> v1_pre_uc_metadata --accuracy <current_accuracy> --summary "Before UC metadata fixes"
```

### Step 12: Apply Changes

1. Deep copy the current `serialized_space` dict
2. Apply all approved changes to produce the updated config
3. Save the updated config to `reports/<space_id>/updated-config.json`

4. **Validate and normalize the config before pushing:**

   - **Claude Code**:
     ```bash
     python scripts/validate_space.py reports/<space_id>/updated-config.json --normalize > reports/<space_id>/validated-config.json
     ```
   - **Notebook**: Import and call:
     ```python
     from validate_space import normalize_serialized_space, validate_serialized_space
     normalized = normalize_serialized_space(updated_config)
     result = validate_serialized_space(normalized)
     print(result["errors"], result["warnings"])
     ```

   - **If validation returns errors**: fix the issues in `updated-config.json` and re-validate. Do not push a config with errors.
   - **If validation returns only warnings**: note them, then proceed.
   - Use `validated-config.json` (normalized output) as input to `update_space.py`.

5. Apply via `scripts/update_space.py`:

   - **Claude Code**:
     ```bash
     python scripts/update_space.py <space_id> reports/<space_id>/validated-config.json
     ```
   - **Notebook**: Call `update_space(space_id, normalized_config)`.

6. Save post-change snapshot:
   ```bash
   python scripts/snapshot_space.py save <space_id> v1_uc_metadata --summary "Applied UC metadata fixes: X changes"
   ```

### Step 13: Re-Run Evaluation

Repeat Step 6 (create eval run, poll, get results, get details for failures).

### Step 14: Report Accuracy Delta

```
## Iteration 1 Results: UC Metadata Fixes

Accuracy: X% → Y% (+Z%)
Changes applied: N
Questions fixed: Q3, Q12
Questions still failing: Q7 (now classified as SQL Example error)
New failures: none
```

### Step 15: Decision Point

- **Accuracy >= target**: Proceed to Phase 4 (Wrap-Up).
- **Accuracy improved, more categories remain**: Move to next category (SQL Examples → Instructions).
- **Accuracy regressed**: Alert the user. Offer to rollback:
  > "Accuracy dropped from X% to Y%. The last batch of changes may have had unintended effects. Would you like to rollback to the previous version (v1_pre_uc_metadata) and try a different approach?"
  
  If rollback:
  ```bash
  python scripts/snapshot_space.py restore <space_id> v1_pre_uc_metadata
  ```
- **All categories exhausted, accuracy < target**: Present remaining failures with analysis. Recommend manual review or additional benchmark questions.

**Repeat Steps 9-15 for each remaining category.**

---

## Phase 4: Wrap-Up

### Step 16: Generate Optimization Report

```markdown
# Optimization Report: <space_title>

**Space ID:** `<space_id>`
**Date:** <YYYY-MM-DD>
**Workspace:** `<workspace_host>`

## Accuracy Progression

| Version | Accuracy | Changes | Category |
|---------|----------|---------|----------|
| v0_baseline | X% | — | Baseline |
| v1_uc_metadata | Y% (+Z%) | N changes | UC Metadata |
| v2_sql_examples | W% (+V%) | M changes | SQL Examples |
| v3_instructions | U% (+T%) | P changes | Instructions |

**Final accuracy: U% (target: 80%)**

## Changes Applied

### Iteration 1: UC Metadata (X changes)
1. ...

### Iteration 2: SQL Examples (Y changes)
1. ...

### Iteration 3: Instructions (Z changes)
1. ...

## Remaining Failures

| Question | Assessment | Reasons | Recommendation |
|----------|-----------|---------|----------------|
| ... | BAD | ... | ... |

## Version History

All snapshots are stored in `reports/<space_id>/versions/`. To rollback:
  ```bash
  python scripts/snapshot_space.py restore <space_id> <version_name>
  ```

To compare versions:
  ```bash
  python scripts/snapshot_space.py diff <space_id> v0_baseline v3_instructions
  ```

Available versions:
<list from manifest.json>
```

### Step 17: Save Report

- **Claude Code**: Save to `reports/<space_id>/optimization-report.md`.
- **Databricks notebook**: Render in a notebook cell via `displayHTML()`.
