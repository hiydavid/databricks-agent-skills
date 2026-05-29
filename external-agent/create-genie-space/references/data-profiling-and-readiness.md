# Data Profiling And Readiness

Use this reference after candidate data sources are selected and before authoring a Genie Space. The goal is to understand whether the data can answer the user's real business questions, not to produce a broad data audit.

## Phased Inspection

Run inspection in phases and summarize insights between phases.

1. **Structure.** Confirm each object exists, capture table/view/Metric View type, comments, columns, data types, constraints, and sample rows with a narrow selected column list.
2. **Quality and usage.** Profile nulls, empty strings, constants, distinct counts, casing issues, boolean-as-string values, sensitive/noisy columns, and usage/lineage when system tables are accessible.
3. **Column profiling.** Profile only columns that affect Genie quality: dates, likely filters, categorical strings, join keys, and candidate measures.
4. **Readiness.** Map the profiled data back to the user's 3-5 business questions and record High/Medium/Low confidence for each question.

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

Row count, key cardinality, and date range:

```sql
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT <candidate_key>) AS distinct_key_count,
  MIN(<date_col>) AS min_date,
  MAX(<date_col>) AS max_date
FROM <catalog>.<schema>.<table>;
```

Null, empty, and distinct metrics for a small column batch:

```sql
SELECT
  SUM(CASE WHEN <col_a> IS NULL THEN 1 ELSE 0 END) AS col_a_nulls,
  COUNT(DISTINCT <col_a>) AS col_a_distinct,
  SUM(CASE WHEN TRIM(CAST(<col_a> AS STRING)) = '' AND <col_a> IS NOT NULL THEN 1 ELSE 0 END) AS col_a_empty
FROM <catalog>.<schema>.<table>;
```

Categorical values for prompt matching and examples:

```sql
SELECT <category_col>, COUNT(*) AS row_count
FROM <catalog>.<schema>.<table>
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
FROM <catalog>.<schema>.<table>;
```

Casing and boolean-as-string checks for low-cardinality strings:

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

Join overlap and cardinality direction:

```sql
SELECT
  COUNT(*) AS left_rows,
  COUNT(DISTINCT l.<left_key>) AS left_key_count,
  COUNT(DISTINCT r.<right_key>) AS matched_right_key_count
FROM <catalog>.<schema>.<left_table> l
LEFT JOIN <catalog>.<schema>.<right_table> r
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

Before JSON authoring, summarize readiness against the user's business questions:

- **Semantic coverage:** required measures, dimensions, filters, and time fields exist.
- **Data quality and freshness:** important fields are populated, typed, current enough, and have usable value patterns.
- **Modelability:** grain is clear, joins are supported by constraints/profiling/query history/user confirmation, and Metric Views already govern semantic logic when applicable.
- **GenAI context readiness:** table/column/Metric View descriptions, synonyms, display names, and prompt matching choices map business language to data.

For each business question, assign:

- **High:** all required sources, fields, values, and join/metric definitions are supported.
- **Medium:** answerable with caveats, missing descriptions, uncertain filters, or user-confirmed assumptions.
- **Low:** missing source, measure, dimension, time field, join path, or governed metric definition.

Do not present Low-confidence questions as fully supported. Add data, revise the question, ask for confirmation, or mark the space as a draft.
