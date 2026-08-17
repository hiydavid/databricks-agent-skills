# Genie Benchmark Evaluation Runs

Reference docs:

- Genie CLI command group: https://docs.databricks.com/gcp/en/dev-tools/cli/reference/genie-commands
- Databricks SDK Genie API: https://databricks-sdk-py.readthedocs.io/en/stable/workspace/dashboards/genie.html
- Benchmark concepts and UI workflow: https://docs.databricks.com/aws/en/genie/benchmarks

Run all helper-script commands from the established workspace folder. Omit `--profile` to use the configured default Databricks CLI profile; pass `--profile <name>` only when the user specifies one.

## Benchmark Execution Modes

Benchmark questions are shared definitions (Databricks documents up to 500 per Space); the execution mode chosen for a run determines how Genie scores them:

- **Chat mode** compares Genie's SQL-generated result set against a provided SQL answer. Only questions that include a checked SQL answer can be scored automatically; questions without one require manual review. Manual review can also be needed when results do not exactly match the SQL answer or Genie cannot assess correctness.
- **Agent mode** (Public Preview) runs the question with Genie's multi-step Agent reasoning and grades the response with an LLM judge; an optional evaluation note is passed to the judge. Per Databricks docs, Agent mode is available through the Databricks UI only — there is no API — so Agent-mode benchmark runs are launched and read in the UI, not through `genie_loop.py`.

Choose the execution target — Chat, Agent, or mixed — from the user's goal, existing SQL answers, evaluation notes, and the latest eval output. Per-question field strategy:

- `single_sql_answer`: deterministic tabular question; add a checked SQL answer. Do not count the question as valid until the SQL is checked.
- `deterministic_with_response_quality`: add checked SQL and an evaluation note when Chat correctness and Agent response quality both matter.
- `multi_step_agent_analysis`: add an evaluation note only when the question requires multiple investigative queries, synthesis, caveats, citations, or supporting tables rather than one canonical result set.
- `ambiguous_or_unverifiable`: ask the user for expected behavior before adding or repairing the question.

Benchmarks are evaluation-only: Genie does not use benchmark questions or answer SQL to improve its context. Never feed benchmark content back into Space configuration.

## Important Preconditions

Benchmark eval runs require benchmark questions in the Genie space. In serialized config JSON, those live at:

```text
benchmarks.questions
```

List benchmark question IDs from a local config:

```bash
jq -r '.benchmarks.questions[]? | [.id, .question] | @tsv' genie_configs/<space_id>_v<version>.json
```

## Ground-Truth SQL Triage

Benchmark answer SQL is ground truth for scoring. Invalid ground truth must be handled as a benchmark issue, not as a Genie tuning target.

- If benchmark answer SQL errors during a benchmark run or read-only verification, classify the affected question as a benchmark-ground-truth issue.
- Do not tune Genie to match invalid SQL, stale business logic, missing data sources or columns, or SQL that cannot execute.
- When possible, verify the issue with read-only SQL inspection only. Do not mutate tables, views, metric views, schemas, benchmark questions, or benchmark answers.
- Record the benchmark question ID, observed error, verification notes, and recommended benchmark-owner correction in `fix_plan/genie_<version>_quality_improvement_plan.md`.
- Exclude invalid-answer questions from accuracy interpretation and regression counts. Do not count them as Genie failures or regressions.
- If exclusions drop the valid set below the sufficiency minimum (see Benchmark Sufficiency And Valid Denominator), treat the benchmark as insufficient for config tuning and run a dedicated benchmark bootstrap or repair config version before continuing.

## Benchmark Sufficiency And Valid Denominator

This section is the canonical statement of the benchmark sufficiency rule; other files reference it instead of restating it.

**Minimum bar.** This skill's working minimum is at least 30 valid benchmark questions for the target execution mode before benchmark-driven tuning (a skill convention, not a product limit). A Chat-mode question counts as valid only when it has exactly one SQL answer and there is no evidence that the answer SQL is invalid or errors during evaluation or read-only verification. An Agent-mode question counts as valid when it is clear and, where grading guidance is needed, has a sound evaluation note.

