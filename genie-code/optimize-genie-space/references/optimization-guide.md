# Genie Optimization Guide

Use this reference when tuning a Genie Space in Databricks-native workflows.

## Core Principle

Translate failed benchmark evidence into structured Genie context. Prefer this order:

1. Focused source scope.
2. Source, Metric View, and column descriptions.
3. Prompt matching for categorical values.
4. Raw-table join specs.
5. SQL snippets for reusable business logic.
6. Representative example SQL for complex patterns.
7. Short global text instructions.

## Benchmark Integrity

Before tuning, review whether the benchmark is useful:

- At least 30 valid question and SQL-answer pairs for benchmark-driven tuning.
- One checked SQL answer per benchmark question.
- Coverage across source selection, Metric View measures, dimensions, filters, joins, date logic, ranking, aggregation grain, and answer shapes.
- No duplicates that only change a category or date.
- No answer SQL that errors, uses stale fields, or encodes the wrong business definition.

If benchmark quality is insufficient, do a dedicated benchmark repair pass first. Do not mix benchmark repair with Genie tuning.

## Failure-To-Fix Routing

- Wrong source or field: improve source and column descriptions, synonyms, and hidden-field choices.
- Wrong Metric View measure or dimension: improve governed measure/dimension metadata or document upstream semantic model gaps.
- Wrong Metric View scope, time dimension, or grain: improve filters, time dimensions, window measures, or source joins in the semantic model.
- Wrong filter value: enable prompt matching for eligible categorical strings or add reusable filter snippets.
- Wrong join: add join specs for raw tables or recommend an upstream view/Metric View for complex relationships.
- Wrong business metric: use governed measures or SQL snippets for reusable formulas.
- Wrong time logic or answer shape: add representative example SQL after simpler surfaces are insufficient.
- Instruction conflict: move source-specific rules out of text instructions into structured surfaces.

## Text Instruction Guardrails

Use text instructions only for global behavior such as:

- fiscal calendar or timezone convention
- default clarification behavior
- universal rounding or answer presentation preference
- global data freshness caveat

Do not use text instructions for source-specific metric formulas, joins, filters, denominator rules, ranking logic, or benchmark-specific aliases.

## Regression Review

After each pass, compare per-question behavior:

- fixed questions
- regressions
- unchanged failures
- new SQL errors
- source-selection changes
- answer-shape changes

Keep a pass only when the improvement outweighs regressions and the changes remain understandable to future Space maintainers.
