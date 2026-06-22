# Rollback and Local Workspace Persistence

Capture a rollback-ready snapshot before every edit, and optionally record auditable multi-pass history. Pairs with `benchmark-eval.md`, `failure-triage.md`, and `tuning-levers.md`.

## Rollback reality

Genie has **no native config versioning, snapshot, or rollback** — the platform will not restore a previous Genie Space configuration for you. Native history that does exist is conversation/run history (threaded chat history and the Monitor view of questions and answers), which is not a config backup.

To get rollback, capture the configuration yourself before editing:

- Export the Space configuration — for example `include_serialized_space=true` on the Genie Spaces API, or a Genie Space export — to the approved workspace folder; and/or
- Track the Space as code with an Asset Bundle (the `genie_spaces` resource with `serialized_space` / `file_path`), which Databricks documents for version-controlling Genie Spaces.

For benchmark repair/pruning passes, capture the current benchmark definitions the same way before changing them.

The rollback snapshot is **mandatory** before any Space/config or benchmark-definition edit; broader multi-pass history (below) is optional.

## Local Workspace File Persistence

Use local workspace files for optimization history. Before any Space/config or benchmark-definition edit, require an approved workspace folder for the minimal rollback snapshot. Prefer a folder in the current user's workspace, such as `/Workspace/Users/<username>/genie_optimization/<space_id>/`. Broader run history, eval logging, and event logging are optional; continue the repair loop using native benchmark output when broader persistence is not approved or workspace-file writes beyond the rollback snapshot are unavailable.

Write only optimization history inside the approved folder. Do not create or mutate source-data tables, views, Metric Views, schemas, benchmark answers, source data, or unrelated workspace assets as part of persistence.

Minimize what is written. Store raw result samples only when needed to explain or reproduce a decision; otherwise prefer hashes, row counts, digests, and concise summaries. Redact sensitive literals in questions, SQL, judge notes, errors, and config text when possible without losing the evidence needed for rollback or comparison. Confirm the approved workspace folder is appropriate for the sensitivity of the Space config, benchmark text, generated SQL, and evaluation notes.

Recommended default layout:

```text
<workspace-history-root>/
  runs/
    <run_id>.json
    <run_id>.md
  config_versions/
    <config_version_id>.json
  eval_results/
    <eval_run_id>.jsonl
  repair_analysis/
    <run_id>_<cluster_id>.md
  events.jsonl
```

Use the JSON and Markdown files for long-running or auditable sessions. The run JSON is the coordinator that connects the candidate edit, parent run, config versions, eval files, repair analysis, and keep/revise/rollback decision. The Markdown files are for human review in the workspace UI. The append-only `events.jsonl` file is optional but useful when the user wants a simple chronological ledger.

Minimum viable layout:

```text
<workspace-history-root>/
  runs/
    <run_id>.md
  config_versions/
    <config_version_id>.json
  eval_results/
    <eval_run_id>.jsonl
```

Allowed event types for `events.jsonl`:

```text
run_started
config_snapshot
eval_question_result
repair_analysis
candidate_decision
iteration_reflection
```

Recommended stable fields:

- Run JSON: `run_id`, `session_id`, `space_id`, `space_name`, `benchmark_execution_target`, `benchmark_id`, `benchmark_version_or_hash`, `iteration`, `parent_run_id`, `baseline_config_version_id`, `candidate_config_version_id`, `target_cluster`, `repair_lever`, `status`, `started_at`, `ended_at`, `baseline_score`, `candidate_score`, `score_delta`, `fixed_count`, `regressed_count`, `unchanged_bad_count`, `unchanged_good_count`, `excluded_count`, `decision`, `rollback_reference`, `notes`.
- Config version JSON: `config_version_id`, `run_id`, `space_id`, `version_label`, `parent_config_version_id`, `captured_at`, `captured_by`, `config_hash`, `config_json`, `changed_surfaces`, `change_summary`, `rollback_reference`.
- Eval result JSONL record: `eval_result_id`, `eval_run_id`, `run_id`, `space_id`, `benchmark_id`, `benchmark_version_or_hash`, `eval_type`, `evaluated_at`, `question_id`, `question_text`, `benchmark_field_strategy`, `assessment`, `valid_tuning_failure`, `exclusion_reason`, `primary_failure`, `secondary_signal`, `failure_cluster`, `expected_sql_hash`, `generated_sql_hash`, `generated_sql`, `evaluation_note_hash`, `expected_result_digest`, `actual_result_digest`, `judge_notes`, `latency_ms`, `error_message`.
- Repair analysis Markdown metadata: `analysis_id`, `run_id`, `space_id`, `created_at`, `cluster_id`, `affected_question_ids`, `root_cause`, `evidence_summary`, `selected_lever`, `rejected_levers`, `config_surface`, `planned_patch_summary`, `expected_fix_count`, `regression_risk`, `benchmark_leakage_check`, `acceptance_decision`, `reflection`, `next_hypothesis`.
- Event JSONL record: `event_id`, `event_ts`, `event_type`, `session_id`, `run_id`, `space_id`, `config_version_id`, `eval_run_id`, `question_id`, `payload_json`.

When persistence is enabled for each candidate pass:

1. Create or reuse the approved workspace history folder.
2. Write the run JSON or run Markdown entry.
3. Capture the before config snapshot before editing.
4. Write repair analysis before editing.
5. Apply the focused Space/config edit.
6. Capture the candidate config snapshot.
7. Write question-level eval results.
8. Write the run summary, acceptance decision, and iteration reflection.

When only the mandatory rollback snapshot is enabled, write at minimum the before config snapshot, snapshot timestamp, Space identifier, editor identity when available, config hash, and rollback reference before editing. Do not proceed with a mutation if the rollback snapshot cannot be captured.

## Iteration Reflection

Write this before starting the next repair pass (and in iterative mode, use it to update cross-pass state and check stop conditions):

```markdown
## Iteration Reflection

- Candidate version:
- Target cluster:
- Lever attempted:
- Result:
- Fixed question IDs:
- Regressed question IDs:
- Still failing question IDs:
- Root cause update:
- Do not repeat:
- Next repair hypothesis:
```

## Genie Repair Plan

Use this template for each candidate pass:

```markdown
## Genie Repair Plan

### Validity exclusions
- Benchmark execution target:
- Benchmark field strategy:
- Invalid expected SQL, unclear evaluation notes, or stale benchmark questions:
- Unchecked SQL-backed questions excluded from valid denominator:
- Permissions, platform, warehouse, or incomplete-eval issues:
- Questions excluded from tuning denominator:

### Failure triage
| Question ID | Execution | Assessment | Valid tuning failure? | Primary failure | Evidence | Recommended lever |
|---|---|---|---:|---|---|---|

### Failure clusters
| Cluster | Question IDs | Shared root cause | Evidence | Proposed lever | Regression questions |
|---|---|---|---|---|---|

### Candidate edit
- Target cluster:
- Smallest repair lever:
- Space/config surface to edit:
- Rollback snapshot reference:
- Current value or before config:
- Exact proposed after value, text, or config snippet:
- Approval request includes exact edit? yes/no:
- Why this should fix the cluster:
- Why this is not benchmark leakage:
- Why this should not regress related questions:

### Local workspace persistence
- Approved workspace folder, if any:
- Before config snapshot written? yes/no:
- Rollback snapshot reference:
- Candidate config snapshot written? yes/no:
- Eval result files written? yes/no:
- Repair analysis written? yes/no:
- Run summary and reflection written? yes/no:

### Evaluation gate
- Affected question IDs:
- Related previous-good regression questions:
- Full benchmark required? Why/why not:

### Acceptance decision
- Chat accuracy delta, if run:
- Agent assessment delta, if run:
- Fixed:
- Regressed:
- Still failing:
- Excluded from denominator:
- Decision: KEEP / REVISE / ROLL BACK
- Reason:

### Iteration reflection
- What was learned:
- Repair approach not to repeat:
- Next repair hypothesis:
```