Use only valid, completed benchmark results when interpreting tuning accuracy. Exclude these from the tuning denominator and regression counts:

- invalid expected SQL or stale benchmark answers;
- benchmark questions that no longer match the current data model;
- incomplete or missing eval output;
- permission, API, warehouse, or platform failures;
- questions with insufficient evidence to decide whether Genie tuning caused the failure.

Keep exclusions explicit in the fix plan and comparison notes. Do not count invalid benchmark or infra failures as Genie repair targets. If exclusions leave fewer than 30 valid Q/A pairs, pause Genie config tuning and do benchmark repair or expansion first.

Also review difficulty and coverage before trusting the baseline:

- Cover multiple entities, metrics, dimensions, filters, joins, time windows, aggregation grains, ranking/window patterns, answer shapes, and business concepts that real users will ask about.
- Difficulty rubric — easy: direct lookup, simple count, single-table filter, no business logic. Medium: reusable metric/filter, categorical mapping, date condition, grouping, basic aggregation, Metric View measure selection. Hard: joins, grain handling, ratios, conditional aggregation, ranking/top-N, rolling/window logic, multi-step business logic, result-shape constraints, Agent-style synthesis.
- Prefer a meaningful mix of medium and hard questions. A benchmark dominated by easy questions is insufficient for tuning even when it has 30 valid questions.
- Flag low diversity when questions cluster around the same table, metric, phrasing, join path, filter type, or SQL pattern, or when variants only swap a date or category literal.

## Benchmark Repair

Use benchmark repair when fewer than 30 valid questions remain for the target execution mode, expected SQL is invalid or stale, evaluation notes are missing or unclear for Agent-style questions, questions are duplicate or trivial, the benchmark is too easy, or coverage is too narrow.

1. Write the benchmark review and intended additions or replacements in `fix_plan/genie_<version>_quality_improvement_plan.md`. For each added, replaced, or retained question, record: question text; field strategy (SQL, evaluation note, or both); expected SQL and validation notes when SQL is appropriate; evaluation note when Agent execution needs grading guidance; difficulty level; coverage category; referenced tables, metric views, and columns; whether it adds coverage or replaces an invalid, stale, duplicate, or trivial question.
2. Capture a rollback snapshot of the current live config with `save-config` before editing benchmark definitions.
3. Copy the latest config to the next version, for example `genie_configs/<space_id>_v1.json`.
4. Edit only `benchmarks.questions` in that version. Keep IDs valid and sort benchmark questions by `id`.
5. Validate expected SQL answers with read-only DBSQL inspection when possible.
6. Validate the config with:

   ```bash
   python3 <skill-dir>/scripts/genie_loop.py validate-config --config genie_configs/<space_id>_v1.json --previous-config genie_configs/<space_id>_v0.json --allow-benchmark-changes
   ```

7. Update the Genie space with the benchmark config:

   ```bash
   python3 <skill-dir>/scripts/genie_loop.py update-space --space-id <space_id> --config genie_configs/<space_id>_v1.json
   ```

8. Create an eval run and pull a report for that benchmark-bearing version. Use that report as the baseline for the first Genie tuning config version.

## Benchmark Pruning

Use benchmark pruning when the benchmark has too many questions for practical iteration (or approaches the 500-question limit), contains many redundant variants, or overweights one source, metric, dimension, or answer shape. Pruning is benchmark repair: get approval first, capture a rollback snapshot, change only benchmark definitions, and do not tune Genie configuration in the same pass.

Prune by evidence, not by arbitrary count. Build a question inventory with fields for execution mode, field strategy, validity, difficulty, coverage category, source/table or Metric View, referenced columns, answer shape, business priority, and recent assessment.

Prefer retaining questions that:

- cover distinct sources, Metric Views, metrics, dimensions, filters, joins, date roles, grain patterns, rankings, answer shapes, and Agent response-quality expectations;
- exercise medium or hard reasoning, reusable business logic, high-value workflows, and historically fragile behavior;
- have current checked SQL, clear Agent evaluation notes, or both as required by the execution target;
- include a small number of easy smoke tests for critical sources or metrics.

Prefer pruning questions that:

- are invalid, stale, ambiguous, unscorable, or missing required ground truth;
- duplicate another question except for a date, category, region, or customer literal;
- test a narrow one-off detail with low business value and no unique failure mode;
- are trivial easy lookups when the same source or metric is already covered by stronger questions;
- overweight one source, metric, dimension, or answer shape compared with the Space's intended usage.

Keep healthy 2–4 natural phrasings of the same intent, since multiple phrasings improve coverage; prune only redundant literal/date/category swaps.

Use a coverage matrix before finalizing the pruned set:

```markdown
## Benchmark Pruning Matrix

| Coverage area | Retained question IDs | Difficulty mix | Pruned near-duplicates | Gap after pruning? |
|---|---|---|---|---|
| Metric View measures | q_001, q_014, q_027 | easy/medium/hard | q_002, q_003 | no |
| Time logic | q_006, q_021 | medium/hard | q_007 | fiscal quarter boundary not covered |
```

Before applying pruning, state the retained denominator, removed or excluded question IDs, coverage preserved, coverage lost, difficulty distribution, and whether follow-up benchmark repair is needed to fill gaps. Retain a compact representative set with at least 30 valid questions unless the user explicitly accepts a smaller diagnostic-only set. After pruning, run the relevant benchmark evaluation and use the completed output as the new baseline.

## Judge-Style Failure Triage

Use GSO-style judging as a mental model only. Do not implement custom judges. For each `BAD` or `NEEDS_REVIEW` question, inspect generated SQL, expected SQL, actual results, and assessment notes when available, then classify the failure across these dimensions:

- `result_correctness`: Did actual results match expected results after reasonable normalization?
- `asset_routing`: Did Genie choose the right table, metric view, or configured source?
- `schema_accuracy`: Did Genie choose the right columns and aliases?
- `logical_accuracy`: Did filters, joins, aggregations, dates, windows, ranking, and grain match intent?
- `completeness`: Did the response answer all required parts?
- `syntax_validity`: Did generated SQL run?
- `response_quality`: Was the final explanation/presentation acceptable when SQL was otherwise correct?
- `benchmark_validity`: Is the expected answer itself valid and current?
- `infra_validity`: Was the eval complete and free of platform/access failures?

Repair triage template:

```markdown
## Repair Triage

| Question ID | Assessment | Valid tuning failure? | Primary failure | Secondary signal | Recommended lever | Notes |
|---|---|---:|---|---|---|---|
| q_001 | BAD | yes | wrong_filter_value | logical_accuracy | entity/value matching + column metadata | status value mismatch |
| q_002 | BAD | no | invalid_expected_sql | benchmark_validity | benchmark repair, not config tuning | expected SQL references removed column |
```

Rules:

- Triage `NEEDS_REVIEW` separately from `BAD`.
- Do not infer root cause from aggregate accuracy alone.
- Use `unknown` or `manual_review` when evidence is insufficient.
- Exclude invalid benchmark and infra failures before selecting Genie repair levers.

## Affected Slice, Regression Slice, And Full Benchmark Gates

Use staged evaluation inside the existing helper-script loop. Do not build a new gate framework.

Gate 1: affected failure slice

- Run the affected failing questions first when practical.
- Purpose: verify the candidate fixes the target cluster.
- If it fails, revise or roll back before spending effort on the full benchmark.

Gate 2: related regression slice

- Run previous-good questions that share the same sources, joins, filters, metrics, or date logic.
- Purpose: catch localized regressions quickly.

Gate 3: full benchmark

- Run the complete benchmark after the targeted and regression checks look acceptable, or when targeted evaluation is unavailable or not representative. For mixed execution goals, compare Chat and Agent runs separately instead of collapsing them into one score.

