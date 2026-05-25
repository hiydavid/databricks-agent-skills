# Genie Optimization Guide

Use this reference when tuning a Genie Space in Databricks-native workflows.

## Core Principle

Translate failed benchmark evidence into structured Genie context. Prefer this order:

1. Focused source scope.
2. Source, Metric View, and column descriptions.
3. Prompt matching for categorical values.
4. Raw-table join specs.
5. SQL snippets for reusable business logic.
6. Representative example SQL for complex patterns.
7. Short global text instructions.

Benchmarks evaluate quality. They do not teach Genie by themselves. Do not copy benchmark questions or answer SQL into sample questions, snippets, examples, or text instructions.

## Benchmark Integrity

Before tuning, review whether the benchmark is useful:

- At least 30 valid question and SQL-answer pairs for benchmark-driven tuning.
- One checked SQL answer per benchmark question.
- Coverage across source selection, Metric View measures, dimensions, filters, joins, date logic, ranking, aggregation grain, and answer shapes.
- No duplicates that only change a category or date.
- No answer SQL that errors, uses stale fields, or encodes the wrong business definition.

If benchmark quality is insufficient, do a dedicated benchmark repair pass first. Do not mix benchmark repair with Genie tuning.

## Repair Decision Stack

Before applying a Space/config edit, answer:

1. Is this a valid tuning failure?
   - Exclude invalid expected SQL, stale benchmark questions, permissions, warehouse/API failures, and incomplete eval output.
2. What changed in the generated SQL or answer?
   - Wrong source, wrong column, wrong join, wrong filter value, missing filter, wrong aggregation, wrong time logic, wrong metric formula, wrong grain, missing output field, syntax failure, or answer-prose issue.
3. What is the smallest repair lever?
   - Source/column metadata, Metric View metadata, entity/value matching, format assistance, join spec, SQL snippet, representative example SQL, or text instruction.
4. Is there a proactive enrichment that would help multiple failures?
   - Missing descriptions, synonyms, categorical value semantics, date-role descriptions, reusable filters/measures, join specs, examples for complex grain/ranking/window logic.
5. What slice proves the repair?
   - Identify affected benchmark question IDs and related previous-good regression questions.
6. What should be recorded for the next loop?
   - Cluster, attempted lever, expected impact, result, regressions, and whether to retry or avoid the approach.

Every tuning pass must name the target failure cluster and repair lever before editing the Space/config.

## Judge-Style Failure Triage

Use judge-style analysis as a mental model only. Do not implement custom judges. For each `BAD` or `NEEDS_REVIEW` question, inspect generated SQL, expected SQL, actual results, and assessment notes when available.

Classify failures across these dimensions:

- `result_correctness`: Did actual results match expected results after reasonable normalization?
- `asset_routing`: Did Genie choose the right table, metric view, or configured source?
- `schema_accuracy`: Did Genie choose the right columns and aliases?
- `logical_accuracy`: Did filters, joins, aggregations, dates, windows, ranking, and grain match intent?
- `completeness`: Did the response answer all required parts?
- `syntax_validity`: Did generated SQL run?
- `response_quality`: Was the final explanation/presentation acceptable when SQL was otherwise correct?
- `benchmark_validity`: Is the expected answer itself valid and current?
- `infra_validity`: Was the eval complete and free of platform/access failures?

```markdown
## Repair Triage

| Question ID | Assessment | Valid tuning failure? | Primary failure | Evidence | Recommended lever |
|---|---|---:|---|---|---|
| q_001 | BAD | yes | wrong_filter_value | generated SQL uses wrong status literal | entity/value matching + column metadata |
| q_002 | BAD | no | invalid_expected_sql | expected SQL references removed column | benchmark repair, not config tuning |
```

Rules:

- Do not count invalid benchmark or infra failures as Genie repair targets.
- Triage `NEEDS_REVIEW` separately from `BAD`.
- Do not infer root cause from aggregate accuracy alone.
- Use `unknown` or `manual_review` when evidence is insufficient.

