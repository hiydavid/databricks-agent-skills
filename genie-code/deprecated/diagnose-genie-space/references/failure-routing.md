# Genie Failure Routing

Use this reference to classify Genie Space failures and choose the smallest useful fix. This file owns the **decision logic**; `config-review.md` owns the **static checklist**. Where a rule is defined there, this file cross-references it rather than restating it.

## Evidence To Gather

This is the canonical pre-flight inventory (the Workflow in `SKILL.md` points here).

- Access and validation limits: Space configuration visibility, Monitor visibility, generated SQL availability, Query History visibility, and whether bounded read-only SQL can run.
- Relevant table, view, and Metric View identifiers and descriptions.
- Metric View measures, dimensions, filters, joins, time dimensions, comments, display names, synonyms, and formatting.
- Table and column descriptions, synonyms, prompt matching settings, and hidden fields.
- Join specs and comments for raw tables exposed together.
- SQL expressions / knowledge-store snippets, example SQL, SQL functions, and text instructions, including conflicts, redundancy, stale assumptions, and Metric View duplication.
- Trusted assets and common/sample questions.
- Permission and governance context: Space ACLs, user `SELECT` privileges, row filters, column masks, and dynamic views.
- Similar benchmark questions, SQL answers, evaluation notes, and execution mode, if present.
- Benchmark inventory size, duplicate clusters, coverage categories, difficulty levels, and whether the set is too small, narrow, easy, redundant, or large for practical iteration.
- Monitor-tab feedback signals: thumbs up/down trends, negative ratings, `Fix it`, `Request review`, needs-review conversations, feedback comments, reviewer comments, repeated user phrasing, generated SQL or error text from reviewable conversations, and private-conversation limitations.
- Agent-mode final reports, research steps, supporting query outputs, citations, tables, charts, and assessment notes when applicable.
- Latency evidence for slow-response cases: see `Latency Pre-Routing`.
- Context-overload evidence for slow-generation cases: see `Generation Latency Or Context Overload`.
- Static config evidence from `config-review.md`, especially when query access is unavailable.
- Read-only checks for data types, categorical values, null rates, cardinality, join grain, and Metric View query behavior when needed and available.

## Config-First Routing

When SQL execution or Query History is unavailable, route from static configuration evidence first and label validation limits clearly.

- Missing, generic, overlapping, or contradictory data source descriptions: route to `Wrong Data Source Or Field`.
- Missing business terms, unclear column semantics, duplicated aliases, or exposed noisy fields: route to `Wrong Data Source Or Field`, `Wrong Filter Value`, or `Generation Latency Or Context Overload`.
- Metric formulas split across Metric Views, SQL expressions, examples, and text instructions: route to `Wrong Metric View Measure, Dimension, Scope, Or Grain`, `Business Logic Or Time Logic Error`, or `Config Conflict Or Redundancy`.
- Reusable filters, date windows, ranking logic, or grain rules encoded in long text instructions: route to `Business Logic Or Time Logic Error` or `Config Conflict Or Redundancy`.
- Conflicting, duplicate, stale, or overly specific SQL expressions and examples: route to `Business Logic Or Time Logic Error`, `Wrong Join`, or `Config Conflict Or Redundancy`.
- Excessive source count, raw/Metric View overlap, broad prompt matching, long instructions, or redundant examples: route to `Generation Latency Or Context Overload`.
- References to tables, views, or columns not attached to the Space: route to `Wrong Data Source Or Field` or `Config Conflict Or Redundancy`.
- Empty answers, per-user discrepancies, or governance-restricted data: route to `Permission, Governance, Or Data Visibility Limitation`.
- Missing citations, unsupported claims, or weak research plans in Agent mode: route to `Weak Agent-Mode Report`.
- If a likely fix depends on data values, join cardinality, freshness, row counts, or runtime timing, keep the diagnosis but set confidence to Medium or Low (see `config-review.md` → No-Query Diagnosis Mode) and name the smallest validation needed.

## Latency Pre-Routing

For slow-response complaints, first separate SQL-runtime latency from query-generation or thinking-phase latency. Gather: Chat versus Agent mode, benchmark versus ad hoc use, total response time, time before SQL appears, Agent reasoning time, final synthesis time, and Query History execution / queue / warehouse startup / scan / spill / result-fetch time; note whether the same simple question is repeatedly slow.

