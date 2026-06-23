# Metric View Profiling And Validation

Use this reference for bounded read-only inspection before drafting or validating a Metric View. Prefer Databricks-native metadata first, then run focused SQL only where it improves semantic confidence. Treat "read-only" as separate from "cheap": avoid broad scans unless the user approves the cost and purpose.

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

Inspect column tags and governance signals to discover security caveats (PII, restricted columns) instead of only asking the user, when these views are accessible (column names follow Unity Catalog `information_schema`; adjust if your environment differs):

```sql
SELECT table_name, column_name, tag_name, tag_value
FROM <catalog>.information_schema.column_tags
WHERE schema_name = '<schema>'
  AND table_name IN ('<table_1>', '<table_2>')
ORDER BY table_name, column_name;
```

Discover and inspect existing Metric Views before authoring a new one. Metric Views appear among the views listed by the tables query above; introspect each candidate's definition and agent metadata with `AS JSON`, then reuse or extend its governed semantics rather than duplicating formulas:

```sql
DESCRIBE TABLE EXTENDED <catalog.schema.metric_view_name> AS JSON;
```

## Source Profiling Templates

Bound profiling with one or more of these controls:

- Start with metadata such as `DESCRIBE TABLE`, `DESCRIBE TABLE EXTENDED`, constraints, comments, and available statistics.
- Use partition, date, tenant, business-unit, or other scoped predicates before aggregate scans.
- Use samples for exploratory value discovery and clearly label them as samples.
- Use approximate aggregates such as `approx_count_distinct` when exact values are not required.
- Ask before running full-table exact counts, full-table distinct counts, or joins across large objects.

Metadata and table detail:

```sql
DESCRIBE TABLE EXTENDED <catalog>.<schema>.<table>;
```

Scoped row count, key cardinality, and date range:

```sql
WITH scoped AS (
  SELECT <candidate_key>, <date_col>
  FROM <catalog>.<schema>.<table>
  WHERE <scope_predicate>
)
SELECT
  COUNT(*) AS scoped_row_count,
  approx_count_distinct(<candidate_key>) AS approx_distinct_key_count,
  MIN(<date_col>) AS min_date,
  MAX(<date_col>) AS max_date
FROM scoped;
```

Scoped null, empty, and distinct checks for KPI and field columns:

```sql
WITH scoped AS (
  SELECT <col_a>, <col_b>
  FROM <catalog>.<schema>.<table>
  WHERE <scope_predicate>
)
SELECT
  SUM(CASE WHEN <col_a> IS NULL THEN 1 ELSE 0 END) AS col_a_nulls,
  approx_count_distinct(<col_a>) AS approx_col_a_distinct,
  SUM(CASE WHEN TRIM(CAST(<col_a> AS STRING)) = '' AND <col_a> IS NOT NULL THEN 1 ELSE 0 END) AS col_a_empty,
  SUM(CASE WHEN <col_b> IS NULL THEN 1 ELSE 0 END) AS col_b_nulls,
  approx_count_distinct(<col_b>) AS approx_col_b_distinct
FROM scoped;
```

Categorical values for candidate filters and display fields:

```sql
WITH scoped AS (
  SELECT <category_col>
  FROM <catalog>.<schema>.<table>
  WHERE <scope_predicate>
)
SELECT <category_col>, COUNT(*) AS row_count
FROM scoped
WHERE <category_col> IS NOT NULL
GROUP BY <category_col>
ORDER BY row_count DESC
LIMIT 50;
```

String normalization and boolean-as-string checks:

```sql
WITH scoped AS (
  SELECT <string_col>
  FROM <catalog>.<schema>.<table>
  WHERE <scope_predicate>
)
SELECT
  LOWER(CAST(<string_col> AS STRING)) AS normalized_value,
  COLLECT_SET(CAST(<string_col> AS STRING)) AS variants,
  COUNT(*) AS row_count
FROM scoped
WHERE <string_col> IS NOT NULL
GROUP BY LOWER(CAST(<string_col> AS STRING))
HAVING COUNT(DISTINCT CAST(<string_col> AS STRING)) > 1
   OR LOWER(CAST(<string_col> AS STRING)) IN ('true', 'false', 'yes', 'no', 'y', 'n')
ORDER BY row_count DESC
LIMIT 50;
```

Measure-input sanity checks:

```sql
WITH scoped AS (
  SELECT <measure_col>
  FROM <catalog>.<schema>.<table>
  WHERE <scope_predicate>
)
SELECT
  COUNT(*) AS scoped_row_count,
  SUM(CASE WHEN <measure_col> IS NULL THEN 1 ELSE 0 END) AS measure_col_nulls,
  MIN(<measure_col>) AS min_measure_col,
  MAX(<measure_col>) AS max_measure_col,
  SUM(<measure_col>) AS sum_measure_col,
  AVG(<measure_col>) AS avg_measure_col
FROM scoped;
```

