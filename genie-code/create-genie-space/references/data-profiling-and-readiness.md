# Data Profiling And Readiness

Use this reference after candidate data sources are selected and before proposing Genie Space changes in Genie Code. Prefer Databricks-native metadata first, then run bounded, cost-aware, read-only SQL to build the evidence the design depends on.

## Context Evidence Gate

Before rating any business question High confidence or proposing a live Space, each included source must have, at minimum:

- Unity Catalog metadata and `DESCRIBE` output (columns, types, comments).
- A row count or a bounded estimate, with sampling or partition scope noted. Never present a sampled count as exact.
- A freshness signal (max event/load date, or lineage/refresh evidence).
- A narrow sample preview of the columns the business questions actually touch.
- Key and join evidence for every proposed relationship: declared constraints, naming, duplicate-key/cardinality checks, or query-history support.

Record any check you cannot complete (permissions, cost, or missing system tables) as an explicit confidence reduction for the affected questions, not a silent omission. Profiling is the evidence that justifies the readiness rating, not optional polish.

## Phased Inspection

1. **Structure.** Confirm each table/view/Metric View, comments, columns, data types, constraints, and sample rows with a narrow selected column list and `LIMIT`.
2. **Keys and relationships.** Read declared primary, foreign, and unique keys from `information_schema` before probing duplicate keys, so join specs start from documented relationships rather than guesses.
3. **Quality.** Profile nulls, empty strings, constants, distinct counts, casing issues, boolean-as-string values, and sensitive/noisy columns with scoped filters or samples before exact full-table scans.
4. **Usage and lineage.** Use table lineage and query history (where the system tables are available and authorized) to find real join paths, common filters, high-traffic columns, and benchmark/sample-question candidates. Treat this as primary design evidence, not an optional extra.
5. **Column profiling.** Profile only columns that affect Genie quality: dates, likely filters, categorical strings, join keys, and candidate measures.
6. **Readiness.** Map the profiled data back to the user's 3-5 business questions and score confidence using the rubric in **Readiness Assessment** below.

## Bounded Profiling Guardrails

- Start with `information_schema`, `DESCRIBE`, table comments, constraints, lineage, query history, and narrow previews.
- Treat exact full-table `COUNT`, `COUNT(DISTINCT)`, categorical scans, null scans, and join probes as broad scans unless table size or partition scope is known to be small.
- For large or unknown-size sources, use partition/date filters, recent slices, or samples to understand shape first. Do not present sampled counts as exact.
- Run exact full-table scans only when the result is needed for readiness, no cheaper metadata signal is available, and the user accepts the likely warehouse cost.

## Required Data Signals

For each table or standard view, identify row count or estimate, grain, freshness/date range, measures, dimensions, likely filters, data-quality caveats, sensitive/noisy fields, join candidates, and whether joins are supported by constraints, naming, duplicate-key/cardinality checks, query history, or user confirmation.

For each Metric View, identify governed measures, dimensions, filters, joins, time dimensions, display names, synonyms, formatting, comments, valid `MEASURE()` query patterns, and upstream semantic gaps.

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

Metric View metadata:

```sql
DESCRIBE TABLE EXTENDED <catalog.schema.metric_view> AS JSON;
```

Exact row count, key cardinality, and date range for small tables, filtered partitions, or approved full scans:

```sql
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT <candidate_key>) AS distinct_key_count,
  MIN(<date_col>) AS min_date,
  MAX(<date_col>) AS max_date
FROM <catalog>.<schema>.<table>
WHERE <partition_or_date_filter_if_available>;
```

Null, empty, and distinct metrics for selected columns. Use a filtered or sampled source first for large tables:

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

Categorical values for prompt matching candidates. Avoid sensitive fields and high-cardinality identifiers:

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

Casing and boolean-as-string checks:

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

Join cardinality and duplicate-key checks. Run on filtered or sampled sources first for large tables, and do not propose a Genie join when duplicate-key or many-to-many behavior is unresolved:

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

Metric View measure and dimension behavior:

```sql
SELECT
  <dimension_name>,
  MEASURE(<measure_name>) AS <measure_alias>
FROM <catalog>.<schema>.<metric_view>
GROUP BY ALL
LIMIT 20;
```

Recent usage and lineage when available:

```sql
SELECT source_table_full_name, target_table_full_name, source_type, target_type
FROM system.access.table_lineage
WHERE (source_table_full_name IN ('<catalog.schema.table>')
   OR target_table_full_name IN ('<catalog.schema.table>'))
  AND event_time >= date_sub(current_date(), 30)
LIMIT 50;
```

```sql
SELECT SUBSTRING(statement_text, 1, 500) AS query_preview, produced_rows
FROM system.query.history
WHERE start_time >= date_sub(current_date(), 7)
  AND execution_status = 'FINISHED'
  AND LOWER(statement_text) LIKE '%<catalog.schema.table>%'
ORDER BY start_time DESC
LIMIT 50;
```

Optional governance signals, only when these features are enabled and you are authorized to read them:

- Column-level classification or sensitivity tags exposed through `information_schema` tag metadata (for example `column_tags`) to spot fields to hide or keep out of prompt matching.
- Data-quality or freshness metrics from Lakehouse Monitoring output tables to gauge whether a field is reliable enough to expose.

If these tables are unavailable or access is denied, proceed without them and note any resulting confidence limitation.

## How To Use Findings

- Hide ETL metadata, all-null columns, raw blobs, embeddings, secrets, tokens, and sensitive free text.
- Put high-null, constant, inconsistent casing, and boolean-as-string caveats in `DATA QUALITY NOTES` only when Genie needs them.
- Enable format assistance on useful dimensions and filters only when representative values are safe to share in Space context. Enable entity matching only for stable low/medium-cardinality strings users are likely to mention, and disable it for sensitive fields or views over row filters, column masks, or dynamic views unless the user confirms the values are safe.
- Use actual profiled values for example SQL parameters and benchmark literals.
- Use query history as evidence for joins, sample questions, examples, and benchmarks. If system tables are unavailable, proceed without mentioning the failure unless it limits confidence.
- Ask the user to confirm metric formulas, joins, fiscal/calendar rules, and default filters that are not supported by evidence.

## Readiness Assessment

This is the canonical readiness rubric for the create-genie-space skill; `SKILL.md` and `space-design-guide.md` point here instead of redefining it.

Assess each business question across four dimensions:

- **Semantic coverage:** required measures, dimensions, filters, and time fields exist.
- **Data quality and freshness:** important fields are populated, current, correctly typed, and have usable values.
- **Modelability:** grain and join paths are supported by evidence or user confirmation.
- **GenAI context readiness:** descriptions, synonyms, display names, and prompt matching map business language to the data.

Then score each question:

- **High:** all required sources, fields, values, and join/metric definitions are supported, and the Context Evidence Gate is met.
- **Medium:** answerable with caveats, missing descriptions, uncertain filters, or user-confirmed assumptions.
- **Low:** missing source, measure, dimension, time field, join path, or governed metric definition.

Do not present Low-confidence questions as fully supported. Add data, revise the question, ask for confirmation, or mark the draft with limitations.
