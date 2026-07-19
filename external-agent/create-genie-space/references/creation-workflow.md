# Genie Space Creation Workflow

Use this reference after the skill triggers. Keep the final JSON compact, valid, and grounded in read-only dataset evidence.

## 1. Inputs To Collect

Minimum required inputs:

- Catalog and schema containing the datasets.
- Data object names and types: table/view identifiers for `data_sources.tables`, Metric View identifiers for `data_sources.metric_views`, or a mix of both. Use fully qualified `catalog.schema.object` identifiers when available.
- Space purpose, intended user group, and 3-5 real business questions the space should answer.

Ask only when needed:

- Whether any listed object is a Metric View and whether SQL functions should be included.
- Expected joins, business metrics, default filters, fiscal calendar, timezone, row-level security caveats, and sensitive columns.
- Desired output path for the decoded `serialized_space` JSON.
- For API payloads: `title`, `parent_path`, and `warehouse_id`.
- For live creation: Databricks profile/workspace and explicit permission to create the space.

## 2. Discovery And Feasibility

Use the user's business questions to drive source selection.

If the user does not know the source objects, search or browse Unity Catalog with:

- Exact terms from the business questions.
- Synonyms and abbreviations: customer/client/account, transaction/txn/trx, diagnosis/dx, procedure/px, etc.
- Related entities that would answer the questions: facts, dimensions, date tables, customer/product/region/account tables.
- Common naming patterns: `fact_`, `dim_`, `gold_`, `silver_`, `analytics`, `summary`, `metric`.

Recommend a focused set, ideally 5 or fewer data objects initially. Explain which business questions each object supports and which objects you would skip because they are staging/raw/noisy or unrelated.

Before deep profiling, do a feasibility check:

- Each business question has plausible measures, dimensions, filters, and time fields.
- Multi-table questions have plausible join paths.
- Metric questions are either governed by Metric Views or have user-confirmed definitions.
- Questions with missing sources or ambiguous definitions are called out before JSON authoring.

If the selected data cannot support a question, ask the user to add data, revise the question, or proceed with an explicit Low-confidence limitation.

## 3. Read-Only DBSQL Discovery And Profiling

Use DBSQL MCP or native Databricks SQL. Keep queries targeted and bounded.

Confirm data objects:

```sql
SHOW TABLES IN <catalog>.<schema>;
```

Inspect table/view metadata:

```sql
SELECT table_catalog, table_schema, table_name, table_type, comment
FROM `<catalog>`.information_schema.tables
WHERE table_schema = '<schema>'
  AND table_name IN ('object_1', 'object_2')
ORDER BY table_name;
```

Inspect table/view columns:

```sql
SELECT table_name, ordinal_position, column_name, data_type, comment
FROM `<catalog>`.information_schema.columns
WHERE table_schema = '<schema>'
  AND table_name IN ('object_1', 'object_2')
ORDER BY table_name, ordinal_position;
```

Inspect constraints when available:

```sql
SELECT table_name, constraint_name, constraint_type
FROM `<catalog>`.information_schema.table_constraints
WHERE table_schema = '<schema>'
  AND table_name IN ('table_1', 'table_2')
ORDER BY table_name, constraint_name;
```

Inspect row counts from information schema when available:

```sql
SELECT table_name, row_count
FROM `<catalog>`.information_schema.tables
WHERE table_schema = '<schema>'
  AND table_name IN ('object_1', 'object_2')
ORDER BY table_name;
```

For Metric Views, inspect the definition and agent metadata:

```sql
DESCRIBE TABLE EXTENDED <catalog.schema.metric_view_name> AS JSON;
```

The returned definition can include dimensions, measures, filters, joins, and agent metadata. Use it to understand what the Metric View already defines before adding extra Genie instructions.

Use `data-profiling-and-readiness.md` for the full profiling workflow. At minimum, profile row count, grain, key cardinality, date freshness, categorical values, null/empty/constant columns, casing issues, boolean-as-string values, noisy/sensitive fields, and join evidence.

Use bounded profiling for candidate table/view columns:

```sql
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT <candidate_key>) AS distinct_key_count,
  MIN(<date_col>) AS min_date,
  MAX(<date_col>) AS max_date
FROM <catalog>.<schema>.<table>;
```

Profile null, empty-string, and distinct-count signals in small batches:

```sql
SELECT
  SUM(CASE WHEN <col_a> IS NULL THEN 1 ELSE 0 END) AS col_a_nulls,
  COUNT(DISTINCT <col_a>) AS col_a_distinct,
  SUM(CASE WHEN TRIM(CAST(<col_a> AS STRING)) = '' AND <col_a> IS NOT NULL THEN 1 ELSE 0 END) AS col_a_empty
FROM <catalog>.<schema>.<table>;
```

For likely categorical filters in table/view data, sample distinct values with limits:

```sql
SELECT <category_col>, COUNT(*) AS row_count
FROM <catalog>.<schema>.<table>
GROUP BY <category_col>
ORDER BY row_count DESC
LIMIT 50;
```

For low-cardinality strings that users might filter by, check casing and boolean-as-string issues:

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

