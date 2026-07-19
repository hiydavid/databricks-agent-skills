# Genie Tuning Diagnosis

Use this reference when a user reports a failing or inconsistent Genie question. The goal is not to tune by instinct; the goal is to classify the failure, support it with evidence, and recommend the smallest structured Genie configuration change that should improve the behavior.

Diagnosis is plan-only. Do not edit config files, update a Genie Space, run benchmark evals, or mutate Databricks data.

This file is the authority for question-level failure triage and fix routing. `best-practices-checklist.md` is the broader static audit rubric. If the two appear to disagree, use this file to decide what to change and use the checklist only to classify/report static health.

## Core Principle

Prefer structured, SQL-grounded Genie context over broad text instructions.

Recommended routing order:

1. Data scope, including whether the right metric view, table, or view is exposed
2. Metric view semantics for governed metrics: measures, dimensions, filters, joins, time dimensions, and agent metadata
3. Table/column metadata for raw table-backed questions
4. Prompt matching on categorical values
5. Join relationships for raw tables exposed directly to Genie
6. SQL snippets/expressions for reusable business logic not already governed by metric views
7. Static or parameterized example SQL for common prompt formats and complex query patterns
8. SQL functions for trusted complex logic that cannot be captured with SQL expressions or example SQL
9. Text instructions only for global behavior that cannot be encoded above

Benchmarks evaluate quality but do not teach Genie by themselves. Failed questions should be translated into data source metadata, metric view model/agent metadata, join specs, SQL snippets, representative example SQL, SQL functions, or focused global instructions.

## Evidence To Gather

Start from the failing question and the user's expected behavior. Then inspect the serialized space for:

- relevant table, view, and metric view identifiers and descriptions
- metric view definitions when the failing question uses governed metrics, including source, measures, dimensions, filters, joins, time dimensions, comments, display names, synonyms, and format metadata
- table and column descriptions
- column synonyms
- `enable_format_assistance` and `enable_entity_matching` flags for v2 spaces
- `get_example_values` and `build_value_dictionary` flags for v1 spaces
- hidden/noisy columns via `exclude`
- join specs and join comments for raw tables directly exposed to Genie
- SQL snippets for filters, expressions, and measures
- example SQLs with similar query patterns
- SQL functions available to the space
- text instructions that might define or conflict with the behavior
- benchmarks with similar intent
- instructions, metadata, examples, or generated SQL that reference tables, views, or columns not attached to the Space (out-of-space references)

Also gather, when the case calls for it:

- **Monitor-tab feedback** (ask the user for exports, screenshots, or reviewable conversation details): thumbs up/down trends, negative ratings, `Fix it` and `Request review` conversations, feedback and reviewer comments, repeated user phrasing, and generated SQL or error text from reviewable conversations. See `Feedback Routing`.
- **Latency evidence** for slow-response complaints: chat vs Agent mode, benchmark vs ad hoc use, total response time, time before SQL appears, Agent reasoning time, final synthesis time, and Query History execution/queue/warehouse-startup/scan/spill/result-fetch time when available. See `Latency Pre-Routing`.
- **Permission and governance context**: Space ACLs, user `SELECT` privileges, row filters, column masks, and dynamic views on attached sources.
- **Benchmark inventory**: size, duplicate clusters, coverage categories, difficulty mix, and whether the set is too small, narrow, easy, redundant, or large for practical iteration.

Use the DBSQL MCP, Databricks SQL, or notebook SQL cells for read-only SQL only when the serialized space does not answer the diagnostic question. Good inspection queries include:

- `DESCRIBE <catalog>.<schema>.<table>`
- `DESCRIBE TABLE EXTENDED <catalog>.<schema>.<metric_view> AS JSON` to inspect metric view YAML, measures, dimensions, joins, filters, and agent metadata
- `SHOW COLUMNS IN <catalog>.<schema>.<table>`
- `SELECT COUNT(*) ...`
- `SELECT <column>, COUNT(*) ... GROUP BY <column> ORDER BY 2 DESC LIMIT 50`
- metric view checks that explicitly list dimensions and evaluate measures with `MEASURE(<measure_name>)`
- bounded `SELECT ... LIMIT 20` samples
- `information_schema` lookups for columns, constraints, and table metadata
- join-grain checks such as row counts before and after a candidate join

Never use DDL or DML for diagnosis.

