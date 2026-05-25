# Genie Space Quality Tuning

Reference docs:

- Tune/build knowledge store: https://docs.databricks.com/aws/en/genie/tune-quality
- Current knowledge store page: https://docs.databricks.com/aws/en/genie/knowledge-store
- Best practices: https://docs.databricks.com/aws/en/genie/best-practices
- Troubleshooting: https://docs.databricks.com/aws/en/genie/troubleshooting
- Metric views: https://docs.databricks.com/gcp/en/business-semantics/metric-views
- Query metric views: https://docs.databricks.com/gcp/en/business-semantics/metric-views/query

Use this when analyzing benchmark reports and proposing edits to `serialized_space`.

## Core Principle

Tune the controllable context around Genie, then re-run benchmarks. Prefer structured, SQL-grounded context over broad text instructions.

Recommended priority:

1. Data scope and metadata
2. Prompt matching on categorical values
3. Join relationships
4. SQL expressions for reusable business logic
5. Example SQL for complex query patterns
6. Text instructions only for global behavior that cannot be encoded above

Benchmarks evaluate quality but do not teach Genie by themselves. To improve quality, translate failed benchmark evidence into metadata, join specs, SQL snippets, example SQL, or focused text instructions.

## Repair Decision Stack

Before editing a config version, answer these questions in the fix plan:

1. Is this a valid tuning failure?
   - Exclude invalid expected SQL, stale benchmark questions, permissions, warehouse/API failures, and incomplete eval output.
2. What changed in the generated SQL or answer?
   - Wrong source, wrong column, wrong join, wrong filter value, missing filter, wrong aggregation, wrong time logic, wrong metric formula, wrong grain, missing output field, syntax failure, or answer-prose issue.
3. What is the smallest repair lever?
   - Source/column metadata, Metric View metadata, entity/value matching, format assistance, join spec, SQL snippet, representative example SQL, or text instruction.
4. Is there a proactive enrichment that would help multiple failures?
   - Missing descriptions, synonyms, categorical value semantics, date-role descriptions, reusable filters/measures, join specs, examples for complex grain/ranking/window logic.
5. What slice proves the repair?
   - Identify affected benchmark question IDs and related previous-good regression questions.
6. What should be recorded for the next loop?
   - Cluster, attempted lever, expected impact, result, regressions, and whether to retry or avoid the approach.

Every tuning pass must name the target failure cluster and repair lever before editing JSON.

For every proposed change, include:

```markdown
- Target cluster:
- Config surface:
- Why this lever:
- Why this is not benchmark leakage:
- Why this is safer than a broad text instruction:
- Regression questions to watch:
```

## Failure Clustering Before Edits

Cluster valid tuning failures before each candidate edit. Fix shared root causes instead of patching one question at a time.

```markdown
## Failure Clusters

| Cluster | Affected Qs | Root Cause | Evidence | Repair Lever | Expected Fixes | Regression Risk |
|---|---:|---|---|---|---:|---|
| status_value_mapping | 5 | Genie maps active/inactive terms to wrong stored values | generated SQL filters `status = 'A'`; expected uses `status = 'ACTIVE'` | column metadata + entity/value matching | 5 | medium |
| customer_order_join | 3 | missing stable customer-to-order join | generated SQL cross-joins or omits customer table | join spec | 3 | high |
```

Repair priority:

1. High-count clusters with one clear structured lever.
2. Critical/P0 benchmark questions.
3. Low-regression metadata enrichment.
4. SQL snippets for reusable logic that metadata cannot express.
5. Representative example SQL for complex grain, ranking, windows, or multi-step logic.
6. Text instructions only for global behavior that cannot be encoded structurally.

## Failure-to-Lever Routing

