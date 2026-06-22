# Genie Config Review

Use this reference when diagnosis depends primarily on Genie Space configuration, especially when the user cannot run SQL, inspect Query History, or view full conversation details. This file is the **static checklist** — what to inspect, surface by surface. `failure-routing.md` owns the **decision logic** (symptom → failure class → smallest fix).

## No-Query Diagnosis Mode

- Continue diagnosis when bounded read-only SQL is unavailable; do not treat missing query access as a blocker.
- State which evidence was reviewed: Space config, generated SQL, final response, Monitor trends, comments, benchmarks, Query History, Unity Catalog metadata, or none.
- Confidence levels (canonical definitions; other files reference these):
  - `High`: config evidence directly explains the issue and no data validation is needed.
  - `Medium`: config evidence strongly suggests the issue but result-level validation, value profiling, cardinality checks, or Query History timing is missing.
  - `Low`: the likely fix depends on data values, row counts, join cardinality, freshness, permissions, or runtime behavior that cannot be inspected.
- Recommend the narrowest validation that would increase confidence, such as one `EXPLAIN`, one generated-SQL review, Query History timing, a Metric View definition review, or user confirmation of business intent.

## Data Sources And Metadata

Check whether the attached data sources are clear, focused, and non-overlapping:

- The source set maps to the Space purpose and common user questions; broad catch-all Spaces should be flagged.
- Raw tables are not exposed beside Metric Views for the same concepts unless raw-detail questions require both.
- Table, view, and Metric View descriptions explain purpose, grain, business boundaries, and when to use or avoid the source.
- Similar sources have differentiating descriptions, synonyms, or names so Genie can choose between them.
- Noisy ingestion, audit, hash, raw JSON, embedding, PII, sensitive free-text, or implementation columns are hidden or clearly de-emphasized.
- Column descriptions explain business meaning, units, grain, date role, valid values, null semantics, and important caveats when they influence user questions.
- Categorical fields that users mention have useful synonyms or prompt/entity matching only when values are safe to expose in shared Space context.
- Prompt/entity-matching safety (prohibition, not a confirmation gate): do **not** enable prompt or entity matching or format assistance on high-cardinality identifiers, sensitive values, masked columns, dynamic views, or views over row-filtered or masked tables. Entity-matching values become shared Space context, and Genie blocks matching on base tables with row filters or column masks; treat unsafe matching as disallowed.
- Out-of-space references: check whether instructions, metadata, examples, or generated SQL reference tables, views, or columns that are not attached to the Space. Genie can query beyond attached assets when prompted or when metadata points outside the Space; route conflicts to `Wrong Data Source Or Field` or `Config Conflict Or Redundancy`.

## Join Relationships

- Raw tables exposed together have explicit join specs with keys, grain, and cardinality notes.
- Join keys match column descriptions and avoid fan-out that silently changes grain.
- Recurring multi-table joins are candidates for an upstream view or Metric View rather than repeated ad hoc joins.
- Missing or ambiguous joins between co-exposed raw tables route to `Wrong Join`.

## Metric Views

- The Metric View has a clear name, description, display names, and synonyms so Genie selects it over raw tables.
- Measures use correct `MEASURE()` semantics; dimensions, time dimensions, and persistent filters match the business definitions and grain.
- Semi-additive, rolling, and windowed measures are defined in the Metric View rather than reconstructed in examples or expressions.
- Formula logic is not duplicated across the Metric View, SQL expressions, examples, and text instructions.
- A mismatch between a curated Metric View's semantics and user expectation routes to `Wrong Metric View Measure, Dimension, Scope, Or Grain`.

## General And Text Instructions

Treat general instructions as a last-resort global surface:

- Keep instructions short, global, and non-overlapping.
- Flag instructions that name specific tables, Metric Views, columns, joins, filters, denominators, numerators, aliases, date fields, ranking logic, or window logic.
- For source-specific rules, recommend moving the rule to source or column descriptions, Metric View metadata, prompt matching, join specs, SQL expressions, representative examples, SQL functions, or upstream semantic models.
- Do not encode benchmark answers, failing prompts, or one-off reviewer comments as global instructions.
- Check whether multiple instructions repeat, contradict, or create precedence ambiguity.
- Use text instructions for broad ambiguity handling, response-quality expectations, caveats, and user-facing summary constraints that cannot be encoded structurally.

## SQL Expressions / Knowledge-Store Snippets

Knowledge-store snippets include table descriptions, join relationships, and SQL expressions; SQL expressions themselves include measures, filters, and fields. Use the precise surface name when reporting findings.