For likely joins, validate overlap and cardinality before adding join specs:

```sql
SELECT
  COUNT(*) AS left_rows,
  COUNT(DISTINCT l.<left_key>) AS left_key_count,
  COUNT(DISTINCT r.<right_key>) AS matched_right_key_count
FROM <catalog>.<schema>.<left_table> l
LEFT JOIN <catalog>.<schema>.<right_table> r
  ON l.<left_key> = r.<right_key>;
```

Use query history and lineage when accessible. Treat this as best-effort evidence; do not block creation if system tables are unavailable:

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

For sample rows, use `LIMIT` and select only the columns needed to understand meaning:

```sql
SELECT <column_a>, <column_b>, <column_c>
FROM <catalog>.<schema>.<table>
LIMIT 20;
```

For Metric View validation queries, explicitly list dimensions and wrap measures with `MEASURE()`:

```sql
SELECT
  <dimension_name>,
  MEASURE(<measure_name>) AS <measure_alias>
FROM <catalog>.<schema>.<metric_view>
GROUP BY ALL
LIMIT 20;
```

Do not use `SELECT *` against Metric Views in examples or benchmarks because measures must be evaluated with `MEASURE()`.

## 4. Interpret The Dataset

For each table or standard view, identify:

- Grain: one row per order, account, event, daily snapshot, line item, etc.
- Primary time columns and their timezone/date grain.
- Measures: additive amounts, counts, balances, ratios, durations.
- Dimensions: customer, product, region, status, type, category, owner.
- Filter columns users are likely to mention.
- Internal or noisy fields to hide: ingestion metadata, raw blobs, technical hashes, duplicate IDs, audit columns, unused PII.
- Join keys and relationship direction.
- Query-history patterns that should influence joins, examples, sample questions, and benchmarks.

For each Metric View, identify:

- Dimensions users can group by or filter on.
- Measures users can ask for, including display names, synonyms, and formatting.
- Built-in filters, joins, and source tables/views already encoded in the Metric View.
- Whether agent metadata covers expected business terms. If it does, prefer relying on the Metric View instead of duplicating formulas in Genie SQL snippets.
- Representative query patterns that use `MEASURE()` correctly.
- Whether mixed queries need to join Metric View results to tables/views. Metric Views cannot be joined directly to tables at query time; wrap the Metric View query in a CTE and join the CTE result.

Ask the user to confirm any join or metric definition that is not supported by constraints, naming, or profiling evidence.

Assess readiness before authoring:

- **Semantic coverage:** required measures, dimensions, filters, and time fields exist.
- **Data quality and freshness:** important fields are populated, typed, current enough, and have usable value patterns.
- **Modelability:** grain is clear and joins are supported by constraints, profiling, query history, or user confirmation.
- **GenAI context readiness:** descriptions, synonyms, display names, and prompt matching choices map business language to data.

Assign High/Medium/Low confidence to each business question. Do not present Low-confidence questions as supported without limitations.

## 5. Author The Version 2 JSON

Start from this shape:

```json
{
  "version": 2,
  "config": {
    "sample_questions": []
  },
  "data_sources": {
    "tables": [],
    "metric_views": []
  },
  "instructions": {
    "text_instructions": [],
    "example_question_sqls": [],
    "sql_functions": [],
    "join_specs": [],
    "sql_snippets": {
      "filters": [],
      "expressions": [],
      "measures": []
    }
  },
  "benchmarks": {
    "questions": []
  }
}
```

Generate every `id` as a unique 32-character lowercase hex string. Sort arrays as described in `space-schema.md`.

### Surface Routing

Prefer the most structured Genie surface that can represent the behavior, using the canonical priority order in `best-practices-checklist.md` (Metric View semantic metadata first, text instructions last).

### Data Sources

Use fully qualified identifiers: `catalog.schema.object`. Put tables and standard views in `data_sources.tables`. Put Metric Views in `data_sources.metric_views`.

Keep the total number of attached tables/views/Metric Views focused: ideally 5 or fewer at first, and no more than 30.

For Metric View-only spaces, `data_sources.tables` can be empty. Do not add the Metric View's underlying source tables unless users need to ask questions that the Metric View cannot answer.

Write table descriptions that state grain and purpose:

```json
"description": ["Order line items with one row per product per order, used for revenue, quantity, discount, and fulfillment analysis."]
```

Write Metric View descriptions that state the business domain, core measures, key dimensions, and any built-in scope:

```json
"description": ["Revenue Metric View with measures for total revenue and order count, dimensions for order date, status, and customer segment, and built-in business definitions for fulfilled orders."]
```

### Columns

Create `column_configs` for columns that Genie can see, plus hidden configs for noisy columns. Use descriptions that add business meaning beyond the name.

For version 2 spaces:

- Use `enable_format_assistance`, not `get_example_values`.
- Use `enable_entity_matching`, not `build_value_dictionary`.
- Set `enable_entity_matching: true` only when `enable_format_assistance: true`.

Recommended defaults:

- Key dimensions and likely filters: `enable_format_assistance: true`.
- Low/medium-cardinality string categories with stable values: `enable_entity_matching: true`.
- Dates, timestamps, IDs, numeric measures: usually `enable_entity_matching: false`.
- High-cardinality free text, notes, emails, URLs, raw JSON, embeddings, and sensitive free text: hide or keep entity matching off.
- Technical columns not useful to end users: `exclude: true`.
- Join keys: keep visible only if users ask about them or Genie needs them for relationships; otherwise describe clearly and consider hiding if joins are fully specified.

### Text Instructions

Use at most one text instruction. Keep it short, global, and under 2,000 characters when possible. Format it with the canonical GSL section template in `space-schema.md` (Text Instructions), omitting empty sections.

Good candidates:

- Fiscal calendar or timezone conventions.
- Default active/current-row rules that cannot be represented as snippets.
- Ambiguous term handling that should trigger clarification.
- Data quality notes that affect SQL generation, such as inconsistent casing or boolean-as-string fields.
- Hard constraints such as PII columns or raw token fields never to project.
- Response conventions that apply across all attached data objects.

Do not put table-specific SQL, metric formulas, join logic, or long documentation in text instructions. Use metadata, snippets, join specs, example SQLs, or functions.

### Join Specs

Add join specs for multi-table/table-view spaces when joins are supported by constraints, naming, or user confirmation.

- Each `sql[0]` should be one equality condition only, such as `orders.customer_id = customers.customer_id`.
- `sql[1]` must be one relationship annotation:
  - `--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--`
  - `--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--`
  - `--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_ONE--`
  - `--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_MANY--`
- For compound joins, create one join spec per equality and use `comment`/`instruction` to say they must be used together.
- Use `comment` for business meaning and `instruction` for when to use the join.
- Do not add direct join specs between Metric Views and tables/views unless the Genie serialized-space schema and API behavior are known to support that exact pattern. For mixed Metric View plus table examples, use an example SQL with a CTE that first aggregates the Metric View, then joins the CTE result to the table/view.

### SQL Snippets

Use snippets for reusable business logic:

- `filters`: active records, non-cancelled orders, current snapshots, standard time windows.
- `expressions`: derived dimensions, bucketing, status normalization.
- `measures`: standard aggregations, KPIs, numerators, denominators, ratios.

Each snippet needs a non-empty `sql`, clear display name/alias, synonyms, instruction, and comment. Prefer snippets over text instructions for formulas and filters.

### Example SQLs

Use example SQLs only for representative patterns Genie may not infer from metadata and snippets:

- Multi-table joins.
- Window functions, ranking, cohort analysis, period-over-period comparisons.
- Complex metric composition or result shape.
- Metric View queries that require explicit dimensions and `MEASURE()` calls.
- Mixed Metric View plus table/view queries that require the CTE wrapping pattern.

Keep examples concise. Include `usage_guidance` for complex examples. Do not copy benchmark questions or benchmark answer SQL verbatim.

For parameterized example SQL:

- The natural-language question should use a concrete real value, not a placeholder.
- SQL may use `:param_name` placeholders.
- Every parameter must have `name`, `description`, `type_hint`, and a real `default_value` from profiling.
- Test parameterized SQL by substituting the default values before including it.

### Sample Questions

Create 5-8 sample questions that demonstrate the space's strongest use cases. They should be user-facing prompts, not tests, and should cover distinct data objects/patterns.

### Benchmarks

For an eval-ready space, target 30 diverse benchmark Q/A pairs. Include fewer only when the data scope cannot support more or the user asks for a lightweight starter config.

Only include benchmark SQL that has been checked with read-only SQL execution or `EXPLAIN`. Benchmarks must use concrete real values, not parameters. Avoid benchmark SQL that returns zero rows unless the question is explicitly testing empty-result behavior. If validation is not possible, return benchmark candidates outside the JSON.

## 6. Validate And Package

Run the validator, resolving `<skill-dir>` to wherever this skill is installed:

```bash
python3 <skill-dir>/scripts/validate_space_json.py <path-to-serialized-space.json>
```

Fix errors before creating an API payload. Review warnings against `best-practices-checklist.md`.

Also validate every SQL-bearing surface before including it where possible:

- Example SQLs and benchmark SQLs should execute or pass `EXPLAIN`.
- SQL snippets should be wrapped in simple `SELECT` queries and tested.
- Join specs should be tested with `SELECT 1 ... JOIN ... LIMIT 1`.
- Metric View examples and benchmarks must use `MEASURE()` and must not directly join Metric Views to other tables without a CTE.

To build a create-space request body, wrap the decoded JSON as a string:

```bash
jq -n \
  --arg title "<space title>" \
  --arg parent_path "<workspace folder path>" \
  --arg warehouse_id "<warehouse id>" \
  --rawfile serialized_space "<path-to-serialized-space.json>" \
  '{
    title: $title,
    parent_path: $parent_path,
    warehouse_id: $warehouse_id,
    serialized_space: $serialized_space
  }' > "<path-to-create-request.json>"
```

Live creation, only when explicitly requested:

```bash
databricks api post /api/2.0/genie/spaces -p <profile> --json @<path-to-create-request.json> -o json
```
