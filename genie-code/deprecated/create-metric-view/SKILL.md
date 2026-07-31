---
name: create-metric-view
description: "Create, draft, validate, or refine a Databricks Unity Catalog Metric View in Genie Code Agent mode. Use when users ask Genie Code to build a governed business-metrics semantic layer — authoring Metric View YAML or CREATE/ALTER VIEW DDL from inspected Unity Catalog sources, with read-only discovery and human approval before any live change. Builds the Metric View itself; to assemble or tune the consuming Genie Space, use Genie Code's native Genie Space skills."
---

# Create Metric View For Genie Code

Create a governed Unity Catalog Metric View from Databricks-native context. Rely on Genie Code Agent mode to inspect workspace assets, Unity Catalog metadata, notebooks, SQL editor output, and approved query results before drafting. Treat the Metric View as a business semantic contract that downstream Genie Spaces and AI/BI Dashboards consume, not as a place to guess metrics.

## Hard Rules

- Use only bounded read-only SQL for discovery and validation unless the user explicitly approves the exact Metric View DDL to run: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema`. Bounding controls (metadata first, scoped predicates, samples, approximate aggregates before broad scans) are in `references/metric-view-profiling-and-validation.md`.
- Never mutate source tables, source views, schemas, or source data. Do not run `DROP`, `TRUNCATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, table rewrites, grants, or source object changes.
- Do not run live `CREATE VIEW`, `CREATE OR REPLACE VIEW`, `ALTER VIEW`, materialization changes, ownership changes, or permission changes until the user approves the exact target object and generated DDL.
- Do not invent KPI formulas, denominators, scope filters, joins, grains, fiscal calendars, timezone handling, display formats, synonyms, or security semantics. Ask the user when workspace evidence is insufficient.
- Other authoring constraints — feature gating, `rely` proof, materialization default-off, explicit fields with `MEASURE()` (never `SELECT *`), and preferring existing governed Metric View semantics over duplicated formulas — are defined in `references/metric-view-design-guide.md`.

## Workflow

1. Sweep workspace context first; do not open by interrogating the user. Mine the Databricks context Genie Code can already read — provided `@` assets, the current notebook or SQL editor tab, workspace search, and relevant dashboards, saved queries, notebooks, and files — for existing KPI definitions, formulas, filters, grains, and business language. Use what you find as evidence instead of guessing.
2. Confirm the business contract per `references/metric-view-design-guide.md` (Design Intake): purpose, audience, owner, target name, consumers, 3-5 real business questions, KPI dictionary, grain, default filters, fiscal/calendar/timezone rules, security caveats, display formats, synonyms, and downstream expectations. Fill gaps from the sweep first; ask the user only for what the workspace cannot supply. Harvest real intent from existing or downstream Genie Spaces (sample/common questions, instructions, synonyms) and discover security caveats from column tags and governance signals where accessible.
3. Confirm the source set: use provided `@` assets or exact Unity Catalog identifiers when available; otherwise search workspace data using business terms, synonyms, and likely fact/dimension naming patterns. Stop when a candidate source's metadata matches the requested grain and KPI inputs; if none matches, report "no candidate source found" and ask the user for an explicit `@` asset or Unity Catalog identifier.
4. Discover existing Metric Views before authoring. Search the target catalog/schema for Metric Views and introspect candidates (see `references/metric-view-profiling-and-validation.md`, `DESCRIBE TABLE EXTENDED ... AS JSON`). Decide create-new vs. extend an existing governed Metric View; never reimplement formulas a governed Metric View already owns.
5. Inspect metadata before samples per `references/metric-view-profiling-and-validation.md` (Phased Inspection); prefer metadata, constraints, and comments over scans.
6. Stop at a feasibility checkpoint per `references/metric-view-design-guide.md` (Feasibility Check): map each KPI and question to sources, fields, measures, filters, time logic, and joins; classify each High/Medium/Low using the rubric there; ask for missing expert definitions before drafting.
7. Author the model per `references/metric-view-design-guide.md` — work top-down (source, fields, measures, filters, joins, agent metadata, materialization), choosing the simplest model that preserves business meaning.
8. Draft `version: 1.1` YAML when agent-metadata support is confirmed per `references/metric-view-design-guide.md` (Feature Availability); otherwise use the supported baseline YAML shape and keep agent-metadata recommendations in review notes. Use the DDL shapes in `references/metric-view-profiling-and-validation.md` (Draft DDL Shapes).
9. Validate before proposing a live run per `references/metric-view-profiling-and-validation.md` (validation templates and Validation Summary) and the Review Checklist in `references/metric-view-design-guide.md`.
10. Present the proposed Metric View for review. Apply DDL only after explicit approval from the user in Databricks, and only with the privileges listed in `references/metric-view-design-guide.md` (Privilege And Ownership).
11. Recommend downstream consumption only after the Metric View is approved and live (step 10), so its semantics will not change under consumers: attach it as a governed data source to Genie Spaces (via Genie Code's native Genie Space skills) and AI/BI Dashboards. Both should consume the governed measures and dimensions rather than reimplementing formulas; document any remaining semantic gaps.

## Output

Provide:

- The target Metric View name and source objects, and whether you are creating new or extending an existing Metric View.
- The workspace context swept and the expert inputs gathered, plus any missing definitions.
- Per-KPI or per-question feasibility confidence with data gaps.
- Proposed YAML or SQL DDL.
- Join, `rely`, filter, materialization, agent metadata, feature availability, and version assumptions.
- Privilege and ownership prerequisites for the target catalog/schema.
- Read-only validation performed, including representative `MEASURE()` queries.
- Any unresolved questions that block live creation or update.
- Downstream Genie Space and AI/BI Dashboard recommendations.
