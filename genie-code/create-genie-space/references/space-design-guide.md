# Genie Space Design Guide

Use this reference when creating or reviewing a Genie Space in Genie Code.

## Read-Only Discovery

Use focused SQL only when workspace metadata is not enough:

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

```sql
DESCRIBE TABLE EXTENDED <catalog.schema.metric_view> AS JSON;
```

```sql
SELECT <category_col>, COUNT(*) AS row_count
FROM <catalog>.<schema>.<table>
GROUP BY <category_col>
ORDER BY row_count DESC
LIMIT 50;
```

For Metric Views, validate query examples with explicit dimensions and `MEASURE()`:

```sql
SELECT
  <dimension_name>,
  MEASURE(<measure_name>) AS <measure_alias>
FROM <catalog>.<schema>.<metric_view>
GROUP BY ALL
LIMIT 20;
```

## Design Priorities

Prefer structured context over broad instructions:

1. Focused data source selection.
2. Table, Metric View, and column descriptions.
3. Synonyms and display names for business terms.
4. Prompt matching for eligible categorical strings.
5. Join specs for raw tables exposed together.
6. SQL snippets for reusable filters, expressions, and measures.
7. Example SQL for complex question patterns.
8. Short text instructions only for global conventions.

## Metric View Guidance

- Treat Metric Views as governed semantic sources.
- Do not attach underlying raw tables unless users also need raw-detail questions.
- Do not duplicate Metric View formulas in snippets or examples unless the example teaches a query shape.
- If the semantic model is wrong or missing a governed measure, dimension, join, or filter, document that as an upstream modeling issue instead of working around it with broad Genie instructions.
- Do not use `SELECT *` against Metric Views in examples or benchmarks.
- If a Metric View output must be combined with another source, wrap the Metric View query in a CTE before joining.

## Static Health Checks

Check the draft for:

- A focused source set, ideally 5 or fewer at first.
- Descriptions that state business purpose and grain.
- Hidden ingestion, audit, hash, raw JSON, embedding, and sensitive free-text fields.
- Prompt matching only on useful eligible categorical strings.
- Joins supported by constraints, naming, row-count checks, or user confirmation.
- No long rulebook-style text instructions.
- Example SQL that teaches reusable patterns, not memorized test questions.
- Benchmarks with one checked SQL answer each and coverage across sources, filters, measures, joins, time logic, and answer shapes.
