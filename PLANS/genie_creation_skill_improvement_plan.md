# Genie Creation Skill Improvement Plan

**Date:** 2026-05-22  
**Target repository:** `https://github.com/hiydavid/databricks-agent-skills`  
**Reference repository:** `https://github.com/databricks-solutions/databricks-genie-workbench`  
**Intended recipient:** Codex or another coding agent working inside `databricks-agent-skills`

## 1. Objective

Improve the `create-genie-space` skills so they behave more like the robust Genie Workbench Create Agent: they should discover candidate data sources, inspect/profile the data, assess readiness, generate a reviewed plan, then compile and validate a Genie Space configuration.

The current skills are already conservative and useful. They enforce read-only behavior, avoid unvalidated benchmark SQL, prefer version 2 space JSON, and include a local validator. The improvement should not replace that baseline. It should add a more reliable pre-configuration workflow and deterministic helper scripts so the agent does not jump from “tables exist” to “here is JSON.”

## 2. Source observations

### 2.1 Reference repo patterns to adapt

The reference `databricks-genie-workbench` Create Agent is documented as a multi-turn, tool-calling LLM agent that moves from business requirements to a configured/deployed Genie Space. Its documented flow has six stages:

1. Requirements gathering
2. Data source discovery
3. Inspection and profiling
4. Plan generation and review
5. Config creation and validation
6. Post-creation guidance

Reference documentation reviewed:

- `docs/04-create-agent.md`  
  `https://github.com/databricks-solutions/databricks-genie-workbench/blob/main/docs/04-create-agent.md`
- `backend/services/create_agent_tools.py`  
  `https://github.com/databricks-solutions/databricks-genie-workbench/blob/main/backend/services/create_agent_tools.py`
- `backend/services/plan_builder.py`  
  `https://github.com/databricks-solutions/databricks-genie-workbench/blob/main/backend/services/plan_builder.py`
- `backend/genie_creator.py`  
  `https://github.com/databricks-solutions/databricks-genie-workbench/blob/main/backend/genie_creator.py`

Important reference behaviors to adapt conceptually:

- The agent separates requirements, discovery, inspection, planning, validation, and creation instead of treating creation as one prompt.
- It has explicit discovery tools for catalogs, schemas, tables, table descriptions, table search, warehouses, and config schema lookup.
- It has explicit profiling and quality tools such as column profiling, data quality assessment, table usage profiling, and readiness assessment.
- It presents a plan before creating the config.
- It generates plan sections independently: tables/columns, sample questions/text instructions, example SQLs, benchmarks, and analytics snippets.
- It validates SQL and drops or repairs bad examples rather than relying on untested output.
- It uses deterministic formatting and API-normalization logic to reduce LLM JSON mistakes.
- It has post-generation validation for shape, IDs, counts, text instruction quality, join specs, Metric View SQL rules, and benchmark quality.

Do **not** copy reference source code into this repo. Use the workflow and quality gates as design input, then implement original scripts and skill text appropriate for `databricks-agent-skills`.

### 2.2 Current repo baseline

Target files reviewed:

- `README.md`  
  `https://github.com/hiydavid/databricks-agent-skills/blob/main/README.md`
- `external-agent/create-genie-space/SKILL.md`  
  `https://github.com/hiydavid/databricks-agent-skills/blob/main/external-agent/create-genie-space/SKILL.md`
- `genie-code/create-genie-space/SKILL.md`  
  `https://github.com/hiydavid/databricks-agent-skills/blob/main/genie-code/create-genie-space/SKILL.md`
- `external-agent/create-genie-space/references/creation-workflow.md`  
  `https://github.com/hiydavid/databricks-agent-skills/blob/main/external-agent/create-genie-space/references/creation-workflow.md`
- `external-agent/create-genie-space/references/best-practices-checklist.md`  
  `https://github.com/hiydavid/databricks-agent-skills/blob/main/external-agent/create-genie-space/references/best-practices-checklist.md`
- `external-agent/create-genie-space/references/metric-views.md`  
  `https://github.com/hiydavid/databricks-agent-skills/blob/main/external-agent/create-genie-space/references/metric-views.md`
- `external-agent/create-genie-space/references/space-schema.md`  
  `https://github.com/hiydavid/databricks-agent-skills/blob/main/external-agent/create-genie-space/references/space-schema.md`
- `external-agent/create-genie-space/scripts/validate_space_json.py`  
  `https://github.com/hiydavid/databricks-agent-skills/blob/main/external-agent/create-genie-space/scripts/validate_space_json.py`

Current strengths:

- Two distributions exist: `external-agent` and `genie-code`.
- Both `create-genie-space` skills include safety rules: read-only SQL, no DDL/DML, no live API calls unless requested, no unvalidated benchmark SQL, and no invented metrics or definitions.
- The existing workflow already asks the agent to collect scope, load references, validate datasets, design a version 2 `serialized_space`, validate locally, and package/create only when requested.
- The existing `creation-workflow.md` includes useful SQL snippets for information schema discovery, constraints, basic profiling, sample distinct values, sample rows, and Metric View inspection.
- The existing checklist covers data source scope, table and column descriptions, synonyms, example values, hidden columns, Metric Views, instructions, examples, joins, snippets, benchmarks, and sample questions.
- The existing validator is stronger than a basic schema check. It validates version, IDs, data source limits, sorted collections, table and Metric View identifiers, column metadata, duplicate IDs, one text instruction, join relationship annotations, benchmark answer shape, benchmark/example duplication, and Metric View SQL patterns such as `MEASURE()` and direct joins.

