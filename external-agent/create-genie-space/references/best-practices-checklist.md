# Genie Space Static Health Checklist

Use this checklist as an authoring and review rubric for a newly generated Genie Space JSON. Start with items relevant to the selected tables, views, Metric Views, and intended use cases, then summarize broader health issues.

This checklist is a quality rubric. `creation-workflow.md` is the authority for the creation sequence and for deciding which Genie configuration surface should represent a concept.

Evaluate each item against the serialized space JSON. For each item, determine:
- **pass**: Meets the criterion
- **fail**: Does not meet the criterion
- **warning**: Partially meets — improvement recommended
- **na**: Not applicable to this space's configuration

Provide a brief explanation for each assessment and, for any fail/warning, give a specific actionable fix referencing actual data source names, table names, column names, Metric View names, or instruction text from the space.

When recommending fixes, route them to the most structured Genie config surface that can represent the behavior. This is the canonical structured-surfaces priority order for this skill; `SKILL.md` and `creation-workflow.md` point here instead of redefining it:

1. Metric View semantic metadata when a selected Metric View already owns the business metric
2. focused data source selection
3. table/column metadata and synonyms
4. format assistance and entity matching for eligible categorical values, after prompt matching safety review
5. join specs for table/table or table/view relationships
6. SQL snippets for reusable filters, expressions, and measures not already captured by Metric Views
7. representative example SQL for complex patterns, including valid Metric View `MEASURE()` queries
8. SQL functions for trusted complex logic that cannot be captured with SQL expressions or static/parameterized examples
9. text instructions only for concise global conventions

**Version detection:** First check `serialized_space.version`. If `2`, use v2 field names (`enable_format_assistance`, `enable_entity_matching`). If `1`, use v1 field names (`get_example_values`, `build_value_dictionary`). Do not mix v1 and v2 fields — v2 spaces reject v1 fields and vice versa.

**Readiness evidence:** For new spaces, confirm the author performed a requirements-driven readiness check. The space should be traceable back to 3-5 real business questions, with unsupported questions either resolved or documented as assumptions/limitations.

---

## Data Sources

### Data Source Scope

**Data Object Count (1-30, ideally ≤5 initially)**
- Check: `serialized_space.data_sources.tables` plus `serialized_space.data_sources.metric_views`
- Why: Too many data objects increase ambiguity and response latency. Start small and expand as needed. Databricks currently supports up to 30 tables or views in a Genie Space, and Metric Views are the preferred simplification layer when metrics/dimensions are already modeled.
- Fail if: No tables, views, or Metric Views are configured, or total data objects exceed 30
- Warning if: Total data objects exceed 10

**Upstream Denormalization Over Many Raw Tables**
- Check: Whether a focused design would need more than ~5 sources, approach the 30-table/view limit, or depend on ambiguous multi-hop joins
- Why: Pre-joining or denormalizing upstream into a curated view or Metric View is the primary strategy for both the table limit and accuracy; attaching many raw tables leaves Genie to recover join paths at query time.
- Warning if: The draft attaches many raw tables where an upstream pre-joined view or Metric View would be cleaner. This skill does not create Metric Views: document the semantic-model gap and recommend authoring the Metric View upstream (for example with a metric-view authoring skill when available).

**Focused Data Object Selection**
- Check: Whether tables, views, and Metric Views appear relevant to the space's stated purpose (`title`, `description`)
- Why: Including unnecessary data objects adds noise and confuses Genie's source selection.
- Warning if: Data objects seem unrelated to the space's purpose

**Business Question Coverage**
- Check: Whether sample questions, examples, benchmarks, snippets, and joins cover the user's stated business questions
- Why: A space can pass structural validation while still failing the user's actual goals
- Warning if: One or more stated questions lack supporting source fields, Metric View measures, joins, examples, or benchmarks

### Tables And Standard Views

