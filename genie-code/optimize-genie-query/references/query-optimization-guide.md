# Genie Query Optimization Guide

Use this reference when analyzing Genie Space generated SQL, SQL warehouse behavior, and table layout from a performance and cost perspective in Databricks-native workflows.

## Navigation

- `Evidence Order`: gather query, profile, table, and warehouse facts before recommending changes.
- `Read-Only SQL Templates`: bounded inspection templates for Genie Query History, warehouse activity, table metadata, layout, and optimization history.
- `Issue Taxonomy`: classify performance symptoms with stable labels.
- `Evidence-To-Lever Routing`: map observed symptoms to the smallest useful recommendation.
- `Validation`: prove that recommendations improve performance without changing the answer.
- `Report Template`: produce a concise, evidence-backed handoff.

## Evidence Order

Use this order unless the user provides a specific statement ID or profile first:

1. Confirm the generated SQL is semantically correct enough to optimize. If the query is answering the wrong business question, route to `semantic_wrong_sql`.
2. Inspect `system.query.history` for Genie-originated statements, durations, scan metrics, cache status, spill, queue time, and warehouse ID.
3. Inspect the Query Profile for the slowest operators, scans, joins, shuffles, sorts, aggregates, memory, rows, and Photon fallback.
4. Inspect the Space sources and instructions that influence query shape, including broad source scope, hidden/exposed columns, joins, SQL snippets, examples, and Metric Views.
5. Inspect source objects for layout, statistics, clustering, partitioning, predictive optimization, and whether views or materialized views would reduce repeated work.
6. Inspect warehouse settings and events only after separating query-shape and table-layout causes from queue, startup, memory, and concurrency causes.

Do not use aggregate latency alone as proof of root cause. Separate compile time, queue time, execution time, scan volume, spill, and result fetch time.

## Databricks Documentation Anchors

- Query Profile: https://docs.databricks.com/aws/en/sql/user/queries/query-profile
- Query History system table: https://docs.databricks.com/aws/en/admin/system-tables/query-history
- SQL warehouse behavior: https://docs.databricks.com/aws/en/compute/sql-warehouse/warehouse-behavior
- SQL warehouse types: https://docs.databricks.com/aws/en/compute/sql-warehouse/warehouse-types
- Query performance insights: https://docs.databricks.com/aws/en/sql/user/queries/performance-insights
- Data skipping: https://docs.databricks.com/aws/en/delta/data-skipping
- Liquid clustering: https://docs.databricks.com/aws/en/delta/clustering
- Optimize data file layout: https://docs.databricks.com/aws/en/delta/optimize
- OPTIMIZE syntax: https://docs.databricks.com/aws/en/sql/language-manual/delta-optimize
- ANALYZE TABLE: https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-analyze-compute-statistics
- Join optimization: https://docs.databricks.com/aws/en/transform/optimize-joins
- Warehouse monitoring queries: https://docs.databricks.com/aws/en/compute/sql-warehouse/monitor/queries
- Warehouses system table: https://docs.databricks.com/aws/en/admin/system-tables/warehouses
- Warehouse events system table: https://docs.databricks.com/aws/en/admin/system-tables/warehouse-events
- Predictive optimization system table: https://docs.databricks.com/aws/en/admin/system-tables/predictive-optimization

## Read-Only SQL Templates

Use exact identifiers provided by the user or discovered from the Space. Keep time windows narrow. If a system table is unavailable, state the limitation and use Query History UI or Query Profile UI evidence instead.

### Genie query history by Space