Current gaps relative to the reference agent:

- The skill does not force a distinct “profile evidence → readiness assessment → plan artifact → config compile” sequence.
- Profiling is documented but not operationalized through helper scripts, expected result formats, or a required profile summary.
- There is no structured plan schema equivalent to the reference agent’s reviewed plan step.
- There is no plan validator to catch invented values, missing evidence, weak table grain descriptions, missing join evidence, or premature config generation.
- The external-agent version has only one script, `validate_space_json.py`; it lacks deterministic helpers for inspection SQL generation, profile result summarization, plan validation, and plan-to-config compilation.
- The Genie Code version mirrors the high-level workflow but does not have enough explicit checkpoints for the in-product agent to follow when it cannot rely on external scripts.
- There is no persistent workspace convention for intermediate artifacts such as requirements, inspection SQL, profile outputs, readiness report, plan JSON, and final `serialized_space`.

## 3. Design principle

Add an evidence-first creation workflow:

```text
business requirements
  -> candidate source discovery
  -> source inspection and profiling
  -> readiness assessment
  -> reviewed space plan
  -> generated serialized_space
  -> structural + best-practice validation
  -> optional package or live creation
  -> post-creation test/evaluation guidance
```

The key change is that the skill should not create final JSON until it has either:

1. Gathered enough data/profile evidence to justify the configuration, or
2. Explicitly labeled the output as a draft due to missing workspace access or missing profiling results.

## 4. Proposed file changes

### 4.1 Update `external-agent/create-genie-space/SKILL.md`

Replace the current linear workflow with a required staged workflow.

Add this creation sequence:

```markdown
## Required creation sequence

1. Requirements brief
   - Capture business goal, target users, domain vocabulary, success criteria, workspace host, warehouse, catalog/schema scope, candidate tables/views/Metric Views, and whether live creation is requested.

2. Data source discovery
   - Use read-only discovery queries or user-provided object names.
   - Prefer a focused source set: ideally <=5 data objects; never exceed 30.
   - Search by table names, column names, table comments, and column comments when the source set is unclear.

3. Inspection and profiling
   - Generate or run read-only inspection SQL.
   - Collect table grain, row counts, freshness, time ranges, key columns, join candidates, null rates, distinct counts, top categorical values, sample rows, and data quality issues.
   - For Metric Views, inspect dimensions, measures, filters, joins, and agent metadata.

4. Readiness assessment
   - Summarize whether the source set is ready for a Genie Space.
   - Identify missing descriptions, unclear grain, unsafe columns, noisy technical columns, weak join keys, stale data, sparse fields, and missing benchmarkable metrics.

5. Space plan
   - Produce a plan artifact before final JSON.
   - The plan must include selected sources, table/Metric View descriptions, column config intent, exclusions, joins, snippets, sample questions, example SQLs, benchmark candidates, and unresolved questions.
   - Do not compile final JSON until the plan is reviewed or marked as an explicit draft.

6. Config compilation
   - Compile version 2 `serialized_space` from the plan.
   - Use deterministic IDs, stable sorting, string arrays where required, fully qualified identifiers, and validated SQL only.

7. Validation
   - Run local validation.
   - Report errors, warnings, unvalidated SQL, and assumptions.
   - Do not claim API readiness when validation fails.

8. Package or live creation
   - Package the create-space API payload by default.
   - Call the live Genie API only when the user explicitly requests it.

9. Post-creation guidance
   - Recommend starting an instruction evaluation/benchmark pass and reviewing failed questions before expanding scope.
```

Add hard gate language:

```markdown
Do not jump directly from object names to final `serialized_space` unless the user explicitly asks for a draft and the response labels missing profiling evidence.
```

Add required output files:

```markdown
When creating artifacts, use this workspace layout unless the user specifies another path:

`genie_workspace/<space_slug>/requirements.md`
`genie_workspace/<space_slug>/inspection.sql`
`genie_workspace/<space_slug>/profile_summary.json`
`genie_workspace/<space_slug>/readiness.md`
`genie_workspace/<space_slug>/plan.json`
`genie_workspace/<space_slug>/serialized_space.json`
`genie_workspace/<space_slug>/create_space_payload.json`
`genie_workspace/<space_slug>/validation_report.md`
```

### 4.2 Update `genie-code/create-genie-space/SKILL.md`

Mirror the same staged workflow, but make it tool-agnostic and suitable for Genie Code’s native environment.

Key edits:

- Add the same “requirements → discovery → profiling → readiness → plan → config → validation → package/create” sequence.
- Tell the agent to use available workspace context and read-only SQL tools when possible.
- When external scripts are unavailable, require the same artifacts conceptually in the response: requirements brief, profile summary, readiness report, plan, config, validation findings.
- Preserve the current restriction that live Genie API creation happens only on explicit request.
- Require that missing profiling access be called out as a limitation.

### 4.3 Add `external-agent/create-genie-space/references/data-profiling.md`

Create a dedicated profiling reference. It should explain what to inspect and provide SQL templates.

Sections:

1. Purpose
2. Minimum evidence before planning
3. Table/view discovery SQL
4. Metric View discovery SQL
5. Row count and freshness SQL
6. Column profiling SQL
7. Categorical value profiling SQL
8. Join candidate profiling SQL
9. Data quality checks
10. PII and technical/ETL field heuristics
11. How to turn profile evidence into Genie config choices

Suggested content for minimum evidence:

```markdown
A plan should have evidence for:

- Source existence and type
- Table or Metric View grain
- Row count or approximate scale
- Freshness and time range when time columns exist
- Business dimensions and measures
- Candidate filter columns
- Candidate entity-matching columns
- Candidate format-assistance columns
- Technical/ETL columns to exclude
- Join keys and relationship direction when using multiple tables
- Real categorical values used in examples and benchmarks
- SQL validation status for every example SQL and benchmark SQL
```

Recommended PII and technical heuristics:

```markdown
Treat columns matching these patterns as sensitive or technical until proven otherwise:

Potential PII: email, phone, ssn, social_security, address, birthdate, dob, name, first_name, last_name, ip_address, device_id, user_id, customer_id when it identifies a person.

Technical/ETL: _rescued_data, _metadata, _commit, _change_type, _change_ordinal, ingest, ingestion, etl, pipeline, batch_id, job_id, run_id, created_at, updated_at, deleted_at, valid_from, valid_to, hash, checksum.
```

### 4.4 Add `genie-code/create-genie-space/references/data-profiling.md`

Use the same content as the external-agent version, but remove references to command-line scripts. Keep read-only SQL templates and the required evidence checklist.

### 4.5 Add `external-agent/create-genie-space/references/plan-schema.md`

Create a structured plan reference so the skill can produce a plan before JSON.

Recommended schema:

```json
{
  "space": {
    "title": "string",
    "description": "string",
    "warehouse_id": "string|null",
    "parent_path": "string|null",
    "creation_mode": "draft|package_only|live_api_requested"
  },
  "requirements": {
    "business_goal": "string",
    "target_users": ["string"],
    "success_criteria": ["string"],
    "domain_terms": [{"term": "string", "definition": "string", "source": "user|profile|assumption"}]
  },
  "source_candidates": [
    {
      "identifier": "catalog.schema.object",
      "type": "table|view|metric_view",
      "why_considered": "string",
      "selected": true,
      "selection_reason": "string"
    }
  ],
  "profile_summary": {
    "generated_from": "manual|sql_results|not_available",
    "tables": [
      {
        "identifier": "catalog.schema.table",
        "grain": "string",
        "row_count": "integer|null",
        "freshness_column": "string|null",
        "time_range": {"min": "string|null", "max": "string|null"},
        "quality_notes": ["string"],
        "columns": [
          {
            "name": "string",
            "type": "string",
            "description_source": "catalog|profile|user|inferred|missing",
            "null_rate": "number|null",
            "distinct_count": "integer|null",
            "top_values": ["string"],
            "recommended_role": "dimension|measure|time|join_key|filter|entity|format_assist|exclude",
            "exclude_reason": "string|null"
          }
        ]
      }
    ],
    "metric_views": [
      {
        "identifier": "catalog.schema.metric_view",
        "measures": ["string"],
        "dimensions": ["string"],
        "filters": ["string"],
        "metadata_notes": ["string"]
      }
    ],
    "joins": [
      {
        "left": "catalog.schema.table.column",
        "right": "catalog.schema.table.column",
        "relationship": "many_to_one|one_to_many|one_to_one|many_to_many|unknown",
        "evidence": "string"
      }
    ]
  },
  "readiness": {
    "status": "ready|needs_user_input|needs_more_data|draft_only",
    "score": 0,
    "blocking_issues": ["string"],
    "warnings": ["string"],
    "recommended_next_steps": ["string"]
  },
  "space_plan": {
    "data_sources": [
      {
        "identifier": "catalog.schema.object",
        "type": "table|view|metric_view",
        "description": "string",
        "column_configs": [
          {
            "column_name": "string",
            "description": "string",
            "synonyms": ["string"],
            "exclude": false,
            "enable_format_assistance": false,
            "enable_entity_matching": false,
            "evidence": "string"
          }
        ]
      }
    ],
    "text_instruction": {
      "purpose": "string",
      "disambiguation": ["string"],
      "data_quality_notes": ["string"],
      "constraints": ["string"]
    },
    "join_specs": [
      {
        "sql_condition": "left_table.left_col = right_table.right_col",
        "relationship_annotation": "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--",
        "comment": "string"
      }
    ],
    "sql_snippets": {
      "measures": [{"name": "string", "sql": "string", "evidence": "string"}],
      "filters": [{"name": "string", "sql": "string", "evidence": "string"}],
      "expressions": [{"name": "string", "sql": "string", "evidence": "string"}]
    },
    "sample_questions": ["string"],
    "example_question_sqls": [
      {"question": "string", "sql": "string", "validation_status": "validated|not_validated", "evidence": "string"}
    ],
    "benchmarks": [
      {"question": "string", "sql": "string", "validation_status": "validated|not_validated", "evidence": "string"}
    ]
  },
  "unresolved_questions": ["string"]
}
```

Add plan quality rules:

