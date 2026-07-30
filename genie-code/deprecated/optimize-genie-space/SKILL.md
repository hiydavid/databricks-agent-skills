---
name: optimize-genie-space
description: "Optimize Databricks Genie Space quality through approved, focused tuning passes in Genie Code Agent mode — one pass by default, or looped toward a target accuracy when the user asks. Use when users want to make reviewed Space edits, repair or prune benchmark questions, run native Chat- or Agent-mode benchmark evaluations, and tune one configuration surface at a time with bounded read-only inspection."
---

# Optimize Genie Space For Genie Code

Improve a Genie Space inside Databricks by turning failed benchmark evidence into the smallest structured configuration change, then re-measuring with native benchmark evaluation. Run in Genie Code Agent mode to inspect Space context, run approved read-only SQL, make reviewed Space edits, launch native benchmark evaluation in the Genie UI, wait for completed output, and compare behavior across passes.

Two "Agent modes" are involved — keep them distinct:

- **Genie Code Agent mode** is the harness this skill runs in; it edits the Space and drives the workflow.
- **Benchmark Agent mode** is one of two Genie benchmark *execution* modes (Chat vs Agent) that determine how Genie scores a benchmark run. Benchmark Agent-mode runs are graded by an LLM judge and, per Databricks docs, can only be launched and read through the Databricks UI (no API).

## Optimization mode: single pass vs iterative

Genie Code has no built-in loop. The default behavior of this skill is a **single focused tuning pass**. Run iteratively only when the user asks (for example, "keep optimizing until the benchmark hits 90%") — and when they do, **the agent itself drives the loop** by repeating the workflow.

**Single-pass mode (default).** Run one pass: review benchmarks, establish a baseline, triage failures, apply one approved edit, re-evaluate, then report keep / revise / roll back and stop. Use the per-action approval gates in the Hard Rules.

**Iterative mode (only on request).** The loop rules are not assumed — capture and confirm them from the user before starting:

- target score and the valid denominator it is measured against (e.g. "≥90% on the Chat-mode benchmark over valid questions");
- benchmark execution mode(s) to optimize and to gate on;
- budget: maximum passes, wall-clock, or evaluation runs;
- stop conditions: target reached, benchmark unrecoverable, or no progress (plateau);
- autonomy: how much to do between check-ins (see Approval below);
- the approved history / rollback folder.

In iterative mode the agent repeats the workflow until a stop condition is met, carrying minimal state across passes (score trajectory, attempted clusters/levers, a do-not-repeat list, rollback references, next hypothesis) and loading prior reflections before each triage. Stop and escalate to the user when: the target is reached; there are N consecutive non-improving passes (plateau — default 3 unless the user sets otherwise); the score oscillates (freeze the last-known-good config); the same cluster keeps failing with no new evidence; or the budget is exhausted.

**Approval.** Single-pass mode keeps the per-action approval gates below. Iterative mode takes **one up-front approval** covering scope, target, budget, allowed edit surfaces, history folder, and rollback policy; after that the agent runs without pausing per edit, but still pauses on any escalation trigger above, on benchmark-definition changes, and on anything outside the approved edit surfaces.

## Hard Rules

