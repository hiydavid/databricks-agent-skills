# Genie Optimization Skill: Repair-Loop Improvement Plan v5

Prepared: 2026-05-20

Target repo: <https://github.com/hiydavid/databricks-agent-skills>

Reference repo: <https://github.com/databricks-solutions/databricks-genie-workbench>

Target skill variants:

- `external-agent/optimize-genie-space/`
- `genie-code/optimize-genie-space/`

## Core framing

Treat these as the **same optimization skill** used by two different coding agents.

The shared improvement is not a new optimizer framework. The shared improvement is better **repair intelligence** inside the existing loop:

```text
review current Space/config + latest benchmark report
-> classify failures
-> cluster shared root causes
-> choose the smallest useful repair lever
-> edit the Space/config
-> run benchmark evaluation
-> compare fixed and regressed questions
-> keep, revise, or roll back
-> record reflection
-> repeat
```

The two skill variants should share the same decision logic, tables, and repair-plan templates. They should differ only in execution details:

- **External agent** needs more operational scaffolding because it works outside Databricks and must reconstruct Databricks context through exported config, reports, helper scripts, and local files. Its version history should remain repo-local: `genie_configs/`, `fix_plan/`, and `results/`.
- **Genie Code** lives natively in Databricks, so its guidance should be more direct: inspect the Space, inspect benchmark output, edit the Space/config, run native evaluation, compare results, and iterate. It should not pretend there is repo-local versioning. For durable multi-pass history, use approved Unity Catalog managed tables when the user wants an auditable optimization trail.

Do not frame Genie Code as an exception to the external-agent workflow. Do not add cross-context warnings or tool-name reminders in the Genie Code docs. Each variant should describe only the workflow that belongs to that agent.

## Objective

Improve convergence speed and accuracy by teaching the agent to make better repairs before editing Genie configuration.

The agent should stop treating every failed benchmark question as a prompt-writing problem. Instead, it should ask:

> Given the failed benchmark questions and generated SQL, which small Genie config surface is most likely to fix the shared root cause without causing regressions?

The desired result is faster movement toward high benchmark accuracy while preserving the existing update-config / eval / compare loop.

## What to borrow from GSO

Borrow the repair strategy, not the infrastructure.

Useful GSO-inspired behaviors:

1. **Baseline evidence first.** Evaluate before changing anything.
2. **Triage failures.** Separate valid Genie tuning failures from invalid benchmark, stale ground-truth, permission, API, warehouse, and incomplete-eval issues.
3. **Cluster related failures.** Fix shared root causes instead of patching one question at a time.
4. **Pick a focused repair lever.** Choose the config surface based on failure type.
5. **Prefer proactive enrichment.** Add structured context before broad text instructions.
6. **Gate candidate patches.** Check the affected slice and regression slice where practical before accepting the change.
7. **Reflect between iterations.** Record what worked, what failed, and what not to repeat.

Do not borrow the heavy GSO architecture for this pass.

## Non-goals

Do not add:

- a new optimizer package;
- GSO persistence tables;
- MLflow prompt registry dependencies;
- Lakebase dependencies;
- a Databricks App runtime;
- a custom judge registry;
- a preflight scanner command;
- a new multi-job pipeline;
- broad helper framework changes.

Do not mutate source data, tables, views, schemas, metric views, or benchmark answers during Genie config tuning.

Creating or writing **dedicated optimization history** is a separate activity from mutating source data. For Genie Code, this can be allowed only after explicit user approval and only in a designated Unity Catalog catalog/schema/table set. Do not create schemas or tables as a hidden side effect of ordinary tuning.

Do not copy benchmark questions or answer SQL into sample questions, example SQL, SQL snippets, or text instructions. Repairs must generalize beyond the benchmark.

## Required Codex scope

Make documentation and skill-instruction changes. Keep code changes optional and small.

Recommended files:

```text
external-agent/optimize-genie-space/SKILL.md
external-agent/optimize-genie-space/references/quality-tuning.md
external-agent/optimize-genie-space/references/evals-and-reports.md
genie-code/optimize-genie-space/SKILL.md
genie-code/optimize-genie-space/references/optimization-guide.md
```