| Failure pattern | Evidence to inspect | Preferred repair lever | Avoid |
|---|---|---|---|
| Wrong table/source selected | Generated SQL uses the wrong configured table or metric view | Improve source descriptions, source names/synonyms, and differentiating metadata | Broad text instruction saying "use table X" for one benchmark |
| Wrong column selected | Correct source, wrong field | Column description, synonyms/business aliases, hide or de-emphasize confusing columns if supported | Example SQL unless the pattern is complex |
| Wrong Metric View measure | Wrong measure selected or measure intent misunderstood | Metric View display names, descriptions, measure metadata, related dimensions | Duplicating governed measure logic in text instructions |
| Wrong metric formula outside Metric View | Wrong numerator, denominator, or aggregation | SQL snippet for reusable measure logic; representative example for complex formula | Global text instruction with metric math |
| Wrong filter value | SQL uses wrong categorical literal or status mapping | Column description with value semantics, entity/value matching, format assistance, reusable filter snippet | Copying benchmark answer filter into example SQL |
| Missing business filter | Expected SQL has a reusable business filter missing in generated SQL | Reusable filter SQL snippet or concise source/column metadata explaining default business scope | Long instruction list of every filter |
| Wrong join path | SQL omits or misuses a join | Join spec after validating keys and grain | Join spec based only on column-name similarity |
| Wrong join relationship/grain | Duplicated rows, wrong counts, many-to-many issue | Join spec with relationship/grain guidance; example SQL for grain-preserving pattern | Blind aggregation workaround |
| Wrong date field | Uses `created_at` instead of `closed_at`, `effective_date`, etc. | Column descriptions for date roles; snippet for common time filter | Text instruction listing many date rules |
| Wrong time window | Wrong interval, boundary, fiscal period, or relative date logic | SQL snippet for reusable window; representative example for complex period logic | One-off benchmark-specific example |
| Wrong aggregation grain | Counts rows instead of entities, averages at wrong level, misses distinct | SQL snippet for reusable grain logic; example SQL for representative complex query | Source description only |
| Ranking/top-N/window failure | Missing window function, wrong tie-breaker, wrong order | Representative example SQL; reusable snippet if the expression repeats | Many examples pasted into global instruction |
| Correct SQL, bad answer prose | SQL/results acceptable but final explanation weak | Short response-quality text instruction | Changing SQL surfaces |
| Syntax failure | Generated SQL invalid | Inspect exact syntax issue; repair snippets/examples only if pattern repeats | Treating syntax failure as business logic failure |
| Invalid expected SQL | Expected benchmark answer errors or is stale | Benchmark repair outside config tuning | Genie config tuning |
| Incomplete eval / permissions / API | Eval did not complete or details missing | Infrastructure/access fix | Genie config tuning |
| Space too broad / asset ambiguity | Failures scatter across many unrelated sources | Source scoping, descriptions, ambiguity reduction, possible Space split recommendation | More global instructions |

## Proactive Enrichment Before Repair

Before proposing a patch, inspect the current Space/config and failing questions for low-risk enrichments:

1. Are source descriptions missing, thin, or indistinguishable?
2. Are business terms from failed questions absent from source/column descriptions or synonyms?
3. Are low-cardinality categorical columns causing wrong literal values?
4. Are status, type, segment, region, channel, or lifecycle values undocumented?
5. Are date roles ambiguous, such as `created_at` vs `closed_at` vs `effective_date`?
6. Are repeated joins failing because join specs are missing or unclear?
7. Are repeated metrics, filters, or time windows better expressed as SQL snippets?
8. Is a representative example needed for complex grain, ranking, window, or period logic?
9. Is text instruction being used as a dumping ground for logic that belongs in metadata, snippets, examples, or joins?
10. Is the Space backed by Metric Views, and should the repair target Metric View metadata rather than raw table logic?
11. Are there too many data sources in one Space, causing routing confusion?

## Text Instruction Last-Resort Rule

Do not use text instructions as the default repair. If the proposed instruction names specific tables, metric views, columns, joins, filters, denominators, numerators, aliases, ranking logic, or window logic, first try to encode the rule in source/column metadata, entity/value matching, format assistance, join specs, SQL snippets, or representative example SQL.

Use text instructions only for global behavior that cannot be encoded structurally. Each text instruction edit must include:

```markdown
## Text Instruction Justification

- Exact instruction text:
- Why structured surfaces were insufficient:
- Which failures this targets:
- Which regressions this could cause:
- How the candidate eval will validate it:
```

## Iteration Reflection Template

After each candidate eval, append this reflection to the fix plan before starting another repair pass:

```markdown
## Iteration Reflection

- Candidate version:
- Target cluster:
- Lever attempted:
- Result:
- Fixed question IDs:
- Regressed question IDs:
- Still failing question IDs:
- Root cause update:
- Do not repeat:
- Next repair hypothesis:
```

## Serialized Config Mapping

Use these serialized-space areas for quality changes:

- `data_sources.tables[].column_configs[]` and `data_sources.metric_views[].column_configs[]` when present
  - `enable_format_assistance`: representative value/type/format context.
  - `enable_entity_matching`: value matching for categorical string columns.
- `instructions.join_specs`
  - Define standard joins when Genie picks wrong joins or omits joins.
- `instructions.sql_snippets`
  - Reusable measures, filters, dimensions, and business expressions.
- `instructions.example_question_sqls`
  - Complete verified SQL examples for complex or multi-step questions.
- `instructions.text_instructions`
  - Concise global behavior rules. Use sparingly.
- `benchmarks.questions`
  - Test coverage only; not tuning context.

## Metric View Source Handling

Before routing fixes, inspect both `data_sources.tables` and `data_sources.metric_views` in the decoded serialized space. Tune the source type that is actually configured for the space instead of assuming all sources are tables.

Metric views are first-class Genie data sources in this workflow. For metric-view-backed spaces, prefer existing metric view measures, dimensions, filters, joins, descriptions, synonyms, and agent metadata before adding SQL snippets, example SQL, or text instructions. Use read-only `DESCRIBE TABLE EXTENDED <catalog.schema.metric_view> AS JSON` when benchmark evidence implicates a metric view definition and you need to inspect its YAML, measures, dimensions, joins, filters, or agent metadata.

This workflow may tune serialized-space metadata for existing metric views. If the root cause is an incorrect or missing Unity Catalog metric view definition, document it as an upstream semantic-layer issue in the fix plan; do not create, alter, export, or mutate metric views as part of this skill.

## Text Instruction Guardrails

`instructions.text_instructions` is the last resort for global behavior. Before editing it, decompose the proposed instruction into atomic rules and route each rule to the most structured config surface that can represent it.

Use `instructions.text_instructions` only for:

- global conventions that apply across the space, such as fiscal calendar, timezone, default rounding, or clarification behavior
- brief result-presentation conventions that are truly universal
- behavior that cannot be represented with metadata, join specs, SQL snippets, or example SQL

Do not put these in `instructions.text_instructions`:

- source-specific or column-specific metric definitions
- filters such as `status = 'Active'`, denominator/numerator rules, or categorical mappings
- join paths or grain-preservation rules
- benchmark-specific aliases or result-shape requirements
- top-N tie breakers, rolling-window implementations, or other multi-step SQL patterns
- long lists of business rules copied from failure analysis

Use this routing instead:

- table, metric view, or column meaning, synonyms, and ambiguity -> data-source/column metadata
- categorical value confusion -> `enable_format_assistance`, `enable_entity_matching`, or metadata
- standard joins -> `instructions.join_specs`
- reusable measures, filters, denominators, numerators, and business expressions -> `instructions.sql_snippets`
- complex query shape, rolling windows, top-N tie breakers, or multi-step grain handling -> representative `instructions.example_question_sqls`
- concise global conventions only -> `instructions.text_instructions`

Before saving a config that changes `instructions.text_instructions`, add a short justification to the fix plan explaining why each remaining text rule is global and why a structured config surface cannot encode it. If the text instruction grows into a paragraph of metric-specific rules, split it apart before updating the space.

When a text instruction is justified, format it as short Markdown sections in this order:

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

Keep each section user-eye friendly: use short bullets, avoid dense paragraphs, and omit metric-specific SQL logic that belongs in snippets, join specs, metadata, or examples. If a section has no true global guidance, write `- None.` rather than filling it with benchmark-specific content.

## Initial Benchmark Dataset Review

Before the first optimization pass, review benchmark quality and record findings in `fix_plan/genie_<version>_quality_improvement_plan.md`. Do this before interpreting baseline accuracy or proposing Genie config edits.

Minimum benchmark bar:

- Require at least 30 valid benchmark question/answer pairs. A pair is valid only when the question has exactly one SQL answer and there is no evidence that the answer SQL is invalid or errors during evaluation or read-only verification.
- If fewer than 30 valid Q/A pairs remain, pause config tuning. Document the count, invalid or missing-answer question IDs, and the benchmark expansion or correction needed.
- After documenting the gap, author enough benchmark Q/A additions or replacements to bring the reviewed valid set to at least 30. Use the available dataset, existing space config, and read-only Databricks SQL inspection to ground the questions and SQL.
- Put the benchmark additions or replacements into a dedicated benchmark bootstrap or repair config version under `genie_configs/`. Do not combine this with Genie tuning changes.
- Validate the benchmark config with `validate-config --previous-config <previous> --allow-benchmark-changes`, update the Genie space, run a full benchmark eval, and pull a versioned report before starting config tuning.