**Table Descriptions**
- Check: Each table in `data_sources.tables[].description`
- Why: Genie uses table descriptions to decide which tables are relevant to a question. Missing descriptions cause incorrect table selection.
- Fail if: Any table has no description or a generic/empty description
- Good: `"description": "Daily sales transactions with line-item details, one row per product per order"`
- Bad: `"description": ""` or `"description": "sales table"`
- Note: Inspect and correct AI-generated Unity Catalog table and column descriptions before trusting them; do not pass inaccurate auto-generated comments into Space context.

- NA if: No tables or standard views are configured

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

**Prompt Matching Safety**
- Check: Which columns have format assistance or entity matching enabled, against the sensitivity review from profiling
- Why: Representative values for prompt matching are generated using the author's permissions and become part of the Space's shared context, visible to Space users. Values beyond the documented caps (120 columns, 1,024 distinct values per column, 127 characters per value) are not indexed, so spend the budget on the highest-signal categorical columns rather than enabling everything.
- Fail if: Format assistance or entity matching is enabled on sensitive fields, high-cardinality identifiers, free text, or any view that references row filters, column masks, or dynamic-view security logic — unless the user explicitly confirmed the values are safe to share. If values might expose data outside the intended audience, hide the column or document the security caveat instead.

**Irrelevant Columns Hidden**
- Check: `data_sources.tables[].column_configs[].exclude` — columns with `exclude: true` are hidden from Genie
- Why: Extra columns increase ambiguity. Hide columns users won't query by setting `exclude: true`.
- Warning if: Columns like internal IDs, audit timestamps, or ETL metadata have `exclude: false` or no `exclude` field
- NA if: No tables or standard views are configured

### Metric Views

**Metric View Descriptions**
- Check: `data_sources.metric_views[].description` (if metric_views exist)
- Why: Metric views surface pre-computed metrics. Without descriptions, Genie can't match questions to the right metric.
- Fail if: Metric views exist but lack descriptions
- NA if: No metric views are defined

**Metric View Semantic Metadata**
- Check: Metric View definition from `DESCRIBE TABLE EXTENDED <catalog.schema.metric_view> AS JSON`, especially display names, synonyms, and format metadata for key dimensions and measures
- Why: Databricks Metric View agent metadata helps Genie understand business terminology and formatting for dimensions and measures.
- Warning if: Key dimensions or measures lack display names or synonyms and users are likely to use business terms that differ from the technical names
- NA if: No Metric Views are defined, or the user does not have permission to inspect the Metric View definition

**Metric View Query Syntax**
- Check: Example SQLs and benchmark answers that query Metric Views
- Why: Metric View measures must be evaluated with `MEASURE()` and should not be queried with `SELECT *`.
- Fail if: Metric View examples or benchmarks select measures without `MEASURE()` or use `SELECT *`
- Warning if: Metric View examples omit representative dimensions or grouping
- NA if: No Metric View examples or benchmarks are present

**Metric View Mixed-Source Joins**
- Check: Mixed Metric View plus table/view example SQLs
- Why: Metric Views cannot be directly joined to other tables at query time. Query the Metric View in a CTE, then join the CTE result to tables/views.
- Fail if: Example SQLs or benchmark answers directly join a Metric View to another table/view
- NA if: The space is Metric View-only or has no mixed-source examples

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
- Warning if: Instructions are excessively long (>2,000 characters or >500 words total) or contain embedded SQL

**Canonical GSL Sections**
- Check: `instructions.text_instructions[].content`
- Why: The Create, Fix, and Optimize workflows need a consistent text-instruction schema
- Warning if: Text instructions do not use the canonical GSL section template (`space-schema.md` → Text Instructions)
- NA if: No text instruction is needed

**Business Jargon Mapped**
- Check: Whether domain-specific terms are mapped in Metric View agent metadata, table/column descriptions, synonyms, SQL snippets, example SQLs, SQL functions, or global text instructions
- Why: If users say "churn rate" but the data uses "customer_attrition_pct", Genie needs that mapping in the most structured surface that fits the concept.
- Warning if: The space uses specialized terminology without definitions

### Example Question SQLs

