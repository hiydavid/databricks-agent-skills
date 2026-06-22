# Tuning Levers

Choose the smallest structured configuration change that fixes a clustered failure. Pairs with `failure-triage.md` (finding the cluster), `benchmark-eval.md` (re-measuring), and `persistence.md` (recording the edit).

## Genie configuration surfaces

Databricks frames a Genie Space's semantic configuration as a **knowledge store**. Edits made here are scoped to the Space and do **not** change Unity Catalog metadata. The surfaces this skill uses, with their documented names:

| Skill lever | Documented surface | Notes |
|---|---|---|
| Source / table / column descriptions | Metadata customization (space-scoped descriptions) | Genie also uses Unity Catalog table/column descriptions; space-level descriptions add or override for the Space only. |
| Synonyms | Prompt matching → synonyms | Business terms that map user language to columns/values. |
| Entity matching | Prompt matching → entity matching | Curated value lists for columns users reference by name; documented limit of up to 120 columns. |
| Format assistance | Prompt matching → format assistance | Representative values so Genie recognizes data types and formats. |
| Join relationships | Join relationships | Define table relationships and relationship type (many-to-one, one-to-many, one-to-one). |
| SQL expressions | SQL expressions | Reusable business logic (measures/filters) Genie can compose. |
| Example SQL queries | Example SQL queries (Instructions) | Prompt→SQL examples Genie matches and learns patterns from. Parameterized example queries used as verified answers — together with SQL functions — are the "trusted assets". |
| SQL functions | Trusted assets → SQL functions | Verified parameterized SQL functions used as trusted answers. |
| Text instructions | Text instructions | Global natural-language guidance; last resort. |

Documented capacity limits worth respecting: up to **100 instructions** (example SQL queries + SQL functions + text instructions), up to **200 knowledge-store snippets** (table descriptions, join relationships, and SQL expressions), and entity matching for up to **120 columns**.

There is **no standalone "output format" control**: answer-formatting rules are written into text instructions (with format assistance helping value/type recognition).

**Metric Views.** You can influence how a Metric View is used from within the Space (space-scoped descriptions, synonyms, prompt matching, joins, SQL expressions, and instructions — none of which change Unity Catalog metadata). The Metric View's own definition — fields, measures, source, filter — and its display names, comments, synonyms, formats, and agent metadata live in the metric view YAML and must be changed **upstream** (Catalog Explorer, SQL `ALTER VIEW`, or the YAML definition). When a failure traces to the Metric View definition itself, recommend an upstream change rather than trying to patch it in the Space.

## Core Principle

Translate failed benchmark evidence into structured Genie context. Prefer this order:

1. Focused source scope.
2. Source, Metric View, and column descriptions.
3. Prompt matching for categorical values (synonyms, entity matching, format assistance).
4. Join relationships for raw-table joins.
5. SQL expressions for reusable business logic.
6. Example SQL queries (and SQL functions) for complex, reusable patterns.
7. Short global text instructions.

Benchmarks evaluate quality. They do not teach Genie by themselves. Do not copy benchmark questions, answer SQL, or evaluation-note wording into descriptions, synonyms, SQL expressions, example SQL queries, or text instructions.

## Failure-to-Lever Routing

