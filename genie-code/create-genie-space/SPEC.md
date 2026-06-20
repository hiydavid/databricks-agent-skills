# Genie Space SPEC.md Template

Use this template before invoking the `create-genie-space` skill when the customer can provide data artifacts before a working session. Use one `SPEC.md` per Genie Space.

This spec captures only customer decisions and business context. Genie Code should derive schema details, profiling, joins, prompt matching, hidden technical fields, readiness, and proposed Genie Space configuration from the artifacts and approved read-only inspection.

Unknowns may be marked `TBD`. Use fully qualified Unity Catalog identifiers (`catalog.schema.object`) whenever known. Do not paste secrets, tokens, credentials, sensitive free text, or unnecessary raw sample data.

## 1. Artifact Package

Provide these before the workshop:

- `DESCRIBE EXTENDED` output for every table, view, and Metric View.
- Metric View definition export or copy for every Metric View.
- Optional: sample rows for tables and standard views.
- Optional: existing dashboards, SQL, notebooks, known-good answers, data dictionaries, or business glossaries.

Missing artifacts or limitations:

- TBD

## 2. Space Goal

| Field | Customer input |
| --- | --- |
| Draft Space title | TBD |
| Owner/requester | TBD |
| SME for business questions | TBD |
| Intended audience | TBD |
| Primary purpose | TBD |
| Success criteria | TBD |
| In scope | TBD |
| Out of scope | TBD |
| Draft only or live creation after approval? | draft only / live creation after approval |

## 3. Sources And Authority

List the candidate sources and the business reason each belongs. Do not summarize columns, measures, or dimensions here; Genie Code derives those from the artifacts.

| Source identifier | Type | Why include it? | Authoritative for | Owner/SME | Caveats |
| --- | --- | --- | --- | --- | --- |
| `catalog.schema.object` | table / view / Metric View | TBD | TBD | TBD | TBD |

Source preference rules:

- If sources overlap, which one should Genie prefer?
- Should raw/detail tables be exposed alongside Metric Views? If yes, for what questions?
- Are any sources staging, deprecated, incomplete, or included only for lookup/enrichment?

## 4. Question And Benchmark Inputs

Provide real analyst questions from customer users or SMEs. Genie Code uses 3-5 questions to understand what the Space is about and derive the initial Space design.

For benchmark analysis, provide at least 15 questions; about 30 is ideal. If fewer than 15 questions are provided, Genie Code can still draft the Space, but benchmark analysis should be treated as incomplete.

Do not require the customer to provide benchmark SQL unless they already have known-good SQL, dashboard logic, or expected results.

| # | Benchmark question | Optional ground-truth SQL | Evaluation notes |
| --- | --- | --- | --- |
| 1 | TBD | TBD | TBD |
| 2 | TBD | TBD | TBD |
| 3 | TBD | TBD | TBD |

Repeat rows as needed.

## 5. Business Semantics

Fill only definitions or conventions that are not already governed by a Metric View, or that require confirmation.

- KPI definitions or formulas:
- Fiscal calendar and timezone:
- Default date range or comparison period:
- Default filters, exclusions, or active/inactive logic:
- Ambiguous terms, acronyms, statuses, or segments:
- Currency, units, rounding, or formatting expectations:

## 6. Security And Caveats

List business-sensitive or policy details the artifacts may not reveal.

- PII or sensitive business fields:
- Fields technically available but inappropriate for the audience:
- Row-level security, masks, or dynamic view caveats:
- Known data quality or freshness issues:
- Required caveats Genie should surface to users:

## 7. Validation And Approval

- Final approver:
- Approval criteria:
- Target workspace/path, if live creation is approved:

No live Genie Space creation or update should happen until the customer explicitly approves the proposed configuration in Databricks.

## Genie Code Should Derive

Do not ask the customer to pre-fill these unless they already have the answer: source profiling, row counts, grain, freshness, column descriptions, Metric View measure/dimension review, prompt/entity matching candidates, hidden technical fields, join evidence, SQL snippets, example SQL, text-instruction justification, benchmark SQL, and per-question readiness.
