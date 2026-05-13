# Genie Space Static Health Checklist

Use this checklist as an authoring and review rubric for a newly generated Genie Space JSON. Start with items relevant to the selected tables and intended use cases, then summarize broader health issues.

This checklist is a quality rubric. `creation-workflow.md` is the authority for the creation sequence and for deciding which Genie configuration surface should represent a concept.

Evaluate each item against the serialized space JSON. For each item, determine:
- **pass**: Meets the criterion
- **fail**: Does not meet the criterion
- **warning**: Partially meets — improvement recommended
- **na**: Not applicable to this space's configuration

Provide a brief explanation for each assessment and, for any fail/warning, give a specific actionable fix referencing actual table names, column names, or instruction text from the space.

When recommending fixes, route them to the most structured Genie config surface that can represent the behavior:

1. table/column metadata and synonyms
2. format assistance and entity matching for categorical values
3. join specs
4. SQL snippets for reusable filters, expressions, and measures
5. representative example SQL for complex patterns
6. SQL functions for trusted complex logic that cannot be captured with SQL expressions or static/parameterized examples
7. text instructions only for concise global conventions

**Version detection:** First check `serialized_space.version`. If `2`, use v2 field names (`enable_format_assistance`, `enable_entity_matching`). If `1`, use v1 field names (`get_example_values`, `build_value_dictionary`). Do not mix v1 and v2 fields — v2 spaces reject v1 fields and vice versa.

---

## Data Sources

### Tables

**Table Count (1–25, ideally ≤5 initially)**
- Check: `serialized_space.data_sources.tables` array length
- Why: Too many tables increases ambiguity and response latency. Start small and expand as needed.
- Fail if: 0 tables or >25 tables
- Warning if: >10 tables

**Table Descriptions**
- Check: Each table in `data_sources.tables[].description`
- Why: Genie uses table descriptions to decide which tables are relevant to a question. Missing descriptions cause incorrect table selection.
- Fail if: Any table has no description or a generic/empty description
- Good: `"description": "Daily sales transactions with line-item details, one row per product per order"`
- Bad: `"description": ""` or `"description": "sales table"`

**Focused Table Selection**
- Check: Whether tables appear relevant to the space's stated purpose (`title`, `description`)
- Why: Including unnecessary tables adds noise and confuses Genie's table selection.
- Warning if: Tables seem unrelated to the space's purpose

### Columns

**Column Descriptions**
- Check: `data_sources.tables[].column_configs[].description`
- Why: Column descriptions help Genie map user questions to the right columns. Descriptions should provide context beyond what the column name conveys.
- Fail if: Columns with non-obvious names have no description
- Good: `"description": "Total revenue in USD after discounts and before tax"`
- Bad: `"description": "amount"` (just restates the column name)

**Column Synonyms**
- Check: `data_sources.tables[].column_configs[].synonyms` array
- Why: Users use varied terminology. Synonyms map business language to column names.
- Warning if: Key business columns lack synonyms
- Good: Column `total_sales` with `"synonyms": ["revenue", "sales amount", "total revenue"]`

**Example Values Enabled**
- Check: `data_sources.tables[].column_configs[].get_example_values` (v1) or `enable_format_assistance` (v2) depending on space version
- Why: Example values help Genie understand the data distribution and generate correct filter values.
- Warning if: Eligible filterable columns don't have `get_example_values: true` (v1) or `enable_format_assistance: true` (v2)
- NA if: Columns are not eligible for prompt matching because of row filters, column masks, dynamic views, or unsupported column types
- Note: v2 spaces reject `get_example_values` — use `enable_format_assistance` instead. Format assistance is automatically applied for eligible columns when tables are added to a space.

**Value Dictionary Enabled**
- Check: `data_sources.tables[].column_configs[].build_value_dictionary` (v1) or `enable_entity_matching` (v2) depending on space version
- Why: For columns with a small set of discrete values (e.g., status, region, category), a value dictionary lets Genie match user terms to exact values.
- Warning if: Eligible low/medium-cardinality string categorical columns that users filter by don't have `build_value_dictionary: true` (v1) or `enable_entity_matching: true` (v2)
- NA if: Columns are non-string, high-cardinality free text, not naturally filtered by exact value, or ineligible because of row filters, column masks, or dynamic views
- Note: v2 spaces reject `build_value_dictionary` — use `enable_entity_matching` instead. Entity matching requires format assistance and supports up to 120 columns, 1,024 distinct values per column, and 127 characters per value.