```sql
SELECT
  statement_id,
  start_time,
  end_time,
  execution_status,
  compute.warehouse_id AS warehouse_id,
  total_duration_ms,
  waiting_for_compute_duration_ms,
  waiting_at_capacity_duration_ms,
  compilation_duration_ms,
  execution_duration_ms,
  total_task_duration_ms,
  result_fetch_duration_ms,
  read_partitions,
  pruned_files,
  read_files,
  read_rows,
  produced_rows,
  read_bytes,
  read_io_cache_percent,
  from_result_cache,
  spilled_local_bytes,
  SUBSTRING(statement_text, 1, 2000) AS statement_preview
FROM system.query.history
WHERE query_source.genie_space_id = '<genie-space-id>'
  AND start_time >= current_timestamp() - INTERVAL 7 DAYS
ORDER BY total_duration_ms DESC
LIMIT 50;
```

### Specific statement lookup

```sql
SELECT
  statement_id,
  workspace_id,
  execution_status,
  compute,
  query_source,
  client_application,
  total_duration_ms,
  waiting_for_compute_duration_ms,
  waiting_at_capacity_duration_ms,
  compilation_duration_ms,
  execution_duration_ms,
  total_task_duration_ms,
  read_files,
  read_rows,
  produced_rows,
  read_bytes,
  from_result_cache,
  spilled_local_bytes,
  error_message,
  statement_text
FROM system.query.history
WHERE statement_id = '<statement-id>';
```

### Slow and expensive Genie patterns

```sql
WITH genie_queries AS (
  SELECT
    statement_id,
    compute.warehouse_id AS warehouse_id,
    start_time,
    total_duration_ms,
    waiting_at_capacity_duration_ms,
    execution_duration_ms,
    compilation_duration_ms,
    read_bytes,
    read_rows,
    produced_rows,
    read_files,
    pruned_files,
    spilled_local_bytes,
    from_result_cache,
    SUBSTRING(statement_text, 1, 500) AS query_preview
  FROM system.query.history
  WHERE query_source.genie_space_id = '<genie-space-id>'
    AND execution_status = 'FINISHED'
    AND start_time >= current_timestamp() - INTERVAL 30 DAYS
)
SELECT *
FROM genie_queries
WHERE from_result_cache = false
ORDER BY total_duration_ms DESC, read_bytes DESC
LIMIT 25;
```

### Warehouse event correlation

```sql
SELECT
  event_time,
  workspace_id,
  warehouse_id,
  event_type,
  cluster_count
FROM system.compute.warehouse_events
WHERE warehouse_id = '<warehouse-id>'
  AND event_time >= current_timestamp() - INTERVAL 7 DAYS
ORDER BY event_time DESC
LIMIT 100;
```

### Warehouse configuration snapshots

```sql
SELECT
  warehouse_id,
  warehouse_name,
  warehouse_type,
  warehouse_size,
  min_clusters,
  max_clusters,
  auto_stop_minutes,
  change_time
FROM system.compute.warehouses
WHERE warehouse_id = '<warehouse-id>'
ORDER BY change_time DESC
LIMIT 10;
```

### Table inventory and comments

```sql
SELECT
  table_catalog,
  table_schema,
  table_name,
  table_type,
  comment
FROM <catalog>.information_schema.tables
WHERE table_schema = '<schema>'
  AND table_name IN ('<table_1>', '<table_2>')
ORDER BY table_name;
```

### Column metadata for query predicates and joins

```sql
SELECT
  table_name,
  ordinal_position,
  column_name,
  data_type,
  comment
FROM <catalog>.information_schema.columns
WHERE table_schema = '<schema>'
  AND table_name = '<table-name>'
ORDER BY ordinal_position;
```

### Table layout and clustering

```sql
DESCRIBE DETAIL <catalog>.<schema>.<table>;
```

```sql
DESCRIBE TABLE EXTENDED <catalog>.<schema>.<table>;
```

### Predictive optimization status

```sql
DESCRIBE CATALOG EXTENDED <catalog>;
DESCRIBE SCHEMA EXTENDED <catalog>.<schema>;
DESCRIBE TABLE EXTENDED <catalog>.<schema>.<table>;
```

### Predictive optimization operations

