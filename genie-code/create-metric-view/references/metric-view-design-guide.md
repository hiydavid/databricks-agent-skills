# Metric View Design Guide

Use this reference after the source set and business goals are known. It is based on Databricks Unity Catalog business semantics and Metric View guidance current as of June 2026.

Official Databricks references:

- Unity Catalog metric views: https://docs.databricks.com/aws/en/business-semantics/metric-views/
- Create and edit metric views: https://docs.databricks.com/aws/en/business-semantics/metric-views/create-edit
- Model metric views: https://docs.databricks.com/aws/en/business-semantics/metric-views/basic-modeling
- Joins in metric views: https://docs.databricks.com/aws/en/business-semantics/metric-views/joins
- Query metric views: https://docs.databricks.com/aws/en/business-semantics/metric-views/query
- Agent metadata: https://docs.databricks.com/aws/en/business-semantics/agent-metadata
- Materialization: https://docs.databricks.com/aws/en/business-semantics/metric-views/materialization
- YAML reference: https://docs.databricks.com/aws/en/business-semantics/metric-views/yaml-reference

## Contents

- Design Intake
- Feasibility Check
- Feature Availability
- Source Choice
- Fields
- Measures
- Filters
- Joins And Cardinality
- Agent Metadata
- Materialization
- Review Checklist

## Design Intake

Capture the business contract before drafting:

- Purpose, audience, owner, target catalog/schema/name, and expected consumers.
- 3-5 real business questions the Metric View must support.
- KPI dictionary: names, formulas, numerator, denominator, filters, grain, allowed dimensions, and examples.
- Calendar and time semantics: date columns, fiscal calendar, timezone, week/month definitions, reporting cutoffs.
- Scope rules: active records, completed orders, excluded statuses, business-unit filters, deleted/test data handling.
- Security and privacy caveats: PII, row-level filters, restricted dimensions, sensitive free text.
- Business language: display names, synonyms, abbreviations, and formatting expectations.
- Known source objects, trusted upstream views, existing Metric Views, certified datasets, and owner contacts.

If a KPI definition, filter, grain, or join is not in the data or expert inputs, ask. A plausible formula is not enough for a governed Metric View.

## Feasibility Check

Before authoring YAML, classify each KPI and question:

- **High:** required source fields, formula, filters, time field, and joins are supported by metadata/profiling or expert confirmation.
- **Medium:** answerable with caveats, uncertain labels, missing display metadata, or a user-confirmed assumption.
- **Low:** missing source, metric formula, denominator, dimension, time field, scope rule, or join evidence.

Do not present Low-confidence items as implemented. Either remove them from the draft, ask for expert input, or label the Metric View as an incomplete draft.

## Feature Availability

Treat feature availability as an environment capability check, not as a user preference. In Genie Code, inspect workspace signals, compiler feedback, and current Databricks docs where possible; do not ask the user to choose a runtime.

As of June 2026:

- Metric View feature support varies by active Databricks SQL and Databricks Runtime surface.
- YAML `version: 1.1` agent metadata requires agent-metadata support, documented for Databricks Runtime 17.3 or above and compatible Databricks SQL behavior.
- `rely.at_most_one_match: true` requires both proven uniqueness and support for the join optimization, documented for Databricks Runtime 18.1 or above and compatible Metric View environments.
- `one_to_many`, nested joins, materialization, and other advanced modeling features should be checked against current feature availability before drafting live DDL.
- If support cannot be confirmed, omit the gated syntax and list it as an optional enhancement with the required capability.

## Source Choice

Choose the smallest source shape that preserves semantics:

- Use a single trusted fact table or business view when one object contains the event or transaction grain.
- Use an existing Metric View as the source when extending governed semantics; do not reimplement its formulas.
- Use joins for dimensions that enrich the fact grain. Validate relationship direction and fanout.
- Use a SQL query source only when a bridge, prefilter, or canonical source expression is necessary and explain why a simpler source was insufficient.
- Avoid raw/staging tables unless the user explicitly wants a draft and accepts the data-quality limitations.

Metric Views can use table-like Unity Catalog assets as sources. Confirm runtime and permission prerequisites before live DDL: source `SELECT`, target catalog/schema privileges, and supported compute.

## Fields

Fields are grouping and filtering attributes. Include only fields that users need for analysis or validation.

- Prefer business names over raw codes. Convert opaque codes with `CASE` only when mapping is known.
- Include both granular and truncated time fields when users need trends and detail-level filtering, such as `Order Date`, `Order Week`, and `Order Month`.
- Keep stable IDs when they are needed for grouping, joins, drill-through, validation, or downstream filters.
- Exclude noisy ingestion metadata, raw JSON, embeddings, hashes, secret-like fields, and sensitive free text unless they are explicitly required.
- Remember that Metric View string fields can behave differently from source `CHAR`/`VARCHAR` padding; profile string filters when exact matching matters.

