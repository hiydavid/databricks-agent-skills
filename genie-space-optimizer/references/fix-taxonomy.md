# Fix Taxonomy: Assessment Reasons → Config Fixes

The Benchmark API returns `assessment_reasons` for each failed evaluation result. This taxonomy maps those reasons to specific Genie Space configuration changes, organized by fix category, with exact config paths and priority ordering.

## Fix Ordering

Apply fixes **left-to-right** — each category builds on the previous:

1. **UC Metadata** — table/column descriptions, synonyms, value dictionaries, join specs
2. **SQL Examples** — example_question_sqls, sql_snippets (measures, expressions)
3. **Instructions** — text_instructions, sql_snippets (filters), business logic

This ordering matters because Genie first resolves schema understanding (which tables/columns?), then query patterns (how to aggregate/join?), then business logic (what does "active customer" mean?). Fixing upstream issues first avoids wasting effort on downstream symptoms.

---

## Quick-Reference Matrix

All 25 assessment labels at a glance. **P** = priority within category (P1 = try first).

| Label | Category | What Went Wrong | Primary Fix Path(s) | P |
|---|---|---|---|---|
| `LLM_JUDGE_INCORRECT_TABLE_OR_FIELD_USAGE` | UC Metadata | Genie's generated SQL references wrong tables, columns, or uses fields that don't match the ground truth SQL's intent. | `tables[].description`, `column_configs[].description`, `column_configs[].synonyms` | P1 |
| `LLM_JUDGE_MISSING_OR_INCORRECT_JOIN` | UC Metadata | Genie's generated SQL is missing necessary joins between tables or has incorrect join conditions/types that produce wrong results. | `instructions.join_specs[]` | P1 |
| `LLM_JUDGE_MISSING_JOIN` | UC Metadata | Genie's generated SQL is missing a required join between tables. *(Undocumented in official API docs — narrower variant of MISSING_OR_INCORRECT_JOIN; may be removed.)* | `instructions.join_specs[]` | P1 |
| `LLM_JUDGE_WRONG_COLUMNS` | UC Metadata | Genie's generated SQL selects wrong columns that don't match the ground truth SQL's intent. *(Undocumented in official API docs — overlaps with INCORRECT_TABLE_OR_FIELD_USAGE; may be removed.)* | `column_configs[].description`, `column_configs[].synonyms` | P2 |
| `RESULT_MISSING_COLUMNS` | UC Metadata | Genie's generated SQL response is missing columns from the provided ground truth SQL. | `column_configs[].description`, `column_configs[].synonyms` | P2 |
| `RESULT_EXTRA_COLUMNS` | UC Metadata | Genie's generated SQL response has more columns than the provided ground truth SQL. | `column_configs[].exclude` | P3 |
| `COLUMN_TYPE_DIFFERENCE` | UC Metadata | The values between the results match but the column type is different. | `column_configs[].description` | P3 |
| `LLM_JUDGE_WRONG_AGGREGATION` | SQL Examples | Genie's generated SQL uses the wrong aggregate function or GROUP BY clause. *(Undocumented in official API docs — narrower variant of MISSING_OR_INCORRECT_AGGREGATION; may be removed.)* | `example_question_sqls[]`, `sql_snippets.measures[]` | P1 |
| `LLM_JUDGE_MISSING_OR_INCORRECT_AGGREGATION` | SQL Examples | Genie's generated SQL is missing GROUP BY clauses or has incorrect grouping that doesn't match the requested aggregation level. | `example_question_sqls[]`, `sql_snippets.measures[]` | P1 |
| `LLM_JUDGE_INCORRECT_FUNCTION_USAGE` | SQL Examples | Genie's generated SQL uses SQL functions incorrectly or inappropriately (wrong parameters, wrong function for the task, etc.). | `example_question_sqls[]`, `sql_functions[]` | P1 |
| `LLM_JUDGE_SYNTAX_ERROR` | SQL Examples | Genie's generated SQL contains syntax errors that prevent execution. *(Undocumented in official API docs; may be removed.)* | `example_question_sqls[]` | P2 |
| `LLM_JUDGE_INCOMPLETE_OR_PARTIAL_OUTPUT` | SQL Examples | Genie's generated SQL returns only some of the requested data or columns, missing parts of what the ground truth SQL returns. | `example_question_sqls[]` | P2 |
| `EMPTY_RESULT` | SQL Examples | Genie's generated SQL results were empty for this benchmark question. | `sql_snippets.filters[]`, `example_question_sqls[]` | P2 |
| `RESULT_MISSING_ROWS` | SQL Examples | Genie's generated SQL response is missing rows from the provided ground truth SQL. | `example_question_sqls[]`, `sql_snippets.filters[]` | P2 |
| `RESULT_EXTRA_ROWS` | SQL Examples | Genie's generated SQL response has more rows than the provided ground truth SQL. | `example_question_sqls[]`, `sql_snippets.filters[]` | P3 |
| `LLM_JUDGE_FORMATTING_ERROR` | SQL Examples | Genie's generated SQL output has incorrect formatting, ordering (ORDER BY), or presentation issues that don't match expectations. | `example_question_sqls[]` | P3 |
| `LLM_JUDGE_WRONG_FILTER` | Instructions | Genie's generated SQL has an incorrect WHERE clause with wrong values, operators, or column filtered. *(Undocumented in official API docs — narrower variant of MISSING_OR_INCORRECT_FILTER; may be removed.)* | `sql_snippets.filters[]`, `text_instructions[].content` | P1 |
| `LLM_JUDGE_MISSING_OR_INCORRECT_FILTER` | Instructions | Genie's generated SQL is missing a WHERE clause condition or has incorrect filter logic that excludes/includes wrong data. | `sql_snippets.filters[]`, `text_instructions[].content` | P1 |
| `LLM_JUDGE_MISINTERPRETATION_OF_USER_REQUEST` | Instructions | Genie's generated SQL fundamentally misunderstands what the user is asking for, addressing the wrong question or goal. | `text_instructions[].content`, `column_configs[].synonyms` | P1 |
| `LLM_JUDGE_INSTRUCTION_COMPLIANCE_OR_MISSING_BUSINESS_LOGIC` | Instructions | Genie's generated SQL fails to apply specified instructions or business logic that should be followed. | `text_instructions[].content`, `sql_snippets.filters[]`, `sql_snippets.expressions[]` | P1 |
| `LLM_JUDGE_INCORRECT_METRIC_CALCULATION` | Instructions | Genie's generated SQL uses incorrect logic or makes wrong assumptions when calculating metrics. | `sql_snippets.measures[]`, `text_instructions[].content` | P1 |
| `LLM_JUDGE_SEMANTIC_ERROR` | Instructions | Genie's generated SQL is syntactically valid but logically wrong, producing incorrect results. *(Undocumented in official API docs; may be removed.)* | `text_instructions[].content`, `example_question_sqls[]` | P2 |
| `SINGLE_CELL_DIFFERENCE` | Instructions | Single value result was produced but differs from ground truth result. | `text_instructions[].content`, `sql_snippets.expressions[]` | P3 |
| `LLM_JUDGE_OTHER` | Instructions | LLM judge identified an error that doesn't fall into other categories. | Analyze SQL diff → map to closest label | P3 |
| `EMPTY_GOOD_SQL` | Benchmark Quality | The benchmark SQL returned an empty result. | N/A — flag for benchmark review | — |

