---
name: diagnose-genie-space
description: "Diagnose Databricks Genie Space quality, static configuration, and response-latency issues without making changes in Databricks Genie Code Agent mode. Use inside Databricks when users ask for plan-only root-cause analysis, health checks, config-only reviews, limited-query-permission reviews, or explanations for wrong SQL, wrong answers, inconsistent answers, slow Chat-mode or Agent-mode responses, query-generation or thinking-phase latency, weak Agent-mode reports, source-selection errors, metric, dimension, filter, join, time logic, general/text instruction problems, SQL snippets or expressions, SQL query examples, data source metadata, table or column descriptions, benchmark size, benchmark coverage, benchmark pruning, monitoring feedback, thumbs up/down trends, Genie Monitor review requests, Genie feedback comments or reviewer comments, usage trends, or conversation-quality signals before tuning."
---

# Diagnose Genie Space For Genie Code

Diagnose Genie Space quality without making changes. Use Genie Code Agent mode to inspect Space configuration first, then Monitor-tab feedback, workspace assets, Unity Catalog metadata, generated SQL, Query History, and bounded read-only SQL output when available.

## Boundaries

- This skill is plan-only. Do not edit the Genie Space, change benchmarks, run benchmark evaluation, or mutate source data.
- Do not send feedback, create comments, delete conversations, edit generated SQL, save instructions, add benchmarks, or change conversation review status during diagnosis.
- Use only bounded read-only SQL: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema`.
- If the user cannot run SQL or inspect Query History, continue with config-only diagnosis and state the lower confidence or validation gap.
- Do not use UI, API, or audit-log access to bypass private-conversation visibility. Treat unavailable conversation content as a limitation.
- Do not copy benchmark questions, answer SQL, evaluation-note wording, or failing prompts into examples, snippets, or instructions.
- Ask for missing business intent or expected behavior when workspace evidence is insufficient.
- Prefer concrete evidence over generic best-practice advice.

## Workflow

1. Establish the tuning case:
   - Space name or identifier
   - failing question, if any
   - observed bad behavior
   - expected answer, SQL, evaluation note, or business rule
   - generated SQL, final response, Agent research evidence, or error text, if available
   - whether the issue came from Chat benchmark execution, Agent benchmark execution, or ad hoc use
   - for latency complaints: whether the slow path is Chat mode, Agent mode, benchmark execution, or ad hoc use; whether delay happens before SQL appears, during Agent reasoning, during SQL execution, or during final response synthesis
   - total observed response time compared with Query History execution, queue, startup, and result-fetch time when available
   - whether the failure is intermittent or repeatable
2. Record access and evidence availability before deciding how much validation is possible:
   - Space configuration visibility: attached sources, descriptions, instructions, snippets, examples, joins, prompt matching, and benchmarks
   - Monitor visibility: usage trends, ratings, review status, visible conversation details, comments, and private-conversation limits
   - Generated SQL, final answer, Agent research evidence, or error availability
   - Query History timing visibility for latency cases
   - Whether bounded read-only SQL can be run; if not, continue with config-only review and label validation gaps clearly
3. Inspect the Space configuration as the primary diagnostic surface. Read `references/config-review.md` for the static checklist:
   - data sources: focused source set, raw table versus Metric View overlap, source boundaries, table and Metric View descriptions, noisy fields, hidden fields, synonyms, and prompt matching
   - column metadata: descriptions that state business meaning, grain, units, valid values, date roles, and confusing or redundant fields
   - general/text instructions: move source-specific metric, filter, join, ranking, window, and table-selection logic into structured surfaces when possible
   - SQL snippets/expressions: check purpose, reuse, conflicts, redundancy, stale assumptions, Metric View formula duplication, and whether the logic belongs upstream
   - SQL query examples: check representative value, non-conflict with snippets or metadata, parameter/default quality, duplicate coverage, and benchmark or failing-prompt leakage
   - join specs, SQL functions, sample questions, benchmarks, trusted assets, and generation-latency context pressure
   - benchmark inventory size, validity, duplicate clusters, coverage categories, and difficulty mix when benchmarks are part of the case
4. Inspect existing Monitor-tab feedback as first-class evidence:
   - weekly digest message volume, active users, thumbs up/down counts or trends, and usage patterns
   - filtered conversations with negative ratings, `Fix it`, `Request review`, needs-review status, repeated questions, or common user phrasing
   - reviewable conversation details: user prompt, Genie response, generated SQL or error, feedback comment, reviewer comments, citations, and whether the issue repeats across conversations
   - latency complaints or comments that mention slow simple questions, slow Agent-mode reports, timeout during thinking, long SQL generation, or needing to start new chats
   - privacy limitations: when conversations are private, use only visible prompt, status, rating, timestamp, and trend metadata; state what could not be inspected
   - fallback evidence, when UI access supports it: Genie `Analyze space usage`, read-only Genie conversation APIs, or read-only `system.access.audit` queries for `updateConversationMessageFeedback` and `createConversationMessageComment`; aggregate where practical and never use fallback logs to recover private or unavailable conversation content
5. For latency complaints, separate SQL-runtime latency from query-generation or thinking-phase latency:
   - if Query History shows execution, queue, warehouse startup, scan, spill, or result-fetch time dominates, stop Space-quality diagnosis and hand off to `optimize-genie-query`
   - if SQL execution is fast but the user waits before SQL appears, during Agent planning/reasoning, or during long response synthesis, classify the case as generation latency or context overload
   - for Agent mode, state that Agent responses can naturally take longer because Agent mode plans, runs multiple queries, and synthesizes a report; for simple deterministic questions, validate Chat mode or trusted assets as the lower-latency path
6. Use bounded read-only SQL only when the Space configuration, latency split, generated SQL, or feedback evidence does not explain the issue. For Metric View failures, inspect the Metric View definition before dropping down to raw sources.
7. Classify the primary failure and secondary contributors using `references/failure-routing.md`. Treat static config findings and feedback as evidence that helps cluster failures, not as separate tuning surfaces.
8. Recommend the smallest structured tuning change. Prefer source scope, table/Metric View/column metadata, Metric View semantics, prompt matching, joins, snippets, and representative examples before text instructions. Representative examples should teach reusable patterns, not memorize benchmarks or failing questions. For generation-latency cases, recommend focused Space configuration cleanup and hand off to `optimize-genie-space` rather than SQL-runtime tuning.
9. Produce a concise diagnostic write-up in chat or notebook output.

## Diagnostic Write-Up

Use this shape:

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
- Highest-risk static issues:
```

End with the next action: either user confirmation needed for missing evidence, a handoff to `optimize-genie-space` for Space configuration cleanup, edits, evaluations, or benchmark repair, a handoff to `optimize-genie-query` when SQL runtime dominates, or a recommendation-only summary when no change is justified.
