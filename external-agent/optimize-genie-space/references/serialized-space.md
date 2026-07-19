# Genie Serialized Space Editing

Reference docs:

- Create/select a Genie space: https://docs.databricks.com/aws/en/genie/conversation-api?language=Create+a+new+space#create-or-select-a-genie-space
- Use/update an existing Genie space: https://docs.databricks.com/aws/en/genie/conversation-api?language=Use+an+existing+space#create-or-select-a-genie-space
- `serialized_space` schema and validation: https://docs.databricks.com/aws/en/genie/conversation-api?language=Use+an+existing+space#understanding-the-serialized_space-field

## Local File Format

Keep files in `genie_configs/` as normal, pretty JSON:

```text
genie_configs/<space_id>_v0.json
genie_configs/<space_id>_v1.json
genie_configs/<space_id>_vtest.json
```

The local file should contain only the decoded `serialized_space` object, not the outer API response.

Genie spaces can be backed by `data_sources.tables`, `data_sources.metric_views`, or both serialized collections. Treat metric views as first-class Genie data sources: their identifiers are three-part Unity Catalog names, and their configs can carry descriptions and column configs like tables. This workflow may tune serialized-space metadata for existing metric views, but it must not create, alter, export, or mutate Unity Catalog metric views.

Validate syntax before building an API request:

```bash
jq empty genie_configs/<space_id>_vtest.json
```

## API Request Shape

`serialized_space` must be sent to Databricks as an escaped JSON string inside the request body. Use `jq --rawfile` so the local editable JSON is wrapped correctly.

Create a request body:

```bash
CONFIG=genie_configs/<space_id>_v<version>.json
REQUEST=/tmp/genie_create_space.json

jq -n \
  --arg title "<Space Title>" \
  --arg parent_path "/Workspace/Users/<username>" \
  --arg warehouse_id "<warehouse_id>" \
  --rawfile serialized_space "$CONFIG" \
  '{
    title: $title,
    parent_path: $parent_path,
    warehouse_id: $warehouse_id,
    serialized_space: $serialized_space
  }' > "$REQUEST"
```

Update a request body:

```bash
CONFIG=genie_configs/<space_id>_v<version>.json
REQUEST=/tmp/genie_update_space.json

jq -n \
  --rawfile serialized_space "$CONFIG" \
  '{ serialized_space: $serialized_space }' > "$REQUEST"
```

## Databricks CLI Commands

Create a new Genie space:

```bash
databricks api post /api/2.0/genie/spaces --json @/tmp/genie_create_space.json -o json
```

Update an existing Genie space:

```bash
SPACE_ID=<space_id>
databricks api patch "/api/2.0/genie/spaces/${SPACE_ID}" --json @/tmp/genie_update_space.json -o json
```

Add `-p <profile>` to any CLI command when the user has specified a non-default profile.

## Schema Checklist

Top-level fields:

- `version`: required; use `2` for new spaces.
- `config.sample_questions`: optional examples shown to users.
- `data_sources.tables`: table or view configs. Each `identifier` must use a three-part Unity Catalog name.
- `data_sources.metric_views`: metric view configs, same shape as tables and first-class data sources that may be configured instead of tables.
- `instructions.text_instructions`: high-level guidance.
- `instructions.example_question_sqls`: example questions with SQL answers.
- `instructions.sql_functions`: SQL functions available to the space.
- `instructions.join_specs`: predefined joins.
- `instructions.sql_snippets`: reusable filters, expressions, and measures.
- `benchmarks.questions`: evaluation questions with SQL ground truth.

Documented capacity limits to keep edits within: up to 30 tables/views (data sources total), 100 instructions (example SQL queries + SQL functions + text instructions), 200 knowledge-store snippets (table descriptions, join relationships, and SQL expressions), entity matching on up to 120 columns, and 500 benchmark questions per Space.

Validation rules that commonly break updates:

- All IDs must be 32-character lowercase hex strings with no hyphens.
- Required IDs include sample questions, text instructions, example SQLs, join specs, SQL snippets, and benchmark questions.
- Arrays with IDs or identifiers must be pre-sorted:
  - tables and metric views by `identifier`
  - column configs by `column_name` for both tables and metric views
  - sample questions, instructions, snippets, joins, and benchmarks by `id`
  - SQL functions by `(id, identifier)`
- IDs in `config.sample_questions` and `benchmarks.questions` must be unique across both collections.
- Instruction IDs must be unique across text instructions, example SQLs, SQL functions, join specs, and all SQL snippet types.
- `(source_identifier, column_name)` must be unique for column configs.
- Individual string elements are limited to 25,000 characters.
- Repeated fields are limited to 10,000 items.
- At most one text instruction is allowed per space.
- Join spec `sql` must have exactly two elements: the join condition using backtick-quoted aliases, then the relationship type annotation.
- Valid join relationship annotations are:
  - `--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--`
  - `--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--`
  - `--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_ONE--`
  - `--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_MANY--`
- Benchmark answers must have exactly one answer with `format` set to `SQL`.
- SQL snippet `sql` fields cannot be empty.
- By default, `validate-config --previous-config` rejects benchmark question or answer changes. For a dedicated benchmark bootstrap or repair config version only, pass `--allow-benchmark-changes` after documenting and validating the benchmark Q/A changes.

Generate a valid ID:

```bash
python3 -c "import uuid; print(uuid.uuid4().hex)"
```

After edits, run `jq empty` locally before creating or updating the space.