- Every selected source needs a reason.
- Every visible column should have a business description or be flagged as missing.
- Every excluded column needs an exclusion reason.
- Entity matching should be enabled only for low/medium-cardinality business entities where the values are useful for lookup.
- Format assistance should be enabled only where formatting or example values help disambiguation.
- Example SQL and benchmark SQL must be marked `validated` before final config unless the entire config is labeled draft.
- String literals in SQL filters should come from profile `top_values`, user-provided requirements, or documented domain definitions.
- Join specs require evidence for key compatibility and relationship direction, or the relationship must be marked unknown and excluded from final config.

### 4.6 Add `genie-code/create-genie-space/references/plan-schema.md`

Use the same plan schema. Add a note that Genie Code can represent the plan in Markdown if JSON is too heavy, but it must preserve the same fields and quality gates.

### 4.7 Update `external-agent/create-genie-space/references/creation-workflow.md`

Expand the current workflow with more explicit gates.

Proposed outline:

```markdown
# Genie Space creation workflow

## 1. Requirements brief
## 2. Candidate source discovery
## 3. Inspection SQL generation
## 4. Profile result interpretation
## 5. Readiness assessment
## 6. Plan generation
## 7. Plan validation
## 8. Serialized space compilation
## 9. Local validation
## 10. API payload packaging or live creation
## 11. Post-creation evaluation
```

Keep existing SQL snippets, but move them under the new profiling reference or cross-link to it.

### 4.8 Update `external-agent/create-genie-space/references/best-practices-checklist.md`

Add checks that correspond to the new staged process:

```markdown
## Evidence and planning
- [ ] Requirements brief exists.
- [ ] Candidate sources were discovered or provided by the user.
- [ ] Selected sources have a selection rationale.
- [ ] Data grain is known for every table/view.
- [ ] Metric View dimensions, measures, filters, and metadata were inspected.
- [ ] Profile summary includes row counts, freshness when applicable, null/distinct metrics, top categorical values, and quality issues.
- [ ] Technical/ETL and sensitive columns were reviewed for exclusion.
- [ ] Join specs have evidence, not just guessed column names.
- [ ] Example SQL and benchmark SQL use real values from user input or profiles.
- [ ] A plan artifact was reviewed before final JSON.
```

### 4.9 Keep `space-schema.md`, but add “compiler expectations”

Add a short section explaining deterministic compilation rules:

- Generate 32-character lowercase hex IDs.
- Sort arrays in the same order the validator expects.
- Use string arrays for text fields that the schema represents as repeated strings.
- Split SQL into arrays only where current schema examples require arrays.
- Use fully qualified identifiers.
- Keep exactly one text instruction.
- Use version 2 fields: `enable_format_assistance` and `enable_entity_matching`.
- Do not use version 1 fields: `get_example_values` and `build_value_dictionary`.

## 5. New helper scripts for external-agent distribution

The external-agent skill should remain usable by Codex or a CLI coding agent. Add scripts that create deterministic intermediate artifacts. The scripts should not require live Databricks access unless explicitly designed to run through a provided SQL client; default behavior should generate SQL or validate local files.

### 5.1 `scripts/generate_inspection_sql.py`

Purpose: generate a read-only SQL file for source discovery and profiling.

Suggested CLI:

```bash
python external-agent/create-genie-space/scripts/generate_inspection_sql.py \
  --catalog main \
  --schema sales \
  --objects orders customers products \
  --output genie_workspace/sales/inspection.sql
```

Suggested behavior:

- Accept `--catalog`, `--schema`, and `--objects`.
- Accept fully qualified names as alternatives.
- Accept `--include-search` with keywords for table/column/comment search.
- Emit only read-only SQL: `SHOW`, `DESCRIBE`, `SELECT`, `WITH`, `INFORMATION_SCHEMA` queries, and Metric View `DESCRIBE EXTENDED AS JSON`.
- Generate sections:
  - catalog/schema verification
  - table/view/Metric View metadata
  - columns and comments
  - constraints if available
  - row count/freshness
  - null/distinct estimates
  - categorical top values for string columns
  - join candidate checks for likely key pairs
  - sample rows with a small limit
- Include comments showing how to capture results into JSON/CSV for the summarizer.

Hard safety requirement:

```python
FORBIDDEN_SQL_RE = r"\b(CREATE|ALTER|DROP|TRUNCATE|INSERT|UPDATE|DELETE|MERGE|OPTIMIZE|VACUUM|RESTORE|GRANT|REVOKE)\b"
```

The generator should fail tests if forbidden verbs appear in generated SQL.

### 5.2 `scripts/summarize_profile_results.py`

Purpose: turn SQL output files into a normalized `profile_summary.json`.

Suggested CLI:

```bash
python external-agent/create-genie-space/scripts/summarize_profile_results.py \
  --input-dir genie_workspace/sales/profile_results \
  --output genie_workspace/sales/profile_summary.json
```

Supported inputs:

- JSON files exported from Databricks SQL query results
- CSV files exported from query results
- A manually authored JSON file following the same structure

Suggested output fields:

- source identifier
- source type
- row count
- freshness column and min/max timestamps
- column name/type/comment
- null rate
- distinct count
- top values
- sample literals
- quality flags
- recommended role
- exclusion recommendation
- entity matching recommendation
- format assistance recommendation
- join evidence