Optional, if it reduces duplication without creating a larger refactor:

```text
external-agent/optimize-genie-space/references/repair-loop-playbook.md
genie-code/optimize-genie-space/references/repair-loop-playbook.md
```

For this pass, do not require changes to helper scripts. The main value is better repair reasoning in the skill instructions.

Also add a small native persistence section for Genie Code. This is not local versioning and not a new optimizer system. It is an optional Unity Catalog table strategy for long-running or auditable tuning sessions.

## Shared repair decision stack

Add this decision stack to both skill variants.

Before editing config, the agent should answer these questions:

```text
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
```

The skill should require the agent to name the target failure cluster and repair lever before editing.

## Judge-style triage without judge infrastructure

Use GSO’s judge idea as a mental model only. Do not implement custom judges.

For each `BAD` or `NEEDS_REVIEW` question, classify the failure across these dimensions:

```text
- result_correctness: Did actual results match expected results after reasonable normalization?
- asset_routing: Did Genie choose the right table, metric view, or configured source?
- schema_accuracy: Did Genie choose the right columns and aliases?
- logical_accuracy: Did filters, joins, aggregations, dates, windows, ranking, and grain match intent?
- completeness: Did the response answer all required parts?
- syntax_validity: Did generated SQL run?
- response_quality: Was the final explanation/presentation acceptable when SQL was otherwise correct?
- benchmark_validity: Is the expected answer itself valid and current?
- infra_validity: Was the eval complete and free of platform/access failures?
```

Add this repair triage template:

```markdown
## Repair Triage

| Question ID | Assessment | Valid tuning failure? | Primary failure | Secondary signal | Recommended lever | Notes |
|---|---|---:|---|---|---|---|
| q_001 | BAD | yes | wrong_filter_value | logical_accuracy | entity/value matching + column metadata | status value mismatch |
| q_002 | BAD | no | invalid_expected_sql | benchmark_validity | benchmark repair, not config tuning | expected SQL references removed column |
```

Rules:

- Do not count invalid benchmark or infra failures as Genie repair targets.
- Triage `NEEDS_REVIEW` separately from `BAD`.
- Do not infer root cause from aggregate accuracy alone.
- Inspect generated SQL, expected SQL, actual results, and assessment notes when available.
- Use `unknown` or `manual_review` when evidence is insufficient.

## Failure clustering before edits

Require failure clustering before each candidate edit.

Add this template:

```markdown
## Failure Clusters

| Cluster | Affected Qs | Root Cause | Evidence | Repair Lever | Expected Fixes | Regression Risk |
|---|---:|---|---|---|---:|---|
| status_value_mapping | 5 | Genie maps active/inactive terms to wrong stored values | generated SQL filters `status = 'A'`; expected uses `status = 'ACTIVE'` | column metadata + entity/value matching | 5 | medium |
| customer_order_join | 3 | missing stable customer-to-order join | generated SQL cross-joins or omits customer table | join spec | 3 | high |
```

Repair priority:

1. High-count clusters with one clear structured lever.
2. Critical/P0 benchmark questions.
3. Low-regression metadata enrichment.
4. SQL snippets for reusable logic that metadata cannot express.
5. Representative example SQL for complex grain, ranking, windows, or multi-step logic.
6. Text instructions only for global behavior that cannot be encoded structurally.

## Failure-to-lever routing table

Add this table to the shared tuning guidance for both variants.

| Failure pattern | Evidence to inspect | Preferred repair lever | Avoid |
|---|---|---|---|
| Wrong table/source selected | Generated SQL uses the wrong configured table or metric view | Improve source descriptions, source names/synonyms, and differentiating metadata | Broad text instruction saying “use table X” for one benchmark |
| Wrong column selected | Correct source, wrong field | Column description, synonyms/business aliases, hide or de-emphasize confusing columns if supported | Example SQL unless the pattern is complex |
| Wrong Metric View measure | Wrong measure selected or measure intent misunderstood | Metric View display names, descriptions, measure metadata, related dimensions | Duplicating governed measure logic in text instructions |
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

