---
name: create-metric-view
description: "Create, draft, validate, or refine Databricks Unity Catalog Metric Views in Databricks Genie Code Agent mode. Use inside Databricks when users ask Genie Code to build governed business metrics, author Metric View YAML or SQL DDL, inspect tables, views, or existing Metric Views, model measures, fields, filters, joins, agent metadata, materialization candidates, validation queries, or prepare approved live CREATE or ALTER VIEW changes without source data mutation."
---

# Create Metric View For Genie Code

Create a governed Unity Catalog Metric View from Databricks-native context. Rely on Genie Code Agent mode to inspect workspace assets, Unity Catalog metadata, notebooks, SQL editor output, and approved query results. Treat the Metric View as a business semantic contract, not as a place to guess metrics.

## Hard Rules

- Use only bounded read-only SQL for discovery and validation unless the user explicitly approves the exact Metric View DDL to run: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema`. Prefer metadata, constraints, scoped predicates, samples, and approximate aggregates before broad scans.
- Never mutate source tables, source views, schemas, or source data. Do not run `DROP`, `TRUNCATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, table rewrites, grants, or source object changes.
- Do not run live `CREATE VIEW`, `CREATE OR REPLACE VIEW`, `ALTER VIEW`, materialization changes, ownership changes, or permission changes until the user approves the exact target object and generated DDL.
- Do not invent KPI formulas, denominators, scope filters, joins, grains, fiscal calendars, timezone handling, display formats, synonyms, or security semantics. Ask the user when workspace evidence is insufficient.
- Do not use feature-gated Metric View syntax unless the active Databricks Metric View environment supports it. If support cannot be confirmed, omit the gated feature and document it as an optional enhancement.
- Do not assert `rely.at_most_one_match: true` unless uniqueness is proven by constraints/profiling or explicitly confirmed by a data owner and the active environment supports the optimization. A wrong `rely` declaration can make measures incorrect.
- Do not use materialization by default. Recommend it only when query patterns, performance goals, workload evidence, and workspace capability justify precomputed aggregations.
- Do not use `SELECT *` against Metric Views. Explicitly list fields and wrap measures with `MEASURE()`.
- Prefer existing governed Metric View semantics over duplicating formulas in downstream Genie Space snippets, examples, or text instructions.

## Workflow

1. Gather expert inputs before modeling: purpose, audience, target object name, metric owner, expected consumers, 3-5 real business questions, KPI dictionary, grain, default filters, fiscal/calendar rules, timezone, security caveats, display formats, synonyms, and downstream Genie Space expectations.
2. Confirm the source set: use provided `@` assets or exact Unity Catalog identifiers when available; otherwise search workspace data using business terms, synonyms, abbreviations, and likely fact/dimension naming patterns.
3. Inspect metadata before samples. Read `references/metric-view-profiling-and-validation.md` and use bounded read-only SQL to identify source purpose, columns, comments, constraints, grain, row counts, freshness, candidate measures, categorical fields, filters, time fields, joins, and existing Metric View definitions.
4. Stop at a feasibility checkpoint. Map each requested KPI and question to available sources, fields, measures, filters, time logic, and joins. Score each item High/Medium/Low confidence and ask for missing expert definitions before drafting.
5. Read `references/metric-view-design-guide.md` before authoring YAML. Choose the simplest model that preserves business meaning:
   - source: one table-like object, existing Metric View, or SQL query when a bridge/prejoin is necessary
   - fields: business-friendly grouping and filtering attributes, including separate granular and truncated time fields
   - measures: atomic aggregate measures first, then composed measures using earlier measures or `MEASURE()` where supported
   - filters: model-level scope only when the scope is a governed business rule
   - joins: fact-to-dimension joins only with evidence; one-to-many only when a multi-grain model is intended and runtime/version support is available
   - agent metadata: display names, comments, synonyms, and formats only when grounded in business language
   - feature availability: use gated features only after compatibility is confirmed from the active Databricks environment, docs, or compiler feedback
   - materialization: only with workload justification and supported workspace capabilities
6. Draft `version: 1.1` YAML when agent metadata support is available; otherwise use the supported YAML shape and keep agent metadata recommendations in review notes. Present either YAML alone or approved SQL DDL such as `CREATE VIEW <target> WITH METRICS LANGUAGE YAML AS $$ ... $$`; use `ALTER VIEW <target> AS $$ ... $$` for an approved existing Metric View update and `CREATE OR REPLACE VIEW` only after explicit replacement approval.
7. Validate before proposing a live run:
   - review YAML/DDL syntax and required fields
   - run or prepare bounded `EXPLAIN` checks for generated Metric View queries
   - validate representative `MEASURE()` queries with explicit fields
   - compare output to known examples, source totals, or expert expectations
   - verify joins and `rely` declarations with constraints, profiling, or owner confirmation
8. Present the proposed Metric View for review. Apply DDL only after explicit approval from the user in Databricks.
9. Recommend downstream Genie Space changes only after the Metric View semantics are stable: attach the Metric View as a governed data source, avoid duplicate metric snippets, and document any remaining semantic gaps.

## Output

Provide:

- The target Metric View name and source objects.
- The expert inputs gathered and missing definitions.
- Per-KPI or per-question feasibility confidence with data gaps.
- Proposed YAML or SQL DDL.
- Join, `rely`, filter, materialization, agent metadata, feature availability, and version assumptions.
- Read-only validation performed, including representative `MEASURE()` queries.
- Any unresolved questions that block live creation or update.
- Downstream Genie Space recommendations.