This script should not invent business meaning. It can recommend roles heuristically, but it must label inference confidence and evidence.

### 5.3 `scripts/validate_plan.py`

Purpose: validate the new `plan.json` before compiling final Genie Space JSON.

Suggested CLI:

```bash
python external-agent/create-genie-space/scripts/validate_plan.py \
  genie_workspace/sales/plan.json \
  --profile-summary genie_workspace/sales/profile_summary.json \
  --strict
```

Validation rules:

- Required top-level sections exist.
- `space.title`, `space.description`, and `source_candidates` are populated.
- Every selected source appears in `profile_summary` unless `generated_from` is `not_available` and `creation_mode` is `draft`.
- Every selected table/view has a grain or a blocking warning.
- Every visible column has a description or warning.
- Every excluded column has a reason.
- Every join spec has evidence.
- Every example SQL and benchmark SQL has `validation_status = validated` unless the plan is draft.
- String literals in SQL filters must be traceable to profile top values, user requirements, or explicit domain definitions.
- Benchmark count warnings:
  - `0`: warning or error depending on strictness
  - `<10`: warn strongly
  - `<30`: warn that optimization readiness is limited
- Example SQL count warnings:
  - `<8`: warn
  - `10-15`: recommended range
- Text instruction must be concise and must not contain SQL.
- No unsupported version 1 fields.
- Metric View SQL must use `MEASURE()` for measures and should use a CTE for mixed Metric View + table/view queries.

### 5.4 `scripts/build_space_from_plan.py`

Purpose: compile a validated `plan.json` into `serialized_space.json`.

Suggested CLI:

```bash
python external-agent/create-genie-space/scripts/build_space_from_plan.py \
  genie_workspace/sales/plan.json \
  --output genie_workspace/sales/serialized_space.json
```

Compiler rules:

- Produce version 2 `serialized_space` only.
- Generate deterministic 32-character lowercase hex IDs from stable names, for example using UUIDv5 or SHA256 truncation.
- Sort tables and Metric Views by identifier.
- Sort column configs by `column_name`.
- Sort instruction collections by generated ID or stable semantic key.
- Use fully qualified identifiers.
- Keep descriptions as string arrays if required by current schema patterns.
- Convert the plan text instruction into one concise text instruction with sections:
  - `PURPOSE`
  - `DISAMBIGUATION`
  - `DATA QUALITY NOTES`
  - `CONSTRAINTS`
- Exclude SQL-bearing guidance from text instructions; put reusable SQL in snippets or examples.
- Include only validated example SQLs and benchmarks unless `--allow-draft-sql` is passed.

### 5.5 `scripts/build_create_space_payload.py`

Purpose: wrap the decoded `serialized_space.json` into a Genie Spaces API request payload without calling the API.

Suggested CLI:

```bash
python external-agent/create-genie-space/scripts/build_create_space_payload.py \
  --serialized-space genie_workspace/sales/serialized_space.json \
  --title "Sales Analytics" \
  --description "Genie Space for sales analytics" \
  --warehouse-id "abc123" \
  --parent-path /Users/example@example.com \
  --output genie_workspace/sales/create_space_payload.json
```

Behavior:

- Read decoded `serialized_space.json`.
- Emit a request body with `title`, `description`, `warehouse_id`, `parent_path`, and `serialized_space` encoded as the API expects.
- Do not call the API.
- Make live creation a separate explicit command or leave it to the user.

### 5.6 Update `scripts/validate_space_json.py`

The existing validator is already useful. Extend it rather than replacing it.

Add or verify these checks:

- Warn when text instruction character count exceeds a practical limit such as 2,500 characters.
- Warn when text instruction contains SQL keywords or looks like an example query.
- Warn when there are multiple sources but no join specs.
- Warn when there are fewer than 8 example SQLs.
- Warn when there are fewer than 10 benchmarks; warn that fewer than 30 limits optimization/evaluation readiness.
- Detect empty snippets and fail if snippets contain no SQL.
- Detect entity matching enabled without format assistance.
- Warn when entity matching is enabled on high-cardinality technical fields.
- Detect version 1 fields in version 2 configs.
- Normalize or warn on invalid join relationship annotations.
- Detect benchmark SQL copied verbatim into example SQLs.
- Flag Metric View SQL that uses `SELECT *`, omits `MEASURE()` for Metric View measures, or directly joins a Metric View without a CTE.
- Emit machine-readable JSON report when `--report-json` is passed.

## 6. Data profiling design details

### 6.1 Minimum inspection SQL templates

The exact SQL should be Databricks SQL compatible and read-only.

#### Source existence and metadata

```sql
SHOW TABLES IN `catalog`.`schema`;

SELECT
  table_catalog,
  table_schema,
  table_name,
  table_type,
  comment
FROM `catalog`.information_schema.tables
WHERE table_schema = 'schema'
  AND table_name IN ('orders', 'customers');
```

#### Column metadata

```sql
SELECT
  table_catalog,
  table_schema,
  table_name,
  column_name,
  ordinal_position,
  data_type,
  comment
FROM `catalog`.information_schema.columns
WHERE table_schema = 'schema'
  AND table_name IN ('orders', 'customers')
ORDER BY table_name, ordinal_position;
```

#### Basic table profile