When a metric view is implicated, inspect the metric view definition and run bounded metric-view queries before inspecting underlying raw tables. Drop down to source tables only to verify metric view source SQL, PK/FK constraints, join cardinality, filter scope, or grain issues.

## Latency Pre-Routing

For slow-response complaints, first separate SQL-runtime latency from query-generation or thinking-phase latency. Gather: chat versus Agent mode, benchmark versus ad hoc use, total response time, time before SQL appears, Agent reasoning time, final synthesis time, and Query History execution/queue/warehouse-startup/scan/spill/result-fetch time when available; note whether the same simple question is repeatedly slow.

- If Query History shows SQL execution, queue, warehouse startup, scan, spill, or result-fetch time dominates total latency **and the generated SQL is semantically correct for the question**, stop Space-quality diagnosis and route to query/warehouse follow-up: SQL query profiling, warehouse sizing, or table layout work outside Space configuration (for example with a query-optimization skill such as `optimize-genie-query` when available). State this handoff explicitly in the report.
- If runtime dominates but the generated SQL is wrong (wrong source, join, grain, or filter producing slow-but-incorrect SQL), classify the underlying Genie failure here and hand off to `optimize-genie-space`; do not treat it as a pure query-runtime problem.
- If SQL execution is fast but the user waits before SQL appears, during Agent reasoning, or during long final response synthesis, classify the case as `Generation Latency Or Context Overload` and recommend Space configuration cleanup through `optimize-genie-space`.
- For Agent mode, state that Agent mode can naturally take longer because it creates a plan, runs multiple queries, learns from results, and synthesizes a report. For simple deterministic questions, validate standard chat, a trusted asset, or a concise parameterized example as the lower-latency path.
- If the latency split is unavailable, ask for or inspect Query History timing before recommending warehouse, table-layout, or Space configuration changes.

## Feedback Routing

Use Monitor-tab feedback as evidence for clustering failures, not as a tuning surface. Do not recommend changing feedback, comments, review status, or conversation history as the fix. This skill runs outside the Databricks workspace UI, so gather Monitor evidence by asking the user for exports, screenshots, or reviewable conversation details.

Translate feedback patterns into the existing repair levers:

- Repeated negative feedback on the same source, metric view, measure, dimension, filter, join, or time pattern: classify the underlying wrong source, semantic model, filter, join, business logic, or time logic failure before choosing the fix.
- Review requests (`Fix it`, `Request review`) with missing SQL, wrong SQL, failed SQL, or unsupported final answers: inspect the generated SQL/error and route to the smallest structured surface that would prevent the same failure.
- User comments that explain a business term, synonym, category label, KPI definition, fiscal period, or expected result shape: treat the comment as business-intent evidence and encode the durable rule in metadata, metric view semantics, prompt matching, snippets, representative examples, or short global instructions.
- High negative-feedback volume with weak or missing benchmark coverage: recommend benchmark repair or additions before benchmark-driven tuning, and use feedback clusters to choose representative benchmark candidates.
- Feedback that contradicts passing benchmark results: check whether benchmarks are stale, too narrow, too easy, or failing to cover real user phrasing before trusting the benchmark signal.
- Privacy rule: when conversations are private or Monitor details are unavailable, use only visible prompt, status, rating, timestamp, and trend metadata; do not use Genie conversation APIs or audit logs to recover hidden content; lower confidence and state the limitation.

## Conflict Resolution And Precedence

Databricks does not publicly document a strict "surface X overrides surface Y" order for Genie Spaces at query time, so do not tell the user that one surface is guaranteed to win. Conflicting guidance resolves through three documented mechanisms; use them to explain the observed symptom and to choose the repair surface.

1. **Bindingness spectrum** — how reliably Genie obeys a surface, strongest to weakest:
   - SQL functions / trusted assets: return a verified answer; when the exact text of a parameterized query is used, Genie answers deterministically from it.
   - SQL snippets/expressions: Genie applies the logic exactly as written when it selects the expression, rather than interpreting natural language.
   - Example SQL queries: on a close match Genie may use the query directly; on a similar question it learns from it.
   - Table/column descriptions and metric view metadata: relevance-selected context, not a rule.
   - Text instructions: soft, interpreted, global, and able to be ignored (Genie ignoring instructions is a documented failure mode).

   This is an authoring and reliability order, not a guaranteed runtime override — which is why the routing order prefers structured surfaces.
