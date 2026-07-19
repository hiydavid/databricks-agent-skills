# Genie Space Static Health Checklist

Use this checklist as supporting evidence after the question-level tuning diagnosis. Start with items relevant to the failing question, then summarize broader health issues. Do not let generic checklist findings outrank concrete evidence about the failing question.

This checklist is an audit and reporting rubric. `tuning-diagnosis.md` is the authority for deciding what to change and which Genie configuration surface to use. If this checklist appears to conflict with the tuning guide, follow `tuning-diagnosis.md` for the recommendation and use this file only to classify/report static health.

Evaluate each item against the serialized space JSON. For each item, determine:
- **pass**: Meets the criterion
- **fail**: Does not meet the criterion
- **warning**: Partially meets — improvement recommended
- **na**: Not applicable to this space's configuration

Provide a brief explanation for each assessment and, for any fail/warning, give a specific actionable fix referencing actual table names, column names, or instruction text from the space.

When recommending fixes, route them to the most structured Genie config surface that can represent the behavior, using the routing order in `tuning-diagnosis.md` (the fix-routing authority for this skill).

**Version detection:** First check `serialized_space.version`. If `2`, use v2 field names (`enable_format_assistance`, `enable_entity_matching`). If `1`, use v1 field names (`get_example_values`, `build_value_dictionary`). Do not mix v1 and v2 fields — v2 spaces reject v1 fields and vice versa.

## No-Query Diagnosis Mode

Continue diagnosis when bounded read-only SQL is unavailable; do not treat missing query access as a blocker. State which evidence was reviewed: Space config, generated SQL, final response, Monitor trends, comments, benchmarks, Query History, Unity Catalog metadata, or none.

Confidence levels (canonical definitions; other files reference these):

- `High`: config evidence directly explains the issue and no data validation is needed.
- `Medium`: config evidence strongly suggests the issue but result-level validation, value profiling, cardinality checks, or Query History timing is missing.
- `Low`: the likely fix depends on data values, row counts, join cardinality, freshness, permissions, or runtime behavior that cannot be inspected.

Recommend the narrowest validation that would increase confidence, such as one `EXPLAIN`, one generated-SQL review, Query History timing, a metric view definition review, or user confirmation of business intent.

---

## Data Sources

### Data Source Scope

**Data Source Count (1–25, ideally ≤5 initially)**
- Check: Total configured data sources across `serialized_space.data_sources.tables`, `serialized_space.data_sources.metric_views`, and any view-like data source arrays exposed by the serialized config. If Unity Catalog views appear as table-like entries under `tables`, count them as data sources.
- Why: Genie Spaces can be backed by tables, views, and metric views. Too many overlapping sources increases ambiguity and response latency; no data sources means Genie has nothing structured to query.
- Fail if: 0 total data sources or >25 total data sources
- Warning if: >10 total data sources
- Pass if: At least one table, view, or metric view is present. Zero tables is not a failure when metric views are present.

**Focused Data Source Selection**
- Check: Whether configured tables, views, and metric views appear relevant to the space's stated purpose (`title`, `description`)
- Why: Including unnecessary data sources adds noise and confuses Genie's source selection.
- Warning if: Data sources seem unrelated to the space's purpose

**Mixed Table And Metric View Ambiguity**
- Check: Whether raw tables/views and metric views expose overlapping business concepts such as revenue, orders, customers, or account balances
- Why: Metric views should be the governed semantic surface for reusable business metrics. Exposing both a metric view and its raw source tables can make Genie choose the wrong source or reimplement governed logic inconsistently.
- Warning if: Raw tables/views and metric views overlap on the same intended questions without clear descriptions or source-scoping guidance
- NA if: The space is metric-view-only or table/view-only, or the mixed sources cover distinct domains

**Out-Of-Space References**
- Check: Whether instructions, metadata, examples, snippets, or generated SQL reference tables, views, or columns that are not attached to the Space
- Why: Genie can query beyond attached assets when prompted or when metadata points outside the Space; dangling references cause wrong-source and missing-data failures.
- Warning if: Any config surface or observed generated SQL references objects not present in `data_sources`
- Route to: `Wrong Data Source, Metric View, Or Field` or `Instruction Conflict Or Overload` in `tuning-diagnosis.md`

### Tables And Views

**Table Descriptions**
- Check: Each table in `data_sources.tables[].description`
- Why: Genie uses table descriptions to decide which tables are relevant to a question. Missing descriptions cause incorrect table selection.
- Fail if: Any table has no description or a generic/empty description
- Good: `"description": "Daily sales transactions with line-item details, one row per product per order"`
- Bad: `"description": ""` or `"description": "sales table"`

- NA if: The space has no raw table/view data sources

### Table Columns

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
- Why: Metric views define reusable, governed metrics. Without descriptions, Genie can't match questions to the right metric view.
- Fail if: Metric views exist but lack descriptions
- NA if: No metric views are defined

