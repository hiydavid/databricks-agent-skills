---
name: optimize-genie-space
description: "Optimize Databricks Genie Space quality from an external coding agent through versioned serialized_space edits and benchmark evaluation loops. Use when users want to fetch and version a Space config, make reviewed config-only quality changes, validate schema and benchmark integrity, run Chat-mode benchmark evals, pull normalized reports, compare accuracy across versions, and iterate toward an accuracy target. For plan-only read-only diagnosis use diagnose-genie-space; for authoring a new Space config use create-genie-space."
---

# Optimize Genie Space

Improve a Genie Space by turning failed benchmark evidence into the smallest structured configuration change, then re-measuring with benchmark evaluation. This skill drives the loop with the bundled helper script and keeps versioned artifacts in local files.

## Workspace Setup

Before the first command, establish three things with the user:

1. **Workspace folder.** Versioned artifacts live in a user-approved local folder. Create it if needed and run all script commands from that folder so relative paths resolve:
   - `genie_configs/`: versioned decoded `serialized_space` JSON files.
   - `fix_plan/`: user-readable quality-improvement plans and decision records.
   - `results/`: normalized benchmark reports, eval details, and accuracy comparisons.
2. **Script location.** Invoke the helper as `python3 <skill-dir>/scripts/genie_loop.py ...`, resolving `<skill-dir>` to wherever this skill is installed (for example `.claude/skills/optimize-genie-space` or `~/.codex/skills/optimize-genie-space`).
3. **Databricks CLI profile.** Use the user's configured default CLI profile by omitting `--profile`. Pass `--profile <name>` only when the user specifies one or the configured default is ambiguous; ask if unclear.

## Optimization Mode: Single Pass vs Iterative

**Single-pass mode (default).** Run one pass: review benchmarks, establish a baseline, triage failures, apply one approved edit, re-evaluate, then report keep / revise / roll back and stop. Ask for approval before each mutating action.

**Iterative mode (only when the user asks for a loop).** Capture the loop rules up front before iterating:

- target score and the valid denominator it is measured against (e.g. "≥90% GOOD on the Chat-mode benchmark over valid questions");
- pass budget (max iterations);
- allowed edit surfaces;
- stop conditions: target reached, benchmark unrecoverable, or no progress;
- the workspace folder for rollback snapshots and history.

In iterative mode, repeat the workflow until a stop condition is met, carrying minimal state across passes (score trajectory, attempted clusters/levers, a do-not-repeat list, rollback references, next hypothesis) and reading prior fix-plan reflections before each triage. Stop and escalate to the user when: the target is reached; there are N consecutive non-improving passes (plateau — default 3 unless the user sets otherwise); the score oscillates (freeze the last-known-good config); the same cluster keeps failing with no new evidence; or the budget is exhausted.

**Approval.** Single-pass mode keeps per-action approval gates. Iterative mode takes one up-front approval covering scope, target, budget, allowed edit surfaces, workspace folder, and rollback policy; after that, run without pausing per edit, but still pause on any escalation trigger above, on benchmark-definition changes, and on anything outside the approved edit surfaces.

## Benchmark Execution Modes

Benchmark questions are shared definitions; the execution mode determines how Genie scores a run:

- **Chat mode** compares Genie's generated SQL/result set against the checked SQL answer. The `genie_loop.py` eval automation (`create-eval-run`, `pull-report`, `compare-reports`) applies to Chat-mode runs.
- **Agent mode** runs multi-step Agent reasoning graded by an LLM judge and, per Databricks docs, can only be launched and read through the Databricks UI (no API). For Agent-mode benchmarks, ask the user to launch runs in the UI and paste or export the per-question output; record it in the fix plan and compare it separately from Chat accuracy instead of collapsing both into one score.

See `references/evals-and-reports.md` for mode-specific field strategy (checked SQL answers vs evaluation notes), benchmark sufficiency, repair, and pruning.

## Hard Rules