---

## Detailed Fix Mappings

### Category 1: UC Metadata Fixes

These errors indicate Genie selected wrong tables, columns, or joins — a schema understanding problem.

#### LLM_JUDGE_INCORRECT_TABLE_OR_FIELD_USAGE

**Category:** UC Metadata | **Priority:** P1
**Description:** Genie's generated SQL references wrong tables, columns, or uses fields that don't match the ground truth SQL's intent.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Improve table description to clarify purpose and grain | `data_sources.tables[].description` | Table Descriptions |
| Improve column description for misused columns | `data_sources.tables[].column_configs[].description` | Column Descriptions |
| Add synonyms mapping user terminology to column names | `data_sources.tables[].column_configs[].synonyms` | Column Synonyms |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Exclude irrelevant columns to reduce noise | `data_sources.tables[].column_configs[].exclude` | Irrelevant Columns Hidden |
| Enable entity matching on low-cardinality columns | `data_sources.tables[].column_configs[].enable_entity_matching` | Value Dictionary Enabled |
| Improve metric view description (if metric views involved) | `data_sources.metric_views[].description` | Metric View Descriptions |

**Diagnostic Signal:** Compare expected vs generated SQL — look at which tables/columns each references. The divergence reveals what Genie misunderstood.

---

#### LLM_JUDGE_MISSING_OR_INCORRECT_JOIN

