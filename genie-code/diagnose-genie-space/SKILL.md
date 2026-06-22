---
name: diagnose-genie-space
description: "Plan-only, read-only diagnosis of Databricks Genie Space quality, configuration, and response-latency problems; produces a root-cause write-up and never edits the Space. Run inside Genie Code Agent mode to diagnose Genie Space standard chat, Genie Spaces Agent mode, or benchmark execution. Use for health checks, config-only or limited-query-permission reviews, and root-causing wrong sources, wrong or inconsistent answers, weak Agent-mode reports, Metric View / prompt-matching / join / benchmark issues, Monitor feedback trends, or generation- vs SQL-runtime latency — before any tuning."
---

# Diagnose Genie Space

Diagnose Genie Space quality without making changes. Inspect Space configuration first, then Monitor-tab feedback, workspace assets, Unity Catalog metadata, generated SQL, Query History, and bounded read-only SQL output when available.

## Modes

- Run this skill in **Genie Code Agent mode** (the execution environment).
- It diagnoses the target Genie Space across **standard chat**, **Genie Spaces Agent mode**, and **benchmark Chat/Agent execution**. Genie Code Agent mode and Genie Spaces Agent mode are different things; keep them distinct when describing the case.

## Boundaries

- This skill is plan-only. Do not edit the Genie Space, change benchmarks, run benchmark evaluation, or mutate source data.
- Do not send feedback, create comments, delete conversations, edit generated SQL, save instructions, add benchmarks, or change conversation review status during diagnosis.
- Use only bounded read-only SQL: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema`. Prefer aggregate or profiling queries, never `SELECT *`, add an explicit `LIMIT` to any row sample, avoid sensitive columns, and never export or persist results.
- Do not use UI, API, or audit-log access to bypass private-conversation visibility. For any read-only fallback, use only allowed GET/list endpoints and aggregate audit fields; never call conversation- or message-creation endpoints. Treat unavailable conversation content as a limitation.
- Do not copy benchmark questions, answer SQL, evaluation-note wording, or failing prompts into examples, expressions, or instructions (canonical detail in `references/config-review.md` → SQL Query Examples).
- If the user cannot run SQL or inspect Query History, continue with config-only diagnosis and state the lower confidence or validation gap.
- Ask for missing business intent or expected behavior when workspace evidence is insufficient.
- Prefer concrete evidence over generic best-practice advice.

## Workflow

1. Establish the tuning case:
   - Space name or identifier
   - failing question, if any
   - observed bad behavior, and expected answer, SQL, evaluation note, or business rule
   - generated SQL, final response, Agent research evidence, or error text, if available
   - whether the issue came from Chat benchmark execution, Agent benchmark execution, or ad hoc use
   - whether the failure is intermittent or repeatable
   - for latency complaints, gather the timing details listed in `references/failure-routing.md` → Latency Pre-Routing
2. Record access and evidence availability before deciding how much validation is possible. Capture visibility per `references/failure-routing.md` → Evidence To Gather (Space config, Monitor, generated SQL / Agent evidence, Query History timing, and whether bounded read-only SQL can run). If SQL is unavailable, continue with config-only review and label validation gaps clearly.
3. Inspect the Space configuration as the primary diagnostic surface. Work through the static checklist in `references/config-review.md` — data sources, column metadata, instructions, SQL expressions / knowledge-store snippets, examples, join relationships, Metric Views, prompt matching, trusted assets / SQL functions, common questions, benchmarks, permissions / governance, and latency context pressure.
4. Inspect existing Monitor-tab feedback as first-class evidence: usage and rating trends, negative-rated or review-requested conversations, reviewable conversation details (prompt, response, generated SQL/error, comments, citations, repetition), and latency complaints. Apply privacy limits from `references/failure-routing.md` → Feedback Routing.
5. For latency complaints, run the split in `references/failure-routing.md` → Latency Pre-Routing. Summary: if Query History shows SQL runtime (execution, queue, startup, scan, spill, result-fetch) dominates **and** the generated SQL is semantically correct → hand off to `optimize-genie-query`; if runtime dominates but the SQL is wrong → classify the Genie failure and hand off to `optimize-genie-space`; if SQL is fast but the wait is before SQL appears, during Agent reasoning, or during synthesis → classify as `Generation Latency Or Context Overload`.
6. Use bounded read-only SQL only when the Space configuration, latency split, generated SQL, or feedback evidence does not explain the issue. For Metric View failures, inspect the Metric View definition before dropping down to raw sources.
7. Classify the primary failure and secondary contributors using `references/failure-routing.md`. Treat static config findings and feedback as evidence that helps cluster failures, not as separate tuning surfaces. When guidance surfaces conflict, apply `references/failure-routing.md` → Conflict Resolution And Precedence to explain the symptom and choose the repair surface.
8. Recommend the smallest structured tuning change. Prefer source scope, table / Metric View / column metadata, Metric View semantics, prompt matching, join specs, SQL expressions, and representative examples before text instructions. Representative examples should teach reusable patterns (see `references/config-review.md` → SQL Query Examples). For generation-latency cases, recommend focused Space configuration cleanup and hand off to `optimize-genie-space` rather than SQL-runtime tuning.
9. Produce a concise diagnostic write-up in chat or notebook output.

## Diagnostic Write-Up

Use this shape. Omit rows or fields that do not apply; for a no-change outcome, state that in Finding and leave the table empty. Confidence uses High/Medium/Low per `references/config-review.md` → No-Query Diagnosis Mode.

```markdown
# Genie Space Diagnosis: <space>

## Case
- Question:
- Observed:
- Expected:
- Mode and latency split:

## Access And Validation
- Space config visibility:
- Monitor visibility:
- Generated SQL / Agent evidence:
- Query History visibility:
- Read-only SQL available:
- Validation limitations:

## Finding
- Primary failure:
- Contributors:
- Confidence:

## Evidence
- Config review:
- Feedback signals:
- Read-only inspection:
- Latency evidence:
- Limitations:

## Recommended Tuning
| Priority | Surface | Change | Rationale | Validation |
|---|---|---|---|---|

## Health Check
- Ready for tuning:
- Feedback coverage:
- Feedback concerns:
- Benchmark concerns:
- Pruning opportunity:
- Benchmark execution target:
- Generation latency concerns:
- Governance / visibility concerns:
- Highest-risk static issues:
```

End with the next action: either user confirmation needed for missing evidence, a handoff to `optimize-genie-space` for Space configuration cleanup, edits, evaluations, or benchmark repair, a handoff to `optimize-genie-query` when SQL runtime dominates and the generated SQL is correct, or a recommendation-only summary when no change is justified.
