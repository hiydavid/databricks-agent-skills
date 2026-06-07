# Genie Space SPEC.md Template

Use this template before invoking the `create-genie-space` skill when you want a spec-driven Genie Space creation flow.

Unknowns may be marked `TBD`. Use fully qualified Unity Catalog identifiers (`catalog.schema.object`) whenever known. Do not paste secrets, tokens, credentials, sensitive free text, or unnecessary raw sample data.

This spec is a design input, not approval to create or update a live Genie Space. Genie Code should complete the profiling and readiness sections only with read-only workspace evidence.

## Space Brief

| Field | Value |
| --- | --- |
| Draft Space title | TBD |
| Owner/requester | TBD |
| Intended audience | TBD |
| Primary purpose | TBD |
| Success criteria | TBD |
| Expected usage mode | Exploratory Q&A / executive reporting / operational triage / benchmarked validation / mixed |
| In-scope questions | TBD |
| Out-of-scope questions | TBD |
| Security or access caveats | TBD |

## Priority Business Questions

Capture 3-5 realistic questions the audience will ask. Genie Code fills readiness confidence after profiling.

### Question 1

- Business question:
- Expected answer shape: single number / table / trend / ranking / comparison / narrative synthesis / other
- Required measures:
- Required dimensions or groupings:
- Required filters:
- Date, fiscal, or timezone logic:
- Candidate source hints:
- Benchmark needed: none / SQL answer / Agent evaluation notes / both
- Readiness confidence (Genie Code fills): High / Medium / Low
- Readiness notes (Genie Code fills):

### Question 2

- Business question:
- Expected answer shape:
- Required measures:
- Required dimensions or groupings:
- Required filters:
- Date, fiscal, or timezone logic:
- Candidate source hints:
- Benchmark needed: none / SQL answer / Agent evaluation notes / both
- Readiness confidence (Genie Code fills): High / Medium / Low
- Readiness notes (Genie Code fills):

### Question 3

- Business question:
- Expected answer shape:
- Required measures:
- Required dimensions or groupings:
- Required filters:
- Date, fiscal, or timezone logic:
- Candidate source hints:
- Benchmark needed: none / SQL answer / Agent evaluation notes / both
- Readiness confidence (Genie Code fills): High / Medium / Low
- Readiness notes (Genie Code fills):

### Optional Question 4

- Business question:
- Expected answer shape:
- Required measures:
- Required dimensions or groupings:
- Required filters:
- Date, fiscal, or timezone logic:
- Candidate source hints:
- Benchmark needed: none / SQL answer / Agent evaluation notes / both
- Readiness confidence (Genie Code fills): High / Medium / Low
- Readiness notes (Genie Code fills):

### Optional Question 5

- Business question:
- Expected answer shape:
- Required measures:
- Required dimensions or groupings:
- Required filters:
- Date, fiscal, or timezone logic:
- Candidate source hints:
- Benchmark needed: none / SQL answer / Agent evaluation notes / both
- Readiness confidence (Genie Code fills): High / Medium / Low
- Readiness notes (Genie Code fills):

## Candidate Data Sources

Start with a focused set, ideally 5 or fewer objects. Include tables, standard views, and existing Metric Views only.

| Identifier | Type | Business role | Inclusion reason | Known grain | Freshness or SLA | Owner | Caveats |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `catalog.schema.object` | table / view / Metric View | TBD | TBD | TBD | TBD | TBD | TBD |

### Metric View Details

Complete this section for each candidate Metric View.

#### `catalog.schema.metric_view`

- Governed measures:
- Governed dimensions:
- Built-in filters:
- Time dimensions:
- Display names and synonyms:
- Formatting metadata:
- Known query pattern using `MEASURE()`:
- Upstream semantic gaps:
- Should underlying source tables also be attached? no / yes, because:

### Table And Standard View Details

Complete this section for each candidate table or standard view.

#### `catalog.schema.table_or_view`

- Business description:
- Grain:
- Primary time columns:
- Candidate key columns:
- Candidate measures:
- Useful dimensions and filters:
- Likely joins:
- Join evidence or confirmation needed:
- Columns to hide from Genie:
- Sensitive, noisy, or low-value fields:
- Data quality caveats already known:

## Business Semantics

### KPI And Metric Definitions

| Name | Definition or formula | Numerator | Denominator | Exclusions | Governed by Metric View? | Confirmation status |
| --- | --- | --- | --- | --- | --- | --- |
| TBD | TBD | TBD | TBD | TBD | yes / no | confirmed / needs confirmation / TBD |

### Calendar, Time, And Defaults

- Fiscal calendar:
- Timezone:
- Default date range:
- Default filters:
- Default currency or units:
- Rounding or formatting conventions:

### Terminology

| User term | Meaning | Maps to source, column, measure, or value | Preferred interpretation | Confirmation status |
| --- | --- | --- | --- | --- |
| TBD | TBD | TBD | TBD | confirmed / needs confirmation / TBD |

### Ambiguities To Resolve

- Ambiguous metric definitions:
- Ambiguous joins:
- Ambiguous filters or segment definitions:
- Terms that may mean different things to different users:

## Genie Space Design Decisions

Genie Code should prefer structured configuration surfaces over broad text instructions.

### Data Sources To Attach

