# Metric Views In Genie Spaces

Use this reference when a new Genie Space should be based on existing Databricks Metric Views, either alone or alongside tables/views.

Source docs:

- Databricks Genie setup: https://docs.databricks.com/aws/en/genie/set-up
- Databricks Genie best practices: https://docs.databricks.com/aws/en/genie/best-practices
- Query Metric Views: https://docs.databricks.com/aws/en/business-semantics/metric-views/query
- Agent metadata in Metric Views: https://docs.databricks.com/aws/en/business-semantics/agent-metadata
- Model Metric Views: https://docs.databricks.com/aws/en/business-semantics/metric-views/basic-modeling

## Scope

This skill attaches existing Metric Views to `serialized_space.data_sources.metric_views`. Do not create or alter Metric Views unless the user explicitly changes the task scope.

Metric Views are useful in Genie Spaces because they pre-define metrics, dimensions, aggregations, and business semantics. Prefer Metric Views when they already encode the KPIs and dimensions users need.

## Discovery

Inspect the Metric View definition:

```sql
DESCRIBE TABLE EXTENDED <catalog.schema.metric_view_name> AS JSON;
```

Review:

- Source data.
- Dimensions available for grouping and filtering.
- Measures available for aggregation.
- Built-in filters and joins.
- Agent metadata: display names, synonyms, and formatting.

Validate representative queries:

```sql
SELECT
  <dimension_name>,
  MEASURE(<measure_name>) AS <measure_alias>
FROM <catalog>.<schema>.<metric_view>
GROUP BY ALL
LIMIT 20;
```

Do not use `SELECT *` for Metric View examples or benchmarks. Measures must be evaluated with `MEASURE()`.

## Authoring Serialized Space JSON

For a Metric View-only space:

```json
{
  "data_sources": {
    "tables": [],
    "metric_views": [
      {
        "id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        "identifier": "catalog.schema.metric_view_name",
        "description": ["Business description of the Metric View, key measures, key dimensions, and scope."]
      }
    ]
  }
}
```

For a mixed space:

- Put standard tables/views in `data_sources.tables`.
- Put Metric Views in `data_sources.metric_views`.
- Do not add underlying source tables for a Metric View unless users need questions outside the Metric View's dimensions/measures.
- Avoid duplicating Metric View measure formulas as Genie SQL snippets. Prefer the Metric View's semantic definition.
- Add SQL snippets only for concepts not already modeled in the Metric View or for cross-source usage patterns.

## Example SQL And Benchmarks

Metric View SQL examples and benchmark answers should:

- Explicitly select dimensions.
- Wrap measures with `MEASURE()`.
- Use `GROUP BY ALL` or explicit grouping when dimensions are selected.
- Use Metric View display names and aliases consistently.
- Avoid `SELECT *`.

For mixed Metric View plus table/view queries, Metric Views cannot be joined directly to other tables at query time. Use a CTE:

```sql
WITH metric_result AS (
  SELECT
    <join_dimension>,
    MEASURE(<measure_name>) AS <measure_alias>
  FROM <catalog>.<schema>.<metric_view>
  GROUP BY <join_dimension>
)
SELECT
  d.<attribute>,
  metric_result.<measure_alias>
FROM metric_result
JOIN <catalog>.<schema>.<dimension_table> d
  ON metric_result.<join_dimension> = d.<join_key>;
```

## Quality Checks

For Metric View-only or mixed spaces, verify:

- At least one data source exists across `tables` and `metric_views`.
- Total attached tables/views/Metric Views stays within the current Genie limit of 30.
- Every Metric View has a clear description in `data_sources.metric_views`.
- Metric View agent metadata includes display names and synonyms for key dimensions and measures.
- Sample questions cover the Metric View's most important dimensions and measures.
- Example SQLs and benchmarks use valid Metric View SQL syntax with `MEASURE()`.
- Mixed examples use the CTE join pattern.
