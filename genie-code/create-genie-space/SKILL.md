---
name: create-genie-space
description: "Create or refine a Databricks Genie Space from Unity Catalog tables, views, and Metric Views in Databricks Genie Code Agent mode. Use inside Databricks when users ask Genie Code to build, bootstrap, configure, or review a Genie Space, inspect workspace data context, choose focused data sources, design instructions, examples, sample questions, and benchmarks, or prepare safe Space changes without source data mutation."
---

# Create Genie Space For Genie Code

Create a focused Genie Space using Databricks-native context. Rely on Genie Code Agent mode to inspect Unity Catalog metadata, open workspace assets, run approved notebook or SQL editor steps, and read returned output.

## Hard Rules

- Use only bounded read-only SQL to inspect data: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema`.
- Never mutate Unity Catalog objects or data. Do not run `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, or equivalent mutation.
- Do not create or alter Metric Views as part of this skill. Use existing Metric Views as Genie data sources and document any upstream semantic model gaps.
- Do not create or update a live Genie Space unless the user explicitly asks and approves the proposed changes in Databricks.
- Do not invent business definitions, joins, fiscal calendars, default filters, or metric formulas. Ask the user when workspace evidence is insufficient.
- Do not add benchmark SQL unless it has been checked with read-only execution or `EXPLAIN`.

## Workflow

1. Clarify the minimum scope: target catalog/schema or provided `@` assets, selected tables/views/Metric Views, audience, Space purpose, and whether the user wants a draft design or approved live change.
2. Inspect the workspace context. Use Unity Catalog metadata, attached assets, and bounded SQL to identify source purpose, comments, columns, data types, grain, date fields, categorical values, measures, sensitive/noisy fields, and likely relationships.
3. For Metric Views, inspect their available measures, dimensions, filters, joins, time dimensions, comments, display names, synonyms, and formatting before adding extra Genie context. Prefer governed Metric View semantics over duplicated SQL logic.
4. Design the Genie Space surfaces:
   - data sources: keep the attached tables/views/Metric Views focused
   - descriptions and synonyms: clarify business meaning and selection boundaries
   - hidden fields: remove noisy technical columns from end-user context
   - prompt matching: enable only for eligible, useful categorical strings
   - joins: add standard raw-table relationships only when evidence or user confirmation supports them
   - snippets/examples: add reusable business logic and representative complex patterns only after metadata is insufficient
   - text instructions: keep global and short
   - sample questions and benchmarks: cover realistic user workflows without teaching from benchmark answers
5. Review the draft against `references/space-design-guide.md` before proposing live changes.
6. Present the proposed Space configuration in the Databricks-native editor or chat output for user review. Apply only after the user approves.

## Output

Provide:

- The Genie Space title or draft title.
- The data sources included and why each belongs.
- Important metadata, prompt matching, join, snippet, example, sample question, and benchmark choices.
- Any assumptions or user confirmations needed before live creation or update.
- The read-only validation performed and any limitations.