## Failure Clustering

Cluster valid tuning failures before each candidate edit. Prefer one failure cluster or a small related cluster set per pass.

```markdown
## Failure Clusters

| Cluster | Question IDs | Shared root cause | Evidence from generated SQL | Proposed lever | Regression questions |
|---|---|---|---|---|---|
| status_value_mapping | q_001, q_004 | Genie maps active/inactive terms to wrong stored values | generated SQL filters `status = 'A'`; expected uses `status = 'ACTIVE'` | column metadata + entity/value matching | q_008, q_011 |
| customer_order_join | q_002, q_006 | missing stable customer-to-order join | generated SQL cross-joins or omits customer table | join spec | q_014 |
```

Repair priority:

1. High-count clusters with one clear structured lever.
2. Critical/P0 benchmark questions.
3. Low-regression metadata enrichment.
4. SQL snippets for reusable logic that metadata cannot express.
5. Representative example SQL for complex grain, ranking, windows, or multi-step logic.
6. Text instructions only for global behavior that cannot be encoded structurally.

## Failure-to-Lever Routing

| Failure pattern | Evidence to inspect | Preferred repair lever | Avoid |
|---|---|---|---|
| Wrong table/source selected | Generated SQL uses the wrong configured table or metric view | Improve source descriptions, source names/synonyms, and differentiating metadata | Broad text instruction saying "use table X" for one benchmark |
| Wrong column selected | Correct source, wrong field | Column description, synonyms/business aliases, hide or de-emphasize confusing columns if supported | Example SQL unless the pattern is complex |
| Wrong Metric View measure | Wrong measure selected or measure intent misunderstood | Space-exposed Metric View display names/descriptions when editable, or document an upstream semantic model gap | Duplicating governed measure logic in text instructions |
| Wrong metric formula outside Metric View | Wrong numerator, denominator, or aggregation | SQL snippet for reusable measure logic; representative example for complex formula | Global text instruction with metric math |
| Wrong filter value | SQL uses wrong categorical literal or status mapping | Column description with value semantics, entity/value matching, format assistance, reusable filter snippet | Copying benchmark answer filter into example SQL |
| Missing business filter | Expected SQL has a reusable business filter missing in generated SQL | Reusable filter SQL snippet or concise source/column metadata explaining default business scope | Long instruction list of every filter |
| Wrong join path | SQL omits or misuses a join | Join spec after validating keys and grain | Join spec based only on column-name similarity |
| Wrong join relationship/grain | Duplicated rows, wrong counts, many-to-many issue | Join spec with relationship/grain guidance; example SQL for grain-preserving pattern | Blind aggregation workaround |
| Wrong date field | Uses `created_at` instead of `closed_at`, `effective_date`, etc. | Column descriptions for date roles; snippet for common time filter | Text instruction listing many date rules |
| Wrong time window | Wrong interval, boundary, fiscal period, or relative date logic | SQL snippet for reusable window; representative example for complex period logic | One-off benchmark-specific example |
| Wrong aggregation grain | Counts rows instead of entities, averages at wrong level, misses distinct | SQL snippet for reusable grain logic; example SQL for representative complex query | Source description only |
| Ranking/top-N/window failure | Missing window function, wrong tie-breaker, wrong order | Representative example SQL; reusable snippet if the expression repeats | Many examples pasted into global instruction |
| Correct SQL, bad answer prose | SQL/results acceptable but final explanation weak | Short response-quality text instruction | Changing SQL surfaces |
| Syntax failure | Generated SQL invalid | Inspect exact syntax issue; repair snippets/examples only if pattern repeats | Treating syntax failure as business logic failure |
| Invalid expected SQL | Expected benchmark answer errors or is stale | Benchmark repair outside config tuning | Genie config tuning |
| Incomplete eval / permissions / API | Eval did not complete or details missing | Infrastructure/access fix | Genie config tuning |
| Space too broad / asset ambiguity | Failures scatter across many unrelated sources | Source scoping, descriptions, ambiguity reduction, possible Space split recommendation | More global instructions |