**Category:** UC Metadata | **Priority:** P1
**Description:** Genie's generated SQL is missing necessary joins between tables or has incorrect join conditions/types that produce wrong results.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add or fix join spec with correct condition | `instructions.join_specs[].left`, `.right`, `.join_type`, `.sql` | Join Specs for Multi-Table Relationships |
| Add business context comment | `instructions.join_specs[].comment` | Join Specs Have Comments |
| Add usage instruction for when to apply this join | `instructions.join_specs[].instruction` | Join Specs Have Comments |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Improve table descriptions to clarify relationships | `data_sources.tables[].description` | Table Descriptions |

**Diagnostic Signal:** Compare JOIN clauses in expected vs generated SQL. Identify which tables should be joined and on which keys.

---

#### LLM_JUDGE_MISSING_JOIN

**Category:** UC Metadata | **Priority:** P1
**Description:** Genie's generated SQL is missing a required join between tables. *(Undocumented in official API docs — narrower variant of MISSING_OR_INCORRECT_JOIN; may be removed.)*

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add join spec for the missing relationship | `instructions.join_specs[]` (all subfields) | Join Specs for Multi-Table Relationships |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Improve table descriptions to indicate how tables relate | `data_sources.tables[].description` | Table Descriptions |

**Diagnostic Signal:** Expected SQL joins tables that the generated SQL queries independently or omits. Check if a join spec exists for this table pair.

---

#### LLM_JUDGE_WRONG_COLUMNS

**Category:** UC Metadata | **Priority:** P2
**Description:** Genie's generated SQL selects wrong columns that don't match the ground truth SQL's intent. *(Undocumented in official API docs — overlaps with INCORRECT_TABLE_OR_FIELD_USAGE; may be removed.)*

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Improve column description for misused columns | `data_sources.tables[].column_configs[].description` | Column Descriptions |
| Add synonyms if user terminology differs from column names | `data_sources.tables[].column_configs[].synonyms` | Column Synonyms |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Exclude noise columns that Genie shouldn't consider | `data_sources.tables[].column_configs[].exclude` | Irrelevant Columns Hidden |

**Diagnostic Signal:** Compare SELECT lists — identify which columns were swapped, added, or omitted vs the expected SQL.

---

#### RESULT_MISSING_COLUMNS

**Category:** UC Metadata | **Priority:** P2
**Description:** Genie's generated SQL response is missing columns from the provided ground truth SQL.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Improve description for the missing columns | `data_sources.tables[].column_configs[].description` | Column Descriptions |
| Add synonyms if user question uses different terminology | `data_sources.tables[].column_configs[].synonyms` | Column Synonyms |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Verify columns are not excluded (`exclude: true`) | `data_sources.tables[].column_configs[].exclude` | Irrelevant Columns Hidden |

**Diagnostic Signal:** Identify which columns are in the expected output but absent from the generated SQL's SELECT.

---

#### RESULT_EXTRA_COLUMNS

**Category:** UC Metadata | **Priority:** P3
**Description:** Genie's generated SQL response has more columns than the provided ground truth SQL.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Exclude noise columns Genie shouldn't select | `data_sources.tables[].column_configs[].exclude` | Irrelevant Columns Hidden |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Improve table description to clarify relevant columns | `data_sources.tables[].description` | Table Descriptions |
| Improve column descriptions to reduce ambiguity | `data_sources.tables[].column_configs[].description` | Column Descriptions |

