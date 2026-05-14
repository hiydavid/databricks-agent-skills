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
