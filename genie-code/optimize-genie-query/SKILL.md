---
name: optimize-genie-query
description: "Triage and optimize query-execution latency and cost for one Databricks Genie Space's real executed SQL in Genie Code Agent mode, using system.query.history scoped to that space plus Query Profile, table layout, and warehouse evidence; recommend read-only levers while preserving answer correctness. Use when the space's SQL is correct but slow or expensive at runtime; for wrong answers or generation/config latency, hand off to Genie Code's native Genie diagnosis or improvement skills."
---

# Optimize Genie Query For Genie Code

Triage and optimize the query-execution performance and cost of a single Genie Space's real executed SQL. Pick up after Genie Code's native diagnosis has attributed a latency complaint to SQL runtime (execution, queue, startup, scan, spill, result-fetch) and confirmed the generated SQL is correct. Anchor on the space's actual executed queries from `system.query.history` filtered by `query_source.genie_space_id`; use the native Query performance insights (Beta) as a triage signal when present; and treat approved benchmark runs as an optional way to generate or reproduce load, not the primary evidence source. Validate every finding against Query Profile, table layout, SQL warehouse evidence, and Unity Catalog metadata. See `references/query-optimization-guide.md` for the evidence order, read-only SQL templates, issue taxonomy, and report template.

## Hard Rules