2. **Relevance selection** — Genie selects the most relevant context, example, and values for each prompt. A more specific, better-matching surface effectively wins because it is selected, not because of a fixed priority, so a conflict can surface as Genie choosing the other source or example.
3. **Context budgets and crowding** — a Space allows 100 instructions (each example SQL query, each SQL function, and the entire text-instructions block each count as one) and 200 knowledge-store snippets (table descriptions, join relationships, and SQL expressions share this). Too many instructions reduce effectiveness, especially in long conversations. An overloaded surface can dilute or crowd out the guidance that should have applied, so a conflict can manifest as the correct rule being ignored.

When diagnosing a conflict, name which mechanism explains the symptom — a different surface was selected, a soft text instruction was ignored or diluted, the exact-text trusted-asset path was missed, or budget crowding — then recommend moving the rule to the most reliable surface that resolves it. When you cannot tell which surface Genie actually used, lower confidence and inspect the generated SQL.

## Prompt Matching Constraints

Apply these constraints before recommending format assistance or entity matching:

- Format assistance is automatically applied for eligible columns when tables are added to a Genie Space.
- Entity matching requires format assistance to be on for the column.
- Entity matching only supports string columns and is best for values users naturally reference, such as state/country codes, product categories, status codes, and department names.
- Entity matching supports up to 120 columns, up to 1,024 distinct values per column, and each value can be up to 127 characters.
- Tables with row filters or column masks are excluded from prompt matching. Space authors must disable entity matching for views that reference tables with row filters or column masks, and for dynamic views.
- Refresh prompt matching values when new values are added or existing values change format.

## Metric View Tuning Guidance

Use metric views as the preferred governed surface for business metrics when the space includes them. Metric views define reusable measures and allow those measures to be grouped by available dimensions at query time. They can also encode filters, joins, window measures, composed measures, and agent metadata.

Before recommending Genie SQL snippets or text instructions for a metric failure, check whether the behavior belongs in the metric view itself:

- wrong metric view selected: improve metric view descriptions, comments, display names, synonyms, or remove/clarify overlapping raw sources
- wrong measure: refine the metric view measure name, expression, comment, display name, synonyms, format, or composed-measure definition
- wrong dimension: add or clarify metric view dimensions and their metadata
- wrong time dimension: expose the granular date/time dimension and useful truncated dimensions such as day, month, quarter, or year; use window measures for rolling, cumulative, period-over-period, or semiadditive metrics
- wrong persistent filter or scope: document metric view-level filters in the metric view description/comment or measure comments, and refine the filter when the governed metric scope is wrong
- wrong metric grain: check whether the metric view measure is atomic, composed, windowed, semiadditive, or filtered correctly, and whether the selected grouping dimensions preserve the intended grain
- wrong join inside a metric: refine the metric view join model and verify many-to-one assumptions before adding Genie join specs around raw source tables

Query metric views with explicit dimensions and `MEASURE(...)` for measures. Do not assume `SELECT *` is a valid diagnostic query for metric outputs. If a metric view must be joined to another table at query time, inspect whether the recommended pattern should wrap the metric view query in a CTE before the join.

## Failure Classes

### Wrong Data Source, Metric View, Or Field

Symptoms:

- Genie selects a similarly named but incorrect data source, metric view, table, view, column, measure, or dimension.
- Genie uses a raw table when a governed metric view should answer the question, or uses a metric view when the question needs raw detail rows.
- Generated SQL omits a required dimension, date, status, amount, or identifier.
- Generated SQL, instructions, metadata, or examples reference tables, views, or columns that are not attached to the Space (out-of-space references). Genie can query beyond attached assets when prompted or when metadata points outside the Space.
- The user says Genie "does not know which source or field to use."

Likely causes:

- missing or generic metric view descriptions
- missing or generic metric view measure/dimension names, comments, display names, or synonyms
- raw tables/views and metric views overlap on the same business concepts
- missing or generic table descriptions
- missing or generic column descriptions
- missing synonyms for business terms
- too many overlapping tables or noisy columns exposed
- examples or snippets point to a competing field

Recommended fixes:

- Refine metric view descriptions and agent metadata when a governed metric is implicated.
- Clarify or reduce overlap between raw sources and metric views that represent the same business concepts.
- Remove or correct out-of-space references in instructions, metadata, and examples.
- Add or refine table and column descriptions.
- Add user-facing synonyms to key business columns.
- Hide irrelevant IDs, ingestion fields, audit timestamps, or duplicate columns with `exclude: true`.
- Add representative example SQL only if the pattern is complex.