| Identifier | Attach? | Reason | Questions supported | Limitations |
| --- | --- | --- | --- | --- |
| `catalog.schema.object` | yes / no / TBD | TBD | TBD | TBD |

### Metadata And Synonyms

- Space or source descriptions to add:
- Column descriptions to add:
- Metric View data-source descriptions to add in the Genie Space:
- Column or measure synonyms:
- Display-name conventions:

### Prompt Matching And Entity Matching

List categorical string fields users are likely to mention directly. Genie Code should verify eligibility, cardinality, and useful values before enabling.

| Source | Column | User-facing values or terms | Enable format assistance? | Enable entity matching? | Evidence |
| --- | --- | --- | --- | --- | --- |
| TBD | TBD | TBD | yes / no / TBD | yes / no / TBD | Genie Code fills |

### Hidden Fields

List ingestion metadata, audit fields, hashes, raw JSON, embeddings, secrets, sensitive free text, unused PII, and other fields that should be hidden from end-user context.

| Source | Column | Reason to hide | Confirmed? |
| --- | --- | --- | --- |
| TBD | TBD | TBD | yes / no / TBD |

### Joins

Only include joins supported by constraints, profiling, query history, naming evidence, or user confirmation.

| Left source and key | Right source and key | Relationship | Business meaning | Evidence required or observed |
| --- | --- | --- | --- | --- |
| TBD | TBD | many-to-one / one-to-many / one-to-one / many-to-many / TBD | TBD | TBD |

### SQL Snippets, Examples, Functions, And Text Instructions

- Reusable filter snippets:
- Reusable expression snippets:
- Reusable measure snippets:
- Example SQL patterns needed for complex questions:
- SQL functions to expose, if any:
- Text instructions needed for global behavior only:

If text instructions are proposed, include:

```markdown
## Text Instruction Justification

- Exact instruction text:
- Why structured surfaces were insufficient:
- Intended global behavior:
- Possible overreach or regression risk:
- How the instruction will be reviewed or validated:
```

## Sample Questions And Benchmarks

### Sample Questions

Sample questions should be user-facing starting points, not copied benchmark tests.

1. TBD
2. TBD
3. TBD
4. TBD
5. TBD

### Benchmark Candidates

Benchmark literals, parameter defaults, and expected SQL should use profiled values. Do not invent statuses, regions, categories, dates, or IDs. Do not copy benchmark answer SQL into example SQL.

| Question | Target mode | Expected answer strategy | Sources and logic covered | Validation status |
| --- | --- | --- | --- | --- |
| TBD | SQL answer / Agent evaluation notes / both | TBD | TBD | not validated / EXPLAIN checked / read-only executed |

## Profiling And Readiness Evidence

Genie Code fills this section during read-only inspection.

### Read-Only Validation Performed

- Metadata inspected:
- SQL commands used:
- Queries executed or explained:
- System lineage/query history checked:
- Limitations:

### Source Profiling Summary

| Source | Row count | Grain | Freshness/date range | Key quality notes | Useful categorical values | Sensitive/noisy fields |
| --- | --- | --- | --- | --- | --- | --- |
| TBD | Genie Code fills | Genie Code fills | Genie Code fills | Genie Code fills | Genie Code fills | Genie Code fills |

### Join Evidence

| Join | Evidence type | Overlap/cardinality result | Confidence | Caveats |
| --- | --- | --- | --- | --- |
| TBD | constraint / profiling / query history / user confirmation | Genie Code fills | High / Medium / Low | TBD |

### Metric View Validation

| Metric View | Measures tested | Dimensions tested | `MEASURE()` query status | Semantic gaps |
| --- | --- | --- | --- | --- |
| TBD | Genie Code fills | Genie Code fills | not tested / EXPLAIN checked / read-only executed | TBD |

### Per-Question Readiness

| Question | Semantic coverage | Data quality and freshness | Modelability | GenAI context readiness | Overall confidence | Gaps or assumptions |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | High / Medium / Low | High / Medium / Low | High / Medium / Low | High / Medium / Low | High / Medium / Low | TBD |
| Q2 | High / Medium / Low | High / Medium / Low | High / Medium / Low | High / Medium / Low | High / Medium / Low | TBD |
| Q3 | High / Medium / Low | High / Medium / Low | High / Medium / Low | High / Medium / Low | High / Medium / Low | TBD |

## Approval Checklist

Before proposing live Genie Space creation or update, confirm:

- [ ] Source set is focused and each attached object supports the Space purpose.
- [ ] Each priority business question is High or Medium readiness, or Low-confidence limitations are explicit.
- [ ] Missing metric definitions are confirmed or marked as assumptions.
- [ ] Missing join relationships are confirmed or marked as assumptions.
- [ ] Fiscal calendar, timezone, and default filters are confirmed or marked as assumptions.
- [ ] Read-only validation was performed for examples, joins, snippets, and SQL benchmarks where applicable.
- [ ] Benchmark SQL uses validated, concrete values and is not copied into sample questions or examples.
- [ ] Text instructions, if any, are justified as global behavior that structured surfaces cannot encode.
- [ ] No source data, Unity Catalog object, or Metric View mutation is required.
- [ ] No live Genie Space creation or update will occur without explicit user approval.