## Measures

Measures are governed aggregate expressions. Start with the smallest reliable measures and compose from there.

- Define atomic measures first: counts, sums, distinct counts, averages, minima, maxima, medians, or percentiles.
- Define ratio and derived measures only after the numerator and denominator are clear.
- Use filtered measures for governed subpopulations, such as revenue from completed orders, only when the filter is a business definition.
- Use `MEASURE()` for composed measures when referencing another measure in query or in supported model expressions.
- Use window measures for trailing, cumulative, period-over-period, or semiadditive behavior only when the time field, window grain, and comparison rule are explicit.
- Avoid duplicating the same formula under multiple names. Use synonyms and display names for alternate business language.

Good review questions:

- Is the measure additive across the requested dimensions?
- Does the denominator change with filters and grouping the way users expect?
- Are nulls, returns, cancellations, test rows, and negative values handled intentionally?
- Does the measure compare to a known report, dashboard, or expert-provided example?

## Filters

Use model-level `filter` only for scope that should apply to every query against the Metric View.

- Good filters: only completed transactions, only production records, exclude deleted/test data, fixed business domain scope.
- Risky filters: default date range, one user's current dashboard filter, exploratory segment selection, or anything users might reasonably toggle.
- Put optional user filters in fields, not the model-level filter.
- Explain every model-level filter in the Metric View comment or output summary.

## Joins And Cardinality

Metric View joins commonly model star or snowflake schemas. By default, joins are many-to-one dimension lookups.

- Validate many-to-one joins with constraints, distinct-count checks, row overlap checks, query history, lineage, or data-owner confirmation.
- Use `rely.at_most_one_match: true` only when the uniqueness condition genuinely holds and the active environment supports the optimization. Databricks does not validate uniqueness at runtime.
- Use `one_to_many` only for intended multi-grain metrics, such as a customer-grain source with order facts below it. Confirm runtime/version support.
- For nested one-to-many joins, watch for accidental double counting and use distinct counts where needed.
- For multiple fact tables at different grains, consider a bridge source that enumerates valid dimension combinations instead of ad hoc fanout.
- Do not expose fields from one-to-many fact branches as normal dimensions unless the Metric View feature rules allow it and the semantics are clear.

## Agent Metadata

Use YAML `version: 1.1` when the active environment supports agent metadata. Agent metadata requires Databricks Runtime 17.3 or above, or compatible Databricks SQL support, and improves AI/BI interpretation, but it must be grounded.

- Add `comment` for the Metric View, important fields, and measures where supported by the YAML reference.
- Explain source choices, model-level filters, joins, and other non-obvious assumptions in the top-level Metric View comment or output summary unless current syntax explicitly supports metadata on that object.
- Add `display_name` when the technical `name` is not the business label.
- Add `synonyms` for real business terms, abbreviations, and common phrasing. Do not pad synonyms with guesses.
- Add `format` for currency, percentages, dates, decimals, and large numbers when the business format is known.
- Keep synonyms under control; too many broad synonyms can make AI source selection less precise.

## Materialization

Treat materialization as an optimization option, not part of the default semantic model.

Recommend it only when:

- The Metric View has repeated workload patterns or known dashboard/Genie/alert queries.
- Query history or benchmarks show expensive aggregations that are stable enough to precompute.
- Refresh cost, freshness, permissions, and maintenance ownership are acceptable.
- The workspace supports Metric View materialization. As of June 2026, materialized Metric Views are Public Preview and use serverless compute.
- Any `relaxed` query rewrite behavior is acceptable for the business freshness and determinism requirements.

Do not add materialization to hide an unclear model or an unvalidated join.

## Review Checklist

Before presenting live DDL, confirm:

- The Metric View has a clear owner, audience, and source grain.
- Every requested KPI is High or Medium confidence, with Medium assumptions stated.
- Low-confidence KPIs are excluded or explicitly marked as blockers.
- Measures are aggregate expressions and have comments.
- Fields are useful for grouping/filtering and avoid noisy or sensitive data.
- Model-level filters are governed scope rules, not default exploration filters.
- Joins have validated cardinality; `rely` is used only with proof or confirmation.
- Feature-gated syntax is included only when active environment support is confirmed.
- Representative queries list fields and use `MEASURE()` for measures.
- The proposed DDL target is fully qualified and approved before execution.
- Downstream Genie Spaces can attach the Metric View without duplicating its formulas.
