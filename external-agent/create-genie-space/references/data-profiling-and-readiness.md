# Data Profiling And Readiness

Use this reference after candidate data sources are selected and before authoring a Genie Space. The goal is to understand whether the data can answer the user's real business questions, not to produce a broad data audit. Prefer metadata first, then run bounded, cost-aware, read-only SQL to build the evidence the design depends on.

## Context Evidence Gate

Before rating any business question High confidence or proposing live Space creation, each included source must have, at minimum:

- Unity Catalog metadata and `DESCRIBE` output (columns, types, comments).
- A row count or a bounded estimate, with sampling or partition scope noted. Never present a sampled count as exact.
- A freshness signal (max event/load date, or lineage/refresh evidence).
- A narrow sample preview of the columns the business questions actually touch.
- Key and join evidence for every proposed relationship: declared constraints, naming, duplicate-key/cardinality checks, or query-history support.

Record any check you cannot complete (permissions, cost, or missing system tables) as an explicit confidence reduction for the affected questions, not a silent omission. Profiling is the evidence that justifies the readiness rating, not optional polish.

## Bounded Profiling Guardrails

- Start with `information_schema`, `DESCRIBE`, table comments, constraints, lineage, query history, and narrow previews.
- Treat exact full-table `COUNT`, `COUNT(DISTINCT)`, categorical scans, null scans, and join probes as broad scans unless table size or partition scope is known to be small.
- For large or unknown-size sources, use partition/date filters, recent slices, or samples to understand shape first. Do not present sampled counts as exact.
- Run exact full-table scans only when the result is needed for readiness, no cheaper metadata signal is available, and the user accepts the likely warehouse cost.

## Phased Inspection

Run inspection in phases and summarize insights between phases.

1. **Structure.** Confirm each object exists, capture table/view/Metric View type, comments, columns, data types, constraints, and sample rows with a narrow selected column list.
2. **Keys and relationships.** Read declared primary, foreign, and unique keys from `information_schema` before probing duplicate keys, so join specs start from documented relationships rather than guesses.
3. **Quality and usage.** Profile nulls, empty strings, constants, distinct counts, casing issues, boolean-as-string values, sensitive/noisy columns, and usage/lineage when system tables are accessible, using scoped filters or samples before exact full-table scans.
4. **Column profiling.** Profile only columns that affect Genie quality: dates, likely filters, categorical strings, join keys, and candidate measures.
5. **Readiness.** Map the profiled data back to the user's 3-5 business questions and record High/Medium/Low confidence for each question, capturing the Context Evidence Gate checks per source.

## Required Data Signals

For each table or standard view, identify:

- Row count and candidate grain: event, transaction, line item, daily snapshot, account, customer, etc.
- Freshness and time coverage from candidate date/timestamp columns.
- Primary time columns and any timezone/date-grain caveats.
- Measures: additive amounts, counts, balances, ratios, durations, numerators, denominators.
- Dimensions and filters: customer, product, region, status, type, owner, category, segment.
- Data quality caveats: all-null columns, high-null columns, empty strings, constant columns, inconsistent casing, boolean values stored as strings, suspicious sentinel values.
- Sensitive/noisy fields: PII, secrets, tokens, raw JSON/blobs, embeddings, ingestion metadata, hashes, duplicate IDs, audit columns.
- Join candidates: key names, distinct counts, overlap, cardinality direction, and whether evidence comes from constraints, query history, row-count checks, or user confirmation.

For each Metric View, identify:

- Measures, dimensions, filters, joins, and time dimensions already governed by the Metric View.
- Agent metadata: display names, synonyms, formatting, and comments for key dimensions and measures.
- Representative query patterns using explicit dimensions and `MEASURE()`.
- Upstream semantic gaps instead of compensating with broad Genie text instructions.

## Read-Only SQL Templates

Workspace metadata and columns:

```sql
SELECT table_catalog, table_schema, table_name, table_type, comment
FROM <catalog>.information_schema.tables
WHERE table_schema = '<schema>'
ORDER BY table_name;
```