Review diversity and challenge:

- Cover multiple entities, metrics, dimensions, filters, joins, time windows, aggregation grains, ranking/window patterns, and business concepts that real users will ask about.
- Flag overly simple questions such as trivial counts, direct lookups, single-table summaries with no business logic, and repeated variants that only swap a date or category.
- Flag low diversity when questions cluster around the same table, metric, phrasing, join path, filter type, or SQL pattern.
- Prefer a benchmark mix that includes reusable business metrics, categorical value handling, multi-table joins, date range and rolling-window logic, conditional aggregation, ratios, top-N/ranking, and result-shape expectations.
- If the benchmark is too simple or not diverse, document weak coverage areas and specific missing categories. Add or replace benchmark Q/A pairs in a dedicated benchmark bootstrap or repair config version before proceeding to config tuning.

Benchmark Q/A additions or replacements should include:

- the benchmark question text
- the expected SQL answer
- the coverage category, such as join, time logic, metric, filter, ranking/windowing, or result shape
- the tables, metric views, and columns used
- validation notes showing the SQL was checked with read-only inspection when possible
- whether it is an addition or a replacement for an invalid, too-simple, or duplicate existing question

## Failure-To-Fix Guide

Use benchmark `assessment_reasons`, generated SQL, and expected SQL to choose the smallest useful intervention.

### Wrong Table, Metric View, Or Column

Symptoms:

- Genie selects a similarly named but incorrect table, metric view, or column.
- Generated SQL omits a required dimension or uses the wrong date/status/amount field.
- Assessment mentions missing or extra columns.

Fixes:

- Add or refine table, metric view, or column descriptions and synonyms.
- Hide irrelevant or confusing columns when possible.
- Add an example SQL query if the question pattern is complex.
- Document an upstream view or metric view opportunity if the base schema has too many overlapping concepts.

### Wrong Filter Value

Symptoms:

- Genie filters for a label that does not exist in the data.
- Genie confuses business terms with stored codes or categories.

Fixes:

- Enable `enable_format_assistance` for the relevant column.
- Enable `enable_entity_matching` for low/medium-cardinality string categorical columns.
- Add synonyms or a SQL filter snippet for common business terms.
- Refresh prompt matching values in the UI when values changed.

Good entity-matching candidates in this repo:

- `status`
- `region`
- `state`
- `channel`
- `category`
- `transaction_type`
- `merchant_category`
- `account_type`
- `relationship_tier`
- `product_category`
- `product_type`
- `reward_program`

Avoid entity matching for high-cardinality free-text or identifier columns unless users naturally filter by those exact values.

### Wrong Join

Symptoms:

- Genie joins through the wrong key.
- Genie misses a needed source.
- Generated SQL has duplicate rows from relationship cardinality mistakes.

Fixes:

- Add `instructions.join_specs` for standard relationships.
- Prefer Unity Catalog PK/FK constraints when available.
- Add example SQL for common multi-table patterns.
- If joins are consistently complex, document whether an upstream pre-joined view or metric view should be created, then keep this workflow to serialized-space edits.

For this banking space, likely standard joins include:

- `accounts.customer_id = customers.customer_id`
- `accounts.product_id = products.product_id`
- `transactions.account_id = accounts.account_id`
- `transactions.customer_id = customers.customer_id`
- `transactions.branch_id = branches.branch_id`
- `service_requests.customer_id = customers.customer_id`
- `service_requests.branch_id = branches.branch_id`
- `customers.primary_branch_id = branches.branch_id`

### Metric Or Business Logic Error

Symptoms:

- Genie calculates the wrong numerator/denominator.
- Genie uses count when expected SQL uses amount, balance, fee, rate, or ratio.
- Genie uses the wrong aggregation grain.

Fixes:

- For metric-view-backed spaces, first inspect available metric view measures, dimensions, filters, joins, descriptions, synonyms, and agent metadata.
- Use read-only `DESCRIBE TABLE EXTENDED <catalog.schema.metric_view> AS JSON` when benchmark evidence implicates a metric view definition.
- If the metric view definition is wrong or missing, document it as an upstream semantic-layer issue instead of tuning `serialized_space`.
- Add SQL snippets/expressions for reusable measures, filters, and dimensions.
- Add example SQL for multi-step logic, windows, ratios, percentiles, and conditional aggregation.
- For table-backed spaces, document an upstream view or metric view opportunity for highly reused metrics.
- Keep expression names and synonyms close to user phrasing.

Good SQL-expression candidates from the benchmark set:

- deposit volume
- net flow
- digital transaction share
- mobile transaction share
- complaint count and complaint rate
- fee revenue
- credit card penetration
- delinquency rate
- credit card utilization
- payment-to-purchase ratio

### Time Logic Error

Symptoms:

- Genie uses the wrong year, range boundary, month grain, or rolling window.
- Genie does not include prior periods needed for `LAG` or rolling averages.

Fixes:

- Add example SQL for the exact time-window pattern.
- Add SQL snippets for reusable date dimensions or filters.
- Add concise text instruction only if a global convention applies, for example fiscal year or timezone.

For benchmark questions, preserve exact phrases like `in 2024`, `in 2025`, `December 2023 through March 2024`, `previous month`, and `prior three months`.

### Result Shape Error

Symptoms:

- Assessment reasons include missing/extra columns.
- Generated SQL gives right values but wrong aliases or granularity.

Fixes:

- Add example SQL for that result shape.
- Add a short text instruction if naming/rounding conventions are global.
- Avoid overfitting to benchmark-only column aliases unless business users expect those names.

### Ignored Or Conflicting Instructions

Symptoms:

- Genie ignores a broad instruction.
- A new fix improves one question but regresses another.

Fixes:

- Remove vague or redundant text instructions.
- Replace text instructions with SQL snippets or examples.
- Keep examples diverse but not overlapping.
- Re-run benchmark evals after every candidate config change and compare GOOD/BAD/NEEDS_REVIEW counts plus per-question regressions.

## Best-Practice Rules

- Keep the space focused; remove or hide data that is not needed for the intended questions.
- Prefer well-described data sources and columns over long instructions.
- Prefer SQL snippets/expressions and example SQL over text instructions.
- Use text instructions only for global behavior, clarification behavior, or summary formatting.
- Avoid contradictory guidance between text instructions, examples, snippets, and benchmark SQL.
- Add example SQL for complex multi-step questions; add SQL snippets for reusable concepts.
- Use benchmarks as an evaluation loop: baseline, change one coherent set of context, update the space, rerun, compare.
- Treat `NEEDS_REVIEW` separately from `BAD`; inspect whether the issue is semantic mismatch, unsupported judging, or missing SQL-answer evidence.

## Analysis Workflow For Benchmark Reports

1. Open the versioned report, for example `results/v1_benchmark_report.json`.
2. Group failures by `assessment_reasons`.
3. Compare `genie_response[].response` SQL to `expected_response[].response` SQL.
4. When the failure cause depends on live schema, metric view definition, or data semantics, use the available Databricks SQL execution capability for read-only exploratory SQL such as bounded samples, cardinality checks, null-rate checks, distinct categorical values, join-grain checks, `DESCRIBE TABLE EXTENDED <catalog.schema.metric_view> AS JSON`, and `information_schema` lookups. In external coding agents, this is usually the DBSQL MCP; in Genie Code, use native DBSQL access.
5. Label each failure with one primary cause:
   - wrong table/metric view/column
   - wrong filter value
   - wrong join
   - metric/business logic error
   - time logic error
   - result shape error
   - execution/error issue
   - judge/manual-review issue
6. Propose the smallest serialized-space edit category for each cluster. For any proposed text instruction, first decompose it into atomic rules and route source, metric, filter, join, alias, ranking, and window logic to structured config surfaces.
7. Write the intended fixes in `fix_plan/genie_<version>_quality_improvement_plan.md` before editing the config.
8. Apply only the planned edits to a new versioned config, update the space, run a fresh eval, and compare against the prior report.
9. Append validation, deployment, eval run, measured accuracy, and regression notes to the same fix plan.

Do not blindly add every failed benchmark as example SQL. Use example SQL for representative complex patterns, and use SQL snippets or metadata when multiple failures share the same reusable concept.