**Representative Example SQL For Complex/Common Patterns**
- Check: `serialized_space.instructions.example_question_sqls` array length
- Why: Example SQLs teach Genie common prompt formats and complex query patterns it cannot infer from schema, metadata, joins, or reusable SQL snippets alone.
- Fail if: An intended use case or benchmark evidence shows a complex/common organization-specific question pattern that lacks a representative example or SQL function
- Warning if: The space likely has complex/common question patterns but no representative examples
- NA if: The space only supports simple table/column lookup or Metric View measure/dimension patterns that are already covered by metadata, joins, Metric View semantics, and SQL snippets

**Examples Cover Complex Patterns**
- Check: Whether example SQLs include multi-table joins, window functions, CTEs, or business logic
- Why: Simple queries (single table SELECT) don't need examples — Genie handles those. Examples should demonstrate patterns Genie would struggle with.
- Warning if: All examples are simple single-table queries

**Examples Are Diverse**
- Check: Whether example SQLs cover different question types and data objects
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

**Parameters Have Real Defaults**
- Check: `instructions.example_question_sqls[].parameters[].default_value`
- Why: Parameterized examples should be tested with real profiled values, and fake defaults produce empty or misleading examples
- Fail if: SQL contains `:param_name` placeholders without matching parameter metadata and real defaults
- Warning if: Defaults look like placeholders rather than values observed during profiling

**Complex Examples Have Usage Guidance**
- Check: `instructions.example_question_sqls[].usage_guidance` on complex examples
- Why: Usage guidance tells Genie when to apply a pattern — what keywords or question types should trigger it.
- Warning if: Complex multi-step examples lack usage guidance

### Trusted Assets

**Trusted Assets For High-Value Questions**
- Check: Whether questions that must be answered consistently use parameterized example SQL or registered UC SQL functions rather than plain examples or text instructions
- Why: Trusted assets are the surfaces that return verified answers. Parameterized example SQL uses `:param_name` parameters with descriptions, type hints, and real defaults; when a user question matches its exact text, Genie can answer deterministically from it. UC SQL functions register reusable, governed logic so Genie calls verified SQL rather than re-deriving it.
- Warning if: A high-value, frequently asked, or audit-sensitive question relies on plain example SQL or a text instruction instead of a trusted asset
- Note: Trusted assets do not replace Metric View semantics — keep governed business definitions in the Metric View and use trusted assets for verified query shapes on top of them. Trusted assets and SQL functions count against the instruction budget, so add the ones that earn their place rather than registering everything.

### Join Specs

**Join Specs for Multi-Table/Table-View Relationships**
- Check: `serialized_space.instructions.join_specs` array
- Why: Without explicit join specs, Genie may guess wrong join conditions for table/table or table/view joins, especially for self-joins or non-obvious foreign keys.
- Warning if: Multiple tables/views exist but no join specs are defined
- NA if: Only 1 table/view is configured, or the space is Metric View-only
- Note: In serialized-space configs, multiple join specs between the same table pair is the safe pattern for multi-column joins. Keep each serialized join spec `sql` element to a single equality expression and add `comment` and `instruction` fields to related specs so they are used together. In the Databricks UI, more complicated join conditions can be captured with SQL expressions.
- Note: For mixed Metric View plus table/view query examples, prefer a CTE pattern over direct Metric View join specs unless Databricks serialized-space behavior is known to support the exact join.

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
- Warning if: Recurring KPIs, ratios, denominators, numerators, or named aggregations are expected but not represented as measures or as Metric View measures

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
- Check: Whether benchmarks cover different data objects, Metric View dimensions/measures, join patterns, aggregations, and filter types
- Why: Narrow benchmarks miss entire categories of user questions.
- Warning if: Benchmarks only test one type of query pattern

**Benchmark Answer Shape**
- Check: Each benchmark question has exactly one `answer` with `format: "SQL"`
- Why: Benchmark evals and accuracy comparison require stable SQL ground truth
- Fail if: Any benchmark question has no SQL answer, multiple answers, or a non-SQL answer

**Benchmark Values Are Real And Concrete**
- Check: Benchmark SQL literals and execution evidence
- Why: Benchmarks with invented filter values often execute successfully but return zero rows, creating weak or misleading evals
- Warning if: Benchmark SQL uses placeholders, fake values, or values not found during profiling
- Warning if: A benchmark query returns zero rows and the question is not explicitly about absence of data