- Never change underlying Databricks tables, views, metric views, data, or schemas.
- Genie has no native config versioning or rollback. Before any Space/config or benchmark-definition edit, capture a rollback snapshot of the current live config with `save-config` (for example `--version vN_rollback`) into `genie_configs/`. Do not proceed with an edit if the snapshot cannot be captured, and record the snapshot reference in the fix plan and acceptance decision.
- Do not change benchmark questions or benchmark answers as part of Genie tuning. Benchmark questions and answers may change only in a dedicated benchmark bootstrap, repair, or pruning config version after the changes are documented and SQL answers are validated with read-only inspection.
- Use only read-only Databricks SQL for inspection. In external coding agents, this is usually the DBSQL MCP; in Databricks notebooks or Genie Code, use native DBSQL access.
- You may edit Genie serialized-space metadata for existing tables, views, or metric views, but you must not create, alter, export, or mutate Unity Catalog metric views.
- Keep all Genie changes in versioned decoded `serialized_space` JSON files under `genie_configs/`.
- Before creating or editing a new config version, write the intended changes in `fix_plan/genie_<version>_quality_improvement_plan.md`.
- Every tuning pass must name the target failure cluster and repair lever before editing JSON. Prefer one cluster or a small set of related clusters per version so regressions are attributable. Never mix benchmark repair or pruning with Genie tuning in the same pass.
- Do not copy benchmark questions, benchmark answer SQL, or evaluation notes into sample questions, SQL snippets, example SQL, or any other config surface (benchmark leakage).
- Use simple report filenames such as `results/v0_benchmark_report.json`; do not put eval run IDs in report filenames.
- Benchmark eval runs are asynchronous. Immediately after `create-eval-run`, result listing can return zero results while the benchmark is still running. Do not treat a zero-result report as complete, do not compare it, and do not report accuracy from it.
- Review benchmark sufficiency and quality before the first pass and before interpreting baseline accuracy (`references/evals-and-reports.md` → Benchmark Sufficiency And Valid Denominator). If the valid set is insufficient, pause config tuning and run a dedicated benchmark bootstrap or repair version first.
- Before editing or pushing config JSON, read `references/serialized-space.md`.
- Before creating eval runs or pulling reports, read `references/evals-and-reports.md`.
- Before analyzing failures or proposing changes, read `references/quality-tuning.md`.

## Exploratory Analysis With Databricks SQL

When benchmark failure analysis requires live data, data-source, or schema inspection, run exploratory read-only queries before proposing config changes. Keep these queries bounded:

- Allowed: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema` queries.
- Not allowed: DDL, DML, `CREATE`, `ALTER`, `DROP`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, or any table/view/metric-view/schema/data mutation.
- Prefer explicit `LIMIT`s for row samples and targeted aggregate checks for cardinality, null rates, categorical values, join grain, and metric definitions.
- Use Databricks SQL findings to support the fix plan, then make only serialized-space config edits under `genie_configs/`.

## Workflow

1. Capture the rollback snapshot and current decoded config (this is also the mandatory pre-edit snapshot):

   ```bash
   python3 <skill-dir>/scripts/genie_loop.py save-config --space-id <id> --version v0
   ```

2. Review the benchmark dataset before tuning using `references/evals-and-reports.md` (execution mode, sufficiency, valid denominator, difficulty and coverage) and `references/quality-tuning.md`. If the benchmark is too small, too simple, not diverse, oversized and redundant, or contains invalid answer SQL, document affected question IDs and weak coverage areas in the fix plan, then run a dedicated benchmark bootstrap, repair, or pruning config version first. Do not mix benchmark changes with Genie tuning changes in the same config version.

   Validate an intentional benchmark bootstrap, repair, or pruning config with:

   ```bash
   python3 <skill-dir>/scripts/genie_loop.py validate-config --config genie_configs/<id>_v1.json --previous-config genie_configs/<id>_v0.json --allow-benchmark-changes
   ```

   After validation passes, update the Genie space with the benchmark config, run an eval, and pull a versioned report. Treat that report as the baseline for the first tuning pass.

3. Analyze the prior version's report, for example `results/v0_benchmark_report.json`, and write the user-facing decision record before editing config:

   ```text
   fix_plan/genie_v1_quality_improvement_plan.md
   ```

   Do not patch directly from aggregate accuracy. Create the repair plan with:

   - input report path and baseline accuracy summary;
   - benchmark execution target (Chat, Agent, or mixed) and field strategy;
   - benchmark validity exclusions for invalid expected SQL, stale questions, permissions, API, warehouse, or incomplete-eval issues;
   - separate repair triage for `BAD` and `NEEDS_REVIEW` questions;
   - failure clusters with evidence from generated SQL, expected SQL, actual results, and assessment notes when available;
   - the chosen target cluster for this pass;
   - the smallest structured serialized-space repair lever;
   - proactive enrichment checks considered;
   - affected question IDs for targeted eval when practical;
   - related previous-good regression questions to watch;
   - rollback snapshot reference;
   - acceptance criteria for keep, revise, or roll back.

4. Copy the latest config to the next version manually, for example `genie_configs/<space_id>_v1.json`, and make only the config-level Genie tuning edits described in the fix plan.

5. Validate before update:

   ```bash
   python3 <skill-dir>/scripts/genie_loop.py validate-config --config genie_configs/<id>_v1.json --previous-config genie_configs/<id>_v0.json
   ```

6. Update the Genie space after validation passes:

   ```bash
   python3 <skill-dir>/scripts/genie_loop.py update-space --space-id <id> --config genie_configs/<id>_v1.json
   ```

7. Create the narrowest useful eval run (Chat mode):

   ```bash
   python3 <skill-dir>/scripts/genie_loop.py create-eval-run --space-id <id>
   ```

   When a candidate targets a known failure cluster, first run an affected-question slice when practical:

   ```bash
   python3 <skill-dir>/scripts/genie_loop.py create-eval-run --space-id <id> --benchmark-question-id <question_id>
   ```

   Repeat `--benchmark-question-id` for multiple affected or regression questions. Then run a small related regression slice of previous-good questions if feasible. Run the full benchmark after the targeted checks look acceptable, or immediately if subset eval is unavailable or not representative. Document the gate used in the fix plan. For Agent-mode benchmarks, run the equivalent subset in the UI instead.

   Save the returned eval run ID. The command submits the benchmark; it does not mean results are immediately available.

8. Pull normalized versioned reports. `pull-report` waits by default, polling until Databricks returns eval results instead of saving an empty report:

   ```bash
   python3 <skill-dir>/scripts/genie_loop.py pull-report --space-id <id> --eval-run-id <run_id> --version v1
   ```

   If zero results are returned after the wait timeout, treat the benchmark as still running or misconfigured and inspect the run before comparing reports.

9. Compare accuracy between versions:

   ```bash
   python3 <skill-dir>/scripts/genie_loop.py compare-reports --baseline results/v0_benchmark_report.json --candidate results/v1_benchmark_report.json --out results/v0_to_v1_accuracy_comparison.json
   ```

10. Append validation, deployment, eval run, versioned report, measured accuracy, comparison, invalid-answer exclusions, question-level movement, the acceptance decision (keep / revise / roll back, with rollback snapshot reference — template in `references/evals-and-reports.md`), and regression notes to the same fix plan.

11. Before starting another repair iteration, read the prior plan's iteration reflection. Avoid repeating a lever that already failed for the same root cause unless new evidence explains why it should work now. In iterative mode, update cross-pass state and check the stop conditions before the next pass.

## Tuning Guidance

Analyze failures using benchmark `assessment_reasons`, generated SQL, and expected SQL. Use `references/quality-tuning.md` to classify failures, cluster root causes, and choose the smallest config-only intervention that addresses the shared failure cause.

First inspect `data_sources.tables` and `data_sources.metric_views` in the decoded serialized space. A space can be table-backed, metric-view-backed, or contain both serialized collections; tune the actual configured source type instead of assuming tables. For metric-view-backed spaces, prefer existing metric view measures, dimensions, descriptions, synonyms, and agent metadata before adding broad instructions. If the root cause is an incorrect or missing Unity Catalog metric view definition, document it as an upstream semantic-layer issue and recommend fixing it upstream (for example with a metric-view authoring skill when available) instead of working around it in the Space.

Do not use `instructions.text_instructions` as a catch-all rulebook. If a proposed text instruction names specific tables, metric views, columns, joins, filters, denominators, numerators, aliases, ranking logic, or window logic, first move that guidance into metadata, join specs, SQL snippets, or example SQL. Keep only true global behavior in text instructions, document why it could not be encoded structurally, and format it with the section template in `references/quality-tuning.md`.

Treat `NEEDS_REVIEW` separately from `BAD`, and compare per-question regressions after each candidate config update.

## Related Skills

- `diagnose-genie-space` — plan-only, read-only root-cause diagnosis of Genie Space quality problems. Run it upstream to understand *why* answers fail before optimizing; it hands off here for versioned edits and eval loops.
- `create-genie-space` — author and validate a new `serialized_space` config when there is no Space to optimize yet.
- Metric-view authoring (for example the `create-metric-view` skill, when available) — when a failure traces to a Metric View's own definition, fix or define the Metric View upstream rather than patching around it in the Space.
- Query optimization (for example the `optimize-genie-query` skill, when available) — tunes a single slow Genie query, not Space-wide configuration. Use this skill for Space-level, benchmark-driven optimization.
