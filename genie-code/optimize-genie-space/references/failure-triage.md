# Failure Triage

Turn failed benchmark evidence into a clustered root cause and a single repair target. Pairs with `benchmark-eval.md` (what to run and how it is scored), `tuning-levers.md` (choosing and applying the fix), and `persistence.md` (recording the analysis).

## Read-Only SQL Inspection

Use SQL only for bounded inspection and validation. Allowed statements are `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, read-only `information_schema`, and read-only system-table queries.

Do not run DDL, DML, maintenance commands, schema or object mutations, warehouse edits, benchmark edits through SQL, or source-data writes. This includes `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, `OPTIMIZE`, `VACUUM`, `ANALYZE`, refresh operations, table rewrites, permission changes, and warehouse configuration changes.

Keep inspection bounded with explicit limits for samples and targeted aggregate checks for validation, cardinality, null rates, categorical values, join grain, metric semantics, and date logic.

## Repair Decision Stack

Before applying a Space/config edit, answer:

1. Is this a valid tuning failure?
   - Exclude invalid expected SQL, unclear evaluation notes, stale benchmark questions, permissions, warehouse/API failures, and incomplete eval output.
   - Record whether the result came from Chat execution, Agent execution, or a mixed run.
2. What changed in the generated SQL or answer?
   - Chat: wrong source, wrong column, wrong join, wrong filter value, missing filter, wrong aggregation, wrong time logic, wrong metric formula, wrong grain, missing output field, syntax failure, or answer-prose issue.
   - Agent: weak research plan, missing hypothesis, insufficient supporting queries, wrong source selection, incomplete evidence, unsupported claim, missing citation/table/chart, poor synthesis, missing caveat, or unclear final report.
3. What is the smallest repair lever? (See `tuning-levers.md`.)
   - Source/column metadata, Metric View metadata, entity matching, format assistance, join relationship, SQL expression, example SQL query, SQL function, or text instruction.
4. Is there a proactive enrichment that would help multiple failures?
   - Missing descriptions, synonyms, categorical value semantics, date-role descriptions, reusable filters/measures, join relationships, examples for complex grain/ranking/window logic, or response-quality guidance for Agent reports.
5. What questions prove the repair?
   - Identify affected benchmark question IDs and related previous-good regression questions.
6. What should be recorded for the next pass?
   - Cluster, attempted lever, expected impact, result, regressions, and whether to retry or avoid the approach.
7. What exact edit is being approved?
   - Record the before value, proposed after value, affected surface, rollback snapshot reference, expected fixes, regression questions, and evaluation gate.

Every tuning pass must name the target failure cluster, repair lever, rollback snapshot reference, and exact proposed edit before editing the Space/config.

## Judge-Style Failure Triage

Use judge-style analysis as a mental model only. Do not implement custom judges. For each `BAD` or `NEEDS_REVIEW` question, inspect the evidence available for the execution mode. For Chat execution, inspect generated SQL, expected SQL, actual results, and assessment notes. For Agent execution, inspect the full response, research steps, supporting query outputs, citations, visualizations, evaluation note, and assessment notes.

Classify failures across these dimensions:

- `result_correctness`: Did actual results match expected results after reasonable normalization?
- `asset_routing`: Did Genie choose the right table, Metric View, or configured source?
- `schema_accuracy`: Did Genie choose the right columns and aliases?
- `logical_accuracy`: Did filters, joins, aggregations, dates, windows, ranking, and grain match intent?
- `completeness`: Did the response answer all required parts?
- `syntax_validity`: Did generated SQL run?
- `agent_investigation_quality`: Did Agent mode form a useful plan, run enough relevant queries, adapt to findings, and gather enough evidence?
- `response_quality`: Was the final explanation, report structure, citation support, table/chart use, and caveat handling acceptable?
- `benchmark_validity`: Is the expected SQL valid and current, and is the evaluation note clear enough for Agent-mode judging?
- `infra_validity`: Was the eval complete and free of platform/access failures?

```markdown
## Repair Triage

| Question ID | Execution | Assessment | Valid tuning failure? | Primary failure | Evidence | Recommended lever |
|---|---|---|---:|---|---|---|
| q_001 | Chat | BAD | yes | wrong_filter_value | generated SQL uses wrong status literal | entity matching + column metadata |
| q_002 | Chat | BAD | no | invalid_expected_sql | expected SQL references removed column | benchmark repair, not config tuning |
| q_003 | Agent | BAD | yes | incomplete_evidence | report names drivers but cites only one aggregate query | source descriptions + representative example pattern |
```

Rules:

- Do not count invalid benchmark or infra failures as Genie repair targets.
- Do not treat an Agent-mode failure as a SQL-match failure unless the eval evidence shows the response was wrong because of a single incorrect query.
- Triage `NEEDS_REVIEW` separately from `BAD`.
- Do not infer root cause from aggregate accuracy alone.
- Use `unknown` or `manual_review` when evidence is insufficient.

## Failure Clustering

Cluster valid tuning failures before each candidate edit. Prefer one primary failure cluster per pass. Include multiple clusters only when they share the same root cause, repair surface, primary repair lever, and validation questions.

```markdown
## Failure Clusters

| Cluster | Question IDs | Shared root cause | Evidence | Proposed lever | Regression questions |
|---|---|---|---|---|---|
| status_value_mapping | q_001, q_004 | Genie maps active/inactive terms to wrong stored values | generated SQL filters `status = 'A'`; expected uses `status = 'ACTIVE'` | column metadata + entity matching | q_008, q_011 |
| customer_order_join | q_002, q_006 | missing stable customer-to-order join | generated SQL cross-joins or omits customer table | join relationship | q_014 |
| revenue_driver_synthesis | q_009, q_012 | Agent report summarizes decline without segment-level evidence | final report lacks cited product or region breakdown queries | source descriptions + representative example pattern | q_016 |
```

Repair priority:

1. High-count clusters with one clear structured lever.
2. Critical/P0 benchmark questions.
3. Low-regression metadata enrichment.
4. SQL expressions for reusable logic that metadata cannot express.
5. Example SQL queries for complex grain, ranking, windows, or multi-step logic.
6. Text instructions only for global behavior that cannot be encoded structurally.