## Proactive enrichment checklist

Before proposing a patch, inspect the current Space/config and failing questions for low-risk enrichments:

```text
1. Are source descriptions missing, thin, or indistinguishable?
2. Are business terms from failed questions absent from source/column descriptions or synonyms?
3. Are low-cardinality categorical columns causing wrong literal values?
4. Are status, type, segment, region, channel, or lifecycle values undocumented?
5. Are date roles ambiguous, such as created_at vs closed_at vs effective_date?
6. Are repeated joins failing because join specs are missing or unclear?
7. Are repeated metrics, filters, or time windows better expressed as SQL snippets?
8. Is a representative example needed for complex grain, ranking, window, or period logic?
9. Is text instruction being used as a dumping ground for logic that belongs in metadata, snippets, examples, or joins?
10. Is the Space backed by Metric Views, and should the repair target Metric View metadata rather than raw table logic?
11. Are there too many data sources in one Space, causing routing confusion?
```

For every proposed change, require:

```markdown
- Target cluster:
- Config surface:
- Why this lever:
- Why this is not benchmark leakage:
- Why this is safer than a broad text instruction:
- Regression questions to watch:
```

## Text-instruction last-resort rule

Add this rule to both variants:

```text
Do not use text instructions as the default repair. If the proposed instruction names specific tables, metric views, columns, joins, filters, denominators, numerators, aliases, ranking logic, or window logic, first try to encode the rule in source/column metadata, entity/value matching, format assistance, join specs, SQL snippets, or representative example SQL. Use text instructions only for global behavior that cannot be encoded structurally.
```

Each text instruction edit must include:

```markdown
## Text Instruction Justification

- Exact instruction text:
- Why structured surfaces were insufficient:
- Which failures this targets:
- Which regressions this could cause:
- How the candidate eval will validate it:
```

## Evaluation gates inside the existing loop

Do not build a new gate framework. Add staged evaluation guidance to both variants.

Suggested gates:

```text
Gate 1: Affected failure slice
- Run the affected failing questions first when practical.
- Purpose: verify the candidate fixes the target cluster.
- If it fails, revise or roll back before spending effort on the full benchmark.

Gate 2: Related regression slice
- Run previous-good questions that share the same sources, joins, filters, metrics, or date logic.
- Purpose: catch localized regressions quickly.

Gate 3: Full benchmark
- Run the complete benchmark after the targeted and regression checks look acceptable, or when targeted evaluation is unavailable or not representative.
```

The skill should compare question-level movement, not only aggregate accuracy:

```text
fixed: BAD/NEEDS_REVIEW -> GOOD
regressed: GOOD -> BAD/NEEDS_REVIEW
unchanged_bad: BAD/NEEDS_REVIEW -> BAD/NEEDS_REVIEW
unchanged_good: GOOD -> GOOD
excluded: invalid benchmark, incomplete eval, infra/access issue
```

## Iteration reflection

Require a reflection section after each candidate eval.

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

The next iteration must read prior reflections before proposing a repair.

## Acceptance decision

After comparing reports, require an explicit keep/revise/rollback decision.

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

Rules:

- Keep the candidate only when it improves valid benchmark accuracy or fixes the target cluster without unacceptable regressions.
- Roll back or revise when the candidate only shifts failures, creates new syntax/infra issues, or depends on benchmark leakage.
- A candidate that fixes one question but regresses several related previous-good questions should not be accepted by default.

## External-agent implementation guidance

The external-agent skill needs detailed operational scaffolding because it lacks native Databricks context.

### Update `external-agent/optimize-genie-space/SKILL.md`

Keep the existing helper-script-driven loop. Strengthen the planning step before config edits.

Replace or augment the current “analyze prior report and write plan” step with:

```markdown
Analyze the prior report before editing config. Do not patch directly from aggregate accuracy.

Create the fix plan with:

1. Benchmark validity exclusions.
2. Repair triage table for BAD and NEEDS_REVIEW questions.
3. Failure clusters.
4. Chosen target cluster for this pass.
5. Proposed smallest structured repair lever.
6. Proactive enrichment checks considered.
7. Regression slice to watch.
8. Targeted eval question IDs, when practical.
9. Acceptance criteria for this candidate.
```

