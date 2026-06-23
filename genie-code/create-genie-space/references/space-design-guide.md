# Genie Space Design Guide

Use this reference when creating or reviewing a Genie Space in Genie Code.

## Requirements And Discovery

Start from the user's actual intent:

- Capture purpose, audience, draft title, and 3-5 concrete business questions.
- Capture business terms, metric definitions, fiscal/calendar conventions, default filters, security caveats, and benchmark mode.
- Before choosing sources, sweep the available workspace context for business terms, filters, joins, and candidate sample questions: provided `@` assets, the current notebook or SQL editor tab, workspace search, and relevant dashboards, saved queries, notebooks, and files. Genie Code can reference `@` resources and search across these asset types, so use them as evidence instead of guessing definitions.
- If objects are not specified, search or browse with exact terms, synonyms, abbreviations, related entities, and common fact/dimension naming patterns.
- Recommend a focused source set, ideally 5 or fewer objects initially and never above the documented 30-table/view Space limit, and explain how each source maps to the business questions.
- When a focused design would need more than ~5 sources, approaches the 30-table/view limit, or depends on ambiguous multi-hop joins, prefer pre-joining or denormalizing upstream into a Metric View or curated view over attaching many raw tables; this is the primary strategy for both the table limit and accuracy. This skill does not create Metric Views, so hand off to the create-metric-view skill and document the semantic-model gap.

Before deeper profiling, check feasibility. Flag missing measures, dimensions, time fields, Metric View measures, or join paths. Let the user add sources, adjust questions, or proceed with explicit limitations.

Before proposing live creation or updates, confirm the Space uses Unity Catalog data, the editor has required Genie and data permissions, a pro or serverless SQL warehouse is available with `CAN USE`, and the draft stays within documented limits: 30 tables/views, 100 instructions, 200 knowledge store snippets, and 500 benchmark questions.

## Read-Only Discovery And Profiling

Use workspace metadata first, then run focused read-only SQL only when metadata is not enough. Prefer narrow previews, filters, samples, and `EXPLAIN`; use broad full-table scans only when necessary and approved. Use `references/data-profiling-and-readiness.md` for SQL templates covering structure, row counts or estimates, grain, freshness/date ranges, null/empty/constant columns, cardinality, casing, boolean-as-string values, join cardinality, Metric View `MEASURE()` behavior, PII/ETL/noisy fields, usage/lineage, and per-question readiness.

## Design Priorities

Prefer structured context over broad instructions:

1. Metric View semantic metadata when it already owns the business definition.
2. Focused data source selection.
3. Table, Metric View, and column descriptions.
4. Synonyms and display names for business terms.
5. Format assistance and entity matching for eligible categorical strings after prompt matching safety review.
6. Join specs for raw tables exposed together.
7. SQL snippets for reusable filters, expressions, and measures not already governed by Metric Views.
8. Example SQL for complex question patterns.
9. SQL functions for trusted registered logic.
10. Short text instructions only for global behavior that cannot be encoded structurally.

## Trusted Assets

Trusted assets are the surfaces that return verified answers: parameterized example SQL queries and registered Unity Catalog SQL functions. Use them for the questions that must be answered consistently:

- **Parameterized example SQL** uses `:param_name` parameters, each with a description, type hint, and real default. When a user's question matches the exact text of a parameterized example, Genie can answer deterministically from it instead of generating fresh SQL.
- **UC SQL functions** register reusable, governed logic so Genie calls verified SQL for that answer rather than re-deriving it.

Prefer trusted assets over plain example SQL or text instructions when a question is high-value, frequently asked, or must return an auditable answer. Trusted assets do not replace Metric View semantics: keep governed business definitions in the Metric View and use trusted assets for verified query shapes on top of them. Trusted assets and SQL functions count against the instruction budget, so add the ones that earn their place rather than registering everything.

## Text Instruction Last-Resort Rule

Do not use text instructions as the default place for guardrails, policies, metric logic, table-selection rules, join rules, filter rules, ranking/windowing rules, or long best-practice lists. If the proposed instruction names specific tables, Metric Views, columns, joins, filters, denominators, numerators, aliases, ranking logic, or window logic, first try to encode the rule in focused source selection, Metric View metadata, source/column descriptions, synonyms, prompt matching, format assistance, entity matching, join specs, SQL snippets, representative example SQL, SQL functions, or an upstream semantic model fix.

