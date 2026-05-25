# Genie Benchmark Evaluation Runs

Reference docs:

- Genie CLI command group: https://docs.databricks.com/gcp/en/dev-tools/cli/reference/genie-commands
- Databricks SDK Genie API: https://databricks-sdk-py.readthedocs.io/en/stable/workspace/dashboards/genie.html
- Benchmark concepts and UI workflow: https://docs.databricks.com/aws/en/genie/benchmarks

Use profile `fevm-test` for this repo unless the user specifies another profile.

## Important Preconditions

Benchmark eval runs require benchmark questions in the Genie space. In serialized config JSON, those live at:

```text
benchmarks.questions
```

The current saved `_vtest` config has no benchmark questions yet.

List benchmark question IDs from a local config:

```bash
jq -r '.benchmarks.questions[]? | [.id, .question] | @tsv' genie_configs/<space_id>_vtest.json
```

## Ground-Truth SQL Triage

Benchmark answer SQL is ground truth for scoring. Invalid ground truth must be handled as a benchmark issue, not as a Genie tuning target.

- If benchmark answer SQL errors during a benchmark run or read-only verification, classify the affected question as a benchmark-ground-truth issue.
- Do not tune Genie to match invalid SQL, stale business logic, missing data sources or columns, or SQL that cannot execute.
- When possible, verify the issue with read-only SQL inspection only. Do not mutate tables, views, metric views, schemas, benchmark questions, or benchmark answers.
- Record the benchmark question ID, observed error, verification notes, and recommended benchmark-owner correction in `fix_plan/genie_<version>_quality_improvement_plan.md`.
- Exclude invalid-answer questions from accuracy interpretation and regression counts. Do not count them as Genie failures or regressions.
- If fewer than 30 valid Q/A pairs remain after exclusions, treat the benchmark as insufficient for config tuning. Author enough validated benchmark Q/A additions or replacements to bring the valid set to at least 30, put them in a dedicated benchmark bootstrap or repair config version, update the Genie space, and run a new baseline eval before continuing config tuning.

## Valid Denominator Rules

Use only valid, completed benchmark results when interpreting tuning accuracy.

Exclude these from the tuning denominator and regression counts:

- invalid expected SQL or stale benchmark answers;
- benchmark questions that no longer match the current data model;
- incomplete or missing eval output;
- permission, API, warehouse, or platform failures;
- questions with insufficient evidence to decide whether Genie tuning caused the failure.

Keep exclusions explicit in the fix plan and comparison notes. Do not count invalid benchmark or infra failures as Genie repair targets. If exclusions leave fewer than 30 valid Q/A pairs, pause Genie config tuning and do benchmark repair or expansion first.

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

- Run the complete benchmark after the targeted and regression checks look acceptable, or when targeted evaluation is unavailable or not representative.

Run selected benchmark questions by repeating `--benchmark-question-id`:

```bash
python3 .agents/skills/databricks-genie-improve/scripts/genie_loop.py create-eval-run \
  --space-id <space_id> \
  --benchmark-question-id <question_id> \
  --profile fevm-test
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
- Valid denominator used:
- Accuracy delta:
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

Keep the candidate only when it improves valid benchmark accuracy or fixes the target cluster without unacceptable regressions. Roll back or revise when the candidate only shifts failures, creates new syntax/infra issues, or depends on benchmark leakage.

## Benchmark Bootstrap Or Repair Eval Flow

Use this flow when the space has too few benchmark Q/A pairs, weak coverage, overly simple questions, duplicate patterns, or invalid ground-truth SQL.

1. Write the benchmark review and intended additions or replacements in `fix_plan/genie_<version>_quality_improvement_plan.md`.
2. Copy the latest config to the next version, for example `genie_configs/<space_id>_v1.json`.
3. Edit only `benchmarks.questions` in that version. Keep IDs valid and sort benchmark questions by `id`.
4. Validate expected SQL answers with read-only DBSQL inspection when possible.
5. Validate the config with:

   ```bash
   python3 .agents/skills/databricks-genie-improve/scripts/genie_loop.py validate-config --config genie_configs/<space_id>_v1.json --previous-config genie_configs/<space_id>_v0.json --allow-benchmark-changes
   ```

6. Update the Genie space with the benchmark config:

   ```bash
   python3 .agents/skills/databricks-genie-improve/scripts/genie_loop.py update-space --space-id <space_id> --config genie_configs/<space_id>_v1.json --profile fevm-test
   ```

7. Create an eval run and pull a report for that benchmark-bearing version. Use that report as the baseline for the first Genie tuning config version.

## Create Eval Run

Run all benchmark questions in the space:

```bash
SPACE_ID=01f14e0e9d9a1f548b182a2f82341992
databricks genie genie-create-eval-run "$SPACE_ID" -p fevm-test -o json
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

SPACE_ID=01f14e0e9d9a1f548b182a2f82341992
databricks genie genie-create-eval-run "$SPACE_ID" -p fevm-test --json @/tmp/genie_eval_run.json -o json
```

`benchmark_question_ids` is optional. If omitted, Databricks evaluates all benchmark questions in the space.

Save the created run ID from the response as `EVAL_RUN_ID`.

Eval runs are asynchronous. The create command submits the benchmark and can return before any question has finished. While the benchmark is still running, listing eval results can return zero rows. Zero results means "not ready" for this workflow, not a valid completed benchmark report.

Use the repo helper to poll before saving normalized reports:

```bash
python3 .agents/skills/databricks-genie-improve/scripts/genie_loop.py pull-report \
  --space-id "$SPACE_ID" \
  --eval-run-id "$EVAL_RUN_ID" \
  --version v1 \
  --profile fevm-test
```

`pull-report` waits by default, polling every 60 seconds for up to 3600 seconds. Use `--wait-timeout-seconds` or `--poll-interval-seconds` if a run needs a different cadence. Do not use `--no-wait` unless you have already confirmed results are available, and do not use `--allow-empty` for benchmark comparisons.

## Inspect Eval Runs

List evaluation runs in a space:

```bash
SPACE_ID=01f14e0e9d9a1f548b182a2f82341992
databricks genie genie-list-eval-runs "$SPACE_ID" -p fevm-test -o json
```

Get one evaluation run:

```bash
SPACE_ID=01f14e0e9d9a1f548b182a2f82341992
EVAL_RUN_ID=<eval_run_id>
databricks genie genie-get-eval-run "$SPACE_ID" "$EVAL_RUN_ID" -p fevm-test -o json
```

List results for a run:

```bash
SPACE_ID=01f14e0e9d9a1f548b182a2f82341992
EVAL_RUN_ID=<eval_run_id>
databricks genie genie-list-eval-results "$SPACE_ID" "$EVAL_RUN_ID" -p fevm-test -o json
```

Get details for a single result:

```bash
SPACE_ID=01f14e0e9d9a1f548b182a2f82341992
EVAL_RUN_ID=<eval_run_id>
RESULT_ID=<result_id>
databricks genie genie-get-eval-result-details "$SPACE_ID" "$EVAL_RUN_ID" "$RESULT_ID" -p fevm-test -o json
```

## Notes

- The eval API commands are beta.
- Benchmark questions with SQL answers can be automatically scored.
- Questions without SQL answers require manual review before accuracy is final.
- Benchmark response details are only visible for a limited time; Databricks docs say result details are visible for one week.