**Irrelevant Columns Hidden**
- Check: `data_sources.tables[].column_configs[].exclude` — columns with `exclude: true` are hidden from Genie
- Why: Extra columns increase ambiguity. Hide columns users won't query by setting `exclude: true`.
- Warning if: Columns like internal IDs, audit timestamps, or ETL metadata have `exclude: false` or no `exclude` field

### Metric Views

**Metric View Descriptions**
- Check: `data_sources.metric_views[].description` (if metric_views exist)
- Why: Metric views surface pre-computed metrics. Without descriptions, Genie can't match questions to the right metric.
- Fail if: Metric views exist but lack descriptions
- NA if: No metric views are defined

---

## Instructions

### Text Instructions

**Global Text Instructions When Needed**
- Check: `serialized_space.instructions.text_instructions` array length
- Why: Text instructions provide global context that shapes how Genie interprets questions and writes SQL. They should be used only for global conventions that do not fit metadata, examples, functions, joins, or SQL snippets.
- Warning if: No text instructions exist and the space appears to need global conventions such as fiscal calendar, timezone, default rounding, response language, or default interpretation rules
- NA if: No true global conventions are needed for this space

**Instructions Are Focused and Minimal**
- Check: Length and content of text instructions
- Why: Overly long or verbose instructions dilute their impact. Instructions should be concise directives, not documentation. SQL examples, metrics, and join logic belong in their respective sections.
- Warning if: Instructions are excessively long (>500 words total) or contain embedded SQL

**Business Jargon Mapped**
- Check: Whether domain-specific terms are mapped in table/column descriptions, synonyms, SQL snippets, example SQLs, SQL functions, or global text instructions
- Why: If users say "churn rate" but the data uses "customer_attrition_pct", Genie needs that mapping in the most structured surface that fits the concept.
- Warning if: The space uses specialized terminology without definitions

### Example Question SQLs

**Representative Example SQL For Complex/Common Patterns**
- Check: `serialized_space.instructions.example_question_sqls` array length
- Why: Example SQLs teach Genie common prompt formats and complex query patterns it cannot infer from schema, metadata, joins, or reusable SQL snippets alone.
- Fail if: An intended use case or benchmark evidence shows a complex/common organization-specific question pattern that lacks a representative example or SQL function
- Warning if: The space likely has complex/common question patterns but no representative examples
- NA if: The space only supports simple table/column lookup or aggregation patterns that are already covered by metadata, joins, and SQL snippets

**Examples Cover Complex Patterns**
- Check: Whether example SQLs include multi-table joins, window functions, CTEs, or business logic
- Why: Simple queries (single table SELECT) don't need examples — Genie handles those. Examples should demonstrate patterns Genie would struggle with.
- Warning if: All examples are simple single-table queries

**Examples Are Diverse**
- Check: Whether example SQLs cover different question types and tables
- Why: Redundant examples waste context. Each should teach a distinct pattern.
- Warning if: Multiple examples use nearly identical patterns

**Queries Are Concise**
- Check: Length and complexity of example SQL queries
- Why: Example queries should be as short as possible while remaining complete. Excessive comments or formatting waste tokens.
- Warning if: Queries contain unnecessary verbosity

**Parameters Have Descriptions**
- Check: `instructions.example_question_sqls[].parameters[].description` (if parameters exist)
- Why: Parameter descriptions help Genie understand what values to substitute.
- Fail if: Parameters exist without descriptions
- NA if: No parameters are used

**Complex Examples Have Usage Guidance**
- Check: `instructions.example_question_sqls[].usage_guidance` on complex examples
- Why: Usage guidance tells Genie when to apply a pattern — what keywords or question types should trigger it.
- Warning if: Complex multi-step examples lack usage guidance

### Join Specs

**Join Specs for Multi-Table Relationships**
- Check: `serialized_space.instructions.join_specs` array
- Why: Without explicit join specs, Genie may guess wrong join conditions, especially for self-joins or non-obvious foreign keys.
- Warning if: Multiple tables exist but no join specs are defined
- NA if: Only 1 table is configured
- Note: In serialized-space configs, multiple join specs between the same table pair is the safe pattern for multi-column joins. Keep each serialized join spec `sql` element to a single equality expression and add `comment` and `instruction` fields to related specs so they are used together. In the Databricks UI, more complicated join conditions can be captured with SQL expressions.