**Diagnostic Signal:** Identify which extra columns Genie included and whether they should be hidden or better described.

---

#### COLUMN_TYPE_DIFFERENCE

**Category:** UC Metadata | **Priority:** P3
**Description:** The values between the results match but the column type is different.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Clarify expected type/format in column description | `data_sources.tables[].column_configs[].description` | Column Descriptions |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add CAST expression snippet for the correct conversion | `instructions.sql_snippets.expressions[]` | Expression Snippets Defined |

**Diagnostic Signal:** Compare column types in the result manifests. Check if a CAST is needed in the generated SQL.

---

### Category 2: SQL Example Fixes

These errors indicate Genie understood the schema but couldn't construct the right query pattern.

#### LLM_JUDGE_WRONG_AGGREGATION

**Category:** SQL Examples | **Priority:** P1
**Description:** Genie's generated SQL uses the wrong aggregate function or GROUP BY clause. *(Undocumented in official API docs — narrower variant of MISSING_OR_INCORRECT_AGGREGATION; may be removed.)*

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add example SQL demonstrating correct aggregation pattern | `instructions.example_question_sqls[].question`, `.sql`, `.usage_guidance` | At Least 1 Example SQL, Examples Cover Complex Patterns |
| Add measure snippet for standard aggregations | `instructions.sql_snippets.measures[]` | Measure Snippets Defined |

**Diagnostic Signal:** Compare GROUP BY and aggregate functions (SUM vs COUNT, etc.) in expected vs generated SQL.

---

#### LLM_JUDGE_MISSING_OR_INCORRECT_AGGREGATION

**Category:** SQL Examples | **Priority:** P1
**Description:** Genie's generated SQL is missing GROUP BY clauses or has incorrect grouping that doesn't match the requested aggregation level.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add example SQL with correct aggregation | `instructions.example_question_sqls[]` | At Least 1 Example SQL, Examples Cover Complex Patterns |
| Add measure snippet defining the standard aggregation | `instructions.sql_snippets.measures[]` | Measure Snippets Defined |

**Diagnostic Signal:** Expected SQL has GROUP BY / aggregate functions that the generated SQL omits or misapplies.

---

#### LLM_JUDGE_INCORRECT_FUNCTION_USAGE

**Category:** SQL Examples | **Priority:** P1
**Description:** Genie's generated SQL uses SQL functions incorrectly or inappropriately (wrong parameters, wrong function for the task, etc.).

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add example SQL showing correct function usage | `instructions.example_question_sqls[]` | At Least 1 Example SQL |
| Register UC function with clear description | `instructions.sql_functions[].identifier`, `.description` | — |

**Diagnostic Signal:** Compare function calls in expected vs generated SQL. Check if the function is a UDF that needs registration.

---

#### LLM_JUDGE_SYNTAX_ERROR

**Category:** SQL Examples | **Priority:** P2
**Description:** Genie's generated SQL contains syntax errors that prevent execution. *(Undocumented in official API docs; may be removed.)*

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add example SQL using correct dialect syntax | `instructions.example_question_sqls[]` | At Least 1 Example SQL |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Register UC function if syntax error involves a UDF | `instructions.sql_functions[]` | — |

**Diagnostic Signal:** The generated SQL fails to execute. Identify the syntax error and whether it stems from dialect confusion or unrecognized functions.

---

#### LLM_JUDGE_INCOMPLETE_OR_PARTIAL_OUTPUT

**Category:** SQL Examples | **Priority:** P2
**Description:** Genie's generated SQL returns only some of the requested data or columns, missing parts of what the ground truth SQL returns.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add example SQL demonstrating the complete pattern (CTEs, UNION, subqueries) | `instructions.example_question_sqls[]` | Examples Cover Complex Patterns |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add usage guidance clarifying completeness expectation | `instructions.example_question_sqls[].usage_guidance` | Complex Examples Have Usage Guidance |

**Diagnostic Signal:** Expected SQL has multiple parts (UNION, CTE) or returns more dimensions than the generated SQL.

---

#### EMPTY_RESULT

