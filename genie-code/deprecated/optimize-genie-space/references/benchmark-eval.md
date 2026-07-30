# Benchmark Review and Evaluation

Review, repair, or prune benchmark questions before tuning, and run and compare native benchmark evaluations. Pairs with `failure-triage.md` (diagnosing failures), `tuning-levers.md` (choosing the fix), and `persistence.md` (recording runs).

## Benchmark Execution Modes

A Genie Space's benchmark is a set of **benchmark questions** (Databricks documents up to 500 per Space). Benchmark questions are shared definitions; the **execution mode** chosen for a run determines how Genie scores them:

- **Chat mode** compares Genie's SQL-generated result set against a provided SQL answer. Only questions that include a checked SQL answer can be scored automatically; questions without one require manual review. Manual review can also be needed when results don't exactly match the SQL answer or Genie cannot assess correctness.
- **Agent mode** (Public Preview) runs the question with Genie's multi-step Agent reasoning and grades the response with an LLM judge (an optional evaluation note is passed to the judge). Per Databricks docs, Agent mode is available through the Databricks UI only — there is no API — so Agent-mode benchmark runs are launched and read in the UI.

Benchmarks are **evaluation-only**: Genie does not use benchmark questions or answer SQL to improve its context. Never feed benchmark content back into Space configuration.

You can run the full benchmark or **a subset of questions** (select questions and run only those), including re-running a subset from a previous result. Benchmark runs may be asynchronous — they continue when you navigate away and expose an execution status — so wait for completed per-question output before comparing.

## Benchmark Integrity

Before tuning, review whether the benchmark is useful:

- Identify the target benchmark execution mode: Chat, Agent, or mixed.
- This skill's working minimum is at least 30 valid benchmark questions for the target execution mode before benchmark-driven tuning (a skill convention, not a product limit).
- Chat execution needs deterministic questions with checked SQL answers. SQL-backed questions count as valid only after the SQL has been checked against the current schema and business definition.
- Agent execution needs clear questions; evaluation notes are optional, added when the expected response needs grading guidance.
- Mixed execution should use one shared question set with per-question SQL answers, evaluation notes, or both, based on answer shape.
- Coverage across source selection, Metric View measures, dimensions, filters, joins, date logic, ranking, aggregation grain, answer shapes, and Agent response quality when applicable.
- A meaningful challenge mix. A benchmark dominated by easy questions is insufficient for tuning even when it has 30 valid questions.
- A manageable size for iterative native evaluation. An oversized benchmark with many redundant variants should be pruned before tuning when it slows iteration, obscures root causes, or overweights narrow behaviors.
- No duplicates that only change a category or date.
- No answer SQL that errors, uses stale fields, or encodes the wrong business definition.
- No Agent evaluation note that is vague, contradictory, or asks the judge to reward unsupported claims.
- SQL-backed questions whose expected SQL cannot be checked are excluded from the valid denominator or treated as diagnostic-only until repaired.

If benchmark quality is insufficient or the benchmark is oversized, do a dedicated benchmark repair or pruning pass first. Do not mix benchmark repair or pruning with Genie tuning.

## Benchmark Difficulty

Use this light rubric when reviewing, repairing, or pruning benchmark questions:

- Easy: direct lookup, simple count, single-table filter, or no business logic.
- Medium: reusable metric/filter, categorical mapping, date condition, grouping, basic aggregation, or Metric View measure selection.
- Hard: joins, grain handling, ratios, conditional aggregation, ranking/top-N, rolling/window logic, multi-step business logic, result-shape constraints, or Agent-style synthesis across several supporting queries.

Prefer a meaningful mix of medium and hard questions. Flag benchmarks as too easy when they are dominated by trivial counts/lookups, repeated one-table summaries, or variants that only swap a date/category.

## Benchmark Repair

Use benchmark repair when fewer than 30 valid benchmark questions remain for the target execution mode, expected SQL is invalid or stale, evaluation notes are missing or unclear for Agent-style questions, questions are duplicate or trivial, the benchmark is too easy, or coverage is too narrow for benchmark-driven tuning.