- Each expression has a clear purpose, intended trigger, and reusable business meaning.
- Expressions do not duplicate a Metric View's measures, filters, dimensions, or formulas unless they intentionally teach a query shape.
- Similar expressions are not near-duplicates with different names, literals, date boundaries, or aggregation grain.
- Expressions do not conflict with source descriptions, Metric View definitions, examples, joins, or general instructions.
- Reusable filters, fiscal periods, ranking logic, date windows, and grain-preserving aggregations are expressed once in the most specific useful surface.
- Expressions avoid stale table names, columns, aliases, literals, deprecated categories, or hardcoded dates unless the business rule requires them.
- Complex recurring logic that is hard to teach safely should be routed to a trusted SQL function, upstream view, or Metric View recommendation.

## SQL Query Examples

Review query examples as teaching artifacts, not benchmark memorization:

- Examples demonstrate representative reusable patterns, such as grain handling, joins, windows, ranking, fiscal periods, or multi-step analysis.
- **Canonical rule (referenced by other files):** examples must not copy benchmark questions, benchmark answer SQL, evaluation-note wording, failing prompts, or reviewer-provided final answers. Representative examples teach reusable patterns; they do not memorize benchmarks or failing questions.
- Examples are not redundant variants that only swap dates, categories, regions, or other literals.
- Examples do not conflict with expressions, Metric View formulas, joins, source metadata, or text instructions.
- Parameterized examples include meaningful parameter names, type hints or descriptions, and realistic defaults.
- Examples are not overly long for simple patterns and do not teach verbose SQL where a concise curated source, expression, or Metric View would be better.
- Examples project only useful columns and avoid `SELECT *`, especially for wide sources or Metric Views.

## Trusted Assets And SQL Functions

- Trusted assets (certified SQL functions or queries) encapsulate complex recurring logic that is unsafe to teach via examples.
- Each trusted asset has a clear purpose and does not duplicate a Metric View measure or an existing expression.
- Excessive trusted assets or SQL functions in context add generation latency; flag overload and route to `Generation Latency Or Context Overload`.

## Common Questions

- Sample/common questions are representative of real usage and are not benchmark leakage.
- They do not over-weight a single source or trivial lookup.
- They align with attached sources and do not imply out-of-space tables.

## Benchmarks

This section is the static inventory check; benchmark routing and repair guidance live in `failure-routing.md`.

- Benchmark inventory size is practical for iteration (Databricks supports up to 500 questions); flag sets that are too small, too narrow, too easy, too redundant, or too large.
- Deterministic Chat benchmarks have checked SQL answers; Agent-style benchmarks have evaluation notes.
- Healthy 2–4 phrasing variants of the same question are expected and should not be pruned as duplicates; prune only redundant literal/date/category swaps.
- Coverage maps to real user patterns and feedback clusters; missing coverage of common patterns is a gap.

## Permissions, Governance, And Data Visibility

- Space ACLs and per-user `SELECT` privileges can make the same question return different or empty answers by user.
- Row filters, column masks, and dynamic views restrict visible rows/columns and can look like wrong-data or wrong-filter failures.
- Empty responses, per-user discrepancies, or "no data" answers should prompt a governance check before classifying as wrong source/filter; route to `Permission, Governance, Or Data Visibility Limitation`.

## Latency Context Pressure

- Static signals that inflate generation latency: high data-source count, raw/Metric View overlap for the same concepts, noisy visible columns, long source-specific text instructions, redundant or oversized example SQL, broad prompt/entity matching, excessive trusted assets or SQL functions, and long generated SQL or text responses.
- These are detection signals only; routing and fixes live in `failure-routing.md` → `Generation Latency Or Context Overload`.

## Static Conflict Patterns

Flag these as high-risk config findings:

- A text instruction says to use one source while source descriptions or examples point elsewhere.
- An expression implements a metric differently from a Metric View or column description.
- Multiple expressions define the same business filter with different literals or date boundaries.
- Example SQL joins raw tables at a different grain than the join spec or source descriptions imply.
- A column description says a field is deprecated, but examples or expressions still use it.
- Prompt matching is enabled for values that the source description says should not be exposed or used.
- Benchmarks or feedback describe business terms that are absent from metadata, expressions, examples, or instructions.

## Reporting Static Findings

For each static finding, report:

- Surface: data source, column, Metric View, join spec, prompt matching, SQL expression / knowledge-store snippet, example SQL, trusted asset, common question, text instruction, benchmark, permission / governance, or feedback-derived gap.
- Issue: missing, unclear, conflicting, redundant, too broad, stale, unsafe, or wrong surface.
- Impact: likely wrong source, wrong field, wrong filter, wrong join, wrong metric, slow generation, weak Agent report, governance/visibility limit, or validation gap.
- Recommended smallest fix: move, merge, clarify, hide, split, prune, or validate.
- Validation needed: none, user confirmation, generated-SQL check, bounded SQL, Query History timing, benchmark repair, or handoff to `optimize-genie-space`.