**Category:** SQL Examples | **Priority:** P2
**Description:** Genie's generated SQL results were empty for this benchmark question.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add filter snippet showing correct WHERE pattern | `instructions.sql_snippets.filters[]` | Filter Snippets Defined |
| Add example SQL with correct filter | `instructions.example_question_sqls[]` | At Least 1 Example SQL |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Enable entity matching on filter columns | `data_sources.tables[].column_configs[].enable_entity_matching` | Value Dictionary Enabled |
| Enable format assistance on filter columns | `data_sources.tables[].column_configs[].enable_format_assistance` | Example Values Enabled |

**Diagnostic Signal:** Compare WHERE clauses — the generated SQL's filters are likely too restrictive or use wrong values. See also [Labels Spanning Categories](#labels-spanning-categories).

---

#### RESULT_MISSING_ROWS

**Category:** SQL Examples | **Priority:** P2
**Description:** Genie's generated SQL response is missing rows from the provided ground truth SQL.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add example SQL showing correct GROUP BY / filter / LIMIT | `instructions.example_question_sqls[]` | At Least 1 Example SQL |
| Add filter snippet if WHERE is too restrictive | `instructions.sql_snippets.filters[]` | Filter Snippets Defined |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add measure snippet if wrong aggregation level | `instructions.sql_snippets.measures[]` | Measure Snippets Defined |