```sql
SELECT
  COUNT(*) AS row_count,
  MIN(event_date) AS min_event_date,
  MAX(event_date) AS max_event_date
FROM `catalog`.`schema`.`orders`;
```

#### Null and distinct profile

For each selected column:

```sql
SELECT
  'orders' AS table_name,
  'status' AS column_name,
  COUNT(*) AS row_count,
  SUM(CASE WHEN status IS NULL THEN 1 ELSE 0 END) AS null_count,
  COUNT(DISTINCT status) AS distinct_count
FROM `catalog`.`schema`.`orders`;
```

#### Top categorical values

```sql
SELECT
  status,
  COUNT(*) AS row_count
FROM `catalog`.`schema`.`orders`
WHERE status IS NOT NULL
GROUP BY status
ORDER BY row_count DESC
LIMIT 25;
```

#### Empty string and inconsistent casing checks

```sql
SELECT
  SUM(CASE WHEN TRIM(status) = '' THEN 1 ELSE 0 END) AS empty_string_count,
  COUNT(DISTINCT status) AS raw_distinct_count,
  COUNT(DISTINCT LOWER(TRIM(status))) AS normalized_distinct_count
FROM `catalog`.`schema`.`orders`;
```

#### Join key uniqueness and overlap

```sql
SELECT
  COUNT(*) AS left_rows,
  COUNT(DISTINCT customer_id) AS left_distinct_customer_id
FROM `catalog`.`schema`.`orders`;

SELECT
  COUNT(*) AS right_rows,
  COUNT(DISTINCT customer_id) AS right_distinct_customer_id
FROM `catalog`.`schema`.`customers`;

SELECT
  COUNT(DISTINCT o.customer_id) AS overlapping_customer_ids
FROM `catalog`.`schema`.`orders` o
JOIN `catalog`.`schema`.`customers` c
  ON o.customer_id = c.customer_id;
```

#### Metric View inspection

```sql
DESCRIBE EXTENDED `catalog`.`schema`.`sales_metrics` AS JSON;
```

Metric View example SQL should use `MEASURE()`:

```sql
SELECT
  order_month,
  MEASURE(total_revenue) AS total_revenue
FROM `catalog`.`schema`.`sales_metrics`
GROUP BY ALL
ORDER BY order_month;
```

For mixed Metric View + table/view SQL, prefer a CTE:

```sql
WITH mv AS (
  SELECT
    customer_id,
    MEASURE(total_revenue) AS total_revenue
  FROM `catalog`.`schema`.`sales_metrics`
  GROUP BY ALL
)
SELECT
  c.customer_name,
  mv.total_revenue
FROM mv
JOIN `catalog`.`schema`.`customers` c
  ON mv.customer_id = c.customer_id;
```

### 6.2 How profiling should influence the plan

Use profile results to drive these choices:

| Profile finding | Genie config implication |
|---|---|
| High null rate | Mention in data quality notes; avoid using as primary filter unless business-critical. |
| Constant/all-null column | Exclude or warn. |
| Technical/ETL column | Exclude by default unless user asks for operational debugging. |
| Low-cardinality business status/category | Good candidate for filter snippet, sample questions, and format assistance. |
| Named business entity column | Candidate for entity matching if values are not too high-cardinality and are useful for lookup. |
| Date/time range | Use in sample questions and freshness notes. |
| Measurable numeric field | Candidate for measure snippet or Metric View measure. |
| Repeated real values | Use in example SQL and benchmark questions; do not invent categories. |
| Weak join overlap | Avoid join spec or mark as unresolved. |
| Clear many-to-one key | Add join spec with relationship annotation and business comment. |

## 7. Readiness assessment rubric

Add this rubric to `data-profiling.md` or a new `references/readiness.md`.

Recommended score: 0-100.

### 7.1 Source quality, 25 points

- 10: Focused and relevant source set
- 5: Source types are known and accessible
- 5: Table/Metric View grain is known
- 5: Data volume and freshness are known

### 7.2 Semantic quality, 25 points

- 10: Table/Metric View descriptions explain business purpose
- 10: Important columns have business descriptions and synonyms
- 5: Domain terms and ambiguous terms are defined

### 7.3 Queryability, 25 points

- 10: Measures/dimensions/filter fields are clear
- 5: Time columns and default date behavior are clear
- 5: Joins have evidence and relationship direction
- 5: Metric View syntax requirements are known when Metric Views are used

### 7.4 Evaluation readiness, 25 points

- 10: At least 8 validated example SQLs
- 10: At least 10 validated benchmarks; target 30 for optimization readiness
- 3: Sample questions cover key user intents
- 2: Known limitations are documented

Status mapping:

- `ready`: score >=80 and no blockers
- `needs_user_input`: score >=60 with missing definitions or ambiguous business rules
- `needs_more_data`: score >=40 with missing profiles, weak join evidence, or unvalidated SQL
- `draft_only`: score <40 or no data access/profile evidence

## 8. Plan generation guidance

Codex should add plan-generation guidance to both skills and references.

A strong plan should be organized into five sections, mirroring the reference agent’s decomposition but adapted for a skill:

1. **Sources and columns**
   - selected tables/views/Metric Views
   - descriptions
   - column configs
   - exclusions
   - format assistance/entity matching recommendations

2. **User-facing guidance**
   - one concise text instruction
   - domain vocabulary
   - disambiguation rules
   - data quality notes
   - hard constraints