Add this hard rule:

```markdown
Every tuning pass must name the target failure cluster and repair lever before editing JSON. Do not make broad mixed edits. Prefer one cluster or a small set of related clusters per version so regressions are attributable.
```

Add targeted-eval guidance using the external-agent’s existing evaluation mechanism. The wording should refer to the helper script behavior already documented in the skill, not introduce a new workflow.

```markdown
When a candidate targets a known failure cluster, first run an affected-question eval slice when practical. Then run a small related regression slice of previous-good questions if feasible. Run the full benchmark after the targeted checks look acceptable. If subset eval is unavailable or not representative, run the full benchmark and document why.
```

Add this final loop requirement:

```markdown
Before starting another repair iteration, read the prior plan’s Iteration Reflection. Avoid repeating a lever that already failed for the same root cause unless new evidence explains why it should work now.
```

### Update `external-agent/optimize-genie-space/references/quality-tuning.md`

Add these sections:

```markdown
# Repair Decision Stack
# Failure-to-Lever Routing
# Proactive Enrichment Before Repair
# Text Instruction Last-Resort Rule
# Failure Cluster Template
# Iteration Reflection Template
```

Include the shared tables and templates from this plan.

### Update `external-agent/optimize-genie-space/references/evals-and-reports.md`

Add these sections:

```markdown
# Valid Denominator Rules
# Judge-Style Failure Triage
# Affected Slice, Regression Slice, and Full Benchmark Gates
# Question-Level Movement Summary
# Acceptance Decision Template
```

Key rules:

- Exclude invalid expected SQL, stale benchmark questions, incomplete evals, permissions/API failures, and warehouse failures from tuning denominator.
- Separate `BAD`, `NEEDS_REVIEW`, and incomplete/missing results.
- Compare fixed and regressed questions, not only aggregate accuracy.
- Use targeted question slices where the existing external-agent workflow supports them.

## Genie Code Unity Catalog table persistence

Genie Code does not need the external-agent local directory model. It already works inside Databricks, so the skill should not invent `genie_configs/`, `fix_plan/`, or `results/` as required local paths.

For durable multi-pass Genie optimization, use approved Unity Catalog managed Delta tables. This gives the native agent a queryable history of config versions, question-level eval outcomes, repair analysis, and keep/revise/rollback decisions.

This is still optional and approval-gated. The repair loop must keep working even when the user does not want persistence.

### Recommended default: four tables

Use **four tables** as the default design. This keeps each record type at its natural grain without becoming a heavy optimizer service.

| Table | Grain | Purpose | Why it exists |
|---|---|---|---|
| `<catalog>.<schema>.genie_opt_runs` | one optimization pass / candidate edit | Run ledger, parent/child linkage, summary metrics, decision | This is the missing coordinator table. It ties config versions, eval results, and analysis together. |
| `<catalog>.<schema>.genie_opt_config_versions` | one Space/config snapshot | Version history, before/after snapshots, config hash, rollback reference | Config snapshots are low-volume but large. They should not be mixed with per-question eval rows. |
| `<catalog>.<schema>.genie_opt_eval_results` | one question result per eval run | Detailed benchmark logging, failure triage, movement analysis | Eval details are high-volume and question-grained. This table supports fixed/regressed/unchanged analysis. |
| `<catalog>.<schema>.genie_opt_repair_analysis` | one failure cluster / repair hypothesis per pass | Root-cause analysis, chosen lever, evidence, reflection | Analysis is cluster-grained and should be queryable separately from raw eval details. |

The fourth table, `genie_opt_runs`, is the most important addition beyond the three obvious categories. Without it, the agent has config versions, eval rows, and analysis notes, but no clean way to answer: "Which candidate edit produced this eval result, what was its parent, and did we keep or roll it back?"

### Why not one table by default?

A single table is easier to create but worse for this workflow. It forces one of two compromises:

1. A very wide table with many null columns because config snapshots, eval rows, and repair analysis have different shapes.
2. An event-log table with `event_type` and `payload_json`, which is simple to append but harder to query for question-level movement, per-cluster accuracy, or config-version lineage.

Use a single table only for an MVP audit log when the team values setup simplicity over analysis quality. For the skill, recommend four tables because the overhead is still small and the query patterns stay clear.

### Minimum viable alternative

If Codex wants a smaller first pass, use **three tables**:

```text
genie_opt_runs                 # include repair analysis JSON/Markdown in this table
genie_opt_config_versions
genie_opt_eval_results
```

In the three-table version, store the repair analysis as `analysis_json` or `analysis_markdown` on `genie_opt_runs`. This is acceptable for a first implementation, but the recommended final state is four tables because cluster-level analysis becomes harder to query from a run-level row.

### Optional fifth table

Do **not** add a fifth table by default.

Add `<catalog>.<schema>.genie_opt_benchmark_snapshots` only when benchmark definitions change often or the team needs to audit historical expected SQL / expected results independently from eval output.

Until then, put these fields on `genie_opt_eval_results`:

```text
benchmark_id
benchmark_version_or_hash
question_id
question_text
expected_sql_hash
expected_result_digest
```

This is enough to detect that a historical result came from a different benchmark version without storing a separate benchmark catalog.

### Suggested table schemas

These schemas are intentionally compact. They favor stable query columns plus JSON/Markdown string fields for details that may evolve.

```sql
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_runs (
  run_id STRING,
  session_id STRING,
  space_id STRING,
  space_name STRING,
  agent_variant STRING,
  benchmark_id STRING,
  benchmark_version_or_hash STRING,
  iteration INT,
  parent_run_id STRING,
  baseline_config_version_id STRING,
  candidate_config_version_id STRING,
  target_cluster STRING,
  repair_lever STRING,
  status STRING,
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  baseline_accuracy DOUBLE,
  candidate_accuracy DOUBLE,
  accuracy_delta DOUBLE,
  fixed_count INT,
  regressed_count INT,
  unchanged_bad_count INT,
  unchanged_good_count INT,
  excluded_count INT,
  decision STRING,
  notes STRING
)
USING DELTA;
```

```sql
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_config_versions (
  config_version_id STRING,
  run_id STRING,
  space_id STRING,
  version_label STRING,
  parent_config_version_id STRING,
  captured_at TIMESTAMP,
  captured_by STRING,
  config_hash STRING,
  config_json STRING,
  changed_surfaces ARRAY<STRING>,
  change_summary STRING
)
USING DELTA;
```

```sql
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_eval_results (
  eval_result_id STRING,
  eval_run_id STRING,
  run_id STRING,
  space_id STRING,
  benchmark_id STRING,
  benchmark_version_or_hash STRING,
  eval_type STRING,
  evaluated_at TIMESTAMP,
  question_id STRING,
  question_text STRING,
  assessment STRING,
  valid_tuning_failure BOOLEAN,
  exclusion_reason STRING,
  primary_failure STRING,
  secondary_signal STRING,
  failure_cluster STRING,
  expected_sql_hash STRING,
  generated_sql_hash STRING,
  generated_sql STRING,
  expected_result_digest STRING,
  actual_result_digest STRING,
  judge_notes STRING,
  latency_ms BIGINT,
  error_message STRING
)
USING DELTA;
```

```sql
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_repair_analysis (
  analysis_id STRING,
  run_id STRING,
  space_id STRING,
  created_at TIMESTAMP,
  cluster_id STRING,
  affected_question_ids ARRAY<STRING>,
  root_cause STRING,
  evidence_summary STRING,
  selected_lever STRING,
  rejected_levers ARRAY<STRING>,
  config_surface STRING,
  planned_patch_summary STRING,
  expected_fix_count INT,
  regression_risk STRING,
  benchmark_leakage_check STRING,
  acceptance_decision STRING,
  reflection STRING,
  next_hypothesis STRING
)
USING DELTA;
```

### Single-table MVP option

If the user explicitly wants the lowest possible setup overhead, use one append-only event table:

```sql
CREATE TABLE IF NOT EXISTS <catalog>.<schema>.genie_opt_events (
  event_id STRING,
  event_ts TIMESTAMP,
  event_type STRING,
  session_id STRING,
  run_id STRING,
  space_id STRING,
  config_version_id STRING,
  eval_run_id STRING,
  question_id STRING,
  payload_json STRING
)
USING DELTA;
```

Allowed `event_type` values:

```text
run_started
config_snapshot
eval_question_result
repair_analysis
candidate_decision
iteration_reflection
```

This single-table option is acceptable for a prototype, but Codex should document that it gives up clean typed queries and will probably need to be split once the user wants cross-run analytics.

### Table write rules

Add these rules to the Genie Code skill docs:

```text
- Use UC table persistence only when the user approves a catalog.schema location.
- Prefer an existing approved schema when available.
- Do not create schemas or tables as a hidden side effect of ordinary tuning.
- Write only optimization history to these tables; do not modify source-data tables, views, Metric Views, or benchmark answers as part of Genie config tuning.
- Store full config snapshots in the config-version table before and after candidate edits.
- Store every evaluated benchmark question in the eval-results table when persistence is enabled.
- Store repair analysis before editing and update the acceptance decision after evaluation.
- If UC table persistence is unavailable or not approved, continue the loop using native benchmark output and include the repair plan, comparison, and reflection in the response.
```

### Where this fits in the Genie Code loop

Add this optional step near the start of the Genie Code workflow:

```markdown
If the optimization will span multiple passes or needs auditable history, confirm an approved Unity Catalog catalog/schema for optimization history. Initialize or reuse the four-table set: runs, config versions, eval results, and repair analysis.
```

Then add this per-candidate instruction:

```markdown
For each candidate pass, write a run row, capture the before config snapshot, write the repair analysis, apply the focused Space/config edit, capture the after config snapshot, write question-level eval results, update the run summary, and record keep/revise/rollback reflection.
```

Rollback guidance should stay conceptual unless the native Genie Code workflow exposes a direct rollback action. The essential requirement is that the prior config snapshot and candidate reflection are saved before further edits.

## Genie Code implementation guidance

The Genie Code skill should get the same repair intelligence, but with native Databricks wording and less operational scaffolding.

Do not describe the Genie Code path by contrasting it with external-agent mechanics. Do not mention external-agent helper operations in the Genie Code docs. The agent already has native Databricks context; the docs should focus on decision quality.

### Update `genie-code/optimize-genie-space/SKILL.md`

Add concise requirements around the native optimization loop:

```markdown
Before applying a Space/config edit, classify failed and needs-review benchmark questions using the repair decision stack in `references/optimization-guide.md`.

If this is a multi-pass optimization or the user wants auditable history, use an approved Unity Catalog table location for snapshots, repair plans, reports, comparisons, and reflections. Treat this as native Databricks table persistence, not repo-local versioning.

Each tuning pass must name:

1. valid benchmark/infra exclusions;
2. the target failure cluster;
3. the selected repair lever;
4. the Space/config surface to edit;
5. expected fixes;
6. related previous-good regression questions to watch;
7. the evaluation gate for this candidate.
```

Add this workflow text:

```markdown
Use the native Genie Code optimization loop:

1. Review the current Space configuration and latest benchmark results.
2. If durable history is needed and approved, initialize or reuse the Unity Catalog optimization-history tables for this Space.
3. Inspect generated SQL, expected SQL, actual results, and assessment notes where available.
4. Exclude invalid benchmark, stale ground-truth, permission, incomplete-eval, or platform failures from tuning decisions.
5. Cluster valid tuning failures by shared root cause.
6. Choose the smallest structured repair lever for the selected cluster.
7. Write the before config snapshot and repair analysis when approved UC optimization-history tables are available.
8. Apply a focused Space/config edit.
9. Run the narrowest useful benchmark evaluation available for the affected questions and related regression questions.
10. Run the full benchmark when the targeted check passes or when a targeted check is not useful.
11. Compare fixed, regressed, unchanged-bad, and unchanged-good questions.
12. Write question-level eval results, run summary metrics, acceptance decision, and reflection when approved UC optimization-history tables are available.
13. Keep, revise, or roll back the candidate based on evidence.
14. Write an iteration reflection before starting the next repair pass.
```