**Diagnostic Signal:** Compare GROUP BY granularity, WHERE conditions, and LIMIT clauses. See also [Labels Spanning Categories](#labels-spanning-categories).

---

#### RESULT_EXTRA_ROWS

**Category:** SQL Examples | **Priority:** P3
**Description:** Genie's generated SQL response has more rows than the provided ground truth SQL.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add example SQL with correct aggregation / DISTINCT / LIMIT | `instructions.example_question_sqls[]` | At Least 1 Example SQL |
| Add filter snippet if missing WHERE clause | `instructions.sql_snippets.filters[]` | Filter Snippets Defined |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add measure snippet if GROUP BY too granular | `instructions.sql_snippets.measures[]` | Measure Snippets Defined |

**Diagnostic Signal:** Check if the generated SQL is missing a WHERE, DISTINCT, LIMIT, or has a more granular GROUP BY than expected. See also [Labels Spanning Categories](#labels-spanning-categories).

---

#### LLM_JUDGE_FORMATTING_ERROR

**Category:** SQL Examples | **Priority:** P3
**Description:** Genie's generated SQL output has incorrect formatting, ordering (ORDER BY), or presentation issues that don't match expectations.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add example SQL with correct ORDER BY / formatting | `instructions.example_question_sqls[]` | At Least 1 Example SQL |
| Add usage guidance specifying expected output format | `instructions.example_question_sqls[].usage_guidance` | Complex Examples Have Usage Guidance |

**Diagnostic Signal:** Results are correct but ORDER BY, column aliases, or LIMIT differ from expected.

---

### Category 3: Instruction / Business Logic Fixes

These errors indicate Genie understood the schema and basic query patterns but misapplied business logic or misinterpreted the question.

#### LLM_JUDGE_WRONG_FILTER

**Category:** Instructions | **Priority:** P1
**Description:** Genie's generated SQL has an incorrect WHERE clause with wrong values, operators, or column filtered. *(Undocumented in official API docs — narrower variant of MISSING_OR_INCORRECT_FILTER; may be removed.)*

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add filter snippet for the correct pattern | `instructions.sql_snippets.filters[]` | Filter Snippets Defined |
| Add text instruction explaining the business rule behind the filter | `instructions.text_instructions[].content` | At Least 1 Text Instruction, Business Jargon Mapped |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Enable entity matching on filter column | `data_sources.tables[].column_configs[].enable_entity_matching` | Value Dictionary Enabled |
| Enable format assistance on filter column | `data_sources.tables[].column_configs[].enable_format_assistance` | Example Values Enabled |

**Diagnostic Signal:** Compare WHERE clauses — identify the specific condition that differs. Check if the filter represents a business rule.

---

#### LLM_JUDGE_MISSING_OR_INCORRECT_FILTER

**Category:** Instructions | **Priority:** P1
**Description:** Genie's generated SQL is missing a WHERE clause condition or has incorrect filter logic that excludes/includes wrong data.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add filter snippet for the missing/correct pattern | `instructions.sql_snippets.filters[]` | Filter Snippets Defined |
| Add text instruction encoding the business rule | `instructions.text_instructions[].content` | At Least 1 Text Instruction |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Enable entity matching on filter column | `data_sources.tables[].column_configs[].enable_entity_matching` | Value Dictionary Enabled |
| Enable format assistance on filter column | `data_sources.tables[].column_configs[].enable_format_assistance` | Example Values Enabled |

**Diagnostic Signal:** Expected SQL has a WHERE condition absent from or different in the generated SQL.

---

#### LLM_JUDGE_MISINTERPRETATION_OF_USER_REQUEST

**Category:** Instructions | **Priority:** P1
**Description:** Genie's generated SQL fundamentally misunderstands what the user is asking for, addressing the wrong question or goal.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add text instruction mapping business jargon to data concepts | `instructions.text_instructions[].content` | Business Jargon Mapped |
| Add column synonyms for misunderstood terms | `data_sources.tables[].column_configs[].synonyms` | Column Synonyms |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add example SQL clarifying the pattern for this question type | `instructions.example_question_sqls[]` | At Least 1 Example SQL |

**Diagnostic Signal:** The generated SQL answers a fundamentally different question. Identify which term or concept was misunderstood.

---

#### LLM_JUDGE_INSTRUCTION_COMPLIANCE_OR_MISSING_BUSINESS_LOGIC

**Category:** Instructions | **Priority:** P1
**Description:** Genie's generated SQL fails to apply specified instructions or business logic that should be followed.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add text instruction encoding the business rule | `instructions.text_instructions[].content` | At Least 1 Text Instruction, Instructions Are Focused and Minimal |
| Add filter snippet for reusable business logic filters | `instructions.sql_snippets.filters[]` | Filter Snippets Defined |
| Add expression snippet for reusable business logic calculations | `instructions.sql_snippets.expressions[]` | Expression Snippets Defined |

**Diagnostic Signal:** Expected SQL applies a business rule (filter, CASE expression, or calculation) absent from the generated SQL. Identify the specific rule.

---

#### LLM_JUDGE_INCORRECT_METRIC_CALCULATION

**Category:** Instructions | **Priority:** P1
**Description:** Genie's generated SQL uses incorrect logic or makes wrong assumptions when calculating metrics.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add measure snippet defining the correct formula | `instructions.sql_snippets.measures[]` | Measure Snippets Defined |
| Add text instruction clarifying the metric definition | `instructions.text_instructions[].content` | At Least 1 Text Instruction, Business Jargon Mapped |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add expression snippet if metric involves CASE logic | `instructions.sql_snippets.expressions[]` | Expression Snippets Defined |
| Improve metric view description (if metric views involved) | `data_sources.metric_views[].description` | Metric View Descriptions |

**Diagnostic Signal:** Compare the aggregation formulas in expected vs generated SQL. Identify the specific calculation difference.

---

#### LLM_JUDGE_SEMANTIC_ERROR

**Category:** Instructions | **Priority:** P2
**Description:** Genie's generated SQL is syntactically valid but logically wrong, producing incorrect results. *(Undocumented in official API docs; may be removed.)*

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add text instruction clarifying the correct interpretation | `instructions.text_instructions[].content` | At Least 1 Text Instruction |
| Add example SQL demonstrating the correct logic | `instructions.example_question_sqls[]` | At Least 1 Example SQL, Examples Cover Complex Patterns |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add filter, expression, or measure snippets as needed | `instructions.sql_snippets.*[]` | Various |

**Diagnostic Signal:** Both SQLs execute successfully but produce different results. Analyze the logical difference — this often requires both text instructions and example SQLs.

---

#### SINGLE_CELL_DIFFERENCE

**Category:** Instructions | **Priority:** P3
**Description:** Single value result was produced but differs from ground truth result.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add text instruction clarifying rounding/precision rules | `instructions.text_instructions[].content` | At Least 1 Text Instruction |
| Add expression snippet for the correct calculation | `instructions.sql_snippets.expressions[]` | Expression Snippets Defined |

**Secondary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Add measure snippet if it's an aggregation precision issue | `instructions.sql_snippets.measures[]` | Measure Snippets Defined |

**Diagnostic Signal:** Compare the specific differing value. Check for ROUND, CAST, or edge-case handling differences.

---

#### LLM_JUDGE_OTHER

**Category:** Instructions | **Priority:** P3
**Description:** LLM judge identified an error that doesn't fall into other categories.

**Primary Fixes:**

| Fix Action | Config Path | Best Practice |
|---|---|---|
| Inspect actual vs expected SQL manually — determine root cause | Depends on analysis | — |

**How to handle:** Compare the expected and generated SQL line by line. Identify the specific mismatch type (wrong table? wrong filter? wrong aggregation?) and map to the closest specific label's fix strategy above. Use that label's config paths and fix actions.

---

### Benchmark Quality Signals

These indicate problems with the benchmark itself, not with the space configuration. They cannot be fixed by config changes.

#### EMPTY_GOOD_SQL

**Category:** Benchmark Quality | **Priority:** N/A
**Description:** The benchmark SQL returned an empty result.

**Action:** Flag to the user for benchmark question review or removal. Skip this question in fix analysis — no config change can fix a broken benchmark.

**Best Practice Ref:** At Least 10 Diverse Q&A Pairs, Benchmark Coverage

---

## Cross-Category Notes

### Deterministic vs LLM Judge Reasons

**Deterministic** (result-level comparison — objective):
`EMPTY_RESULT`, `RESULT_MISSING_ROWS`, `RESULT_EXTRA_ROWS`, `RESULT_MISSING_COLUMNS`, `RESULT_EXTRA_COLUMNS`, `SINGLE_CELL_DIFFERENCE`, `EMPTY_GOOD_SQL`, `COLUMN_TYPE_DIFFERENCE`

**LLM Judge** (SQL-level semantic analysis — subjective):
All `LLM_JUDGE_*` prefixed reasons.

A single failed benchmark may have **both** deterministic and LLM judge reasons. Use both to triangulate the root cause. For example, `RESULT_MISSING_ROWS` + `LLM_JUDGE_WRONG_FILTER` together confirm a WHERE clause problem.

### Multi-Reason Failures

When a benchmark result has multiple assessment reasons, prioritize the upstream cause:
1. If it includes a table/field/join reason → start with UC metadata fix
2. If it includes aggregation/function reasons but no schema reasons → SQL example fix
3. If it includes only interpretation/compliance reasons → instruction fix

If reasons span multiple categories, create fixes in all relevant categories but apply them in order (UC metadata first, then SQL examples, then instructions).

### Labels Spanning Categories

Some labels can have root causes in multiple categories. Their primary category assignment reflects the most common cause, but check for cross-category signals:

| Label | Primary Category | May Also Need |
|---|---|---|
| `EMPTY_RESULT` | SQL Examples | Instructions — if the root cause is a business-logic filter (e.g., wrong status value), add a `sql_snippets.filters[]` entry AND a `text_instructions` clarifying the filter rule |
| `RESULT_MISSING_ROWS` | SQL Examples | Instructions — if rows are missing due to a too-restrictive business filter rather than wrong aggregation |
| `RESULT_EXTRA_ROWS` | SQL Examples | Instructions — if extra rows appear due to a missing business-logic exclusion filter |
| `LLM_JUDGE_SEMANTIC_ERROR` | Instructions | SQL Examples — often requires both `text_instructions` (clarify intent) AND `example_question_sqls` (demonstrate pattern) |

**Decision rule:** If the result also has an LLM judge reason that clearly points to one category, follow that. If the deterministic reason stands alone, compare the WHERE clauses and GROUP BY to determine whether it's a filter issue (Instructions) or aggregation issue (SQL Examples).

---

## Config Path Index

Inverted lookup: for each config path, which labels can be fixed by modifying it. Useful when the optimizer is already touching a path and wants to know what else might benefit.

| Config Path | Labels Addressable |
|---|---|
| `data_sources.tables[].description` | INCORRECT_TABLE_OR_FIELD_USAGE, MISSING_OR_INCORRECT_JOIN, MISSING_JOIN, RESULT_EXTRA_COLUMNS |
| `data_sources.tables[].column_configs[].description` | INCORRECT_TABLE_OR_FIELD_USAGE, WRONG_COLUMNS, RESULT_MISSING_COLUMNS, RESULT_EXTRA_COLUMNS, COLUMN_TYPE_DIFFERENCE |
| `data_sources.tables[].column_configs[].synonyms` | INCORRECT_TABLE_OR_FIELD_USAGE, WRONG_COLUMNS, RESULT_MISSING_COLUMNS, MISINTERPRETATION_OF_USER_REQUEST |
| `data_sources.tables[].column_configs[].exclude` | WRONG_COLUMNS, RESULT_EXTRA_COLUMNS, RESULT_MISSING_COLUMNS (verify not excluded) |
| `data_sources.tables[].column_configs[].enable_entity_matching` | WRONG_FILTER, MISSING_OR_INCORRECT_FILTER, EMPTY_RESULT |
| `data_sources.tables[].column_configs[].enable_format_assistance` | WRONG_FILTER, MISSING_OR_INCORRECT_FILTER, EMPTY_RESULT |
| `data_sources.metric_views[].description` | INCORRECT_TABLE_OR_FIELD_USAGE, INCORRECT_METRIC_CALCULATION |
| `instructions.text_instructions[].content` | MISINTERPRETATION_OF_USER_REQUEST, INSTRUCTION_COMPLIANCE_OR_MISSING_BUSINESS_LOGIC, WRONG_FILTER, MISSING_OR_INCORRECT_FILTER, INCORRECT_METRIC_CALCULATION, SEMANTIC_ERROR, SINGLE_CELL_DIFFERENCE |
| `instructions.example_question_sqls[]` | WRONG_AGGREGATION, MISSING_OR_INCORRECT_AGGREGATION, INCORRECT_FUNCTION_USAGE, SYNTAX_ERROR, INCOMPLETE_OR_PARTIAL_OUTPUT, FORMATTING_ERROR, EMPTY_RESULT, RESULT_MISSING_ROWS, RESULT_EXTRA_ROWS, SEMANTIC_ERROR, MISINTERPRETATION_OF_USER_REQUEST |
| `instructions.join_specs[]` | MISSING_OR_INCORRECT_JOIN, MISSING_JOIN |
| `instructions.sql_functions[]` | INCORRECT_FUNCTION_USAGE, SYNTAX_ERROR |
| `instructions.sql_snippets.filters[]` | WRONG_FILTER, MISSING_OR_INCORRECT_FILTER, EMPTY_RESULT, RESULT_MISSING_ROWS, RESULT_EXTRA_ROWS, INSTRUCTION_COMPLIANCE_OR_MISSING_BUSINESS_LOGIC |
| `instructions.sql_snippets.expressions[]` | INSTRUCTION_COMPLIANCE_OR_MISSING_BUSINESS_LOGIC, COLUMN_TYPE_DIFFERENCE, SINGLE_CELL_DIFFERENCE, INCORRECT_METRIC_CALCULATION |
| `instructions.sql_snippets.measures[]` | WRONG_AGGREGATION, MISSING_OR_INCORRECT_AGGREGATION, INCORRECT_METRIC_CALCULATION, RESULT_MISSING_ROWS, RESULT_EXTRA_ROWS, SINGLE_CELL_DIFFERENCE |

**Config paths not mapped to any label** (correctly excluded from fix taxonomy):
- `config.sample_questions` — UX only, does not affect SQL accuracy
- `instructions.example_question_sqls[].parameters` — relevant when building parameterized examples but not triggered by any specific label
- `benchmarks.questions` — the evaluation target, not a fix lever (except `EMPTY_GOOD_SQL` signals broken benchmarks to remove)