```sql
SELECT table_name, ordinal_position, column_name, data_type, comment
FROM <catalog>.information_schema.columns
WHERE table_schema = '<schema>'
ORDER BY table_name, ordinal_position;
```

Declared keys and constraints. Run before the duplicate-key probes so join specs start from documented relationships:

```sql
SELECT
  tc.constraint_type,
  tc.table_name,
  kcu.column_name,
  kcu.ordinal_position
FROM <catalog>.information_schema.table_constraints tc
JOIN <catalog>.information_schema.key_column_usage kcu
  ON tc.constraint_catalog = kcu.constraint_catalog
 AND tc.constraint_schema = kcu.constraint_schema
 AND tc.constraint_name = kcu.constraint_name
WHERE tc.table_schema = '<schema>'
  AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')
ORDER BY tc.table_name, tc.constraint_type, kcu.ordinal_position;
```

Unity Catalog primary and foreign keys are informational and not enforced, so confirm any relationship found here with the duplicate-key/cardinality checks below before proposing a Genie join.

Row count, key cardinality, and date range — for small tables, filtered partitions, or approved full scans:

```sql
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT <candidate_key>) AS distinct_key_count,
  MIN(<date_col>) AS min_date,
  MAX(<date_col>) AS max_date
FROM <catalog>.<schema>.<table>
WHERE <partition_or_date_filter_if_available>;
```

Null, empty, and distinct metrics for a small column batch — use a filtered or sampled source first for large tables:

```sql
WITH bounded_source AS (
  SELECT <col_a>
  FROM <catalog>.<schema>.<table>
  WHERE <partition_or_date_filter_if_available>
)
SELECT
  SUM(CASE WHEN <col_a> IS NULL THEN 1 ELSE 0 END) AS col_a_nulls,
  COUNT(DISTINCT <col_a>) AS col_a_distinct,
  SUM(CASE WHEN TRIM(CAST(<col_a> AS STRING)) = '' AND <col_a> IS NOT NULL THEN 1 ELSE 0 END) AS col_a_empty
FROM bounded_source;
```

Categorical values for prompt matching and examples — avoid sensitive fields and high-cardinality identifiers:

```sql
WITH bounded_source AS (
  SELECT <category_col>
  FROM <catalog>.<schema>.<table>
  WHERE <partition_or_date_filter_if_available>
)
SELECT <category_col>, COUNT(*) AS row_count
FROM bounded_source
WHERE <category_col> IS NOT NULL
GROUP BY <category_col>
ORDER BY row_count DESC
LIMIT 50;
```

Date freshness and sparsity:

```sql
SELECT
  MIN(<date_col>) AS min_value,
  MAX(<date_col>) AS max_value,
  COUNT(*) AS row_count,
  SUM(CASE WHEN <date_col> IS NULL THEN 1 ELSE 0 END) AS null_count
FROM <catalog>.<schema>.<table>
WHERE <partition_or_date_filter_if_available>;
```

Casing and boolean-as-string checks for low-cardinality strings:

```sql
WITH bounded_source AS (
  SELECT <string_col>
  FROM <catalog>.<schema>.<table>
  WHERE <partition_or_date_filter_if_available>
)
SELECT
  LOWER(CAST(<string_col> AS STRING)) AS normalized_value,
  COLLECT_SET(CAST(<string_col> AS STRING)) AS variants,
  COUNT(*) AS row_count
FROM bounded_source
WHERE <string_col> IS NOT NULL
GROUP BY LOWER(CAST(<string_col> AS STRING))
HAVING COUNT(DISTINCT CAST(<string_col> AS STRING)) > 1
   OR LOWER(CAST(<string_col> AS STRING)) IN ('true', 'false', 'yes', 'no', 'y', 'n')
ORDER BY row_count DESC
LIMIT 50;
```

Join cardinality and duplicate-key probe. Run on filtered or sampled sources first for large tables, and do not propose a Genie join when duplicate-key or many-to-many behavior is unresolved:

