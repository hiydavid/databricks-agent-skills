# Fix Taxonomy: Assessment Reasons → Config Fixes

The Benchmark API returns `assessment_reasons` for each failed evaluation result. This taxonomy maps those reasons to specific Genie Space configuration changes, organized by fix category.

## Fix Ordering

Apply fixes **left-to-right** — each category builds on the previous:

1. **UC Metadata** — table/column descriptions, synonyms, value dictionaries, join specs
2. **SQL Examples** — example_question_sqls, sql_snippets (measures, expressions)
3. **Instructions** — text_instructions, sql_snippets (filters), business logic

This ordering matters because Genie first resolves schema understanding (which tables/columns?), then query patterns (how to aggregate/join?), then business logic (what does "active customer" mean?). Fixing upstream issues first avoids wasting effort on downstream symptoms.

---

## Category 1: UC Metadata Fixes

These errors indicate Genie selected wrong tables, columns, or joins — a schema understanding problem.

| Assessment Reason | Root Cause | Config Fix |
|---|---|---|
| `LLM_JUDGE_INCORRECT_TABLE_OR_FIELD_USAGE` | Genie picked the wrong table or column | Improve `data_sources.tables[].description` to clarify table purpose and grain. Add/improve `column_configs[].description` for misused columns. Add `column_configs[].synonyms` if user terminology differs from column names. |
| `LLM_JUDGE_MISSING_OR_INCORRECT_JOIN` | Genie used wrong join or missed a join entirely | Add/fix `instructions.join_specs` between the relevant tables. Include `comment` (business context) and `instruction` (when to use). For multi-column joins, use separate join specs with cross-referencing comments. |
| `LLM_JUDGE_MISSING_JOIN` | Genie omitted a required join | Add `instructions.join_specs` for the missing relationship. Check if related tables have clear descriptions that indicate how they relate. |
| `RESULT_MISSING_COLUMNS` | Output is missing expected columns | Check if the expected columns have clear descriptions. Add synonyms if user question uses different terminology. Verify columns are not excluded (`exclude: true`). |
| `LLM_JUDGE_WRONG_COLUMNS` | Genie selected the wrong columns in SELECT | Improve `column_configs[].description` for misused columns. Add `column_configs[].synonyms` if user terminology differs from column names. Check if irrelevant columns should be excluded (`exclude: true`) to reduce noise. |
| `RESULT_EXTRA_COLUMNS` | Output has unexpected extra columns | Improve table/column descriptions to clarify which columns are relevant. Consider setting `exclude: true` on noise columns. |
| `COLUMN_TYPE_DIFFERENCE` | Values match but types differ | Check column descriptions — clarify expected types. May indicate a CAST is needed, which should be added as an expression snippet. |

**How to generate fixes:**
- Compare the expected SQL's table/column usage against the generated SQL
- Look at which tables the expected SQL joins and add join specs if missing
- For each wrong column, check if the description or synonyms could guide Genie better
- Enable `enable_entity_matching` (v2) / `build_value_dictionary` (v1) on low-cardinality columns used in WHERE clauses
- Enable `enable_format_assistance` (v2) / `get_example_values` (v1) on filterable columns

---

## Category 2: SQL Example Fixes

These errors indicate Genie understood the schema but couldn't construct the right query pattern.

| Assessment Reason | Root Cause | Config Fix |
|---|---|---|
| `LLM_JUDGE_WRONG_AGGREGATION` / `LLM_JUDGE_MISSING_OR_INCORRECT_AGGREGATION` | Wrong GROUP BY or aggregate function | Add `instructions.example_question_sqls` demonstrating the correct aggregation pattern. Add `sql_snippets.measures` for standard aggregations (SUM, AVG, COUNT DISTINCT). |
| `LLM_JUDGE_INCORRECT_FUNCTION_USAGE` | SQL functions used incorrectly | Add an example SQL showing correct function usage. If it's a UDF, add it to `instructions.sql_functions` with a clear description. |
| `LLM_JUDGE_INCOMPLETE_OR_PARTIAL_OUTPUT` | Query returns only some of the expected data | Add an example SQL that demonstrates the complete query pattern. Check if a CTE or subquery pattern is needed. |
| `LLM_JUDGE_FORMATTING_ERROR` | Wrong ordering, presentation, or formatting | Add `usage_guidance` to relevant example SQLs specifying expected output format. Add ORDER BY / LIMIT patterns as example SQLs. |
| `LLM_JUDGE_SYNTAX_ERROR` | Generated SQL has syntax errors | Check if the pattern requires dialect-specific syntax. Add an example SQL using the correct syntax. |
| `EMPTY_RESULT` | Genie's SQL returned no rows | The generated SQL's filters may be too restrictive. Compare WHERE clauses — add a filter snippet or example SQL showing the correct filter pattern. |
| `RESULT_MISSING_ROWS` / `RESULT_EXTRA_ROWS` | Row count doesn't match expected | Check aggregation level (GROUP BY), filter conditions (WHERE), and LIMIT clauses. Add example SQL if the pattern is non-obvious. |