## Proactive Enrichment Before Repair

Before proposing a patch, inspect the current Space/config and failing questions for low-risk enrichments:

1. Are source descriptions missing, thin, or indistinguishable?
2. Are business terms from failed questions absent from source/column descriptions or synonyms?
3. Are low-cardinality categorical columns causing wrong literal values?
4. Are status, type, segment, region, channel, or lifecycle values undocumented?
5. Are date roles ambiguous, such as `created_at` vs `closed_at` vs `effective_date`?
6. Are repeated joins failing because join specs are missing or unclear?
7. Are repeated metrics, filters, or time windows better expressed as SQL snippets?
8. Is a representative example needed for complex grain, ranking, window, or period logic?
9. Is text instruction being used as a dumping ground for logic that belongs in metadata, snippets, examples, or joins?
10. Is the Space backed by Metric Views, and should the repair target Metric View metadata rather than raw table logic?
11. Are there too many data sources in one Space, causing routing confusion?

## Text Instruction Last-Resort Rule

Do not use text instructions as the default repair. If the proposed instruction names specific tables, metric views, columns, joins, filters, denominators, numerators, aliases, ranking logic, or window logic, first try to encode the rule in source/column metadata, entity/value matching, format assistance, join specs, SQL snippets, or representative example SQL.

Use text instructions only for global behavior that cannot be encoded structurally. Each text instruction edit must include:

```markdown
## Text Instruction Justification

- Exact instruction text:
- Why structured surfaces were insufficient:
- Which failures this targets:
- Which regressions this could cause:
- How the candidate eval will validate it:
```

## Evaluation Gates

Use staged evaluation inside the native benchmark loop. Do not build a new gate framework.

Gate 1: affected failure slice

- Run the affected failing questions first when practical.
- Purpose: verify the candidate fixes the target cluster.
- If it fails, revise or roll back before spending effort on the full benchmark.

Gate 2: related regression slice

- Run previous-good questions that share the same sources, joins, filters, metrics, or date logic.
- Purpose: catch localized regressions quickly.

Gate 3: full benchmark

- Run the complete benchmark after the targeted and regression checks look acceptable, or when targeted evaluation is unavailable or not representative.

Compare question-level movement:

```text
fixed: BAD/NEEDS_REVIEW -> GOOD
regressed: GOOD -> BAD/NEEDS_REVIEW
unchanged_bad: BAD/NEEDS_REVIEW -> BAD/NEEDS_REVIEW
unchanged_good: GOOD -> GOOD
excluded: invalid benchmark, incomplete eval, infra/access issue
```

## Acceptance Decision

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

## Iteration Reflection

Write this before starting the next repair pass:

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
- Invalid expected SQL or stale benchmark questions:
- Permissions, platform, warehouse, or incomplete-eval issues:
- Questions excluded from tuning denominator:

### Failure triage
| Question ID | Assessment | Valid tuning failure? | Primary failure | Evidence | Recommended lever |
|---|---|---:|---|---|---|

### Failure clusters
| Cluster | Question IDs | Shared root cause | Evidence from generated SQL | Proposed lever | Regression questions |
|---|---|---|---|---|---|

### Candidate edit
- Target cluster:
- Smallest repair lever:
- Space/config surface to edit:
- Why this should fix the cluster:
- Why this is not benchmark leakage:
- Why this should not regress related questions:

### UC table persistence
- Approved catalog.schema, if any:
- Config version row written? yes/no:
- Eval result rows written? yes/no:
- Repair analysis row written? yes/no:
- Run summary row updated? yes/no:

### Evaluation gate
- Affected question IDs:
- Related previous-good regression questions:
- Full benchmark required? Why/why not:

### Acceptance decision
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

## Optional Unity Catalog Table Persistence