```sql
WITH
left_keys AS (
  SELECT <left_key>, COUNT(*) AS left_rows_per_key
  FROM <catalog>.<schema>.<left_table>
  WHERE <left_partition_or_date_filter_if_available>
    AND <left_key> IS NOT NULL
  GROUP BY <left_key>
),
right_keys AS (
  SELECT <right_key>, COUNT(*) AS right_rows_per_key
  FROM <catalog>.<schema>.<right_table>
  WHERE <right_partition_or_date_filter_if_available>
    AND <right_key> IS NOT NULL
  GROUP BY <right_key>
)
SELECT
  COUNT(*) AS left_key_count,
  SUM(CASE WHEN r.<right_key> IS NULL THEN 1 ELSE 0 END) AS unmatched_left_key_count,
  SUM(CASE WHEN r.<right_key> IS NOT NULL THEN 1 ELSE 0 END) AS matched_left_key_count,
  SUM(CASE WHEN l.left_rows_per_key > 1 THEN 1 ELSE 0 END) AS duplicate_left_key_count,
  SUM(CASE WHEN COALESCE(r.right_rows_per_key, 0) > 1 THEN 1 ELSE 0 END) AS duplicate_right_key_count,
  MAX(COALESCE(r.right_rows_per_key, 0)) AS max_right_rows_per_left_key
FROM left_keys l
LEFT JOIN right_keys r
  ON l.<left_key> = r.<right_key>;
```

Recent usage and lineage when system tables are accessible:

```sql
SELECT source_table_full_name, target_table_full_name, source_type, target_type
FROM system.access.table_lineage
WHERE (source_table_full_name IN ('<catalog.schema.table>')
   OR target_table_full_name IN ('<catalog.schema.table>'))
  AND event_time >= date_sub(current_date(), 30)
LIMIT 50;
```

```sql
SELECT
  executed_by,
  SUBSTRING(statement_text, 1, 500) AS query_preview,
  total_duration_ms,
  produced_rows
FROM system.query.history
WHERE start_time >= date_sub(current_date(), 7)
  AND execution_status = 'FINISHED'
  AND LOWER(statement_text) LIKE '%<catalog.schema.table>%'
ORDER BY start_time DESC
LIMIT 50;
```

## How To Use Findings

- Hide columns that are ETL metadata, all-null, raw blobs, embeddings, secrets, tokens, or sensitive free text.
- Flag high-null, constant, inconsistent casing, and boolean-as-string columns in `DATA QUALITY NOTES` only when Genie must know the caveat.
- Enable format assistance on useful dimensions and filters. Enable entity matching only for stable low/medium-cardinality string categories that users are likely to mention.
- Use actual profiled values for example SQL parameters and benchmark literals. Do not invent statuses, tiers, category labels, or regions.
- Use query history as evidence for joins, common filters, sample questions, examples, and benchmarks. If system tables are unavailable, proceed without mentioning the failure unless it limits confidence.
- Ask the user to confirm any metric formula, join relationship, fiscal/calendar rule, or default filter that is not supported by metadata, profiling, query history, or constraints.

## Readiness Assessment

This is the canonical readiness rubric for the create-genie-space skill; `SKILL.md` and `best-practices-checklist.md` point here instead of redefining it.

Before JSON authoring, summarize readiness against the user's business questions:

- **Semantic coverage:** required measures, dimensions, filters, and time fields exist.
- **Data quality and freshness:** important fields are populated, typed, current enough, and have usable value patterns.
- **Modelability:** grain is clear, joins are supported by constraints/profiling/query history/user confirmation, and Metric Views already govern semantic logic when applicable.
- **GenAI context readiness:** table/column/Metric View descriptions, synonyms, display names, and prompt matching choices map business language to data.

For each business question, assign:

- **High:** all required sources, fields, values, and join/metric definitions are supported, and the Context Evidence Gate is met.
- **Medium:** answerable with caveats, missing descriptions, uncertain filters, or user-confirmed assumptions.
- **Low:** missing source, measure, dimension, time field, join path, or governed metric definition.

Do not present Low-confidence questions as fully supported. Add data, revise the question, ask for confirmation, or mark the space as a draft.