```sql
SELECT
  start_time,
  end_time,
  catalog_name,
  schema_name,
  table_name,
  operation_type,
  operation_status,
  operation_metrics
FROM system.storage.predictive_optimization_operations_history
WHERE catalog_name = '<catalog>'
  AND schema_name = '<schema>'
  AND table_name = '<table-name>'
  AND start_time >= current_timestamp() - INTERVAL 30 DAYS
ORDER BY start_time DESC
LIMIT 50;
```

### Explain a bounded candidate query

```sql
EXPLAIN
<generated_sql_or_rewritten_candidate>;
```

Use `EXPLAIN` to inspect query shape without executing the full workload. Do not treat `EXPLAIN` as a replacement for Query Profile when runtime symptoms such as spill, skew, queueing, or poor pruning matter.

## Query Profile Evidence

When Query Profile is available, capture:

- top operators by time, rows, memory, and spill;
- scans with high read bytes, high read files, low pruning, or wide projected columns;
- joins that multiply rows or join large inputs before selective filters;
- shuffles, sorts, windows, and aggregates that dominate task time;
- Photon fallback or non-Photon operators;
- cache status, because cached queries might not have a profile and do not prove cold-query performance.

If only the Query History row is available, use the `statement_id` and workspace ID to instruct the user how to open Query Profile from Query History.

## Issue Taxonomy

| Issue | Evidence | Preferred routing |
|---|---|---|
| `warehouse_queue` | High `waiting_at_capacity_duration_ms`, queued queries, warehouse events near load spikes | Warehouse max clusters, serverless/IWM, scheduling, or workload isolation |
| `warehouse_startup` | High `waiting_for_compute_duration_ms`, stopped warehouse, cold starts dominate total duration | Auto-stop review, serverless warehouse, scheduled warmup only if justified |
| `warehouse_memory_spill` | High `spilled_local_bytes`, Query Profile spill on joins/sorts/aggregates | Reduce rows/columns first; then consider warehouse size if query work is necessary |
| `scan_no_pruning` | High read files/bytes/rows, low pruned files, scan operators dominate | Add predicates, align with clustering/partition keys, table layout recommendation |
| `missing_delta_stats` | Query insights or layout evidence show missing/incomplete data-skipping stats | Recommend Delta statistics/predictive optimization follow-up |
| `missing_optimizer_stats` | Query insights or plan shows weak join/order choices and missing cost stats | Recommend optimizer statistics/predictive optimization follow-up |
| `layout_key_mismatch` | Filters do not use clustering or partition columns; high scan bytes | Recommend query filter rewrite, liquid clustering key review, or source/view redesign |
| `wide_projection` | `SELECT *`, projected wide columns, high read bytes relative to produced rows | Hide noisy columns, use narrower examples/snippets, project needed columns only |
| `exploding_join` | Join output greatly exceeds input rows; duplicated entities; profile join dominates | Fix join condition, reduce input rows, clarify grain, prejoin or materialize stable relationship |
| `selective_join_filter_late` | Selective filters applied after large joins | Push filters before joins, add source examples/snippets, or pre-filtered view |
| `redundant_aggregation` | Aggregation does not change result or repeats upstream aggregation | Remove redundant aggregation or add constraints/upstream model guidance |
| `many_join_planning_pressure` | Many joins/aggregations, high compilation time, complex plan | Prejoined view, materialized view, Metric View, or source scope reduction |
| `metric_view_or_source_scope_too_broad` | Genie chooses broad raw source or many overlapping sources for simple questions | Focus Genie data sources, hide columns, prefer Metric View or curated view |
| `photon_fallback` | Query Profile or insight shows non-Photon operation | Rewrite unsupported operation or accept fallback when correctness requires it |
| `federated_pushdown_limit` | Foreign table query reads too much remote data or filters cannot push down | Rewrite pushdown-friendly predicates, use `AND` composition, materialize local Delta when appropriate |
| `cache_only_speedup` | Fast run only from result cache; cold query remains slow or profile missing | Validate cold-query path with trivial change or uncached profile |
| `semantic_wrong_sql` | SQL is fast or slow but answers the wrong business question | Stop performance tuning; hand off to `diagnose-genie-space` or `optimize-genie-space` |