Use text instructions only for global behavior that cannot be encoded structurally, such as broad ambiguity handling, response-quality expectations, caveats, or user-facing summary constraints. Genie's response summary and narrative behavior are governed by text instructions rather than structured metadata, so when summary behavior must change, use a focused text instruction that states what to clarify, when, and the desired summary constraint. When proposing or editing text instructions, carry over the optimization-style justification requirement and adapt it for creation/refinement context:

```markdown
## Text Instruction Justification

- Exact instruction text:
- Why structured surfaces were insufficient:
- Intended global behavior:
- Possible overreach or regression risk:
- How the instruction will be reviewed or validated:
```

## Prompt Matching Safety

- Representative values for prompt matching are generated using the author's permissions and become part of the Space's shared context.
- Enable entity matching only for stable string columns users are likely to mention, such as state codes, product categories, statuses, or departments.
- Entity matching is capped: Databricks indexes entity-matching values for up to 120 columns per Space, up to 1,024 distinct values per column, with each value up to 127 characters (Tune Genie Space quality docs). Values beyond these limits are not indexed, so spend the budget on the highest-signal categorical columns rather than enabling everything.
- Disable or avoid format assistance and entity matching on sensitive fields, high-cardinality identifiers, free text, and any view that references row filters, column masks, or dynamic-view security logic unless the user explicitly confirms the values are safe to share with Space users.
- If prompt matching values might expose data outside the intended audience, do not enable them; hide the column or document the security caveat instead.

## Joins

- Declare each proposed join's relationship type (1:1, 1:M, or M:M) and direction, not just that a key matches. The relationship type drives fan-out and aggregation correctness, so it is design evidence, not a detail.
- Resolve duplicate-key and cardinality risk with the checks in `references/data-profiling-and-readiness.md` before proposing any M:M or unresolved-cardinality join, and document the relationship with its evidence (declared keys, naming, cardinality checks, query history, or user confirmation).

## Metric View Guidance

- Treat Metric Views as governed semantic sources.
- Do not attach underlying raw tables unless users also need raw-detail questions.
- Do not duplicate Metric View formulas in snippets or examples unless the example teaches a query shape.
- If the semantic model is wrong or missing a governed measure, dimension, join, or filter, document that as an upstream modeling issue instead of working around it with broad Genie instructions.
- Do not use `SELECT *` against Metric Views in examples or benchmarks.
- If a Metric View output must be combined with another source, wrap the Metric View query in a CTE before joining.

## Examples And Benchmarks

- Validate every example SQL, benchmark SQL, snippet, and join with read-only execution or `EXPLAIN` when possible.
- Use real profiled values for parameter defaults, benchmark literals, and sample question wording.
- Parameterized examples may use `:param_name`, but every parameter needs a description, type hint, and real default value.
- Benchmarks should be concrete and hardcoded, not parameterized.
- Avoid zero-row benchmark SQL unless the benchmark explicitly tests empty results.
- Keep sample questions user-facing, example SQL instructive, and benchmarks evaluative. Do not copy benchmark questions or benchmark answer SQL into examples.
- Provide 2-4 natural phrasings for each key question or intent across sample questions and benchmark coverage, so matching is robust to how users actually word requests.

## Readiness

Before proposing a live change, score each business question High/Medium/Low using the canonical rubric and the Context Evidence Gate in `references/data-profiling-and-readiness.md`.

## Static Health Checks

Check the draft for:

- A focused source set, ideally 5 or fewer at first.
- Required permissions, pro/serverless SQL warehouse availability, Unity Catalog data access, and documented limits are satisfied before live creation or update.
- Descriptions that state business purpose and grain. Inspect and correct AI-generated table and column descriptions before trusting them; do not pass inaccurate auto-generated comments into Space context.
- Hidden ingestion, audit, hash, raw JSON, embedding, and sensitive free-text fields.
- Prompt matching only on useful eligible categorical strings after checking shared-context exposure, row filters, column masks, and dynamic views.
- Joins supported by constraints, naming, cardinality/duplicate-key checks, query history, or user confirmation.
- No long rulebook-style text instructions.
- Text instructions only for global behavior that cannot be encoded structurally, with adapted justification when proposed or edited.
- Example SQL that teaches reusable patterns, not memorized test questions.
- Example SQL parameters with real defaults and descriptions.
- Benchmarks with ground truth appropriate to the intended execution mode: checked SQL for deterministic Chat-style questions, evaluation notes for Agent-style multi-step analysis, and both when a deterministic question also needs full-response judging. Cover sources, filters, measures, joins, time logic, answer shapes, evidence quality, and response synthesis as applicable.
