---
name: create-genie-space
description: "Create a brand-new Databricks Genie Space from Unity Catalog tables, views, and Metric Views in Databricks Genie Code Agent mode. Use when users point at data sources and ask Genie Code to bootstrap or draft a focused initial Space: gathering workspace context, choosing sources, and designing structured context, examples, sample questions, and benchmarks without mutating source data. For tuning an existing Space use optimize-genie-space; for read-only diagnosis use diagnose-genie-space."
---

# Create Genie Space For Genie Code

Create a focused Genie Space using Databricks-native context. Rely on Genie Code Agent mode to inspect Unity Catalog metadata, open workspace assets, run approved notebook or SQL editor steps, and read returned output.

## Hard Rules

- Use only bounded read-only SQL to inspect data: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema`. Prefer metadata, narrow previews, partition/date filters, and sampled profiling; use broad full-table scans only when needed and approved.
- Never mutate Unity Catalog objects or data. Do not run `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, or equivalent mutation.
- Do not create or alter Metric Views as part of this skill. Use existing Metric Views as Genie data sources and document any upstream semantic model gaps.
- Do not create or update a live Genie Space unless the user explicitly asks and approves the proposed changes in Databricks.
- Do not invent business definitions, joins, fiscal calendars, default filters, or metric formulas. Ask the user when workspace evidence is insufficient.
- Do not add benchmark SQL unless it has been checked with read-only execution or `EXPLAIN`.
- Do not add Agent-style benchmark evaluation notes unless the expected response criteria are grounded in user intent, workspace evidence, or validated business definitions.
- Do not rate a business question High confidence or propose a live Space until each included source clears the context evidence gate: Unity Catalog metadata and `DESCRIBE`, a row count or estimate, a freshness signal, a narrow sample preview of question-relevant columns, and key/join evidence for every proposed relationship. Record any check you cannot complete as an explicit confidence reduction, not a silent omission. See `references/data-profiling-and-readiness.md`.
- When a focused design would need more than ~5 sources, approaches the 30 table/view limit, or depends on ambiguous multi-hop joins, prefer pre-joining or denormalizing upstream (a Metric View or curated view) over attaching many raw tables. This skill does not create Metric Views; hand off to the `create-metric-view` skill and document the gap.
- Before proposing a live Space change, confirm required Genie permissions, a pro or serverless SQL warehouse, Unity Catalog data access, and documented Space limits.

## Workflow

1. Gather requirements: target audience, Space purpose, draft title, 3-5 real business questions, known terminology, KPI definitions, fiscal/calendar conventions, default filters, security caveats, and intended benchmark execution target when benchmarks are requested.
2. Sweep workspace context, then discover data. Before recommending sources, mine the available Databricks context for business terms, filters, joins, and candidate sample questions: provided `@` assets, the current notebook or SQL editor tab, workspace search, and relevant dashboards, saved queries, notebooks, and files. Use exact Unity Catalog identifiers when given; otherwise search/browse using requirement terms, synonyms, abbreviations, and likely fact/dimension naming patterns. Recommend a focused source set and explain how each source maps to the business questions. See the discovery guidance in `references/space-design-guide.md`.
3. Check feasibility before deep inspection. Compare selected tables/views/Metric Views to the business questions and flag missing measures, time columns, dimensions, or join paths. Proceed only when the user accepts the source set, adds data, or adjusts the questions.
4. Inspect and profile in phases. Read Unity Catalog metadata first, then use bounded SQL and `references/data-profiling-and-readiness.md` to identify source purpose, row counts or estimates, grain, freshness, comments, columns, data types, null/empty/constant columns, categorical values, measures, sensitive/noisy fields, declared keys and likely relationships, and usage/lineage signals. Capture the per-source evidence required by the context evidence gate (see Hard Rules) and record any check you cannot complete as a confidence reduction.
5. For Metric Views, inspect governed measures, dimensions, filters, joins, time dimensions, and metadata before adding extra Genie context, and prefer governed semantics over duplicated SQL logic. See the Metric View guidance in `references/space-design-guide.md`.
6. Assess readiness for each business question using the canonical High/Medium/Low rubric in `references/data-profiling-and-readiness.md`. Mark unsupported questions and upstream semantic model gaps explicitly.
7. Design the Genie Space surfaces in priority order, preferring structured context over text instructions and following the full ranking, trusted-assets guidance, prompt-matching safety, and join-cardinality rules in `references/space-design-guide.md`. Cover focused data sources, descriptions and synonyms, hidden noisy fields, prompt matching, joins, snippets and example SQL, trusted assets (parameterized examples and SQL functions) for verified answers, text instructions only as a last resort, and sample questions and benchmarks that match realistic workflows and the intended execution mode.
8. Review the draft against `references/space-design-guide.md`, including platform limits, prerequisites, prompt matching safety, and join cardinality, before proposing live changes.
9. Present the proposed Space configuration in the Databricks-native editor or chat output for user review. Apply only after the user approves.
10. Frame the result as iteration 1: start with the focused source set, benchmark early against the real business questions, and plan to monitor usage and user feedback to iterate. For tuning an existing Space, hand off to `optimize-genie-space`; for read-only diagnosis of a struggling Space, handoff to `diagnose-genie-space`.

## Output

Provide:

- The Genie Space title or draft title.
- The data sources included and why each belongs.
- Per-question readiness confidence and data gaps.
- Important metadata, prompt matching, join, snippet, example, sample question, and benchmark choices.
- Benchmark execution target and field strategy when benchmarks are included.
- Platform limit and prerequisite checks before any live creation or update.
- Any assumptions or user confirmations needed before live creation or update.
- The read-only validation performed and any limitations.
- Next steps: a benchmark-early plan and handoff to `optimize-genie-space` (tuning) or `diagnose-genie-space` (diagnosis) for ongoing iteration.