| Failure pattern | Evidence to inspect | Preferred repair lever | Avoid |
|---|---|---|---|
| Wrong table/source selected | Generated SQL uses the wrong configured table or Metric View | Improve source descriptions, source names/synonyms, and differentiating metadata | Broad text instruction saying "use table X" for one benchmark |
| Wrong column selected | Correct source, wrong field | Column description, synonyms/business aliases, hide or de-emphasize confusing columns if supported | Example SQL query unless the pattern is complex |
| Wrong Metric View measure | Wrong measure selected or measure intent misunderstood | Space-exposed Metric View display names/descriptions when editable, or document an upstream semantic model gap | Duplicating governed measure logic in text instructions |
| Wrong metric formula outside Metric View | Wrong numerator, denominator, or aggregation | SQL expression for reusable measure logic; example SQL query for complex formula | Global text instruction with metric math |
| Wrong filter value | SQL uses wrong categorical literal or status mapping | Column description with value semantics, entity matching, format assistance, reusable filter expression | Copying benchmark answer filter into an example SQL query |
| Missing business filter | Expected SQL has a reusable business filter missing in generated SQL | Reusable filter SQL expression or concise source/column metadata explaining default business scope | Long instruction list of every filter |
| Wrong join path | SQL omits or misuses a join | Join relationship after validating keys and grain | Join relationship based only on column-name similarity |
| Wrong join relationship/grain | Duplicated rows, wrong counts, many-to-many issue | Join relationship with relationship/grain guidance; example SQL query for grain-preserving pattern | Blind aggregation workaround |
| Wrong date field | Uses `created_at` instead of `closed_at`, `effective_date`, etc. | Column descriptions for date roles; SQL expression for common time filter | Text instruction listing many date rules |
| Wrong time window | Wrong interval, boundary, fiscal period, or relative date logic | SQL expression for reusable window; example SQL query for complex period logic | One-off benchmark-specific example |
| Wrong aggregation grain | Counts rows instead of entities, averages at wrong level, misses distinct | SQL expression for reusable grain logic; example SQL query for representative complex query | Source description only |
| Ranking/top-N/window failure | Missing window function, wrong tie-breaker, wrong order | Example SQL query; reusable SQL expression if the expression repeats | Many examples pasted into a global instruction |
| Correct SQL, bad answer prose | SQL/results acceptable but final explanation weak | Short response-quality text instruction | Changing SQL surfaces |
| Weak Agent research plan | Agent response starts from a vague or narrow plan and misses obvious comparison axes | Source descriptions, Metric View descriptions, and example SQL queries that show useful analytic dimensions | Long text instruction that scripts every benchmark |
| Incomplete Agent evidence | Final report makes claims without enough supporting query results, citations, tables, or charts | Clarify source/metric semantics; add example SQL queries only for reusable investigative patterns | Adding a single SQL answer for a multi-step analysis question |
| Unsupported Agent synthesis | Report overstates causality, misses caveats, or ignores data limitations | Short global response-quality instruction when the behavior is truly global | Encoding one benchmark's final prose as an instruction |
| Unclear Agent benchmark rubric | LLM judge lacks enough criteria to assess the report | Benchmark repair: add or refine evaluation note | Genie config tuning |
| Syntax failure | Generated SQL invalid | Inspect exact syntax issue; repair SQL expressions/example queries only if the pattern repeats | Treating syntax failure as business logic failure |
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
6. Are repeated joins failing because join relationships are missing or unclear?
7. Are repeated metrics, filters, or time windows better expressed as SQL expressions?
8. Is an example SQL query needed for complex grain, ranking, window, or period logic?
9. Do Agent-mode failures show missing investigation dimensions, weak evidence collection, unsupported synthesis, or missing caveats?
10. Is a text instruction being used as a dumping ground for logic that belongs in metadata, SQL expressions, example queries, or joins?
11. Is the Space backed by Metric Views, and should the repair target Metric View metadata rather than raw table logic?
12. Are there too many data sources in one Space, causing routing confusion?

## Text Instruction Last-Resort Rule

Do not use text instructions as the default repair. If the proposed instruction names specific tables, Metric Views, columns, joins, filters, denominators, numerators, aliases, ranking logic, or window logic, first try to encode the rule in source/column metadata, entity matching, format assistance, join relationships, SQL expressions, or example SQL queries.

Use text instructions only for global behavior that cannot be encoded structurally. Each text instruction edit must include:

```markdown
## Text Instruction Justification

- Exact instruction text:
- Why structured surfaces were insufficient:
- Which failures this targets:
- Which regressions this could cause:
- How the candidate eval will validate it:
```