Avoid:

- adding a text instruction that says "always use column X" when metadata can express the distinction
- hiding required technical keys that join specs need

### Wrong Metric View Measure Or Dimension

Symptoms:

- Genie selects the right metric view but uses the wrong measure.
- Genie groups by the wrong dimension or misses a required dimension.
- Genie confuses business terms such as bookings, billings, ARR, revenue, active users, conversion, or retention.
- Generated SQL does not use the expected `MEASURE(...)` call for a metric view measure.

Likely causes:

- the metric view does not expose the needed measure or dimension
- measure or dimension names are too technical or too similar
- missing display names, synonyms, comments, or format metadata
- a complex metric is modeled as one opaque expression instead of atomic and composed measures
- examples or snippets duplicate stale raw-table logic instead of using the metric view

Recommended fixes:

- Add or refine metric view measures and dimensions when the governed semantic model is missing needed concepts.
- Add agent metadata: business-facing display names, synonyms, comments, and formats for important measures and dimensions.
- Model complex ratios from atomic measures with `MEASURE(...)` references rather than repeating aggregation logic.
- Add example SQL only when the question shape needs a representative metric view query pattern after the metric view itself is clear.

Avoid:

- adding a raw-table SQL snippet that duplicates a governed metric view measure
- solving measure selection with a broad text instruction when measure metadata can encode the mapping

### Wrong Metric View Scope, Time Dimension, Or Grain

Symptoms:

- Genie answers from the right metric view but includes records outside the intended metric scope.
- A metric view-level filter such as completed orders, active accounts, or production events is missing, hidden, or misunderstood.
- Genie uses the wrong date/time dimension or date truncation.
- Rolling, cumulative, period-over-period, or balance-style questions return the wrong grain.
- Aggregating a semiadditive measure across time gives nonsensical results.

Likely causes:

- metric view persistent filters are absent, wrong, or not documented in descriptions/comments
- the metric view lacks granular or truncated time dimensions needed by the question
- window, composed, filtered, or semiadditive measures are not modeled for the intended question type
- source joins inside the metric view change row grain or violate expected many-to-one relationships

Recommended fixes:

- Add or refine metric view-level filters when the governed metric should always use a scoped population.
- Document persistent filter scope in the metric view description, view comment, or measure comments.
- Add clear time dimensions and truncated dimensions for common trend grains.
- Use metric view window measures for rolling, cumulative, period-over-period, and semiadditive metrics when available.
- Validate source joins and PK/FK constraints with bounded read-only SQL before changing Genie join specs.

Avoid:

- adding text instructions that restate hidden filter logic without fixing the metric view scope
- adding example SQL that works around a broken governed metric definition

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

- Add or refine `instructions.join_specs` when raw tables are exposed directly to Genie.
- For metric-view-owned relationships, refine the metric view join model first.
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

- governed metric definitions are missing, incomplete, or ambiguous in the metric view
- reusable metrics are not encoded as SQL snippets
- denominator/numerator rules live only in prose
- relevant columns lack descriptions or synonyms
- an example SQL exists but is too narrow or inconsistent

Recommended fixes:

- For metric-view-backed governed metrics, refine the metric view first: atomic measures, composed measures, filtered measures, window measures, dimensions, filters, joins, and agent metadata.
- Add SQL measure snippets for standard aggregations only when no metric view governs the metric.
- Add SQL expression snippets for reusable CASE logic, dimensions, ratios, or derived fields when those concepts are not better modeled in a metric view.
- Add SQL filter snippets for recurring exclusions or business states when they are not metric view-level scope.
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

- metric view time dimensions or window measures are missing, ambiguous, or too coarse
- date columns are insufficiently described
- global fiscal calendar or timezone conventions are absent
- reusable date filters are missing
- complex time patterns lack representative examples

Recommended fixes:

- For metric views, add or clarify granular and truncated time dimensions, and use window measures for rolling, cumulative, period-over-period, or semiadditive logic.
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

- the metric view query is using the wrong measure/dimension grouping or omits required `MEASURE(...)` expressions
- the result-shape expectation is a complex pattern, not a simple metadata issue
- examples do not cover ranking/window/shape conventions
- text instructions overfit aliases or benchmark-only output details