- Never mutate underlying tables, views, Metric Views, schemas, or source data.
- Keep SQL inspection read-only and bounded: only `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, read-only `information_schema`, and read-only system-table queries. Never run DDL, DML, maintenance, schema/object mutations, warehouse edits, benchmark edits via SQL, or source-data writes (`CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, `OPTIMIZE`, `VACUUM`, `ANALYZE`, refreshes, table rewrites, permission changes, warehouse config changes). Full guidance: `references/failure-triage.md`.
- Make one focused tuning pass at a time: one primary failure cluster and one primary repair lever, unless several clusters share the same root cause, repair surface, and validation questions. Never mix benchmark repair or pruning with Genie tuning in the same pass.
- Benchmarks are evaluation-only. Per Databricks docs, Genie does not use benchmark questions or answer SQL to improve its context — they cannot "teach" Genie, and you must never copy benchmark questions, answer SQL, or evaluation-note wording into Space configuration (descriptions, synonyms, example SQL, instructions, etc.).
- Benchmark questions are shared definitions; the execution mode (Chat or Agent) determines scoring. Chat mode compares SQL/result sets and needs a checked SQL answer (or the question is manual-review only); Agent mode is graded by an LLM judge.
- Benchmark Agent-mode runs are launched and read in the Databricks UI only (no API). Do not assume programmatic launch for Agent-mode evaluations.
- Benchmark evaluation may run asynchronously. Do not compare a run until it has completed and produced per-question output.
- Prefer structured Genie configuration over broad text instructions (`references/tuning-levers.md`).
- Get explicit user approval before applying Space edits, changing benchmark definitions, launching native benchmark evaluations, or writing local workspace history. (In iterative mode this is the single up-front approval above, plus the standing pause triggers.)
- Genie has no native config versioning or rollback. Before any Space/config or benchmark-definition edit, export a rollback-ready snapshot of the current configuration (for example, the Space's `serialized_space` export, or an Asset Bundle) into the approved local workspace folder. Do not proceed with an edit if the snapshot cannot be captured. See `references/persistence.md`.
- Benchmark repair or pruning changes only benchmark definitions, never source data or Genie tuning surfaces.
- Before each Space/config edit, classify failed and needs-review benchmark questions with the repair decision stack in `references/failure-triage.md`, and name the target cluster, repair lever, configuration surface, expected fixes, related previous-good regression questions, rollback snapshot reference, and evaluation gate.
- Beyond the mandatory rollback snapshot, durable multi-pass history is optional. Write any history only inside the user-approved local workspace folder; never write outside it.

## Workflow

1. Confirm the target Space and goal: higher benchmark score, a failure cluster, a specific question pattern, or a general quality pass. If the user wants iterative optimization, capture the loop rules now (see "Optimization mode").
2. Determine the benchmark execution target — Chat, Agent, or mixed — from the goal, benchmark/eval context, existing SQL answers, evaluation notes, and the latest eval output. If ambiguous or the Space has no benchmark questions, ask whether to bootstrap or optimize for Chat, Agent, or both.
3. Review benchmark quality before tuning using `references/benchmark-eval.md` (valid-question count for the target mode, Chat needs checked SQL answers, Agent needs clear questions with optional evaluation notes for grading guidance, exclusions, coverage, and challenge mix).
4. If the benchmark is insufficient or oversized, run or recommend a dedicated benchmark repair or pruning pass first (`references/benchmark-eval.md`) — with approval, changing only benchmark definitions — then use the completed evaluation as the new baseline.
5. Establish baseline behavior from the latest completed benchmark evaluation, or run a native evaluation after approval.
6. Before any Space/config or benchmark-definition edit, confirm the approved local workspace folder and export the rollback snapshot (`references/persistence.md`). Initialize or reuse the multi-pass history layout if auditable history is wanted.
7. Inspect the evidence for the target mode (`references/failure-triage.md`): Chat — generated vs expected SQL, results, result-shape, syntax, assessment notes; Agent — final response, plan, multi-query evidence, citations, tables/charts, completeness, caveats, assessment notes.
8. Exclude invalid-benchmark, stale-ground-truth, unclear-note, permission, incomplete-eval, warehouse, and platform failures from tuning decisions (`references/failure-triage.md`).
9. Cluster the remaining valid failures by shared root cause (`references/failure-triage.md`).
10. Choose one primary failure cluster and the smallest structured repair lever (`references/tuning-levers.md`). Include multiple clusters only when they share root cause, repair surface, and validation questions.
11. Write the repair analysis in the approved folder, referencing the rollback snapshot captured in step 6 (capture a fresh pre-edit config version only if the config changed since then) (`references/persistence.md`).
12. Present the exact proposed edit for approval: before/after values or exact text/config snippets, affected surface, expected fixes, regression questions, evaluation gate, and rollback snapshot reference.
13. Apply the approved edit on the smallest structured surface (`references/tuning-levers.md`): source/column descriptions, Metric View metadata exposed in the Space (or an upstream semantic-model recommendation), prompt matching (synonyms / entity matching / format assistance), join relationships, SQL expressions, example SQL queries, SQL functions, or — last resort — a short text instruction.
14. After approval, run the narrowest useful native evaluation: the affected questions plus related previous-good regression questions (`references/benchmark-eval.md`).
15. After approval, run the full relevant benchmark when targeted checks pass or targeted evaluation is unavailable / unrepresentative, then wait for completed per-question output.
16. Compare baseline vs candidate (`references/benchmark-eval.md`): execution/scoring mode, Chat accuracy change (when run), Agent assessment change (when run), fixed, regressed, unchanged clusters, and excluded questions.
17. When history is enabled, write question-level results, run-summary metrics, the acceptance decision, and the reflection (`references/persistence.md`).
18. Decide keep / revise / roll back and report it.
19. In iterative mode, write the iteration reflection, update cross-pass state, check stop conditions, then start the next pass or stop and summarize.

## Output

Provide a concise optimization summary. This is the user-facing summary; the detailed record templates (Acceptance Decision, Iteration Reflection, Genie Repair Plan) live in `references/persistence.md` and are written only to the approved history folder.

```markdown
# Genie Space Optimization: <space>

## Benchmark Review
- Execution target:
- Valid question count:
- Checked SQL-backed question count:
- Pruning recommendation:
- Benchmark field strategy:
- Exclusions:
- Coverage gaps:

## Tuning Pass
- Goal:
- Validity exclusions:
- Target cluster:
- Repair lever:
- Space/config surface:
- Rollback snapshot:
- Exact change approved:
- Changes applied:
- Why this was the smallest useful pass:
- Regression questions watched:

## Comparison
- Baseline Chat accuracy:
- Candidate Chat accuracy:
- Baseline Agent assessment:
- Candidate Agent assessment:
- Fixed:
- Regressed:
- Unchanged:
- Excluded:

## Decision
- Keep / revise / roll back:
- Iteration reflection:
- Next recommended pass:
```

## Related skills

- `diagnose-genie-space` — root-cause Genie Space quality problems. Run it upstream to understand *why* answers fail before optimizing.
- `create-metric-view` — when a failure traces to a Metric View's own definition (fields, measures, source, filter), fix or define the Metric View upstream rather than patching it in the Space.
- `create-genie-space` — build a new Space (including initial benchmark questions) when there is no Space to optimize yet.
- `optimize-genie-query` — distinct skill: it tunes a single Genie query, not Space-wide configuration. Use `optimize-genie-space` (this skill) for Space-level, benchmark-driven optimization.