**No Benchmark Leakage**
- Check: Sample questions and example SQLs compared with benchmark questions and benchmark answer SQL
- Why: Benchmarks should evaluate generalization, not teach the exact answer through examples
- Fail if: Example SQL copies benchmark answer SQL or benchmark question text
- Warning if: Sample questions duplicate benchmark questions verbatim

---

## Limits And Scale

**Instruction Count**
- Check: Count `text_instructions`, `example_question_sqls`, `sql_functions`, `join_specs`, and all SQL snippet entries
- Why: Genie instruction surfaces have practical/API limits and large instruction stores dilute prompt context
- Warning if: Total instruction objects exceed 100

**Prompt Matching Count**
- Check: Number of columns with v2 `enable_entity_matching: true`
- Why: Entity matching is most useful on a focused set of categorical columns and has platform limits
- Warning if: Entity matching is enabled for more than 120 columns, or broadly enabled on IDs, timestamps, numeric measures, or high-cardinality free text

**Knowledge-Store Snippet Count**
- Check: Count table descriptions, join relationships, and SQL expressions together
- Why: Databricks documents up to 200 knowledge-store snippets per Space; bloated stores dilute context
- Warning if: Snippet-style entries approach or exceed 200

**Benchmark Count**
- Check: Count `benchmarks.questions`
- Why: Databricks documents up to 500 benchmark questions per Space; oversized sets slow iteration
- Warning if: Benchmark questions approach or exceed 500

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

**Natural Phrasing Variants**
- Check: Whether key intents have 2-4 natural phrasings across sample questions and benchmark coverage
- Why: Users word the same request different ways; multiple phrasings make matching robust to real usage.
- Warning if: Each key intent appears in only one phrasing, or variants only swap a date or category literal

---

## Live-Creation Prerequisites

Before proposing live creation or update through the API, confirm:

- The Space uses Unity Catalog data and the editor has the required Genie and data permissions.
- A pro or serverless SQL warehouse is available with `CAN USE`.
- The draft stays within documented limits: 30 tables/views, 100 instructions, 200 knowledge-store snippets, and 500 benchmark questions.
- The Context Evidence Gate in `data-profiling-and-readiness.md` is met for every included source, or uncompleted checks are recorded as confidence reductions.

---

## Remediation Priority Guide

When generating the prioritized remediation plan, assign each fix to a tier:

### Critical (must fix) — `fail` items related to intended use cases
These are likely to cause incorrect answers. Fix before live creation or optimizer handoff.
- Missing Metric View descriptions or table/column descriptions → wrong data object or column selection
- Invalid Metric View example SQL or benchmark SQL → generated SQL can fail or teach the wrong pattern
- Missing representative examples/functions for a reported complex pattern → Genie can't learn or trust that pattern
- Missing global text instructions for a relevant global convention → inconsistent interpretation across prompts
- Missing parameter descriptions → incorrect parameterized queries
- Malformed benchmark SQL answers → unreliable evals

### Recommended (should fix) — `warning` items affecting accuracy
These reduce answer quality. Fix before or during optimization.
- Missing Metric View agent metadata or column synonyms → user terminology not mapped
- Prompt matching not enabled on eligible categorical/filter columns → wrong filter values
- Missing join specs (multi-table/table-view spaces) → wrong or missing joins
- Missing CTE examples for mixed Metric View plus table/view questions → invalid direct joins
- Fewer than 30 diverse benchmark Q&A pairs → weak baseline for optimization
- Missing SQL snippets for reusable business logic implicated by questions or benchmarks → inconsistent aggregations/filters
- Irrelevant columns not hidden → increased ambiguity

### Nice-to-Have — `warning` items affecting UX only
These improve user experience but don't affect SQL accuracy.
- Missing sample questions → no UI starting points
- Verbose instructions → token waste but no accuracy impact
- Missing usage guidance on examples → suboptimal but not wrong
- Generic sample questions → poor discoverability