Recommended fixes:

- For metric view queries, clarify which dimensions and measures should appear for the question type.
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
- Move governed metric definitions into metric views when a metric view owns the business concept.
- Move metric view discovery terms into metric view descriptions, display names, synonyms, comments, and formats.
- Move categorical value handling into format assistance, entity matching, synonyms, or filter snippets.
- Move raw table joins into join specs; move metric-view-owned joins into the metric view model.
- Move reusable measures and filters into SQL snippets.
- Move trusted complex logic into SQL functions when examples and snippets are insufficient.
- Keep only concise global conventions in `instructions.text_instructions`.

Use `Conflict Resolution And Precedence` above to explain which mechanism (bindingness, relevance selection, or budget crowding) produced the symptom.

### Generation Latency Or Context Overload

Symptoms:

- Users complain chat or Agent-mode responses are too slow for simple questions.
- SQL execution is fast but Genie spends a long time thinking before SQL appears.
- Agent mode reasons for too long on a deterministic lookup or aggregation question.
- Generated SQL or answer text is exceptionally long; long conversations get slower or time out during the thinking phase.

Likely causes:

- too many or overlapping data sources, raw tables exposed alongside metric views for the same business concepts
- noisy columns left visible
- long source-specific text instructions
- redundant or oversized example SQL
- broad prompt matching or entity matching on columns that do not help common questions
- too many SQL functions in context, token-limit pressure, long chat history
- complex examples that teach verbose SQL for simple questions

Recommended fixes (hand off to `optimize-genie-space` for implementation):

- Reduce attached sources to a focused set, ideally 5 or fewer initially and within the documented 30 table/view limit; split broad spaces by domain when needed.
- Prefer metric views, pre-joined views, or materialized views for repeated business questions.
- Hide noisy columns with `exclude`.
- Move metric, filter, and join logic out of text instructions into metric view semantics, snippets, join specs, or representative examples.
- Keep text instructions short, global, and non-overlapping; prune redundant or excessively long example SQL.
- Recommend starting a new chat when long conversation history is likely influencing generation.

Avoid:

- optimizing warehouse size, table layout, or generated SQL when Query History shows runtime is not the bottleneck
- adding broad text instructions such as "be faster"
- adding more examples before pruning redundant context
- treating Agent-mode latency on simple questions as a SQL performance problem without validating standard chat or trusted assets

### Permission, Governance, Or Data Visibility Limitation

Symptoms:

- Empty or "no data" answers.
- The same question returns different results for different users.
- Rows or columns appear missing; results look filtered or masked.
- Users report they cannot see data they expect.

Likely causes:

- Space ACLs or insufficient user `SELECT` privileges.
- Row filters, column masks, or dynamic views applied to attached sources; end-user permissions applied at query time.

Recommended fixes:

- This is usually not a tuning problem. Confirm the governance model (ACLs, grants, row filters, column masks, dynamic views), state which limitation applies, and route data-access remediation to the workspace or governance owner rather than Space tuning.
- Lower confidence and name the smallest check (for example, comparing results across users or inspecting grants) when the split is unverified.

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
- behavior that cannot be represented with metric views, metadata, join specs, SQL snippets, or example SQL

Do not put these in text instructions:

- table-specific, column-specific, or metric-view-owned metric definitions
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
- **Ready for baseline eval**: 30+ valid-looking SQL Q/A pairs with diverse coverage across data sources, metric views, measures, dimensions, filters, joins, time logic, aggregations, ranking/window patterns, and result shapes.

Invalid ground-truth SQL is a benchmark issue, not a Genie tuning target. If the user provides eval evidence that expected SQL errors or is semantically stale, recommend benchmark repair before tuning.

## Recommendation Template

For every suggested fix, write:

- **Failure class**: one primary class from this reference.
- **Evidence**: serialized-space fields and read-only SQL findings that support the diagnosis.
- **Config surface**: data source metadata, metric view model/agent metadata, entity/format assistance, join spec, SQL snippet/expression, example SQL, SQL function, or text instruction.
- **Suggested change**: exact wording or JSON-level intent, without editing the config.
- **Why this surface**: why a more structured surface is better than a broader instruction.
- **Validation**: how to test after implementation, usually by retrying the failing question and then running benchmark evals via `optimize-genie-space`.