Add this hard rule:

```markdown
Prefer one failure cluster or a small related cluster set per candidate edit. Do not make broad mixed edits unless the report shows one shared root cause across those edits.
```

### Update `genie-code/optimize-genie-space/references/optimization-guide.md`

Add compact native guidance. This file should include:

```markdown
# Repair Decision Stack
# Judge-Style Failure Triage
# Failure Clustering
# Failure-to-Lever Routing
# Proactive Enrichment Before Repair
# Text Instruction Last-Resort Rule
# Evaluation Gates
# Acceptance Decision
# Iteration Reflection
# Optional Unity Catalog Table Persistence
```

Add a compact section that explains: use approved UC managed Delta tables for optimization history; recommend four tables for runs, config versions, eval results, and repair analysis; allow a three-table MVP by embedding analysis in runs; allow a single-table event-log only when the user prioritizes setup simplicity over query quality; continue without persistence if not approved or unavailable.

Add this repair-plan template:

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

The Genie Code guide should include the same failure-to-lever table and proactive enrichment checklist as the external-agent guide, written as native Space optimization guidance.

### Genie Code acceptance criteria

Codex should treat the Genie Code updates as complete when:

1. `genie-code/optimize-genie-space/SKILL.md` requires repair triage before edits.
2. `genie-code/optimize-genie-space/SKILL.md` requires a named failure cluster and chosen repair lever per candidate edit.
3. `genie-code/optimize-genie-space/SKILL.md` describes the native benchmark evaluation loop directly.
4. `genie-code/optimize-genie-space/references/optimization-guide.md` includes the repair decision stack.
5. `genie-code/optimize-genie-space/references/optimization-guide.md` includes the failure-to-lever routing table.
6. `genie-code/optimize-genie-space/references/optimization-guide.md` includes proactive enrichment guidance.
7. `genie-code/optimize-genie-space/references/optimization-guide.md` includes repair-plan, acceptance-decision, and iteration-reflection templates.
8. The Genie Code docs stay concise and native to Databricks.
9. The Genie Code docs include optional UC-native table persistence for multi-pass or auditable optimization, with a recommended four-table design and a simpler MVP fallback.

## Shared authoring rule for both variants

Each skill should speak in the language of its agent.

- External-agent docs may include more explicit context-recovery steps, local artifacts, helper-script references, and report-handling details.
- Genie Code docs should assume native access to Databricks context and focus on repair reasoning, evaluation, and acceptance decisions.
- Shared concepts should be aligned across both variants: triage, clustering, repair lever, proactive enrichment, evaluation gate, acceptance decision, reflection.

## Optional small external-agent helper enhancement

Only if Codex can keep it small, enhance the external-agent report comparison output to group question-level movement as:

```text
fixed: BAD/NEEDS_REVIEW -> GOOD
regressed: GOOD -> BAD/NEEDS_REVIEW
unchanged_bad: BAD/NEEDS_REVIEW -> BAD/NEEDS_REVIEW
unchanged_good: GOOD -> GOOD
excluded: invalid benchmark / infra / incomplete eval
```

This is optional. The agent can already perform this comparison from report artifacts if the docs instruct it to do so.

## Overall acceptance criteria

The implementation is complete when:

1. The optimization loop remains recognizably the same.
2. Both skill variants require failure classification before config edits.
3. Both skill variants require one focused target cluster or related cluster set per candidate version.
4. Both skill variants include the failure-to-lever routing table.
5. Both skill variants include the proactive enrichment checklist.
6. Both skill variants include the text-instruction last-resort rule.
7. Both skill variants explain affected-slice, regression-slice, and full-benchmark evaluation gates using the execution style of that variant.
8. Both skill variants require iteration reflection after each candidate.
9. Both skill variants require an acceptance decision before declaring success.
10. External-agent guidance includes the additional operational scaffolding it needs.
11. Genie Code guidance stays native, concise, and free of external-agent operational references.
12. Genie Code includes optional Unity Catalog table persistence for durable history, without making persistence mandatory or cloning local directory versioning.
13. No heavy architecture, new dependency, or GSO clone is introduced.