Use Unity Catalog managed Delta tables only when the user approves a catalog/schema location for optimization history. This is optional. Continue the repair loop using native benchmark output when persistence is not approved or unavailable.

Write only optimization history to these tables. Do not modify source-data tables, views, Metric Views, schemas, benchmark answers, or source data as part of Genie config tuning.

Recommended default: four tables.

| Table | Grain | Purpose |
|---|---|---|
| `<catalog>.<schema>.genie_opt_runs` | one optimization pass / candidate edit | Run ledger, parent/child linkage, summary metrics, decision |
| `<catalog>.<schema>.genie_opt_config_versions` | one Space/config snapshot | Before/after snapshots, config hash, rollback reference |
| `<catalog>.<schema>.genie_opt_eval_results` | one question result per eval run | Question-level benchmark logging, triage, movement analysis |
| `<catalog>.<schema>.genie_opt_repair_analysis` | one failure cluster / repair hypothesis per pass | Root-cause analysis, chosen lever, evidence, reflection |

Use the four-table design for long-running or auditable sessions. The `genie_opt_runs` table is the coordinator that connects the candidate edit, parent run, config versions, eval rows, and keep/revise/rollback decision.

Minimum viable alternative: three tables.

```text
genie_opt_runs                 # include repair analysis JSON/Markdown in this table
genie_opt_config_versions
genie_opt_eval_results
```

Use a single append-only event table only when the user prioritizes setup simplicity over typed queries:

```text
genie_opt_events
```

Allowed event types:

```text
run_started
config_snapshot
eval_question_result
repair_analysis
candidate_decision
iteration_reflection
```

Recommended stable columns:

- `genie_opt_runs`: `run_id`, `session_id`, `space_id`, `space_name`, `agent_variant`, `benchmark_id`, `benchmark_version_or_hash`, `iteration`, `parent_run_id`, `baseline_config_version_id`, `candidate_config_version_id`, `target_cluster`, `repair_lever`, `status`, `started_at`, `ended_at`, `baseline_accuracy`, `candidate_accuracy`, `accuracy_delta`, `fixed_count`, `regressed_count`, `unchanged_bad_count`, `unchanged_good_count`, `excluded_count`, `decision`, `notes`.
- `genie_opt_config_versions`: `config_version_id`, `run_id`, `space_id`, `version_label`, `parent_config_version_id`, `captured_at`, `captured_by`, `config_hash`, `config_json`, `changed_surfaces`, `change_summary`.
- `genie_opt_eval_results`: `eval_result_id`, `eval_run_id`, `run_id`, `space_id`, `benchmark_id`, `benchmark_version_or_hash`, `eval_type`, `evaluated_at`, `question_id`, `question_text`, `assessment`, `valid_tuning_failure`, `exclusion_reason`, `primary_failure`, `secondary_signal`, `failure_cluster`, `expected_sql_hash`, `generated_sql_hash`, `generated_sql`, `expected_result_digest`, `actual_result_digest`, `judge_notes`, `latency_ms`, `error_message`.
- `genie_opt_repair_analysis`: `analysis_id`, `run_id`, `space_id`, `created_at`, `cluster_id`, `affected_question_ids`, `root_cause`, `evidence_summary`, `selected_lever`, `rejected_levers`, `config_surface`, `planned_patch_summary`, `expected_fix_count`, `regression_risk`, `benchmark_leakage_check`, `acceptance_decision`, `reflection`, `next_hypothesis`.
- `genie_opt_events`: `event_id`, `event_ts`, `event_type`, `session_id`, `run_id`, `space_id`, `config_version_id`, `eval_run_id`, `question_id`, `payload_json`.

When persistence is enabled for each candidate pass:

1. Write a run row.
2. Capture the before config snapshot.
3. Write repair analysis before editing.
4. Apply the focused Space/config edit.
5. Capture the after config snapshot.
6. Write question-level eval results.
7. Update the run summary, acceptance decision, and iteration reflection.