- If Query History shows SQL execution, queue, warehouse startup, scan, spill, or result-fetch time dominates total latency **and the generated SQL is semantically correct for the question**, stop Space-quality diagnosis and hand off to `optimize-genie-query`.
- If runtime dominates but the generated SQL is wrong (wrong source, join, grain, or filter producing slow-but-incorrect SQL), classify the underlying Genie failure and hand off to `optimize-genie-space`; do not treat it as a pure query-runtime problem.
- If SQL execution is fast but the user waits before SQL appears, during Agent reasoning, or during long final response synthesis, classify the case as `Generation Latency Or Context Overload` and recommend Space configuration cleanup through `optimize-genie-space`.
- For Agent mode, state that Agent mode can naturally take longer because it creates a plan, runs multiple queries, learns from results, and synthesizes a report. For simple deterministic questions, validate Chat mode, a trusted asset, or a concise parameterized example as the lower-latency path.
- If the latency split is unavailable, ask for or inspect Query History timing before recommending warehouse, table-layout, or Space configuration changes.

## Routing Order

1. Data source scope and descriptions.
2. Metric View semantic model and agent-facing metadata.
3. Table and column metadata.
4. Prompt matching for categorical value confusion.
5. Join specs for raw-table relationships.
6. SQL expressions for reusable business logic.
7. Example SQL for complex patterns.
8. SQL functions / trusted assets for trusted complex logic.
9. Short response-quality instructions only for global Agent-report behavior.
10. Text instructions only for global conventions.

## Conflict Resolution And Precedence

Databricks does not publicly document a strict "surface X overrides surface Y" order for Genie Spaces at query time, so do not tell the user that one surface is guaranteed to win. Conflicting guidance resolves through three documented mechanisms; use them to explain the observed symptom and to choose the repair surface.

1. Bindingness spectrum — how reliably Genie obeys a surface, strongest to weakest:
   - Trusted assets / SQL functions: return a verified answer, and when the exact text of a parameterized query is used, Genie answers deterministically from it.
   - SQL expressions (knowledge store): Genie applies the logic exactly as written when it selects the expression, rather than interpreting natural language.
   - Example SQL queries: on a close match Genie may use the query directly; on a similar question it learns from it.
   - Table and column comments and Metric View metadata: relevance-selected context, not a rule.
   - General / text instructions: soft, interpreted, global, and able to be ignored (Genie ignoring instructions is a documented failure mode). Only text instructions affect natural-language summary generation.
   This is why Databricks recommends defining logic as SQL expressions and examples and using text instructions only as a last resort, and why the Routing Order above prefers structured surfaces. It is an authoring and reliability order, not a guaranteed runtime override.
2. Relevance selection — Genie selects the most relevant context, example, and values for each prompt. A more specific, better-matching surface effectively wins because it is selected, not because of a fixed priority, so a conflict can surface as Genie choosing the other source or example.
3. Context budgets and crowding — a Space allows 100 instructions (each example SQL query, each SQL function, and the entire general-instructions block each count as one) and 200 knowledge-store snippets (table descriptions, join relationships, and SQL expressions share this). The general-instructions block counts as one slot regardless of length, and too many instructions reduce effectiveness, especially in long conversations. An overloaded or bloated surface can dilute or crowd out the guidance that should have applied, so a conflict can manifest as the correct rule being ignored.

When diagnosing a conflict, name which mechanism explains the symptom — a different surface was selected, a soft text instruction was ignored or diluted, the exact-text trusted-asset path was missed, or budget crowding — then recommend moving the rule to the most reliable surface that resolves it. When you cannot tell which surface Genie actually used, lower confidence and inspect the generated SQL.

Terminology: in Genie and Unity Catalog docs, "governance" means data-access control (ACLs, row filters, column masks), not semantic authority. A Metric View is a cleaner, more reliable semantic surface to prefer, not a documented override of conflicting comments or instructions.

Scope: this precedence picture is for Genie Spaces query-time generation. Genie Code, the environment this skill runs in, separately prioritizes workspace instructions over user instructions, and Genie One uses an ontology authority score; neither governs Genie Space SQL generation. Keep them distinct.

## Feedback Routing

Use feedback as evidence for clustering failures, not as a tuning surface. Do not recommend changing feedback, comments, review status, or conversation history as the fix.

Translate feedback patterns into the existing repair levers:

