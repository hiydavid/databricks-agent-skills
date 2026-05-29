# Genie Space Design Guide

Use this reference when creating or reviewing a Genie Space in Genie Code.

## Requirements And Discovery

Start from the user's actual intent:

- Capture purpose, audience, draft title, and 3-5 concrete business questions.
- Capture business terms, metric definitions, fiscal/calendar conventions, default filters, security caveats, and benchmark mode.
- If objects are not specified, search or browse with exact terms, synonyms, abbreviations, related entities, and common fact/dimension naming patterns.
- Recommend a focused source set, ideally 5 or fewer objects initially, and explain how each source maps to the business questions.

Before deeper profiling, check feasibility. Flag missing measures, dimensions, time fields, Metric View measures, or join paths. Let the user add sources, adjust questions, or proceed with explicit limitations.

## Read-Only Discovery And Profiling

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

```sql
SELECT
  SUM(CASE WHEN <col_a> IS NULL THEN 1 ELSE 0 END) AS col_a_nulls,
  COUNT(DISTINCT <col_a>) AS col_a_distinct,
  SUM(CASE WHEN TRIM(CAST(<col_a> AS STRING)) = '' AND <col_a> IS NOT NULL THEN 1 ELSE 0 END) AS col_a_empty
FROM <catalog>.<schema>.<table>;
```

```sql
SELECT
  COUNT(*) AS left_rows,
  COUNT(DISTINCT l.<left_key>) AS left_key_count,
  COUNT(DISTINCT r.<right_key>) AS matched_right_key_count
FROM <catalog>.<schema>.<left_table> l
LEFT JOIN <catalog>.<schema>.<right_table> r
  ON l.<left_key> = r.<right_key>;
```

Use `references/data-profiling-and-readiness.md` for row counts, grain, freshness/date ranges, null/empty/constant columns, cardinality, casing, boolean-as-string, PII/ETL/noisy fields, usage/lineage, and per-question readiness.

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

1. Metric View semantic metadata when it already owns the business definition.
2. Focused data source selection.
3. Table, Metric View, and column descriptions.
4. Synonyms and display names for business terms.
5. Format assistance and entity matching for eligible categorical strings.
6. Join specs for raw tables exposed together.
7. SQL snippets for reusable filters, expressions, and measures not already governed by Metric Views.
8. Example SQL for complex question patterns.
9. SQL functions for trusted registered logic.
10. Short text instructions only for global behavior that cannot be encoded structurally.

## Text Instruction Last-Resort Rule

Do not use text instructions as the default place for guardrails, policies, metric logic, table-selection rules, join rules, filter rules, ranking/windowing rules, or long best-practice lists. If the proposed instruction names specific tables, Metric Views, columns, joins, filters, denominators, numerators, aliases, ranking logic, or window logic, first try to encode the rule in focused source selection, Metric View metadata, source/column descriptions, synonyms, prompt matching, format assistance, entity matching, join specs, SQL snippets, representative example SQL, SQL functions, or an upstream semantic model fix.

Use text instructions only for global behavior that cannot be encoded structurally, such as broad ambiguity handling, response-quality expectations, caveats, or user-facing summary constraints. When proposing or editing text instructions, carry over the optimization-style justification requirement and adapt it for creation/refinement context:

```markdown
## Text Instruction Justification

- Exact instruction text:
- Why structured surfaces were insufficient:
- Intended global behavior:
- Possible overreach or regression risk:
- How the instruction will be reviewed or validated:
```

## Metric View Guidance

- Treat Metric Views as governed semantic sources.
- Do not attach underlying raw tables unless users also need raw-detail questions.
- Do not duplicate Metric View formulas in snippets or examples unless the example teaches a query shape.
- If the semantic model is wrong or missing a governed measure, dimension, join, or filter, document that as an upstream modeling issue instead of working around it with broad Genie instructions.
- Do not use `SELECT *` against Metric Views in examples or benchmarks.
- If a Metric View output must be combined with another source, wrap the Metric View query in a CTE before joining.

## Examples And Benchmarks

- Validate every example SQL, benchmark SQL, snippet, and join with read-only execution or `EXPLAIN` when possible.
- Use real profiled values for parameter defaults, benchmark literals, and sample question wording.
- Parameterized examples may use `:param_name`, but every parameter needs a description, type hint, and real default value.
- Benchmarks should be concrete and hardcoded, not parameterized.
- Avoid zero-row benchmark SQL unless the benchmark explicitly tests empty results.
- Keep sample questions user-facing, example SQL instructive, and benchmarks evaluative. Do not copy benchmark questions or benchmark answer SQL into examples.

## Readiness

Before proposing a live change, summarize High/Medium/Low confidence for each business question:

- **Semantic coverage:** measures, dimensions, filters, and time fields exist.
- **Data quality and freshness:** important fields are populated, current, typed, and have usable values.
- **Modelability:** grain and join paths are supported by evidence or user confirmation.
- **GenAI context readiness:** descriptions, synonyms, display names, and prompt matching choices map business language to data.

## Static Health Checks

Check the draft for:

- A focused source set, ideally 5 or fewer at first.
- Descriptions that state business purpose and grain.
- Hidden ingestion, audit, hash, raw JSON, embedding, and sensitive free-text fields.
- Prompt matching only on useful eligible categorical strings.
- Joins supported by constraints, naming, row-count checks, or user confirmation.
- No long rulebook-style text instructions.
- Text instructions only for global behavior that cannot be encoded structurally, with adapted justification when proposed or edited.
- Example SQL that teaches reusable patterns, not memorized test questions.
- Example SQL parameters with real defaults and descriptions.
- Benchmarks with ground truth appropriate to the intended execution mode: checked SQL for deterministic Chat-style questions, evaluation notes for Agent-style multi-step analysis, and both when a deterministic question also needs full-response judging. Cover sources, filters, measures, joins, time logic, answer shapes, evidence quality, and response synthesis as applicable.
