---
name: create-genie-space
description: "Create a Databricks Genie Space serialized_space JSON from Unity Catalog datasets. Use when users ask to build, bootstrap, author, or generate a new Genie Space config for catalog/schema data objects including tables, views, and Metric Views; validate selected data objects with read-only Databricks SQL or DBSQL MCP, inspect schemas and data shape, choose appropriate Genie configuration surfaces, and produce JSON/API payloads that follow Databricks Genie best practices. This skill may create config files but must not mutate source tables, views, Metric Views, schemas, or data. For tuning an existing Space use optimize-genie-space; for read-only diagnosis use diagnose-genie-space."
---

# Create Genie Space

Create a new Databricks Genie Space configuration from selected Unity Catalog data objects: tables, views, Metric Views, or a combination of these. The default output is a decoded `serialized_space` JSON file that can be validated locally and then wrapped in a Databricks create-space API request.

## Hard Rules

- Use only bounded read-only Databricks SQL for dataset inspection: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema` queries. Prefer metadata, narrow previews, partition/date filters, and sampled profiling; use broad full-table scans only when needed and approved (`references/data-profiling-and-readiness.md` → Bounded Profiling Guardrails).
- Never run DDL, DML, `CREATE`, `ALTER`, `DROP`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, or table/schema/data mutation.
- Do not create or alter Metric Views as part of this skill. Add existing Metric Views to `data_sources.metric_views`. When the semantic model is wrong or missing, document the upstream gap and recommend authoring or fixing the Metric View upstream (for example with a metric-view authoring skill when available).
- Use the DBSQL MCP when available in external coding agents; in Databricks notebooks or Genie Code, use native DBSQL/notebook SQL.
- Do not create a live Genie Space through the API unless the user explicitly asks for live creation and provides the required workspace details.
- Do not rate a business question High confidence or propose live creation until each included source clears the Context Evidence Gate (`references/data-profiling-and-readiness.md`): Unity Catalog metadata and `DESCRIBE`, a row count or estimate, a freshness signal, a narrow preview of question-relevant columns, and key/join evidence for every proposed relationship. Record any check you cannot complete as an explicit confidence reduction, not a silent omission.
- Do not include unvalidated benchmark SQL in the JSON. If SQL cannot be validated with read-only execution or `EXPLAIN`, put benchmark candidates in notes instead of `benchmarks.questions`.
- Do not invent uncertain business definitions, joins, fiscal calendars, default filters, or metric formulas. Ask the user when the data does not prove them.
- Do not copy benchmark questions or benchmark answer SQL into sample questions, snippets, or example SQL.

## Workflow

1. **Gather requirements.** Capture the space purpose, audience, title or draft title, and 3-5 real business questions users want Genie to answer. Capture known business terms, KPI definitions, fiscal/calendar rules, default filters, row-level/security caveats, and sensitive columns.
2. **Discover or confirm data.** If the user knows the catalog, schema, tables/views, or Metric Views, confirm those exact objects. Otherwise, search or browse Unity Catalog using terms from the requirements, synonyms, abbreviations, and likely fact/dimension naming patterns. Recommend a focused source set — ideally 5 or fewer objects initially — and explain how each source maps to the business questions. When a focused design would need many more sources or depends on ambiguous multi-hop joins, recommend pre-joining or denormalizing upstream into a curated view or Metric View instead of attaching many raw tables.
3. **Check feasibility.** Before deep profiling, compare the selected data objects to the business questions. Identify obvious gaps such as missing measures, time columns, dimensions, or join paths. Ask the user to proceed, add data, or adjust questions when the selected objects cannot support the goal.
4. **Load references.** Read `references/creation-workflow.md` and `references/data-profiling-and-readiness.md` before authoring JSON. If any selected object is a Metric View, read `references/metric-views.md`. Read `references/best-practices-checklist.md` while reviewing quality. Read `references/space-schema.md` when field shape or validation rules matter.
5. **Inspect and profile in phases.** Use read-only DBSQL to confirm each object exists, inspect metadata, then profile data quality, representative values, grain, freshness, joins, and usage/lineage signals, capturing the per-source Context Evidence Gate checks. Inspect and correct AI-generated Unity Catalog table/column descriptions before trusting them. For Metric Views, inspect the definition/metadata and validate representative queries with explicit dimensions and `MEASURE()` calls. Keep samples bounded and avoid dumping sensitive values.
6. **Assess readiness.** For each business question, state High/Medium/Low confidence using the rubric in `references/data-profiling-and-readiness.md`. Resolve low-confidence gaps before proceeding or mark the JSON as a draft with explicit limitations.
7. **Design and review the space.** Build a version 2 `serialized_space` object with focused `data_sources.tables` and/or `data_sources.metric_views`, preferring structured surfaces over text instructions in the priority order defined in `references/best-practices-checklist.md`. Prefer trusted assets — parameterized example SQL with exact-text matching and UC SQL functions — over plain examples for high-value questions that must return verified answers. Follow the prompt-matching safety rules in `references/best-practices-checklist.md` before enabling format assistance or entity matching. Provide 2-4 natural phrasings per key intent across sample questions and benchmark coverage. Present the plan or draft config for review before live creation.
8. **Validate locally.** Save the decoded JSON under a user-requested path, then run the validator, resolving `<skill-dir>` to wherever this skill is installed (for example `.claude/skills/create-genie-space` or `~/.codex/skills/create-genie-space`):

   ```bash
   python3 <skill-dir>/scripts/validate_space_json.py <path-to-serialized-space.json>
   ```

   Fix all structural errors. Treat warnings from the best-practice checks as items to either address or explain.
9. **Package for creation only when requested.** If the user wants an API payload, wrap the validated JSON as the `serialized_space` string in the create-space request body. If the user asks to create the live space, first confirm the prerequisites in `references/best-practices-checklist.md` (Genie and data permissions, a pro or serverless SQL warehouse with `CAN USE`, Unity Catalog data access, documented capacity limits), then confirm the target workspace/profile and use the Databricks Genie create API only after validation passes.

## Output Requirements

When finishing a creation task, provide:

- The path to the validated decoded `serialized_space` JSON.
- A concise summary of requirements, data objects included, Metric Views attached, readiness confidence, evidence-gate checks completed or reduced, columns hidden, joins added, snippets/examples/benchmarks created, and any assumptions.
- The validation command result.
- Any unresolved questions that affect correctness, such as ambiguous joins or business metric definitions.

If DBSQL access is unavailable, produce the inspection SQL the user should run and mark the JSON as a draft, not validated.
