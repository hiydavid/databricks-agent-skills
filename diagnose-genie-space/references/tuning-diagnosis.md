# Genie Tuning Diagnosis

Use this reference when a user reports a failing or inconsistent Genie question. The goal is not to tune by instinct; the goal is to classify the failure, support it with evidence, and recommend the smallest structured Genie configuration change that should improve the behavior.

Diagnosis is plan-only. Do not edit config files, update a Genie Space, run benchmark evals, or mutate Databricks data.

This file is the authority for question-level failure triage and fix routing. `best-practices-checklist.md` is the broader static audit rubric. If the two appear to disagree, use this file to decide what to change and use the checklist only to classify/report static health.

## Core Principle

Prefer structured, SQL-grounded Genie context over broad text instructions.

Recommended routing order:

1. Data scope and table/column metadata
2. Prompt matching on categorical values
3. Join relationships
4. SQL snippets/expressions for reusable business logic
5. Static or parameterized example SQL for common prompt formats and complex query patterns
6. SQL functions for trusted complex logic that cannot be captured with SQL expressions or example SQL
7. Text instructions only for global behavior that cannot be encoded above

Benchmarks evaluate quality but do not teach Genie by themselves. Failed questions should be translated into metadata, join specs, SQL snippets, representative example SQL, SQL functions, or focused global instructions.

## Evidence To Gather

Start from the failing question and the user's expected behavior. Then inspect the serialized space for:

- relevant table and metric view identifiers
- table and column descriptions
- column synonyms
- `enable_format_assistance` and `enable_entity_matching` flags for v2 spaces
- `get_example_values` and `build_value_dictionary` flags for v1 spaces
- hidden/noisy columns via `exclude`
- join specs and join comments
- SQL snippets for filters, expressions, and measures
- example SQLs with similar query patterns
- SQL functions available to the space
- text instructions that might define or conflict with the behavior
- benchmarks with similar intent

Use the DBSQL MCP, Databricks SQL, or notebook SQL cells for read-only SQL only when the serialized space does not answer the diagnostic question. Good inspection queries include:

- `DESCRIBE <catalog>.<schema>.<table>`
- `SHOW COLUMNS IN <catalog>.<schema>.<table>`
- `SELECT COUNT(*) ...`
- `SELECT <column>, COUNT(*) ... GROUP BY <column> ORDER BY 2 DESC LIMIT 50`
- bounded `SELECT ... LIMIT 20` samples
- `information_schema` lookups for columns, constraints, and table metadata
- join-grain checks such as row counts before and after a candidate join

Never use DDL or DML for diagnosis.

## Prompt Matching Constraints

Apply these constraints before recommending format assistance or entity matching:

- Format assistance is automatically applied for eligible columns when tables are added to a Genie Space.
- Entity matching requires format assistance to be on for the column.
- Entity matching only supports string columns and is best for values users naturally reference, such as state/country codes, product categories, status codes, and department names.
- Entity matching supports up to 120 columns, up to 1,024 distinct values per column, and each value can be up to 127 characters.
- Tables with row filters or column masks are excluded from prompt matching. Space authors must disable entity matching for views that reference tables with row filters or column masks, and for dynamic views.
- Refresh prompt matching values when new values are added or existing values change format.

## Failure Classes

### Wrong Table Or Column

Symptoms:

- Genie selects a similarly named but incorrect table or column.
- Generated SQL omits a required dimension, date, status, amount, or identifier.
- The user says Genie "does not know which field to use."

Likely causes:

- missing or generic table descriptions
- missing or generic column descriptions
- missing synonyms for business terms
- too many overlapping tables or noisy columns exposed
- examples or snippets point to a competing field

Recommended fixes:

- Add or refine table and column descriptions.
- Add user-facing synonyms to key business columns.
- Hide irrelevant IDs, ingestion fields, audit timestamps, or duplicate columns with `exclude: true`.
- Add representative example SQL only if the pattern is complex.

Avoid:

- adding a text instruction that says "always use column X" when metadata can express the distinction
- hiding required technical keys that join specs need

### Wrong Filter Value

Symptoms:

- Genie filters for a value that does not exist.
- Genie guesses a label instead of a stored code.
- Genie gets casing, spacing, abbreviations, or category synonyms wrong.
- Genie misunderstands "active", "closed", "digital", "premium", or similar business terms.

Likely causes:

- categorical column values are not available to prompt matching
- low-cardinality category columns lack entity matching
- business terms are not mapped to stored codes
- filter logic is reusable but not represented as a snippet

Recommended fixes:

- For v2 spaces, verify `enable_format_assistance` is on for eligible filterable columns.
- For v2 spaces, enable `enable_entity_matching` only on eligible low/medium-cardinality categorical string columns.
- For v1 spaces, use `get_example_values` and `build_value_dictionary` where eligible.
- Add column synonyms for business terminology.
- Add a filter SQL snippet when the business term maps to reusable SQL logic rather than one stored value.

Avoid:

- enabling entity matching on high-cardinality free-text columns unless users naturally filter by exact values
- enabling entity matching where row filters, column masks, or dynamic views make prompt matching ineligible
- adding every categorical mapping to global text instructions

### Wrong Join

Symptoms:

- Genie omits a required table.
- Genie joins through the wrong key.
- Generated SQL duplicates rows or changes the intended grain.
- Self-joins or bridge tables are mishandled.

Likely causes:

- no join specs for the relevant relationship
- ambiguous key names
- missing relationship cardinality comments
- compound joins represented incorrectly
- grain preservation is not documented

Recommended fixes:

- Add or refine `instructions.join_specs`.
- For serialized-space config changes, use one join spec per equality condition for multi-column joins.
- For Databricks UI workflows, use SQL expressions for more complicated join conditions when the UI supports them.
- Include `comment` and `instruction` text explaining relationship meaning and when related specs should be used together.
- Add example SQL only for a representative multi-table pattern that needs more than join specs.

Avoid:

- encoding joins only in text instructions
- using compound `AND` or `OR` in a single serialized-space join spec condition

### Metric Or Business Logic Error

Symptoms:

- Genie uses count when the expected answer uses amount, balance, fee, rate, or ratio.
- Genie calculates the wrong numerator, denominator, or aggregation grain.
- Genie misses exclusions such as inactive records, reversals, test data, or cancelled orders.
- A business term such as revenue, churn, retention, utilization, penetration, conversion, or complaint rate is interpreted incorrectly.

Likely causes:

- reusable metrics are not encoded as SQL snippets
- denominator/numerator rules live only in prose
- relevant columns lack descriptions or synonyms
- an example SQL exists but is too narrow or inconsistent

Recommended fixes:

- Add SQL measure snippets for standard aggregations.
- Add SQL expression snippets for reusable CASE logic, dimensions, ratios, or derived fields.
- Add SQL filter snippets for recurring exclusions or business states.
- Add representative example SQL for multi-step metrics, windows, ratios, or conditional aggregation.
- Add a Unity Catalog SQL function when logic is too complex or sensitive to expose as example SQL or snippets, or when a trusted reusable function is the right interface.

Avoid:

- putting table-specific metric definitions in text instructions
- copying a benchmark answer or failing question verbatim into example SQL

### Time Logic Error

Symptoms:

- Genie uses the wrong date column.
- Genie gets year, month, fiscal period, or date boundary wrong.
- Rolling windows, previous periods, or month-over-month logic are incorrect.
- The result uses the wrong aggregation grain.

Likely causes:

- date columns are insufficiently described
- global fiscal calendar or timezone conventions are absent
- reusable date filters are missing
- complex time patterns lack representative examples

Recommended fixes:

- Add date column descriptions and synonyms.
- Add filter snippets for standard periods when they are reusable.
- Add example SQL for rolling windows, prior-period comparisons, or grain-sensitive time logic.
- Use text instructions only for true global conventions such as fiscal year start, timezone, or default date interpretation.

### Result Shape Error

Symptoms:

- Answer uses the right data but wrong columns, aliases, ordering, limit, or grouping.
- The user expects one row but Genie returns a time series, or the reverse.
- Ranking or tie-breaking is wrong.

Likely causes:

- the result-shape expectation is a complex pattern, not a simple metadata issue
- examples do not cover ranking/window/shape conventions
- text instructions overfit aliases or benchmark-only output details

Recommended fixes:

- Add representative example SQL for the expected result shape.
- Add snippets for reusable ranking or dimension logic when possible.
- Use a SQL function if the result shape depends on complex trusted logic that should not be rewritten by Genie.
- Use concise global text only if the shape convention applies across the entire space.

### Instruction Conflict Or Overload

Symptoms:

- Genie ignores a broad instruction.
- Different examples or snippets imply different logic.
- A new fix improves one question but risks other behavior.
- Text instructions read like a long rulebook.

Likely causes:

- too many table-specific rules in text instructions
- metric, filter, join, or ranking logic is encoded in prose instead of structured surfaces
- examples are redundant or contradictory

Recommended fixes:

- Move table/column meaning into metadata.
- Move categorical value handling into format assistance, entity matching, synonyms, or filter snippets.
- Move joins into join specs.
- Move reusable measures and filters into SQL snippets.
- Move trusted complex logic into SQL functions when examples and snippets are insufficient.
- Keep only concise global conventions in `instructions.text_instructions`.

## SQL Function Escalation

Use SQL functions only when simpler structured context is insufficient. They are appropriate when:

- the question requires complex logic that cannot be captured cleanly with a static or parameterized example SQL query
- the logic should be trusted and reused across teams
- the implementation should stay encapsulated rather than exposed or rewritten in generated SQL

SQL functions must be registered in Unity Catalog and added to the Genie Space. Space users need `EXECUTE` permission on any SQL function used as a trusted asset. Do not recommend SQL functions as the default fix for ordinary metadata, filter, join, or reusable measure problems.

## Text Instruction Guardrails

Use `instructions.text_instructions` only for:

- global conventions that apply across the space, such as fiscal calendar, timezone, default rounding, or clarification behavior
- brief result-presentation conventions that are truly universal
- behavior that cannot be represented with metadata, join specs, SQL snippets, or example SQL

Do not put these in text instructions:

- table-specific or column-specific metric definitions
- filters such as `status = 'Active'`, denominator/numerator rules, or categorical mappings
- join paths or grain-preservation rules
- benchmark-specific aliases or result-shape requirements
- top-N tie breakers, rolling-window implementations, or other multi-step SQL patterns
- long lists of business rules copied from failure analysis

If a text instruction is justified, keep it short and organize it with:

```markdown
## PURPOSE

- State the space's intended analytical purpose in one or two bullets.

## DISAMBIGUATION

- Define global terminology or ambiguity-resolution rules that apply across the space.

## DATA QUALITY NOTES

- Note global null, freshness, coding, or data-quality caveats that affect interpretation.

## CONSTRAINTS

- List global constraints that apply to all generated answers.

## Instructions you must follow when providing summaries

- State concise summary and presentation expectations for user-facing answers.
```

If a section has no true global guidance, write `- None.` rather than filling it with table-specific rules.

## Benchmark Readiness

Static diagnosis can inspect benchmark shape and coverage, but it does not prove the expected SQL is correct. Treat benchmark readiness as follows:

- **Not Ready**: fewer than 10 benchmark Q/A pairs, no SQL answers, or malformed benchmark answer shapes.
- **Needs Work**: 10-29 valid-looking SQL Q/A pairs, weak diversity, repeated simple questions, or unclear expected SQL.
- **Ready for baseline eval**: 30+ valid-looking SQL Q/A pairs with diverse coverage across entities, metrics, dimensions, filters, joins, time logic, aggregations, ranking/window patterns, and result shapes.

Invalid ground-truth SQL is a benchmark issue, not a Genie tuning target. If the user provides eval evidence that expected SQL errors or is semantically stale, recommend benchmark repair before tuning.

## Recommendation Template

For every suggested fix, write:

- **Failure class**: one primary class from this reference.
- **Evidence**: serialized-space fields and read-only SQL findings that support the diagnosis.
- **Config surface**: metadata, entity/format assistance, join spec, SQL snippet/expression, example SQL, SQL function, or text instruction.
- **Suggested change**: exact wording or JSON-level intent, without editing the config.
- **Why this surface**: why a more structured surface is better than a broader instruction.
- **Validation**: how to test after implementation, usually by retrying the failing question and then running benchmark evals via `optimize-genie-space`.
