---
name: databricks-genie-improve
description: "Use for this repo's Databricks Genie improvement loop: fetch and version serialized_space configs, make config-only quality changes, validate schema and benchmark integrity, update a Genie space, run benchmark evals, pull normalized reports, compare accuracy, and analyze failures."
---

# Databricks Genie Improve

Use this skill for iterative Databricks Genie space improvement in this repo. Run commands from the repo root so relative paths resolve to the project directories below. The default Databricks CLI profile is `fevm-test` unless the user explicitly specifies another profile.

## Project Directories

- `genie_configs/`: versioned decoded `serialized_space` JSON files.
- `fix_plan/`: user-readable quality-improvement plans and decision records.
- `results/`: normalized benchmark reports, eval details, and accuracy comparisons.

## Hard Rules

- Never change underlying Databricks tables, views, metric views, data, or schemas.
- Do not change benchmark questions or benchmark answers as part of Genie tuning. Benchmark questions and answers may change only in a dedicated benchmark bootstrap or repair config version after the changes are documented and SQL answers are validated with read-only inspection.
- Use only read-only Databricks SQL for inspection.
- Use the available Databricks SQL execution capability for exploratory analysis that inspects Databricks tables, views, metric views, schemas, sample values, joins, or metric behavior. In external coding agents, this is usually the DBSQL MCP; in Genie Code, use native DBSQL access.
- You may edit Genie serialized-space metadata for existing tables, views, or metric views, but you must not create, alter, export, or mutate Unity Catalog metric views.
- Keep all Genie changes in versioned decoded `serialized_space` JSON files under `genie_configs/`.
- Before creating or editing a new config version, write the intended changes in `fix_plan/genie_<version>_quality_improvement_plan.md`.
- Every tuning pass must name the target failure cluster and repair lever before editing JSON. Prefer one cluster or a small set of related clusters per version so regressions are attributable.
- Do not copy benchmark questions or benchmark answer SQL into sample questions, SQL snippets, or example SQL.
- Use simple report filenames such as `results/v0_benchmark_report.json`; do not put eval run IDs in report filenames.
- Benchmark eval runs are asynchronous. Immediately after `create-eval-run`, `genie-list-eval-results` can return zero results while the benchmark is still running. Do not treat a zero-result report as complete, do not compare it, and do not report accuracy from it.
- Before the first optimization pass and before interpreting baseline accuracy, review benchmark question and answer quality. If fewer than 30 valid benchmark Q/A pairs remain after excluding invalid answers, pause config tuning, create a benchmark bootstrap or repair config version with enough validated Q/A pairs to bring the reviewed set to at least 30, update the Genie space with it, and run a new baseline eval.
- Before editing or pushing config JSON, read `references/serialized-space.md`.
- Before creating eval runs or pulling reports, read `references/evals-and-reports.md`.
- Before analyzing failures or proposing changes, read `references/quality-tuning.md`.

## Exploratory Analysis With Databricks SQL

When benchmark failure analysis requires live data, data-source, or schema inspection, use the available Databricks SQL execution capability to run exploratory queries before proposing config changes. In external coding agents, this is usually the DBSQL MCP; in Genie Code, use native DBSQL access. Keep these queries read-only and bounded:

- Allowed: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema` queries.
- Not allowed: DDL, DML, `CREATE`, `ALTER`, `DROP`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, or any table/view/metric-view/schema/data mutation.
- Prefer explicit `LIMIT`s for row samples and targeted aggregate checks for cardinality, null rates, categorical values, join grain, and metric definitions.
- Use Databricks SQL findings to support the fix plan, then make only serialized-space config edits under `genie_configs/`.

## Workflow

1. Fetch the current decoded config:

   ```bash
   python3 .agents/skills/databricks-genie-improve/scripts/genie_loop.py save-config --space-id <id> --version v0 --profile fevm-test
   ```

2. Review the benchmark dataset before tuning. Confirm at least 30 valid question/answer pairs, check diversity and challenge level, and flag invalid ground-truth SQL using `references/quality-tuning.md` and `references/evals-and-reports.md`.

   If the benchmark is too small, too simple, not diverse, or contains invalid answer SQL, document affected question IDs and weak coverage areas in the fix plan. Then use read-only data-source/schema inspection to author validated benchmark Q/A additions or replacements in a new config version. Do not mix benchmark bootstrap or repair changes with Genie tuning changes in the same config version.

   Validate an intentional benchmark bootstrap or repair config with:

   ```bash
   python3 .agents/skills/databricks-genie-improve/scripts/genie_loop.py validate-config --config genie_configs/<id>_v1.json --previous-config genie_configs/<id>_v0.json --allow-benchmark-changes
   ```

   After validation passes, update the Genie space with the benchmark config, run an eval, and pull a versioned report. Treat that report as the baseline for the first tuning pass.

3. Analyze the prior version's report, for example `results/v0_benchmark_report.json`, and write the user-facing decision record before editing config:

   ```text
   fix_plan/genie_v1_quality_improvement_plan.md
   ```

   Do not patch directly from aggregate accuracy. Create the repair plan with:

   - input report path and baseline accuracy summary;
   - benchmark validity exclusions for invalid expected SQL, stale questions, permissions, API, warehouse, or incomplete-eval issues;
   - separate repair triage for `BAD` and `NEEDS_REVIEW` questions;
   - failure clusters with evidence from generated SQL, expected SQL, actual results, and assessment notes when available;
   - the chosen target cluster for this pass;
   - the smallest structured serialized-space repair lever;
   - proactive enrichment checks considered;
   - affected question IDs for targeted eval when practical;
   - related previous-good regression questions to watch;
   - acceptance criteria for keep, revise, or roll back.

4. Copy the latest config to the next version manually, for example `genie_configs/<space_id>_v1.json`, and make only the config-level Genie tuning edits described in the fix plan.

5. Validate before update:

   ```bash
   python3 .agents/skills/databricks-genie-improve/scripts/genie_loop.py validate-config --config genie_configs/<id>_v1.json --previous-config genie_configs/<id>_v0.json
   ```

6. Update the Genie space after validation passes:

   ```bash
   python3 .agents/skills/databricks-genie-improve/scripts/genie_loop.py update-space --space-id <id> --config genie_configs/<id>_v1.json --profile fevm-test
   ```

7. Create the narrowest useful eval run:

   ```bash
   python3 .agents/skills/databricks-genie-improve/scripts/genie_loop.py create-eval-run --space-id <id> --profile fevm-test
   ```

   When a candidate targets a known failure cluster, first run an affected-question slice when practical:

   ```bash
   python3 .agents/skills/databricks-genie-improve/scripts/genie_loop.py create-eval-run --space-id <id> --benchmark-question-id <question_id> --profile fevm-test
   ```

   Repeat `--benchmark-question-id` for multiple affected or regression questions. Then run a small related regression slice of previous-good questions if feasible. Run the full benchmark after the targeted checks look acceptable, or immediately if subset eval is unavailable or not representative. Document the gate used in the fix plan.

   Save the returned eval run ID. The command submits the benchmark; it does not mean results are immediately available.

8. Pull normalized versioned reports. `pull-report` waits by default, polling until Databricks returns eval results instead of saving an empty report:

   ```bash
   python3 .agents/skills/databricks-genie-improve/scripts/genie_loop.py pull-report --space-id <id> --eval-run-id <run_id> --version v1 --profile fevm-test
   ```

   If zero results are returned after the wait timeout, treat the benchmark as still running or misconfigured and inspect the run before comparing reports.

9. Compare accuracy between versions:

   ```bash
   python3 .agents/skills/databricks-genie-improve/scripts/genie_loop.py compare-reports --baseline results/v0_benchmark_report.json --candidate results/v1_benchmark_report.json --out results/v0_to_v1_accuracy_comparison.json
   ```

10. Append validation, deployment, eval run, versioned report, measured accuracy, comparison, invalid-answer exclusions, question-level movement, acceptance decision, and regression notes to the same fix plan.

11. Before starting another repair iteration, read the prior plan's iteration reflection. Avoid repeating a lever that already failed for the same root cause unless new evidence explains why it should work now.

## Tuning Guidance

Analyze failures using benchmark `assessment_reasons`, generated SQL, and expected SQL. Use `references/quality-tuning.md` to classify failures, cluster root causes, and choose the smallest config-only intervention that addresses the shared failure cause:

First inspect `data_sources.tables` and `data_sources.metric_views` in the decoded serialized space. A space can be table-backed, metric-view-backed, or contain both serialized collections; tune the actual configured source type instead of assuming tables. For metric-view-backed spaces, prefer existing metric view measures, dimensions, descriptions, synonyms, and agent metadata before adding broad instructions.

- data-source and column metadata for wrong table, metric view, or column failures
- `enable_format_assistance` and `enable_entity_matching` for categorical value confusion
- `instructions.join_specs` for missing or incorrect joins
- `instructions.sql_snippets` for reusable measures, filters, dimensions, and business logic
- `instructions.example_question_sqls` only for representative complex patterns, never copied from benchmark questions or answers
- `instructions.text_instructions` only for concise global behavior that cannot be encoded structurally

Do not use `instructions.text_instructions` as a catch-all rulebook. If a proposed text instruction names specific tables, metric views, columns, joins, filters, denominators, numerators, aliases, ranking logic, or window logic, first move that guidance into metadata, join specs, SQL snippets, or example SQL. Keep only true global behavior in text instructions, document why it could not be encoded structurally, and format it with the section template in `references/quality-tuning.md`.

Treat `NEEDS_REVIEW` separately from `BAD`, and compare per-question regressions after each candidate config update.
