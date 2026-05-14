---
name: optimize-genie-space
description: "Optimize Databricks Genie Space quality in Databricks Genie Code Agent mode. Use inside Databricks for iterative Genie Space tuning with benchmark review, one focused configuration pass at a time, read-only data inspection, native benchmark evaluation, baseline-to-candidate comparison, and regression analysis without local helper scripts or external workspace setup."
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

## Workflow

1. Confirm the target Space and optimization goal: higher benchmark accuracy, a failure cluster, a specific user question pattern, or a general quality pass.
2. Review benchmark quality before tuning:
   - count valid question and SQL-answer pairs
   - exclude missing, invalid, duplicated, trivial, or stale ground truth
   - check coverage across sources, metrics, filters, joins, time logic, ranking, and answer shapes
   - if fewer than 30 valid pairs remain, recommend a benchmark repair pass before tuning
3. Establish baseline behavior from the latest completed benchmark evaluation or run a native evaluation after user approval.
4. Analyze failure clusters using `references/optimization-guide.md`.
5. Propose one focused pass with expected impact and regression risk.
6. Apply approved Space edits using the smallest structured surface:
   - data source or column descriptions
   - Metric View metadata or upstream semantic model recommendation
   - prompt matching settings
   - join specs
   - SQL snippets
   - representative example SQL
   - short global text instruction
7. Re-run the benchmark evaluation after approval and wait for completed per-question output.
8. Compare baseline and candidate behavior:
   - accuracy change
   - fixed questions
   - regressions
   - unchanged failure clusters
   - benchmark questions excluded due to invalid ground truth
9. Summarize whether to keep, revise, or roll back the pass.

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
- Changes applied:
- Why this was the smallest useful pass:

## Comparison
- Baseline accuracy:
- Candidate accuracy:
- Fixed:
- Regressed:
- Unchanged:

## Decision
- Keep / revise / roll back:
- Next recommended pass:
```
