# Metric View Profiling And Validation

Use this reference for bounded read-only inspection before drafting or validating a Metric View. Prefer Databricks-native metadata first, then run focused SQL only where it improves semantic confidence.

## Contents

- Phased Inspection
- Metadata Templates
- Source Profiling Templates
- Join Validation Templates
- Existing Usage Evidence
- Draft DDL Shapes
- Validation Query Templates
- Validation Summary

## Phased Inspection

1. **Confirm objects.** Verify source and target catalog/schema names, object types, comments, owners where visible, and permissions limitations.
2. **Inspect structure.** Read table/view/Metric View metadata, columns, types, comments, constraints, and existing definitions.
3. **Profile only relevant columns.** Focus on candidate keys, time fields, KPI inputs, filters, categorical dimensions, and join keys.
4. **Validate semantics.** Compare draft fields and measures to known examples, source totals, expert definitions, and representative `MEASURE()` queries.

## Metadata Templates

List tables and views in a schema:

```sql
SELECT table_catalog, table_schema, table_name, table_type, comment
FROM <catalog>.information_schema.tables
WHERE table_schema = '<schema>'
ORDER BY table_name;
```

Inspect columns:

```sql
SELECT table_name, ordinal_position, column_name, data_type, comment
FROM <catalog>.information_schema.columns
WHERE table_schema = '<schema>'
  AND table_name IN ('<table_1>', '<table_2>')
ORDER BY table_name, ordinal_position;
```

Inspect constraints when available:

```sql
SELECT table_name, constraint_name, constraint_type
FROM <catalog>.information_schema.table_constraints
WHERE table_schema = '<schema>'
  AND table_name IN ('<table_1>', '<table_2>')
ORDER BY table_name, constraint_name;
```

Inspect key-column usage when available:

```sql
SELECT constraint_name, table_name, column_name, ordinal_position
FROM <catalog>.information_schema.key_column_usage
WHERE table_schema = '<schema>'
  AND table_name IN ('<table_1>', '<table_2>')
ORDER BY table_name, constraint_name, ordinal_position;
```

Inspect an existing Metric View definition and agent metadata:

```sql
DESCRIBE TABLE EXTENDED <catalog.schema.metric_view_name> AS JSON;
```

## Source Profiling Templates

Row count, key cardinality, and date range:

```sql
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT <candidate_key>) AS distinct_key_count,
  MIN(<date_col>) AS min_date,
  MAX(<date_col>) AS max_date
FROM <catalog>.<schema>.<table>;
```

Null, empty, and distinct checks for KPI and field columns:

```sql
SELECT
  SUM(CASE WHEN <col_a> IS NULL THEN 1 ELSE 0 END) AS col_a_nulls,
  COUNT(DISTINCT <col_a>) AS col_a_distinct,
  SUM(CASE WHEN TRIM(CAST(<col_a> AS STRING)) = '' AND <col_a> IS NOT NULL THEN 1 ELSE 0 END) AS col_a_empty,
  SUM(CASE WHEN <col_b> IS NULL THEN 1 ELSE 0 END) AS col_b_nulls,
  COUNT(DISTINCT <col_b>) AS col_b_distinct
FROM <catalog>.<schema>.<table>;
```

Categorical values for candidate filters and display fields:

```sql
SELECT <category_col>, COUNT(*) AS row_count
FROM <catalog>.<schema>.<table>
WHERE <category_col> IS NOT NULL
GROUP BY <category_col>
ORDER BY row_count DESC
LIMIT 50;
```

String normalization and boolean-as-string checks:

```sql
SELECT
  LOWER(CAST(<string_col> AS STRING)) AS normalized_value,
  COLLECT_SET(CAST(<string_col> AS STRING)) AS variants,
  COUNT(*) AS row_count
FROM <catalog>.<schema>.<table>
WHERE <string_col> IS NOT NULL
GROUP BY LOWER(CAST(<string_col> AS STRING))
HAVING COUNT(DISTINCT CAST(<string_col> AS STRING)) > 1
   OR LOWER(CAST(<string_col> AS STRING)) IN ('true', 'false', 'yes', 'no', 'y', 'n')
ORDER BY row_count DESC
LIMIT 50;
```

Measure-input sanity checks:

```sql
SELECT
  COUNT(*) AS row_count,
  SUM(CASE WHEN <measure_col> IS NULL THEN 1 ELSE 0 END) AS measure_col_nulls,
  MIN(<measure_col>) AS min_measure_col,
  MAX(<measure_col>) AS max_measure_col,
  SUM(<measure_col>) AS sum_measure_col,
  AVG(<measure_col>) AS avg_measure_col
FROM <catalog>.<schema>.<table>;
```

Candidate model-level filter impact:

```sql
SELECT
  COUNT(*) AS all_rows,
  SUM(CASE WHEN <candidate_filter> THEN 1 ELSE 0 END) AS in_scope_rows,
  SUM(CASE WHEN NOT (<candidate_filter>) OR <candidate_filter> IS NULL THEN 1 ELSE 0 END) AS out_of_scope_rows
FROM <catalog>.<schema>.<table>;
```

## Join Validation Templates

Many-to-one join overlap and fanout check:

```sql
SELECT
  COUNT(*) AS source_rows,
  COUNT(DISTINCT s.<source_key>) AS source_key_count,
  COUNT(DISTINCT d.<dimension_key>) AS matched_dimension_key_count,
  SUM(CASE WHEN d.<dimension_key> IS NULL THEN 1 ELSE 0 END) AS unmatched_source_rows
FROM <catalog>.<schema>.<source_table> s
LEFT JOIN <catalog>.<schema>.<dimension_table> d
  ON s.<source_key> = d.<dimension_key>;
```

Check whether the joined side is unique before using `rely.at_most_one_match: true`:

```sql
SELECT
  <dimension_key>,
  COUNT(*) AS row_count
FROM <catalog>.<schema>.<dimension_table>
GROUP BY <dimension_key>
HAVING COUNT(*) > 1
ORDER BY row_count DESC
LIMIT 50;
```

One-to-many branch profile:

```sql
SELECT
  COUNT(*) AS source_rows,
  COUNT(DISTINCT s.<source_key>) AS source_keys,
  COUNT(f.<fact_key>) AS joined_fact_rows,
  COUNT(DISTINCT f.<fact_key>) AS joined_fact_keys
FROM <catalog>.<schema>.<source_table> s
LEFT JOIN <catalog>.<schema>.<fact_table> f
  ON f.<fact_source_key> = s.<source_key>;
```

## Existing Usage Evidence

Use lineage and query history only when accessible. Treat missing system-table access as a limitation, not a failure.

```sql
SELECT source_table_full_name, target_table_full_name, source_type, target_type
FROM system.access.table_lineage
WHERE (source_table_full_name IN ('<catalog.schema.object>')
   OR target_table_full_name IN ('<catalog.schema.object>'))
  AND event_time >= date_sub(current_date(), 30)
LIMIT 50;
```

```sql
SELECT
  SUBSTRING(statement_text, 1, 800) AS query_preview,
  total_duration_ms,
  produced_rows
FROM system.query.history
WHERE start_time >= date_sub(current_date(), 30)
  AND execution_status = 'FINISHED'
  AND LOWER(statement_text) LIKE '%<catalog.schema.object>%'
ORDER BY start_time DESC
LIMIT 50;
```

## Draft DDL Shapes

Create or replace a Metric View only after user approval:

```sql
CREATE OR REPLACE VIEW <catalog.schema.metric_view_name> WITH METRICS LANGUAGE YAML AS
$$
version: 1.1
comment: "<business purpose and scope>"
source: <catalog.schema.source_object>

fields:
  - name: <Business Field>
    expr: <source_expression>
    comment: "<business meaning>"

measures:
  - name: <Business Measure>
    expr: <aggregate_expression>
    comment: "<business definition>"
$$;
```

Update an existing Metric View only after user approval:

```sql
ALTER VIEW <catalog.schema.metric_view_name>
AS
$$
version: 1.1
comment: "<business purpose and scope>"
source: <catalog.schema.source_object>
fields:
  - name: <Business Field>
    expr: <source_expression>
measures:
  - name: <Business Measure>
    expr: <aggregate_expression>
$$;
```

## Validation Query Templates

Validate fields and measures with explicit column lists:

```sql
SELECT
  `<field_name>`,
  MEASURE(`<measure_name>`) AS <measure_alias>
FROM <catalog>.<schema>.<metric_view_name>
GROUP BY ALL
ORDER BY `<field_name>`
LIMIT 50;
```

Validate filters:

```sql
SELECT
  `<filter_field>`,
  MEASURE(`<measure_name>`) AS <measure_alias>
FROM <catalog>.<schema>.<metric_view_name>
WHERE `<filter_field>` = '<known_value>'
GROUP BY ALL
LIMIT 50;
```

Validate time fields:

```sql
SELECT
  `<time_field>`,
  MEASURE(`<measure_name>`) AS <measure_alias>
FROM <catalog>.<schema>.<metric_view_name>
GROUP BY ALL
ORDER BY `<time_field>`
LIMIT 100;
```

Use `EXPLAIN` for bounded shape checks:

```sql
EXPLAIN
SELECT
  `<field_name>`,
  MEASURE(`<measure_name>`) AS <measure_alias>
FROM <catalog>.<schema>.<metric_view_name>
GROUP BY ALL;
```

When joining Metric View output to another table for validation or downstream examples, wrap the Metric View query in a CTE:

```sql
WITH metric_result AS (
  SELECT
    `<field_key>` AS field_key,
    MEASURE(`<measure_name>`) AS <measure_alias>
  FROM <catalog>.<schema>.<metric_view_name>
  GROUP BY ALL
)
SELECT d.<dimension_label>, m.<measure_alias>
FROM metric_result m
JOIN <catalog>.<schema>.<dimension_table> d
  ON m.field_key = d.<dimension_key>
LIMIT 50;
```

## Validation Summary

Report:

- Source objects inspected and permission limitations.
- KPI and question confidence: High, Medium, or Low.
- Read-only profiling performed and important caveats.
- Join/cardinality evidence and whether `rely` is justified.
- Representative Metric View queries checked with `MEASURE()`.
- Known source-total or expert-example comparisons.
- DDL not executed unless the user approved it.