**Join Specs Have Comments**
- Check: `instructions.join_specs[].comment`
- Why: Comments explain the business meaning of the relationship, helping Genie choose the right join for a given question.
- Warning if: Join specs exist without comments

### SQL Snippets

**Filter Snippets Defined**
- Check: `serialized_space.instructions.sql_snippets.filters` array
- Why: Common filters (time periods, active records, business-specific conditions) reduce errors when Genie needs to filter data.
- Warning if: A reusable business-defined filter is implicated by intended use cases, benchmarks, or sample questions but is not defined as a snippet

**Expression Snippets Defined**
- Check: `serialized_space.instructions.sql_snippets.expressions` array
- Why: Reusable expressions for categorizations, calculations, and business logic ensure consistency across queries.
- Warning if: The space has reusable categorization, derived dimensions, calculations, or business logic that is not represented structurally

**Measure Snippets Defined**
- Check: `serialized_space.instructions.sql_snippets.measures` array
- Why: Measures define standard aggregations (revenue, count, average) that should be computed consistently.
- Warning if: Recurring KPIs, ratios, denominators, numerators, or named aggregations are expected but not represented as measures

---

## Benchmarks

**At Least 30 Diverse Q&A Pairs For Optimization Readiness**
- Check: `serialized_space.benchmarks.questions` array length and diversity
- Why: Benchmarks validate that Genie produces correct SQL. Diverse coverage catches regressions across different question types.
- Fail if: Fewer than 10 benchmark questions
- Warning if: 10-29 benchmark questions, or questions cluster around a single topic or table
- Pass if: 30+ valid-looking SQL Q&A pairs with diverse coverage
- Note: Static review can check answer shape and coverage, but it cannot prove expected SQL correctness unless the user provides read-only validation evidence

**Benchmark Coverage**
- Check: Whether benchmarks cover different tables, join patterns, aggregations, and filter types
- Why: Narrow benchmarks miss entire categories of user questions.
- Warning if: Benchmarks only test one type of query pattern

**Benchmark Answer Shape**
- Check: Each benchmark question has exactly one `answer` with `format: "SQL"`
- Why: Benchmark evals and accuracy comparison require stable SQL ground truth
- Fail if: Any benchmark question has no SQL answer, multiple answers, or a non-SQL answer

---

## Config

**Sample Questions Present**
- Check: `serialized_space.config.sample_questions` array
- Why: Sample questions appear in the Genie UI as starting points for users. They demonstrate what the space can answer.
- Warning if: No sample questions are defined

**Sample Questions Are Representative**
- Check: Whether sample questions cover the space's key capabilities
- Why: Sample questions should showcase the most valuable query patterns and guide users toward what the space does well.
- Warning if: Sample questions are generic or don't reflect the space's data

---

## Remediation Priority Guide

When generating the prioritized remediation plan, assign each fix to a tier:

### Critical (must fix) — `fail` items related to intended use cases
These are likely to cause incorrect answers. Fix before live creation or optimizer handoff.
- Missing table/column descriptions → wrong table/column selection
- Missing representative examples/functions for a reported complex pattern → Genie can't learn or trust that pattern
- Missing global text instructions for a relevant global convention → inconsistent interpretation across prompts
- Missing parameter descriptions → incorrect parameterized queries
- Malformed benchmark SQL answers → unreliable evals

### Recommended (should fix) — `warning` items affecting accuracy
These reduce answer quality. Fix before or during optimization.
- Missing column synonyms → user terminology not mapped
- Prompt matching not enabled on eligible categorical/filter columns → wrong filter values
- Missing join specs (multi-table spaces) → wrong or missing joins
- Fewer than 30 diverse benchmark Q&A pairs → weak baseline for optimization
- Missing SQL snippets for reusable business logic implicated by questions or benchmarks → inconsistent aggregations/filters
- Irrelevant columns not hidden → increased ambiguity

### Nice-to-Have — `warning` items affecting UX only
These improve user experience but don't affect SQL accuracy.
- Missing sample questions → no UI starting points
- Verbose instructions → token waste but no accuracy impact
- Missing usage guidance on examples → suboptimal but not wrong
- Generic sample questions → poor discoverability