## Evidence-To-Lever Routing

| Evidence pattern | Preferred recommendation | Avoid |
|---|---|---|
| Queue time dominates and execution time is acceptable | Increase max clusters, use serverless/IWM where available, separate workloads, or schedule heavy runs away from peak | Rewriting correct SQL without evidence of query inefficiency |
| Startup time dominates occasional usage | Review auto-stop, use serverless for faster startup, consider user workflow expectations | Keeping warehouses always on without cost justification |
| Spill on wide join, sort, window, or aggregate | Reduce input rows/columns, push filters, fix join grain, pre-aggregate, or materialize repeated heavy steps; then consider warehouse size | Scaling warehouse as the first answer when query work is avoidable |
| Full scan with low pruning | Add selective predicates, align query with partition/clustering keys, recommend liquid clustering or layout changes when filters are durable | `OPTIMIZE` without identifying filter columns or layout mismatch |
| Missing data-skipping or optimizer stats | Recommend predictive optimization or `ANALYZE` follow-up with owner approval | Running `ANALYZE` inside this skill |
| Wide projection from Genie examples or broad columns | Hide noisy columns, improve examples/snippets to project required fields, prefer curated source | Adding a text instruction that says "avoid SELECT *" as the only fix |
| Exploding joins or duplicated rows | Clarify join keys and grain, add or revise Genie join specs only via quality workflow, recommend upstream prejoined view for repeated pattern | Blind `DISTINCT` or aggregation workaround |
| Many joins and high compilation time | Recommend curated view, materialized view, Metric View, or narrower source set | More raw tables and broader source exposure |
| Metric formula is expensive but governed | Recommend upstream Metric View/materialized view review with semantic owner | Duplicating governed formula in Genie text instructions |
| Query uses foreign or federated source with poor pushdown | Rewrite predicates for pushdown or recommend local Delta/materialized source | Assuming Delta layout features apply to the remote source |
| Query is semantically wrong | Hand off to quality diagnosis or optimization | Optimizing a wrong result |

## Recommendation Owners

Use clear owners in reports:

- `Genie space curator`: source scope, hidden columns, examples, snippets, and quality-skill handoff.
- `Data model owner`: views, materialized views, Metric Views, joins, grain, and source design.
- `Table owner`: statistics, predictive optimization, liquid clustering, `OPTIMIZE`, data layout, and file maintenance.
- `Warehouse admin`: warehouse type, size, max clusters, serverless/IWM, auto-stop, workload isolation, and permissions.
- `Business owner`: expected unchanged answer, latency target, cost tradeoff, and acceptable refresh/materialization behavior.

## Validation

Validate recommendations without mutating assets during this skill:

- Re-run or inspect the same question with a cold Query Profile when possible.
- Compare answer shape and key totals before and after any approved follow-up change.
- Check `total_duration_ms`, queue durations, execution duration, read bytes, read files, read rows, produced rows, spill bytes, and top operators.
- For warehouse recommendations, compare queue/startup metrics across similar workload windows.
- For table-layout recommendations, confirm filters match clustering, partitioning, or statistics columns and that read bytes/files decrease after approved maintenance.
- For source/model recommendations, run affected Genie questions and related correctness checks through `diagnose-genie-space` or `optimize-genie-space` when answer quality could change.

## Report Template

```markdown
# Genie Query Optimization: <space>

## Case
- Question:
- Statement ID:
- Warehouse:
- Time window:
- Goal:
- Correctness status:

## Workload Evidence
- Query history:
- Duration breakdown:
- Scan/result ratio:
- Repeated patterns:
- Cache status:

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

Each recommendation must name evidence, severity, owner, validation, and risk. If no evidence supports a change, say so and request the missing query profile, statement ID, or warehouse access rather than guessing.