- This skill does not own latency attribution. If it is not yet confirmed that SQL runtime (not query generation) dominates and the SQL is correct, hand back to Genie Code's native diagnosis skill rather than re-deriving the generation-vs-execution split here.
- This skill is diagnostic and recommendation-first. Do not edit the Genie Space, benchmark definitions, SQL warehouse settings, Unity Catalog objects, source schemas, or source data.
- Anchor on the target space's real executed queries from `system.query.history`, filtered by `query_source.genie_space_id`. The Query History UI cannot filter by Genie Space or query source, so scope with the SQL templates in the reference, not the UI filter bar. `query_source.genie_space_id` identifies a space, not an individual Genie message, so attribute findings at the workload level.
- Treat benchmark runs as optional load generation or before/after validation, never the primary evidence source. Launch a native benchmark run only after explicit user approval; benchmark definition, evaluation, and quality tuning belong to Genie Code's native Genie improvement skill.
- Use only bounded read-only SQL: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, `information_schema`, and system-table reads.
- Do not run `ALTER`, `OPTIMIZE`, `ANALYZE`, `VACUUM`, `CREATE`, `DROP`, `TRUNCATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, table rewrites, warehouse edits, benchmark definition edits, or Genie Space edits.
- Preserve answer correctness. If the generated SQL is semantically wrong, stop performance tuning and hand off to Genie Code's native Genie diagnosis or improvement skill.
- Treat Query performance insights as a Beta feature gated on the workspace Previews page: absent, hidden, or unavailable insights are limitations, not evidence that performance is healthy.
- Treat cache hits, missing Query Profile access, private or encrypted system-table fields, unavailable system tables, and incomplete query history as limitations.
- Prefer concrete insight, query, profile, warehouse, and table-layout evidence over generic optimization advice.
- When a query has actionable insights, the Query History or Query Profile UI exposes an Optimize button that opens Genie Code; treat any Genie Code rewrite or recommendation as a candidate to validate, not as proof.
- Recommend mutating actions such as `ANALYZE`, predictive optimization, liquid clustering, `OPTIMIZE`, materialized views, source rewrites, Space edits, benchmark edits, or warehouse scaling only as user-approved follow-up work outside this skill.

## Workflow

1. Establish the performance case:
   - Space name or identifier, and its Genie Space ID
   - SQL warehouse ID or name
   - Query History time window of interest (and a benchmark run window only if a benchmark is used)
   - latency, queue-time, cost, spill, scan, or concurrency goal
   - expected unchanged answer shape or business result
2. Confirm you are in the right place (latency-side gate). This skill optimizes the execution side; it does not decide generation vs execution latency:
   - require upstream attribution from Genie Code's native diagnosis: is SQL runtime confirmed to dominate, with the generated SQL correct?
   - if that attribution is missing, hand back to the native diagnosis skill for its latency split rather than re-deriving the generation-vs-execution decision here
   - if the attribution points to generation/thinking-phase latency or to space configuration, hand off to Genie Code's native Genie improvement skill
   - only when SQL runtime dominates and the SQL is correct, continue
3. Locate the space's executed queries:
   - query `system.query.history` filtered by `query_source.genie_space_id` for the target window (see `references/query-optimization-guide.md` -> Read-Only SQL Templates); the Query History UI cannot filter by Space, so scope with SQL
   - record statement IDs, duration breakdown, scan/spill/cache metrics, warehouse, and recurring SQL shapes for the slowest and most expensive queries
   - if production history is sparse or unrepresentative, optionally launch the narrowest useful native benchmark run after explicit user approval, then re-query Query History
4. Use Query performance insights as the primary triage signal when available:
   - in Query History or the Query Profile, prioritize the space's queries that carry performance insights
   - when a query has actionable insights, the Optimize button opens Genie Code; preserve its prefilled context but treat its rewrite or recommendation as a candidate, not proof
   - group repeated queries by insight label, source object, SQL shape, warehouse, and question pattern
5. Fall back when insights are absent or inaccessible:
   - if insights are missing, hidden, empty, delayed, or unavailable, use `references/query-optimization-guide.md` and inspect Query History, Query Profile, table layout, Space context, and warehouse evidence manually
   - state the Beta/access limitation explicitly in the report
6. Confirm correctness scope before tuning:
   - compare the generated SQL intent to the originating question, Space context, and expected answer
   - if the SQL answers the wrong business question, classify it as `semantic_wrong_sql` and hand off to a quality skill
   - if the SQL is correct but slow, continue with performance diagnosis
7. Validate the insight or candidate rewrite against Query Profile. Inspect the dominant operators and the symptom class (scans, joins, shuffles, sorts, windows, aggregates, wide projections, Photon fallback, poor pruning, memory, spill, task time), and confirm any rewrite is semantically equivalent before proposing it. Use `EXPLAIN` only for bounded candidate shape checks, not as a profile replacement. Classify using the reference Issue Taxonomy.
8. Inspect the Space surfaces that can influence expensive but correct SQL (sources, hidden/wide columns, joins, snippets, examples, Metric Views) only as evidence for an execution-side recommendation; route any generation/config or semantic-quality change to a quality skill. See `references/query-optimization-guide.md` -> Evidence Order step 8.
9. Inspect table and layout evidence with bounded reads (type, row-count estimates, size, partitioning, clustering keys, file layout, freshness, predictive-optimization status, and whether statistics support data skipping and the optimizer); templatesin `references/query-optimization-guide.md` -> Read-Only SQL Templates.
10. Inspect SQL warehouse evidence (type, size, max clusters, serverless/pro/classic capabilities, Photon/Predictive IO availability, startup delays, queue pressure, spill symptoms, warehouse events) and decide whether the symptom points to queue/concurrency, startup, memory pressure, scan volume, query shape, or table layout.
11. Classify findings using `references/query-optimization-guide.md`: insight labels and validated issue labels, query-shape issues, table-layout/statistics issues, warehouse capacity/concurrency issues, Genie Space source/scope issues, semantic correctness issues, and evidence/access limitations.
12. Recommend the smallest useful performance lever. Prefer reducing query work before increasing compute unless the evidence primarily shows queue pressure, startup delay, or unavoidable memory pressure.
13. Produce a concise query optimization report using the report template in `references/query-optimization-guide.md` -> Report Template.

## Output

Use the report template in `references/query-optimization-guide.md` -> Report Template. End with the next action: user confirmation needed for any mutating follow-up, a handoff to Genie Code's native diagnosis skill (for latency attribution or semantic quality) or native Genie improvement skill (for space configuration and benchmark-driven quality work), or a recommendation-only summary when no change is justified.
