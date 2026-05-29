---
name: create-genie-space
description: "Create a Databricks Genie Space serialized_space JSON from Unity Catalog datasets. Use when users ask to build, bootstrap, author, or generate a new Genie Space config for catalog/schema data objects including tables, views, and Metric Views; validate selected data objects with read-only Databricks SQL or DBSQL MCP, inspect schemas and data shape, choose appropriate Genie configuration surfaces, and produce JSON/API payloads that follow Databricks Genie best practices. This skill may create config files but must not mutate source tables, views, Metric Views, schemas, or data."
---

# Create Genie Space

Create a new Databricks Genie Space configuration from selected Unity Catalog data objects: tables, views, Metric Views, or a combination of these. The default output is a decoded `serialized_space` JSON file that can be validated locally and then wrapped in a Databricks create-space API request.

## Hard Rules

- Use only read-only Databricks SQL for dataset inspection: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema` queries.
- Never run DDL, DML, `CREATE`, `ALTER`, `DROP`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, or table/schema/data mutation.
- Do not create or alter Metric Views as part of this skill. Add existing Metric Views to `data_sources.metric_views`.
- Use the DBSQL MCP when available in external coding agents; in Databricks Genie Code or notebooks, use native DBSQL/notebook SQL.
- Do not create a live Genie Space through the API unless the user explicitly asks for live creation and provides the required workspace details.
- Do not include unvalidated benchmark SQL in the JSON. If SQL cannot be validated with read-only execution or `EXPLAIN`, put benchmark candidates in notes instead of `benchmarks.questions`.
- Do not invent uncertain business definitions, joins, fiscal calendars, default filters, or metric formulas. Ask the user when the data does not prove them.

## Workflow

1. **Gather requirements.** Capture the space purpose, audience, title or draft title, and 3-5 real business questions users want Genie to answer. Capture known business terms, KPI definitions, fiscal/calendar rules, default filters, row-level/security caveats, and sensitive columns.
2. **Discover or confirm data.** If the user knows the catalog, schema, tables/views, or Metric Views, confirm those exact objects. Otherwise, search or browse Unity Catalog using terms from the requirements, synonyms, abbreviations, and likely fact/dimension naming patterns. Recommend a focused source set and explain how each source maps to the business questions.
3. **Check feasibility.** Before deep profiling, compare the selected data objects to the business questions. Identify obvious gaps such as missing measures, time columns, dimensions, or join paths. Ask the user to proceed, add data, or adjust questions when the selected objects cannot support the goal.
4. **Load references.** Read `references/creation-workflow.md` and `references/data-profiling-and-readiness.md` before authoring JSON. If any selected object is a Metric View, read `references/metric-views.md`. Read `references/best-practices-checklist.md` while reviewing quality. Read `references/space-schema.md` when field shape or validation rules matter.
5. **Inspect and profile in phases.** Use read-only DBSQL to confirm each object exists, inspect metadata, then profile data quality, representative values, grain, freshness, joins, and usage/lineage signals. For Metric Views, inspect the definition/metadata and validate representative queries with explicit dimensions and `MEASURE()` calls. Keep samples bounded and avoid dumping sensitive values.
6. **Assess readiness.** For each business question, state High/Medium/Low confidence based on semantic coverage, data quality/freshness, modelability/join evidence, and GenAI context readiness. Resolve low-confidence gaps before proceeding or mark the JSON as a draft with explicit limitations.
7. **Design and review the space.** Build a version 2 `serialized_space` object with focused `data_sources.tables` and/or `data_sources.metric_views`. Prefer structured surfaces in this order: Metric View semantic metadata, table/column metadata, synonyms, format assistance/entity matching, join specs, SQL snippets, example SQLs, SQL functions, then concise global text instructions. Present the plan or draft config for review before live creation.
8. **Validate locally.** Save the decoded JSON under `genie_configs/` or another user-requested path, then run:

   ```bash
   python3 external-agent/create-genie-space/scripts/validate_space_json.py <path-to-serialized-space.json>
   ```

   Fix all structural errors. Treat warnings from the best-practice checks as items to either address or explain.
9. **Package for creation only when requested.** If the user wants an API payload, wrap the validated JSON as the `serialized_space` string in the create-space request body. If the user asks to create the live space, confirm the target workspace/profile and use the Databricks Genie create API only after validation passes.

## Output Requirements

When finishing a creation task, provide:

- The path to the validated decoded `serialized_space` JSON.
- A concise summary of requirements, data objects included, Metric Views attached, readiness confidence, columns hidden, joins added, snippets/examples/benchmarks created, and any assumptions.
- The validation command result.
- Any unresolved questions that affect correctness, such as ambiguous joins or business metric definitions.

If DBSQL access is unavailable, produce the inspection SQL the user should run and mark the JSON as a draft, not validated.