**How to generate fixes:**
- Use the expected SQL from the benchmark as the basis for new example_question_sqls
- Generalize the pattern — don't just copy the benchmark verbatim; create a reusable pattern
- Add `usage_guidance` explaining when Genie should apply this pattern
- For recurring aggregations, create `sql_snippets.measures` entries
- For recurring expressions (CASE statements, calculations), create `sql_snippets.expressions` entries

---

## Category 3: Instruction / Business Logic Fixes

These errors indicate Genie understood the schema and basic query patterns but misapplied business logic or misinterpreted the question.

| Assessment Reason | Root Cause | Config Fix |
|---|---|---|
| `LLM_JUDGE_MISINTERPRETATION_OF_USER_REQUEST` | Genie fundamentally misunderstood the question | Add `instructions.text_instructions` mapping business jargon to data concepts. Add column synonyms for commonly misunderstood terms. |
| `LLM_JUDGE_INSTRUCTION_COMPLIANCE_OR_MISSING_BUSINESS_LOGIC` | Genie didn't follow business rules | Add `instructions.text_instructions` encoding the business rule (e.g., "Revenue excludes cancelled orders", "Active customers = ordered in last 90 days"). Add `sql_snippets.filters` or `sql_snippets.expressions` for reusable business logic. |
| `LLM_JUDGE_WRONG_FILTER` / `LLM_JUDGE_MISSING_OR_INCORRECT_FILTER` | Wrong or missing WHERE clause | Add `sql_snippets.filters` for the correct filter pattern. Add `instructions.text_instructions` if the filter represents a business rule (e.g., "Always exclude test accounts"). |
| `LLM_JUDGE_INCORRECT_METRIC_CALCULATION` | Metric computed incorrectly | Add `sql_snippets.measures` defining the correct metric formula. Add `instructions.text_instructions` clarifying the metric definition if it's non-obvious. |
| `LLM_JUDGE_SEMANTIC_ERROR` | Query is syntactically valid but logically wrong | Analyze the semantic gap. Usually requires a combination of text instructions (clarify intent) and example SQLs (demonstrate correct logic). |
| `LLM_JUDGE_OTHER` | Uncategorized error | Inspect the actual vs expected SQL manually. Determine whether the fix belongs to UC metadata, SQL examples, or instructions. |
| `SINGLE_CELL_DIFFERENCE` | Single value differs from expected | Check if it's a rounding, formatting, or calculation issue. Add a text instruction or expression snippet for the correct calculation. |

**How to generate fixes:**
- Read the benchmark question and both SQLs to understand the business intent
- Encode business rules as concise text instructions — one rule per instruction, not documentation
- Create filter snippets for common temporal filters ("last 30 days", "YTD", "current quarter")
- Create expression snippets for business classifications (customer tiers, status mappings)
- Create measure snippets for standard KPIs (revenue, margin, churn rate)

---

## Deterministic vs LLM Judge Reasons

**Deterministic** (result-level comparison — objective):
`EMPTY_RESULT`, `RESULT_MISSING_ROWS`, `RESULT_EXTRA_ROWS`, `RESULT_MISSING_COLUMNS`, `RESULT_EXTRA_COLUMNS`, `SINGLE_CELL_DIFFERENCE`, `EMPTY_GOOD_SQL`, `COLUMN_TYPE_DIFFERENCE`

**LLM Judge** (SQL-level semantic analysis — subjective):
All `LLM_JUDGE_*` prefixed reasons.

A single failed benchmark may have **both** deterministic and LLM judge reasons. Use both to triangulate the root cause. For example, `RESULT_MISSING_ROWS` + `LLM_JUDGE_WRONG_FILTER` together confirm a WHERE clause problem.

---

## Multi-Reason Failures

When a benchmark result has multiple assessment reasons, prioritize the upstream cause:
1. If it includes a table/field/join reason → start with UC metadata fix
2. If it includes aggregation/function reasons but no schema reasons → SQL example fix
3. If it includes only interpretation/compliance reasons → instruction fix

If reasons span multiple categories, create fixes in all relevant categories but apply them in order (UC metadata first, then SQL examples, then instructions).

---

## Benchmark Quality Signals

These assessment reasons indicate problems with the benchmark itself, not with the space configuration. They cannot be fixed by config changes.

| Assessment Reason | Root Cause | Action |
|---|---|---|
| `EMPTY_GOOD_SQL` | The benchmark's expected SQL returned no rows — the benchmark question is broken or the underlying data has changed | Flag to the user for benchmark question review or removal. Skip this question in fix analysis — no config change can fix a broken benchmark. |