- Repeated negative feedback on the same source, Metric View, measure, dimension, filter, join, or time pattern: classify the underlying wrong source, semantic model, filter, join, business logic, or time logic failure before choosing the fix.
- Review requests with missing SQL, wrong SQL, failed SQL, or unsupported final answers: inspect the generated SQL/error and route to the smallest structured surface that would prevent the same failure.
- User comments that explain a business term, synonym, category label, KPI definition, fiscal period, or expected result shape: treat the comment as business-intent evidence and encode the durable rule in metadata, Metric View semantics, prompt matching, expressions, representative examples, or short global instructions.
- Repeated weak Agent-mode reports (missing citations, unsupported claims, thin research plans): route to `Weak Agent-Mode Report`.
- High negative-feedback volume with weak or missing benchmark coverage: recommend benchmark repair or benchmark additions before benchmark-driven tuning, and use feedback clusters to choose representative benchmark candidates.
- Feedback that contradicts passing benchmark results: check whether benchmarks are stale, too narrow, too easy, missing Agent evaluation notes, or failing to cover real user phrasing before trusting the benchmark signal.
- Canonical privacy rule: when conversations are private or Monitor details are unavailable, use only visible prompt, status, rating, timestamp, and trend metadata; do not use Genie conversation APIs or audit logs to recover hidden content; lower confidence and state the limitation. (`SKILL.md` Boundaries states the one-line prohibition; this is the full rule.)

## Failure Classes

### Wrong Data Source Or Field

Symptoms: wrong table, Metric View, column, measure, or dimension; raw table chosen when a curated Metric View should answer; important source omitted; references to tables not attached to the Space; repeated feedback says Genie used the wrong data source or field.

Fix: clarify source and field descriptions, synonyms, and source boundaries; hide irrelevant fields; remove or correct out-of-space references; add example SQL only for complex patterns.

### Wrong Metric View Measure, Dimension, Scope, Or Grain

Symptoms: wrong `MEASURE()` call, invalid grouping, missed persistent filter, wrong time dimension, incorrect semiadditive or rolling logic; feedback clusters around a curated KPI, grouping, scope, or grain mismatch.

Fix: improve Metric View names, comments, display names, synonyms, formats, filters, dimensions, window measures, or upstream joins. Add Genie examples only after the curated source is clear.

### Wrong Filter Value

Symptoms: invalid category, wrong code or label, casing mismatch, misunderstood business term; user feedback names the expected label, code, synonym, or filter scope.

Fix: enable prompt matching only for eligible useful categorical strings (safety criteria: `config-review.md` → Data Sources And Metadata), add synonyms, or add a reusable filter expression when a business term maps to SQL logic.

### Wrong Join

Symptoms: missing table, wrong key, duplicate rows, changed grain, unsupported bridge or self-join; feedback or review comments mention duplicated rows, missing related records, or impossible cross-source combinations.

Fix: add or clarify raw-table join specs backed by constraints, naming, row-count checks, or user confirmation. For complex recurring joins, recommend an upstream view or Metric View.

### Business Logic Or Time Logic Error

Symptoms: wrong numerator, denominator, aggregation, fiscal period, date boundary, rolling window, ranking, or answer shape; feedback supplies the expected KPI definition, time convention, ranking rule, or result shape.

Fix: use SQL expressions for reusable expressions or filters, Metric View measures for curated metrics, and representative example SQL for complex multi-step shapes. Keep examples representative (see `config-review.md` → SQL Query Examples for the no-benchmark-copy rule).

### Weak Agent-Mode Report

Symptoms: incomplete research plan, too few supporting queries, weak evidence, unsupported causal claims, missing citations, missing supporting table/chart, poor synthesis, missing caveats, or review requests for unsupported Agent-mode conclusions.

Evidence mapping: missing or contradictory response-quality instructions; weak or missing Agent benchmark evaluation notes; source or Metric View semantics too thin to support citations; unsupported causal claims in the final report.

Fix: improve source and Metric View descriptions, clarify metric and dimension semantics so citations are well grounded, add representative examples for reusable investigative patterns, or add a short global response-quality instruction only when the problem is not source-specific.

### Generation Latency Or Context Overload

Symptoms: users complain Chat-mode or Agent-mode responses are too slow for simple questions; SQL execution is fast but Genie spends a long time thinking before SQL appears; Agent mode reasons for too long on deterministic lookup or aggregation questions; generated SQL or answer text is exceptionally long; long conversations get slower or time out during the thinking phase.

Likely causes: too many or overlapping data sources, raw tables exposed alongside Metric Views for the same business concepts, noisy columns left visible, long source-specific text instructions, redundant or oversized example SQL, broad prompt matching or entity matching on columns that do not help common questions, too many trusted assets or SQL functions in context, token-limit pressure, long chat history, or complex examples that teach verbose SQL for simple questions.

Fix: reduce `data_sources.tables` plus `data_sources.metric_views` to a focused set, targeting five or fewer sources initially and staying under the Databricks 30 table/view limit; split broad spaces by domain when needed; prefer Metric Views, prejoined views, or materialized views for repeated business questions; hide noisy columns with `exclude`; move metric, filter, and join logic out of text instructions into Metric View semantics, SQL expressions, join specs, or representative examples; keep text instructions short, global, and non-overlapping; prune redundant or excessively long example SQL; use trusted assets or views to encapsulate common complex queries; recommend starting a new chat when long conversation history is likely influencing generation.