**Metric View Semantic Coverage**
- Check: Metric view definitions, when available through read-only inspection, for measures, dimensions, filters, joins, and time dimensions needed for the space's intended questions
- Why: Metric views separate measure definitions from dimensions so governed metrics can be queried consistently across available dimensions.
- Warning if: Intended questions require a measure, grouping dimension, filter dimension, join path, or time dimension that is absent from the metric view
- NA if: No metric views are defined or the serialized config does not expose enough information and no read-only metric view definition was inspected

**Metric View Agent Metadata**
- Check: Metric view YAML agent metadata, when available, for display names, synonyms, formatting, and comments on important measures and dimensions
- Why: Agent metadata gives business context to metric view measures and dimensions. Synonyms help Genie discover fields from user language, while display names and formats help make measures understandable and consistently presented.
- Warning if: Important measures or dimensions have technical names, missing synonyms for common business terms, missing comments, or missing format metadata for currency, percentage, date, or other presentation-sensitive values
- NA if: No metric views are defined or the metric view definition is not available for inspection

**Persistent Filter Scope Documented**
- Check: Metric view-level `filter` definitions and comments/descriptions when read-only metric view definitions are available
- Why: Persistent filters define the metric scope, such as completed orders only. If the scope is invisible to Genie users and authors, generated answers can look inconsistent with raw-table expectations.
- Warning if: A metric view-level filter materially changes metric scope but the metric view description, comment, or measure comments do not explain it
- NA if: No metric views are defined, no persistent filter exists, or the metric view definition was not inspected

**Metric View Time Modeling**
- Check: Metric view dimensions for date/time fields and truncated time dimensions used by intended trend questions
- Why: Genie needs clear time dimensions for detailed questions, period grouping, rolling windows, and trend analysis. Metric views should expose granular time dimensions and, where useful, truncated dimensions such as month, quarter, or year.
- Warning if: Intended questions include trends, period comparisons, or rolling windows but the metric view lacks appropriate time dimensions or window/composed measures
- NA if: No metric views are defined or intended questions do not involve time

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
- Check: Whether domain-specific terms are mapped in metric view names/descriptions, measure/dimension display names, metric view synonyms, table/column descriptions, column synonyms, SQL snippets, example SQLs, SQL functions, or global text instructions
- Why: If users say "churn rate" but the governed metric is named `customer_attrition_pct`, Genie needs that mapping in the most structured surface that fits the concept.
- Warning if: The space uses specialized terminology without definitions

### Example Question SQLs

**Representative Example SQL For Complex/Common Patterns**
- Check: `serialized_space.instructions.example_question_sqls` array length
- Why: Example SQLs teach Genie common prompt formats and complex query patterns it cannot infer from schema, metadata, joins, or reusable SQL snippets alone.
- Fail if: A reported failure or benchmark evidence shows a complex/common organization-specific question pattern that lacks a representative example or SQL function
- Warning if: The space likely has complex/common question patterns but no representative examples
- NA if: The space only supports simple table/column lookup or aggregation patterns that are already covered by metadata, metric view definitions, joins, and SQL snippets

**Examples Cover Complex Patterns**
- Check: Whether example SQLs include multi-table joins, metric view `MEASURE(...)` usage, window functions, CTEs, or business logic
- Why: Simple queries (single table SELECT) don't need examples — Genie handles those. Examples should demonstrate patterns Genie would struggle with.
- Warning if: All examples are simple single-table queries

**Examples Are Diverse**
- Check: Whether example SQLs cover different question types, data sources, metric views, tables, measures, and dimensions
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
- NA if: Only 1 table is configured, or the space is metric-view-only and the necessary joins are already modeled inside the metric view
- Note: In serialized-space configs, multiple join specs between the same table pair is the safe pattern for multi-column joins. Keep each serialized join spec `sql` element to a single equality expression and add `comment` and `instruction` fields to related specs so they are used together. In the Databricks UI, more complicated join conditions can be captured with SQL expressions.
- Metric view note: For governed metrics, prefer fixing joins in the metric view model when the metric view owns the semantic relationship. Use Genie join specs for raw tables exposed directly to Genie.

**Join Specs Have Comments**
- Check: `instructions.join_specs[].comment`
- Why: Comments explain the business meaning of the relationship, helping Genie choose the right join for a given question.
- Warning if: Join specs exist without comments

### SQL Snippets

**Filter Snippets Defined**
- Check: `serialized_space.instructions.sql_snippets.filters` array
- Why: Common filters (time periods, active records, business-specific conditions) reduce errors when Genie needs to filter data.
- Warning if: A reusable business-defined filter is implicated by the failing question, benchmarks, or sample questions, is not already governed by a metric view filter or dimension, and is not defined as a snippet

**Expression Snippets Defined**
- Check: `serialized_space.instructions.sql_snippets.expressions` array
- Why: Reusable expressions for categorizations, calculations, and business logic ensure consistency across queries.
- Warning if: The space has reusable categorization, derived dimensions, calculations, or business logic that is not represented structurally in a metric view or snippet

