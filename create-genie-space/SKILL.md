---
name: create-genie-space
description: "Create a Databricks Genie Space serialized_space JSON from Unity Catalog datasets. Use when users ask to build, bootstrap, author, or generate a new Genie Space config for catalog/schema/table data; validate selected tables with read-only Databricks SQL or DBSQL MCP, inspect schemas and data shape, choose appropriate Genie configuration surfaces, and produce JSON/API payloads that follow Databricks Genie best practices. This skill may create config files but must not mutate source tables or schemas."
---

# Create Genie Space

Create a new Databricks Genie Space configuration from selected Unity Catalog tables. The default output is a decoded `serialized_space` JSON file that can be validated locally and then wrapped in a Databricks create-space API request.

## Hard Rules

- Use only read-only Databricks SQL for dataset inspection: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema` queries.
- Never run DDL, DML, `CREATE`, `ALTER`, `DROP`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, or table/schema/data mutation.
- Use the DBSQL MCP when available in external coding agents; in Databricks Genie Code or notebooks, use native DBSQL/notebook SQL.
- Do not create a live Genie Space through the API unless the user explicitly asks for live creation and provides the required workspace details.
- Do not include unvalidated benchmark SQL in the JSON. If SQL cannot be validated with read-only execution or `EXPLAIN`, put benchmark candidates in notes instead of `benchmarks.questions`.
- Do not invent uncertain business definitions, joins, fiscal calendars, default filters, or metric formulas. Ask the user when the data does not prove them.

## Workflow

1. **Collect scope.** Ask for the catalog, schema, and table names if missing. Also ask for the space purpose/audience and whether the user wants JSON only or an API create payload. If creating a payload, collect `title`, `parent_path`, and `warehouse_id`.
2. **Load references.** Read `references/creation-workflow.md` before authoring the JSON. Read `references/best-practices-checklist.md` while reviewing quality. Read `references/space-schema.md` when field shape or validation rules matter.
3. **Validate datasets.** Use read-only DBSQL to confirm each table exists, inspect comments, columns, data types, row/grain signals, candidate date columns, categorical values, measures, and likely joins. Keep samples bounded and avoid dumping sensitive values.
4. **Design the space.** Build a version 2 `serialized_space` object with focused tables, descriptive table/column metadata, useful synonyms, hidden noisy columns, entity matching/format assistance only where appropriate, explicit join specs, reusable SQL snippets, representative sample questions, and validated benchmarks when feasible.
5. **Validate locally.** Save the decoded JSON under `genie_configs/` or another user-requested path, then run:

   ```bash
   python3 create-genie-space/scripts/validate_space_json.py <path-to-serialized-space.json>
   ```

   Fix all structural errors. Treat warnings from the best-practice checks as items to either address or explain.
6. **Package for creation only when requested.** If the user wants an API payload, wrap the validated JSON as the `serialized_space` string in the create-space request body. If the user asks to create the live space, confirm the target workspace/profile and use the Databricks Genie create API only after validation passes.

## Output Requirements

When finishing a creation task, provide:

- The path to the validated decoded `serialized_space` JSON.
- A concise summary of tables included, columns hidden, joins added, snippets/examples/benchmarks created, and any assumptions.
- The validation command result.
- Any unresolved questions that affect correctness, such as ambiguous joins or business metric definitions.

If DBSQL access is unavailable, produce the inspection SQL the user should run and mark the JSON as a draft, not validated.
