---
name: optimize-genie-space
description: "Optimize Databricks Genie Space quality in Databricks Genie Code Agent mode. Use inside Databricks for iterative Genie Space tuning with benchmark review, one focused configuration pass at a time, read-only data inspection, native benchmark evaluation, baseline-to-candidate comparison, and regression analysis."
---

# Optimize Genie Space For Genie Code

Improve a Genie Space iteratively inside Databricks. Use Genie Code Agent mode to inspect Space context, run approved read-only SQL, make reviewed Space edits, launch native benchmark evaluation, wait for completed output, and compare behavior across tuning passes.

## Hard Rules

- Never mutate underlying tables, views, Metric Views, schemas, or source data.
- Keep SQL inspection read-only and bounded.
- Make one focused tuning pass at a time. Do not mix benchmark repair with Genie tuning in the same pass.
- Do not copy benchmark questions or answer SQL into sample questions, snippets, examples, or text instructions.
- Benchmarks evaluate quality; they do not teach Genie by themselves.
- Benchmark evaluation can be asynchronous. Do not compare a run until it has completed and produced per-question output.
- Prefer structured Genie context over broad text instructions.
- Get user approval before changing benchmark definitions. Benchmark repair changes only benchmark definitions, never source data or Genie tuning surfaces.
- Before applying a Space/config edit, classify failed and needs-review benchmark questions using the repair decision stack in `references/optimization-guide.md`.
- Every tuning pass must name the target failure cluster, selected repair lever, Space/config surface, expected fixes, related previous-good regression questions, and evaluation gate.
- If durable multi-pass history is needed, use Unity Catalog optimization-history tables only after the user approves a catalog/schema location. Persistence is optional and must not modify source data.

## Workflow

1. Confirm the target Space and optimization goal: higher benchmark accuracy, a failure cluster, a specific user question pattern, or a general quality pass.
2. Review benchmark quality before tuning:
   - count valid question and SQL-answer pairs
   - exclude missing, invalid, duplicated, trivial, or stale ground truth
   - check coverage and challenge level across sources, metrics, filters, joins, time logic, ranking, and answer shapes
   - if fewer than 30 valid pairs remain or the benchmark is dominated by trivial/easy questions, perform or recommend a dedicated benchmark repair pass before tuning
3. For benchmark repair, get approval before changing benchmark definitions, repair only benchmark definitions, validate expected SQL with read-only SQL where practical, run a full native benchmark evaluation, and use the completed output as the new baseline.
4. Establish baseline behavior from the latest completed benchmark evaluation or run a native evaluation after user approval.
5. If the optimization will span multiple passes or needs auditable history, confirm an approved Unity Catalog catalog/schema for optimization history and initialize or reuse the table set described in `references/optimization-guide.md`.
6. Inspect generated SQL, expected SQL, actual results, and assessment notes where available.
7. Exclude invalid benchmark, stale ground-truth, permission, incomplete-eval, warehouse, or platform failures from tuning decisions.
8. Cluster valid tuning failures by shared root cause using `references/optimization-guide.md`.
9. Choose one failure cluster or small related cluster set and select the smallest structured repair lever.
10. Write the before config snapshot and repair analysis when approved Unity Catalog optimization-history tables are available.
11. Apply approved Space edits using the selected structured surface:
   - data source or column descriptions
   - Metric View metadata exposed in the Space or an upstream semantic model recommendation
   - prompt matching settings
   - join specs
   - SQL snippets
   - representative example SQL
   - short global text instruction
12. Run the narrowest useful native benchmark evaluation available for affected questions and related previous-good regression questions.
13. Run the full benchmark when targeted checks pass or when targeted evaluation is unavailable or not representative, then wait for completed per-question output.
14. Compare baseline and candidate behavior:
   - accuracy change
   - fixed questions
   - regressions
   - unchanged failure clusters
   - benchmark questions excluded due to invalid ground truth
15. Write question-level eval results, run summary metrics, acceptance decision, and reflection when approved Unity Catalog optimization-history tables are available.
16. Summarize whether to keep, revise, or roll back the pass.
17. Write an iteration reflection before starting the next repair pass.

## Output

Provide a concise optimization summary:

```markdown
# Genie Space Optimization: <space>

## Benchmark Review
- Valid question count:
- Exclusions:
- Coverage gaps:

## Tuning Pass
- Goal:
- Validity exclusions:
- Target cluster:
- Repair lever:
- Space/config surface:
- Changes applied:
- Why this was the smallest useful pass:
- Regression questions watched:

## Comparison
- Baseline accuracy:
- Candidate accuracy:
- Fixed:
- Regressed:
- Unchanged:
- Excluded:

## Decision
- Keep / revise / roll back:
- Iteration reflection:
- Next recommended pass:
```