**Measure Snippets Defined**
- Check: `serialized_space.instructions.sql_snippets.measures` array
- Why: Measures define standard aggregations (revenue, count, average) that should be computed consistently.
- Warning if: Recurring KPIs, ratios, denominators, numerators, or named aggregations are expected but not represented as metric view measures or SQL measure snippets
- Note: If a metric view already governs the measure, prefer refining the metric view before duplicating the logic as a Genie SQL snippet.

---

## Benchmarks

**At Least 30 Diverse Q&A Pairs For Optimization Readiness**
- Check: `serialized_space.benchmarks.questions` array length and diversity
- Why: Benchmarks validate that Genie produces correct SQL. Diverse coverage catches regressions across different question types. (The 30-question bar is a skill convention; the full sufficiency rule and remediation flow live in `optimize-genie-space`.)
- Fail if: Fewer than 10 benchmark questions
- Warning if: 10-29 benchmark questions, or questions cluster around a single topic or table
- Pass if: 30+ valid-looking SQL Q&A pairs with diverse coverage
- Note: Static diagnosis can check answer shape and coverage, but it cannot prove expected SQL correctness unless the user provides read-only validation evidence

**Benchmark Coverage**
- Check: Whether benchmarks cover different data sources, metric views, measures, dimensions, join patterns, aggregations, and filter types
- Why: Narrow benchmarks miss entire categories of user questions.
- Warning if: Benchmarks only test one type of query pattern

**Benchmark Answer Shape**
- Check: Each benchmark question has exactly one `answer` with `format: "SQL"`
- Why: Benchmark evals and accuracy comparison require stable SQL ground truth
- Fail if: Any benchmark question has no SQL answer, multiple answers, or a non-SQL answer

**No Benchmark Leakage**
- Check: Sample questions, snippets, and example SQLs compared with benchmark questions, benchmark answer SQL, and evaluation notes
- Why: Benchmarks should evaluate generalization, not teach the exact answer through config surfaces.
- Canonical rule (referenced by other files): never copy benchmark questions, benchmark answer SQL, or evaluation-note wording into sample questions, SQL snippets, example SQL, or any other config surface. Representative examples teach reusable patterns; they do not memorize benchmarks or failing questions.
- Fail if: Example SQL copies benchmark answer SQL or benchmark question text
- Warning if: Sample questions duplicate benchmark questions verbatim

---

## Permissions, Governance, And Data Visibility

**Governance Restrictions That Mimic Quality Failures**
- Check: Space ACLs, per-user `SELECT` privileges, row filters, column masks, and dynamic views on attached sources, when inspectable
- Why: Empty responses, per-user discrepancies, or "no data" answers can look like wrong-source or wrong-filter failures but are data-access limitations.
- Warning if: Attached sources have row filters, column masks, or dynamic-view security and users report empty, filtered, or per-user-inconsistent answers
- Route to: `Permission, Governance, Or Data Visibility Limitation` in `tuning-diagnosis.md`; remediation goes to the workspace or governance owner, not Space tuning

---

## Latency Context Pressure

Static signals that inflate generation latency (detection only; routing and fixes live in `tuning-diagnosis.md` → `Generation Latency Or Context Overload`):

- high data-source count, or raw/metric view overlap for the same concepts
- noisy visible columns
- long source-specific text instructions
- redundant or oversized example SQL
- broad prompt/entity matching
- excessive SQL functions in context
- long generated SQL or text responses

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

### Critical (must fix) — `fail` items related to the reported failure
These are likely to cause incorrect answers. Fix before running the optimizer.
- Missing data source descriptions → wrong source, metric view, table, or view selection
- Missing metric view descriptions for metric-view-backed failures → wrong metric view selection
- Missing representative examples/functions for a reported complex pattern → Genie can't learn or trust that pattern
- Missing global text instructions for a relevant global convention → inconsistent interpretation across prompts
- Missing parameter descriptions → incorrect parameterized queries
- Malformed benchmark SQL answers → unreliable evals

### Recommended (should fix) — `warning` items affecting accuracy
These reduce answer quality. Fix before or during optimization.
- Missing column synonyms → user terminology not mapped
- Missing metric view agent metadata on important measures/dimensions → governed metrics are hard for Genie to discover from business language
- Metric view missing measures, dimensions, filters, joins, or time dimensions needed by intended questions → governed metrics cannot answer those questions reliably
- Raw tables/views overlap with metric views on the same business concepts → Genie may bypass governed metric definitions
- Prompt matching not enabled on eligible categorical/filter columns → wrong filter values
- Missing join specs (multi-table spaces) → wrong or missing joins
- Fewer than 30 diverse benchmark Q&A pairs → weak baseline for optimization
- Missing SQL snippets for reusable business logic implicated by questions or benchmarks and not already governed by a metric view → inconsistent aggregations/filters
- Irrelevant columns not hidden → increased ambiguity

### Nice-to-Have — `warning` items affecting UX only
These improve user experience but don't affect SQL accuracy.
- Missing sample questions → no UI starting points
- Verbose instructions → token waste but no accuracy impact
- Missing usage guidance on examples → suboptimal but not wrong
- Generic sample questions → poor discoverability