3. **Example SQLs**
   - 8-15 validated examples
   - uses fully qualified identifiers
   - uses real values from profiles or requirements
   - demonstrates measures, filters, joins, time windows, and Metric View syntax where applicable

4. **Benchmarks**
   - at least 10 validated benchmarks for initial readiness
   - target 30 when the user wants evaluation/optimization readiness
   - no verbatim copying from example SQLs
   - each has one SQL answer

5. **Analytics scaffolding**
   - join specs
   - measures
   - filters
   - expressions
   - snippets that help Genie generate consistent SQL

The skill can ask the model to draft these sections, but scripts should validate counts, provenance, and structure.

## 9. Validation and testing plan

### 9.1 Unit tests to add

Create a test directory if one does not already exist:

```text
external-agent/create-genie-space/tests/
```

Suggested tests:

```text
test_generate_inspection_sql.py
  - generated SQL contains only read-only statements
  - fully qualified identifiers are quoted correctly
  - Metric View inspection SQL is emitted when requested
  - search mode emits table/column/comment search SQL

test_summarize_profile_results.py
  - parses JSON result fixtures
  - parses CSV result fixtures
  - flags all-null, constant, high-null, empty string, and casing issues
  - recommends exclusions for technical/ETL columns
  - preserves evidence instead of inventing descriptions

test_validate_plan.py
  - fails missing required sections
  - warns for selected sources without profile evidence
  - fails unvalidated SQL in strict mode
  - flags invented SQL literals not present in profiles or requirements
  - requires evidence on joins
  - warns for weak example/benchmark counts
  - enforces Metric View SQL rules

test_build_space_from_plan.py
  - deterministic IDs are stable across runs
  - output is version 2
  - arrays are sorted
  - one text instruction is emitted
  - excluded columns and v2 entity/format fields compile correctly
  - output passes validate_space_json.py

test_validate_space_json.py
  - keep existing coverage if present
  - add cases for text instruction length, SQL in text instructions, Metric View SQL, direct MV joins, duplicate benchmark/example content, entity matching without format assistance
```

### 9.2 Golden fixtures

Add fixture files:

```text
external-agent/create-genie-space/tests/fixtures/minimal_valid_plan.json
external-agent/create-genie-space/tests/fixtures/minimal_profile_summary.json
external-agent/create-genie-space/tests/fixtures/minimal_serialized_space.json
external-agent/create-genie-space/tests/fixtures/bad_unvalidated_sql_plan.json
external-agent/create-genie-space/tests/fixtures/bad_metric_view_sql_space.json
```

### 9.3 Suggested commands for Codex to run

```bash
python external-agent/create-genie-space/scripts/validate_space_json.py \
  external-agent/create-genie-space/tests/fixtures/minimal_serialized_space.json

python external-agent/create-genie-space/scripts/validate_plan.py \
  external-agent/create-genie-space/tests/fixtures/minimal_valid_plan.json \
  --profile-summary external-agent/create-genie-space/tests/fixtures/minimal_profile_summary.json \
  --strict

pytest external-agent/create-genie-space/tests
```

If the repo does not already use `pytest`, Codex can either add a minimal test dependency note or use `python -m unittest`.

## 10. Codex task brief

Use this section directly as the implementation prompt.

### Task 1: Baseline scan

Inspect the current repo before editing:

```bash
find external-agent/create-genie-space -maxdepth 3 -type f | sort
find genie-code/create-genie-space -maxdepth 3 -type f | sort
sed -n '1,220p' external-agent/create-genie-space/SKILL.md
sed -n '1,260p' genie-code/create-genie-space/SKILL.md
sed -n '1,260p' external-agent/create-genie-space/references/creation-workflow.md
sed -n '1,260p' external-agent/create-genie-space/scripts/validate_space_json.py
```

Preserve existing safety language. Do not remove the current read-only, no-live-API-without-request, no-unvalidated-benchmarks, and no-invented-definitions rules.

### Task 2: Update skill workflows

Edit:

```text
external-agent/create-genie-space/SKILL.md
genie-code/create-genie-space/SKILL.md
```

Add the staged workflow:

```text
requirements -> discovery -> profiling -> readiness -> plan -> config -> validation -> package/live creation -> post-creation evaluation
```

Make `plan` a required intermediate artifact unless the user explicitly asks for a quick draft.

### Task 3: Add references

Add:

```text
external-agent/create-genie-space/references/data-profiling.md
external-agent/create-genie-space/references/plan-schema.md
genie-code/create-genie-space/references/data-profiling.md
genie-code/create-genie-space/references/plan-schema.md
```

Update:

```text
external-agent/create-genie-space/references/creation-workflow.md
external-agent/create-genie-space/references/best-practices-checklist.md
external-agent/create-genie-space/references/space-schema.md
```

For the Genie Code distribution, either add equivalent references if its folder already has a references directory, or add concise inline references in `SKILL.md` if the distribution is intentionally smaller. Prefer mirrored references for consistency.

### Task 4: Add profiling and planning scripts

Add original implementations:

```text
external-agent/create-genie-space/scripts/generate_inspection_sql.py
external-agent/create-genie-space/scripts/summarize_profile_results.py
external-agent/create-genie-space/scripts/validate_plan.py
external-agent/create-genie-space/scripts/build_space_from_plan.py
external-agent/create-genie-space/scripts/build_create_space_payload.py
```