Run selected benchmark questions by repeating `--benchmark-question-id`:

```bash
python3 <skill-dir>/scripts/genie_loop.py create-eval-run \
  --space-id <space_id> \
  --benchmark-question-id <question_id>
```

## Question-Level Movement Summary

Compare question-level movement, not only aggregate accuracy:

```text
fixed: BAD/NEEDS_REVIEW -> GOOD
regressed: GOOD -> BAD/NEEDS_REVIEW
unchanged_bad: BAD/NEEDS_REVIEW -> BAD/NEEDS_REVIEW
unchanged_good: GOOD -> GOOD
excluded: invalid benchmark, incomplete eval, infra/access issue
```

Record fixed and regressed question IDs in the fix plan. A candidate that fixes one question but regresses several related previous-good questions should not be accepted by default.

## Acceptance Decision Template

After comparing reports, add an explicit keep/revise/rollback decision:

```markdown
## Acceptance Decision

- Baseline report:
- Candidate report:
- Candidate config or Space version:
- Rollback snapshot reference:
- Benchmark execution target:
- Benchmark field strategy:
- Valid denominator used:
- Chat accuracy delta, if run:
- Agent assessment delta, if run:
- Fixed:
- Regressed:
- Unchanged target failures:
- New syntax/access/eval issues:
- Benchmark or infra exclusions:
- Leakage review:
- Decision: KEEP / REVISE / ROLL BACK
- Reason:
- Rollback action, if needed:
```

Keep the candidate only when it improves the valid benchmark score or fixes the target cluster without unacceptable regressions and has a recorded rollback snapshot reference. Roll back or revise when the candidate only shifts failures, creates new syntax/infra issues, depends on benchmark leakage, or lacks enough rollback information to safely continue.

## Create Eval Run

Run all benchmark questions in the space:

```bash
databricks genie genie-create-eval-run <space_id> -o json
```

Run selected benchmark questions:

```bash
cat > /tmp/genie_eval_run.json <<'JSON'
{
  "benchmark_question_ids": [
    "<benchmark_question_id>"
  ]
}
JSON

databricks genie genie-create-eval-run <space_id> --json @/tmp/genie_eval_run.json -o json
```

`benchmark_question_ids` is optional. If omitted, Databricks evaluates all benchmark questions in the space. Add `-p <profile>` to any CLI command when the user has specified a non-default profile.

Save the created run ID from the response as the eval run ID.

Eval runs are asynchronous. The create command submits the benchmark and can return before any question has finished. While the benchmark is still running, listing eval results can return zero rows. Zero results means "not ready" for this workflow, not a valid completed benchmark report.

Use the helper to poll before saving normalized reports:

```bash
python3 <skill-dir>/scripts/genie_loop.py pull-report \
  --space-id <space_id> \
  --eval-run-id <eval_run_id> \
  --version v1
```

`pull-report` waits by default, polling every 60 seconds for up to 3600 seconds. Use `--wait-timeout-seconds` or `--poll-interval-seconds` if a run needs a different cadence. Do not use `--no-wait` unless you have already confirmed results are available, and do not use `--allow-empty` for benchmark comparisons.

## Inspect Eval Runs

List evaluation runs in a space:

```bash
databricks genie genie-list-eval-runs <space_id> -o json
```

Get one evaluation run:

```bash
databricks genie genie-get-eval-run <space_id> <eval_run_id> -o json
```

List results for a run:

```bash
databricks genie genie-list-eval-results <space_id> <eval_run_id> -o json
```

Get details for a single result:

```bash
databricks genie genie-get-eval-result-details <space_id> <eval_run_id> <result_id> -o json
```

## Notes

- The eval API commands are beta.
- Benchmark questions with SQL answers can be automatically scored (Chat mode).
- Questions without SQL answers require manual review before accuracy is final.
- Benchmark response details are only visible for a limited time; Databricks docs say result details are visible for one week.