Candidate model-level filter impact:

```sql
WITH scoped AS (
  SELECT <filter_columns>
  FROM <catalog>.<schema>.<table>
  WHERE <scope_predicate>
)
SELECT
  COUNT(*) AS scoped_rows,
  SUM(CASE WHEN <candidate_filter> THEN 1 ELSE 0 END) AS in_scope_rows,
  SUM(CASE WHEN NOT (<candidate_filter>) OR <candidate_filter> IS NULL THEN 1 ELSE 0 END) AS out_of_scope_rows
FROM scoped;
```

## Join Validation Templates

Check whether the joined side is unique before using `rely.at_most_one_match: true`:

```sql
SELECT
  <dimension_key>,
  COUNT(*) AS row_count
FROM <catalog>.<schema>.<dimension_table>
WHERE <dimension_scope_predicate>
GROUP BY <dimension_key>
HAVING COUNT(*) > 1
ORDER BY row_count DESC
LIMIT 50;
```

Many-to-one base versus joined row behavior:

```sql
WITH source_scope AS (
  SELECT <source_row_id>, <source_key>
  FROM <catalog>.<schema>.<source_table>
  WHERE <source_scope_predicate>
),
dimension_scope AS (
  SELECT <dimension_key>
  FROM <catalog>.<schema>.<dimension_table>
  WHERE <dimension_scope_predicate>
),
joined AS (
  SELECT
    s.<source_row_id>,
    s.<source_key>,
    d.<dimension_key> AS matched_dimension_key
  FROM source_scope s
  LEFT JOIN dimension_scope d
    ON s.<source_key> = d.<dimension_key>
)
SELECT
  (SELECT COUNT(*) FROM source_scope) AS base_rows,
  (SELECT COUNT(*) FROM joined) AS joined_rows,
  (SELECT COUNT(*) FROM joined WHERE matched_dimension_key IS NULL) AS unmatched_rows,
  (SELECT COUNT(*) FROM joined) - (SELECT COUNT(*) FROM source_scope) AS fanout_rows;
```

Source rows with multiple joined matches:

```sql
WITH source_scope AS (
  SELECT <source_row_id>, <source_key>
  FROM <catalog>.<schema>.<source_table>
  WHERE <source_scope_predicate>
),
dimension_scope AS (
  SELECT <dimension_key>
  FROM <catalog>.<schema>.<dimension_table>
  WHERE <dimension_scope_predicate>
)
SELECT
  s.<source_row_id>,
  s.<source_key>,
  COUNT(d.<dimension_key>) AS match_count
FROM source_scope s
LEFT JOIN dimension_scope d
  ON s.<source_key> = d.<dimension_key>
GROUP BY s.<source_row_id>, s.<source_key>
HAVING COUNT(d.<dimension_key>) > 1
ORDER BY match_count DESC
LIMIT 50;
```

One-to-many branch profile:

```sql
WITH source_scope AS (
  SELECT <source_key>
  FROM <catalog>.<schema>.<source_table>
  WHERE <source_scope_predicate>
),
fact_scope AS (
  SELECT <fact_key>, <fact_source_key>
  FROM <catalog>.<schema>.<fact_table>
  WHERE <fact_scope_predicate>
)
SELECT
  (SELECT COUNT(*) FROM source_scope) AS source_rows,
  approx_count_distinct(s.<source_key>) AS approx_source_keys,
  COUNT(f.<fact_key>) AS joined_fact_rows,
  approx_count_distinct(f.<fact_key>) AS approx_joined_fact_keys
FROM source_scope s
LEFT JOIN fact_scope f
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

In these skeletons `version: 1.1` enables agent metadata and requires the supporting runtime (see Feature Availability in `metric-view-design-guide.md`); use the supported baseline version when agent metadata is not available.

Create a new Metric View only after user approval:

```sql
CREATE VIEW <catalog.schema.metric_view_name> WITH METRICS LANGUAGE YAML AS
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

Replace a Metric View only after explicit replacement approval:

```sql
CREATE OR REPLACE VIEW <catalog.schema.metric_view_name> WITH METRICS LANGUAGE YAML AS
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

Update an existing Metric View only after user approval. The update form is bare `ALTER VIEW <target> AS $$ ... $$`; the `WITH METRICS LANGUAGE YAML` marker appears only on `CREATE` and `CREATE OR REPLACE`:

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
- KPI and question confidence: High, Medium, or Low (levels defined in `metric-view-design-guide.md`, Feasibility Check).
- Read-only profiling performed and important caveats.
- Join/cardinality evidence and whether `rely` is justified.
- Representative Metric View queries checked with `MEASURE()`.
- Known source-total or expert-example comparisons.
- DDL not executed unless the user approved it.