Use benchmark pruning when the benchmark started with too many questions for practical iteration or contains many redundant variants. Pruning is benchmark repair: get approval first, change only benchmark definitions, and do not tune Genie configuration in the same pass.

A valid benchmark question has a current, non-trivial question plus enough checked ground truth for the intended execution mode:

- `single_sql_answer`: add a checked SQL answer for deterministic tabular questions. Do not count the question as valid until the SQL is checked.
- `deterministic_with_response_quality`: add checked SQL and an evaluation note when Chat correctness and Agent response quality both matter. Do not count the question as valid until the SQL is checked.
- `multi_step_agent_analysis`: add an evaluation note only when the question requires multiple investigative queries, synthesis, caveats, citations, visualizations, or supporting tables rather than one canonical result set.
- `ambiguous_or_unverifiable`: ask the user for expected behavior before adding or repairing the question.

Checked SQL must match the current schema and business definition, run successfully or have read-only validation evidence, and avoid obsolete tables, columns, filters, or Metric View assumptions. If SQL validation is unavailable or fails, exclude the question from the valid denominator or mark it diagnostic-only until repaired. Evaluation notes should state the expected content, evidence, caveats, and response-quality criteria without prescribing a hidden one-off answer.

Before changing benchmark definitions, capture a rollback-ready before snapshot (see `persistence.md`), present exact before/after benchmark definition changes, get user approval, and keep the pass limited to benchmark definitions. Do not mix benchmark repair or pruning with Genie tuning.

For each added, replaced, retained, or pruned benchmark question, record:

- question text;
- benchmark field strategy: SQL, evaluation note, both, or excluded;
- expected SQL and validation notes, when SQL is appropriate;
- exact before/after benchmark definition changes for added, replaced, retained, or pruned questions;
- evaluation note, when Agent execution needs response-grading guidance;
- difficulty level;
- coverage category, such as source routing, Metric View measure, filter, join, time logic, ranking, aggregation grain, answer shape, multi-query investigation, evidence quality, or response synthesis;
- referenced tables, Metric Views, and columns;
- whether it adds coverage, replaces an invalid, stale, duplicate, or trivial question, or is retained as a representative question;
- pruning rationale when removed or excluded.

Repair enough benchmark questions to reach at least 30 valid questions for the target execution mode. Count only checked SQL-backed questions, intentionally Agent-only questions with clear evaluation notes, or mixed questions with the required checked SQL and notes. When pruning, retain a compact representative set with at least 30 valid questions unless the user explicitly accepts a smaller diagnostic-only set. After benchmark repair or pruning, run the relevant native benchmark evaluation, wait for completed per-question output, and use that result as the new baseline before starting Genie tuning.

## Benchmark Pruning

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

Use a coverage matrix before finalizing the pruned set:

```markdown
## Benchmark Pruning Matrix

| Coverage area | Retained question IDs | Difficulty mix | Pruned near-duplicates | Gap after pruning? |
|---|---|---|---|---|
| Metric View measures | q_001, q_014, q_027 | easy/medium/hard | q_002, q_003 | no |
| Time logic | q_006, q_021 | medium/hard | q_007 | fiscal quarter boundary not covered |
| Agent synthesis | q_030, q_031 | hard | q_032, q_033 | no |
```

Before applying pruning, state the retained denominator, removed or excluded question IDs, coverage preserved, coverage lost, difficulty distribution, and whether follow-up benchmark repair is needed to fill gaps. After pruning, run the relevant native benchmark evaluation and use the completed output as the new baseline.

## Evaluation Gates

Use staged evaluation inside the native benchmark loop. Do not build a new gate framework.

Gate 1: affected failure subset

- Run the affected failing questions first when practical.
- Purpose: verify the candidate fixes the target cluster.
- If it fails, revise or roll back before spending effort on the full benchmark.

Gate 2: related regression subset

- Run previous-good questions that share the same sources, joins, filters, metrics, or date logic.
- Purpose: catch localized regressions quickly.

Gate 3: full benchmark

- Run the complete relevant benchmark after the targeted and regression checks look acceptable, or when targeted evaluation is unavailable or not representative. For mixed execution goals, compare Chat and Agent runs separately instead of collapsing them into one score.

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