Scripts should use only the Python standard library unless the repo already has dependency management that supports more packages.

### Task 5: Extend config validator

Extend:

```text
external-agent/create-genie-space/scripts/validate_space_json.py
```

Add missing warnings/checks from this plan. Keep compatibility with the existing CLI. Add `--report-json` if practical.

### Task 6: Add tests and fixtures

Add fixtures and tests for the scripts and validator. Include at least:

- valid minimal plan
- valid minimal profile summary
- generated serialized space that passes validator
- invalid unvalidated SQL plan
- invalid Metric View SQL config
- invalid join annotation
- invented literal example if `validate_plan.py` supports literal provenance checks

### Task 7: Verify the end-to-end external-agent path

A successful dry run should be possible without Databricks credentials:

```bash
python external-agent/create-genie-space/scripts/generate_inspection_sql.py \
  --catalog main \
  --schema sales \
  --objects orders customers \
  --output /tmp/inspection.sql

python external-agent/create-genie-space/scripts/validate_plan.py \
  external-agent/create-genie-space/tests/fixtures/minimal_valid_plan.json \
  --profile-summary external-agent/create-genie-space/tests/fixtures/minimal_profile_summary.json \
  --strict

python external-agent/create-genie-space/scripts/build_space_from_plan.py \
  external-agent/create-genie-space/tests/fixtures/minimal_valid_plan.json \
  --output /tmp/serialized_space.json

python external-agent/create-genie-space/scripts/validate_space_json.py \
  /tmp/serialized_space.json

python external-agent/create-genie-space/scripts/build_create_space_payload.py \
  --serialized-space /tmp/serialized_space.json \
  --title "Example Sales Space" \
  --description "Example dry-run payload" \
  --warehouse-id "0000000000000000" \
  --parent-path "/Users/example@example.com" \
  --output /tmp/create_space_payload.json
```

## 11. Acceptance criteria

The change is complete when all of these are true:

1. Both `create-genie-space` skills require profiling/readiness/planning before final config, or explicitly label missing evidence as draft mode.
2. The external-agent version has deterministic helper scripts for inspection SQL generation, profile summary normalization, plan validation, plan-to-config compilation, and API payload packaging.
3. Existing safety guarantees remain intact: no write SQL, no live API without explicit request, no unvalidated benchmark SQL, no invented metric definitions.
4. `validate_space_json.py` still works with its existing CLI and includes the enhanced best-practice checks.
5. A new `plan.json` schema exists and is referenced by both skill distributions.
6. A new `data-profiling.md` reference exists and explains how profiling evidence maps to Genie configuration choices.
7. Metric View guidance remains explicit: use `MEASURE()`, avoid `SELECT *`, and use CTEs for mixed Metric View + table/view SQL.
8. Tests or fixture-based smoke checks demonstrate the end-to-end dry run without requiring Databricks credentials.
9. Final agent output includes paths to the plan, serialized space JSON, API payload when created, validation report, warnings, and unresolved questions.
10. Generated plans and configs can distinguish `ready`, `needs_user_input`, `needs_more_data`, and `draft_only` states.

## 12. Non-goals

Do not add these in the first implementation pass:

- A full web application.
- Server-sent event streaming.
- Long-running session storage.
- Automatic live Databricks API calls by default.
- Copying source code from the reference repo.
- Automatic DDL, table creation, Metric View creation, or permission changes.

The reference app includes app-level features such as streaming and persisted sessions. The skill repo should adapt the agentic workflow, not the application architecture. Use filesystem artifacts to capture intermediate state instead.

## 13. Suggested final user-facing output format for the improved skill

When the improved skill creates or drafts a space, its final answer should look like this:

```markdown
## Genie Space draft: <title>

Status: ready | needs_user_input | needs_more_data | draft_only

Artifacts:
- Requirements: `genie_workspace/<slug>/requirements.md`
- Inspection SQL: `genie_workspace/<slug>/inspection.sql`
- Profile summary: `genie_workspace/<slug>/profile_summary.json`
- Readiness report: `genie_workspace/<slug>/readiness.md`
- Plan: `genie_workspace/<slug>/plan.json`
- Serialized space: `genie_workspace/<slug>/serialized_space.json`
- API payload: `genie_workspace/<slug>/create_space_payload.json`
- Validation report: `genie_workspace/<slug>/validation_report.md`

Validation:
- Errors: <n>
- Warnings: <n>
- SQL validation: <validated_count>/<total_count>

Main assumptions:
- ...

Unresolved questions:
- ...

Recommended next step:
- Review unresolved questions, then run or re-run benchmarks before expanding the source scope.
```

## 14. Priority order

Implement in this order:

1. Skill workflow and reference updates.
2. `plan-schema.md` and `data-profiling.md`.
3. `validate_plan.py`.
4. `generate_inspection_sql.py`.
5. `build_space_from_plan.py`.
6. `build_create_space_payload.py`.
7. `summarize_profile_results.py`.
8. `validate_space_json.py` enhancements.
9. Tests and fixtures.

Rationale: the skill behavior and plan validation create the main quality improvement even before full profile parsing is implemented. The profile summarizer can be incremental because users and agents can manually author `profile_summary.json` in the early version.