## Databricks-native persistence rationale

Unity Catalog managed Delta tables are the right native home for Genie Code optimization history when the user wants queryable, durable state. The table layer should help the repair loop remember config versions, eval details, analysis, and keep/revise/rollback decisions; it should not become a new optimizer service.

Do not overbuild this. Start with the four-table design only when approved, use the three-table MVP when Codex needs a lighter implementation, and use the single-table event log only for a prototype.

## Codex-ready implementation prompt

```text
You are working in https://github.com/hiydavid/databricks-agent-skills.

Goal: Improve both optimize-genie-space skill variants so the agent converges to higher Genie benchmark accuracy faster while preserving the existing update-config -> eval -> compare loop. Do not build a GSO clone. Port only the repair-loop heuristics from the Databricks Genie Workbench / Genie Space Optimizer reference repo.

Treat external-agent/optimize-genie-space and genie-code/optimize-genie-space as the same optimization skill used by two different coding agents. The shared decision logic should be the same: triage failures, cluster root causes, choose the smallest repair lever, make a focused config edit, evaluate affected and regression questions where practical, compare fixed/regressed questions, decide keep/revise/rollback, and record reflection.

Important distinction:
- external-agent needs more operational scaffolding because it works outside Databricks and depends on exported config, local artifacts, reports, and helper workflow instructions.
- genie-code lives natively in Databricks, so write its guidance as direct native Space/config and benchmark-evaluation guidance. Keep it concise and do not include external-agent operational mechanics in the Genie Code docs.

Required changes:
1. Update external-agent/optimize-genie-space/SKILL.md so every tuning pass requires repair triage, failure clustering, a chosen repair lever, proactive enrichment consideration, targeted/regression checks where practical, acceptance decision, and iteration reflection.
2. Update external-agent/optimize-genie-space/references/quality-tuning.md with:
   - repair decision stack
   - failure-to-lever routing table
   - proactive enrichment checklist
   - text-instruction last-resort rule
   - failure cluster template
   - iteration reflection template
3. Update external-agent/optimize-genie-space/references/evals-and-reports.md with:
   - valid denominator rules
   - judge-style triage dimensions
   - affected-slice / regression-slice / full-benchmark gate guidance
   - question-level movement summary
   - acceptance decision template
4. Update genie-code/optimize-genie-space/SKILL.md with the same repair-loop requirements, written as native Genie Code workflow guidance. Include an optional native table persistence step for multi-pass or auditable sessions: use approved Unity Catalog managed Delta tables for runs, config versions, eval results, and repair analysis.
5. Update genie-code/optimize-genie-space/references/optimization-guide.md with compact native versions of the same repair-loop guidance, including the Genie Repair Plan template and optional UC table persistence guidance.

Constraints:
- Preserve all existing hard safety rules.
- Do not add MLflow, Lakebase, GSO job, custom judge infrastructure, or a new optimizer package.
- Do not require new helper commands.
- Do not mutate source data, schemas, tables, views, or metric views.
- Creating/writing dedicated optimization history in Unity Catalog is allowed only after user approval and only in the approved catalog/schema; it must not be confused with source-data mutation.
- Do not change benchmark answers as part of config tuning.
- Do not copy benchmark questions or answer SQL into sample questions, examples, snippets, or text instructions.
- Keep text instructions as last resort.
- Keep changes small and documentation-focused.

Validation:
- Verify referenced files exist.
- Ensure SKILL.md still describes the same core config/eval/compare loop.
- Ensure external-agent has enough operational detail for a non-native coding agent.
- Ensure Genie Code docs are native and concise.
- Ensure Genie Code does not use repo-local versioning language.
- Ensure UC table persistence is optional, approval-gated, and uses a recommended four-table design with a smaller MVP fallback; do not require volumes or repo-local versioning for Genie Code.
- Summarize changed files and confirm no heavy refactor or new dependency was introduced.
```
