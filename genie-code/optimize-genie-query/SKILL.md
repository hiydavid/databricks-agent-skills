---
name: optimize-genie-query
description: "Analyze Databricks Genie Space query performance and SQL warehouse behavior without making changes in Databricks Genie Code Agent mode. Use inside Databricks when users ask to investigate slow, expensive, queued, spilling, full-scan, poorly pruned, high-latency, high-cost, or warehouse-constrained Genie Space queries while preserving answer correctness."
---

# Optimize Genie Query For Genie Code

Analyze Genie Space generated SQL, query profiles, table layout, and SQL warehouse behavior from a performance and cost lens. Use Genie Code Agent mode to inspect the Space, Query History, Query Profile, Unity Catalog metadata, system tables, and bounded read-only SQL output when needed.

## Hard Rules

- This skill is diagnostic and recommendation-first. Do not edit the Genie Space, benchmarks, SQL warehouse settings, Unity Catalog objects, source schemas, or source data.
- Use only bounded read-only SQL: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, `information_schema`, and system-table reads.
- Do not run `ALTER`, `OPTIMIZE`, `ANALYZE`, `VACUUM`, `CREATE`, `DROP`, `TRUNCATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, table rewrites, warehouse edits, benchmark edits, or Genie Space edits.
- Preserve answer correctness. If the generated SQL is semantically wrong, stop performance tuning and hand off to `diagnose-genie-space` or `optimize-genie-space`.
- Treat cache hits, missing Query Profile access, private or encrypted system-table fields, unavailable system tables, and incomplete query history as limitations, not evidence that performance is healthy.
- Prefer concrete query, profile, warehouse, and table-layout evidence over generic optimization advice.
- Recommend mutating actions such as `ANALYZE`, predictive optimization, liquid clustering, `OPTIMIZE`, materialized views, source rewrites, or warehouse scaling only as user-approved follow-up work outside this skill.

## Workflow

1. Establish the performance case:
   - Space name or identifier
   - slow or expensive user question
   - generated SQL, final answer, or statement ID if available
   - SQL warehouse ID or name
   - relevant time window
   - latency, queue-time, cost, spill, scan, or concurrency goal
   - expected unchanged answer shape or business result
2. Confirm correctness scope before tuning:
   - compare the generated SQL intent to the user question, Space context, and expected answer when available
   - if the SQL answers the wrong business question, classify it as `semantic_wrong_sql` and hand off to a quality skill
   - if the SQL is correct but slow, continue with performance diagnosis
3. Inspect the Space surfaces that can influence expensive SQL:
   - attached tables, views, Metric Views, materialized views, measures, dimensions, filters, and descriptions
   - hidden or exposed columns, especially wide free-text, JSON, arrays, maps, structs, blobs, embeddings, and noisy technical fields
   - joins, snippets, example SQL, SQL functions, prompt matching settings, and text instructions
   - source scope issues, overlapping tables, raw-table exposure where a prejoined view or Metric View would be more efficient, and broad examples that encourage `SELECT *`
4. Inspect Genie-originated query history when accessible. Use `references/query-optimization-guide.md` and filter by `query_source.genie_space_id`, statement ID, warehouse, or time window. Capture:
   - statement ID, status, error text when visible, warehouse ID, statement text when visible, and query source
   - total, waiting-for-compute, waiting-at-capacity, compilation, execution, task, and result-fetch durations
   - read partitions, pruned files, read files, read rows, produced rows, read bytes, IO cache percent, result cache, and spilled bytes
   - repeated slow query patterns, concurrency windows, warehouse events, and cost signals when accessible
5. Inspect Query Profile evidence when available:
   - top operators by time, rows, memory, spill, and task time
   - scans, joins, shuffles, sorts, windows, aggregates, filters, wide projections, Photon fallback, full table scans, exploding joins, and poor pruning
   - whether the profile came from a real execution rather than result cache
6. Inspect table and layout evidence with bounded reads:
   - table type, row count estimates, size, partitioning, clustering keys, file layout, freshness, and whether sources are managed, external, foreign, Delta, Iceberg, views, materialized views, or Metric Views
   - predictive optimization inheritance/status, recent predictive optimization operations when accessible, and whether statistics support data skipping and the optimizer
   - commonly filtered, joined, grouped, ranked, or ordered columns from the generated SQL and Query History
7. Inspect SQL warehouse evidence:
   - warehouse type, size, max clusters, serverless/pro/classic capabilities, Photon/Predictive IO/IWM availability, startup delays, queue pressure, spill symptoms, and warehouse events
   - whether the symptom points to queue/concurrency, startup, memory pressure, scan volume, query shape, or table layout
8. Classify findings using `references/query-optimization-guide.md`. Separate:
   - query-shape issues
   - table-layout/statistics issues
   - warehouse capacity or concurrency issues
   - Genie Space source/scope issues
   - semantic correctness issues
   - evidence/access limitations
9. Recommend the smallest useful performance lever. Prefer reducing query work before increasing compute unless the evidence primarily shows queue pressure, startup delay, or unavoidable memory pressure.
10. Produce a concise query optimization report in chat or notebook output.

## Output

Use this shape:

```markdown
# Genie Query Optimization: <space>

## Case
- Question:
- Statement ID:
- Warehouse:
- Goal:
- Correctness status:

## Workload Evidence
- Query history:
- Repeated patterns:
- Access limitations:

## Query Plan Findings
| Severity | Issue | Evidence | Recommendation | Owner | Validation | Risk |
|---|---|---|---|---|---|---|

## Warehouse Findings
| Severity | Issue | Evidence | Recommendation | Owner | Validation | Risk |
|---|---|---|---|---|---|---|

## Table And Layout Findings
| Severity | Issue | Evidence | Recommendation | Owner | Validation | Risk |
|---|---|---|---|---|---|---|

## Recommendations
| Priority | Lever | Change | Why | Validation |
|---|---|---|---|---|

## Validation Plan
- Read-only check:
- Query Profile check:
- Warehouse check:
- Expected unchanged answer:

## Limitations
- Missing evidence:
- Confidence:
- Handoff:
```

End with the next action: user confirmation needed for any mutating follow-up, a handoff to `diagnose-genie-space` or `optimize-genie-space` for semantic quality issues, or a recommendation-only summary when no change is justified.