Avoid: optimizing warehouse size, table layout, or generated SQL when Query History shows runtime is not the bottleneck; adding broad text instructions such as "be faster"; adding more examples before pruning redundant context; treating Agent-mode latency on simple questions as a SQL performance problem without validating Chat mode or trusted assets.

### Permission, Governance, Or Data Visibility Limitation

Symptoms: empty or "no data" answers; the same question returns different results for different users; rows or columns appear missing; results look filtered or masked; users report they cannot see data they expect.

Likely causes: Space ACLs, insufficient user `SELECT` privileges, row filters, column masks, or dynamic views applied to attached sources; end-user permissions applied at query time.

Fix: this is usually not a tuning problem. Confirm the governance model (ACLs, grants, row filters, column masks, dynamic views), state which limitation applies, and route data-access remediation to the workspace or governance owner rather than Space tuning. Lower confidence and name the smallest check (for example, comparing results across users or inspecting grants) when the split is unverified.

### Config Conflict Or Redundancy

Symptoms: data source descriptions, column descriptions, Metric View metadata, expressions, examples, prompt matching, benchmarks, feedback-derived assumptions, or text instructions conflict; expressions or examples duplicate the same business logic with different literals, date boundaries, aliases, or aggregation grain; text instructions contain a long source-specific rulebook; examples or expressions repeat Metric View formulas; static config review finds stale table names, deprecated fields, or overlapping source guidance.

Fix: consolidate the rule into the most specific structured surface, remove redundant examples or expressions, clarify source and column descriptions, route shared formulas to Metric View metadata or upstream semantic-model recommendations, keep examples representative and non-duplicative, and keep text instructions short, global, and non-overlapping. When query access is unavailable, report the static conflict and name the smallest validation needed before applying a tuning edit.

### Benchmark Ground Truth Problem

Symptoms: invalid SQL answer, missing SQL for a deterministic Chat benchmark, unclear or missing evaluation note for an Agent-style benchmark, a multi-query analysis question forced into a single SQL answer, or benchmark pass rates that conflict with recent negative user feedback on the same pattern.

Fix: repair benchmark definitions outside Genie tuning. Use checked SQL for deterministic tabular questions, evaluation notes for Agent-style multi-step analysis, and both only when the same question has a single canonical result plus full-response quality criteria.

### Benchmark Set Too Large Or Redundant

Symptoms: too many questions for practical benchmark iteration or a count approaching/exceeding the 500-question limit; many near-duplicates that only swap dates or category literals; one source or metric overweighted; too many trivial lookup questions; repeated variants that obscure root-cause patterns; or feedback clusters showing important real user patterns missing from the benchmark.

Fix: recommend a dedicated benchmark pruning pass outside Genie tuning. Retain a representative set that preserves diversity, source and metric coverage, answer shapes, historically fragile behavior, and a meaningful mix of medium and hard questions, with only a small number of easy smoke tests. Keep healthy 2–4 phrasing variants of the same question, since multiple phrasings improve coverage; prune only redundant variants that swap dates, categories, or literals without adding coverage. Record pruned question IDs and the coverage or difficulty rationale.

## Health Signals

Treat these as blockers or warnings during diagnosis:

- Too many overlapping data sources.
- Generic table, Metric View, or column descriptions.
- Important categorical filters without prompt matching.
- Raw tables exposed together with missing joins.
- Conflicting or redundant SQL expressions, example SQL, source metadata, Metric View metadata, prompt matching, or text instructions.
- Expressions or examples that duplicate a Metric View's formulas without teaching a query shape.
- Example SQL that copies benchmark material (see `config-review.md` → SQL Query Examples).
- High negative-feedback or review-request volume for patterns with weak benchmark coverage.
- Feedback comments that repeatedly define business terms missing from metadata, Metric Views, prompt matching, expressions, examples, or short global instructions.
- Passing benchmark results that contradict recent negative feedback on equivalent real user questions.
- Benchmark set too small, narrow, easy, redundant, or large; missing checked SQL answers for deterministic Chat execution; or missing evaluation notes for Agent-style questions.
- Text instructions containing source-specific SQL logic.
- Governance restrictions (ACLs, row filters, column masks, dynamic views) that could cause empty or per-user-inconsistent answers.
- Generation-latency and context-pressure signals: see `Generation Latency Or Context Overload` (and `config-review.md` → Latency Context Pressure for static detection).
