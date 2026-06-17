# Genie Config Review

Use this reference when diagnosis depends primarily on Genie Space configuration, especially when the user cannot run SQL, inspect Query History, or view full conversation details.

## No-Query Diagnosis Mode

- Continue diagnosis when bounded read-only SQL is unavailable; do not treat missing query access as a blocker.
- State which evidence was reviewed: Space config, generated SQL, final response, Monitor trends, comments, benchmarks, Query History, Unity Catalog metadata, or none.
- Use `High` confidence only when config evidence directly explains the issue and no data validation is needed.
- Use `Medium` confidence when config evidence strongly suggests the issue but result-level validation, value profiling, cardinality checks, or Query History timing is missing.
- Use `Low` confidence when the likely fix depends on data values, row counts, join cardinality, freshness, permissions, or runtime behavior that cannot be inspected.
- Recommend the narrowest validation that would increase confidence, such as one `EXPLAIN`, one generated-SQL review, Query History timing, a Metric View definition review, or user confirmation of business intent.

## Data Sources And Metadata

Check whether the attached data sources are clear, focused, and non-overlapping:

- The source set maps to the Space purpose and common user questions; broad catch-all Spaces should be flagged.
- Raw tables are not exposed beside Metric Views for the same governed concepts unless raw-detail questions require both.
- Table, view, and Metric View descriptions explain purpose, grain, business boundaries, and when to use or avoid the source.
- Similar sources have differentiating descriptions, synonyms, or names so Genie can choose between them.
- Noisy ingestion, audit, hash, raw JSON, embedding, PII, sensitive free-text, or implementation columns are hidden or clearly de-emphasized.
- Column descriptions explain business meaning, units, grain, date role, valid values, null semantics, and important caveats when they influence user questions.
- Categorical fields that users mention have useful synonyms or prompt/entity matching only when values are safe to expose in shared Space context.
- Prompt matching is not broad, redundant, or enabled on high-cardinality identifiers, sensitive values, masked columns, dynamic views, or row-filtered views without explicit safety confirmation.

## General And Text Instructions

Treat general instructions as a last-resort global surface:

- Keep instructions short, global, and non-overlapping.
- Flag instructions that name specific tables, Metric Views, columns, joins, filters, denominators, numerators, aliases, date fields, ranking logic, or window logic.
- For source-specific rules, recommend moving the rule to source or column descriptions, Metric View metadata, prompt matching, join specs, SQL snippets, representative examples, SQL functions, or upstream semantic models.
- Do not encode benchmark answers, failing prompts, or one-off reviewer comments as global instructions.
- Check whether multiple instructions repeat, contradict, or create precedence ambiguity.
- Use text instructions for broad ambiguity handling, response-quality expectations, caveats, and user-facing summary constraints that cannot be encoded structurally.

## SQL Snippets And Expressions

Review snippets and expressions for reusable, coherent business logic:

- Each snippet has a clear purpose, intended trigger, and reusable business meaning.
- Snippets do not duplicate governed Metric View measures, filters, dimensions, or formulas unless they intentionally teach a query shape.
- Similar snippets are not near-duplicates with different names, literals, date boundaries, or aggregation grain.
- Snippets do not conflict with source descriptions, Metric View definitions, examples, joins, or general instructions.
- Reusable filters, fiscal periods, ranking logic, date windows, and grain-preserving aggregations are expressed once in the most specific useful surface.
- Expressions avoid stale table names, columns, aliases, literals, deprecated categories, or hardcoded dates unless the business rule requires them.
- Complex recurring SQL logic that is hard to teach safely should be routed to a trusted SQL function, upstream view, or Metric View recommendation.

## SQL Query Examples

Review query examples as teaching artifacts, not benchmark memorization:

- Examples demonstrate representative reusable patterns, such as grain handling, joins, windows, ranking, fiscal periods, or multi-step analysis.
- Examples do not copy benchmark questions, benchmark answer SQL, evaluation-note wording, failing prompts, or reviewer-provided final answers.
- Examples are not redundant variants that only swap dates, categories, regions, or other literals.
- Examples do not conflict with snippets, Metric View formulas, joins, source metadata, or text instructions.
- Parameterized examples include meaningful parameter names, type hints or descriptions, and realistic defaults.
- Examples are not overly long for simple patterns and do not teach verbose SQL where a concise governed source, snippet, or Metric View would be better.
- Examples project only useful columns and avoid `SELECT *`, especially for wide sources or Metric Views.

## Static Conflict Patterns

Flag these as high-risk config findings:

- A text instruction says to use one source while source descriptions or examples point elsewhere.
- A snippet implements a metric differently from a Metric View or column description.
- Multiple snippets define the same business filter with different literals or date boundaries.
- Example SQL joins raw tables at a different grain than the join spec or source descriptions imply.
- A column description says a field is deprecated, but examples or snippets still use it.
- Prompt matching is enabled for values that the source description says should not be exposed or used.
- Benchmarks or feedback describe business terms that are absent from metadata, snippets, examples, or instructions.

## Reporting Static Findings

For each static finding, report:

- Surface: data source, column, Metric View, prompt matching, join spec, SQL snippet/expression, example SQL, text instruction, benchmark, or feedback-derived gap.
- Issue: missing, unclear, conflicting, redundant, too broad, stale, unsafe, or wrong surface.
- Impact: likely wrong source, wrong field, wrong filter, wrong join, wrong metric, slow generation, weak Agent report, or validation gap.
- Recommended smallest fix: move, merge, clarify, hide, split, prune, or validate.
- Validation needed: none, user confirmation, generated-SQL check, bounded SQL, Query History timing, benchmark repair, or handoff to `optimize-genie-space`.
