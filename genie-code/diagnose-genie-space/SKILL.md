---
name: diagnose-genie-space
description: "Diagnose Databricks Genie Space quality issues in Databricks Genie Code Agent mode. Use inside Databricks when users ask why a Genie Space gives wrong SQL, wrong answers, inconsistent answers, weak Agent-mode reports, source-selection errors, metric, dimension, filter, join, time logic, benchmark, or instruction problems, or when they need a plan-only health check before tuning."
---

# Diagnose Genie Space For Genie Code

Diagnose Genie Space quality without making changes. Use Genie Code Agent mode to inspect the Space, workspace assets, Unity Catalog metadata, and bounded read-only SQL output when needed.

## Boundaries

- This skill is plan-only. Do not edit the Genie Space, change benchmarks, run benchmark evaluation, or mutate source data.
- Use only bounded read-only SQL: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema`.
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
   - whether the failure is intermittent or repeatable
2. Inspect the Space context:
   - attached tables, views, Metric Views, measures, dimensions, filters, and descriptions
   - relevant column comments, synonyms, prompt matching settings, and hidden fields
   - join specs, SQL snippets, example SQL, text instructions, sample questions, and benchmarks
3. Use bounded read-only SQL only when the Space context does not explain the issue. For Metric View failures, inspect the Metric View definition before dropping down to raw sources.
4. Classify the primary failure and secondary contributors using `references/failure-routing.md`.
5. Recommend the smallest structured tuning change. Prefer metadata, Metric View semantics, prompt matching, joins, snippets, and representative examples before text instructions.
6. Produce a concise diagnostic write-up in chat or notebook output.

## Diagnostic Write-Up

Use this shape:

```markdown
# Genie Space Diagnosis: <space>

## Case
- Question:
- Observed:
- Expected:

## Finding
- Primary failure:
- Contributors:
- Confidence:

## Evidence
- Space context:
- Read-only inspection:
- Limitations:

## Recommended Tuning
| Priority | Surface | Change | Rationale | Validation |
|---|---|---|---|---|

## Health Check
- Ready for tuning:
- Benchmark concerns:
- Benchmark execution target:
- Highest-risk static issues:
```

End with the next action: either user confirmation needed, a safe manual Space edit, or a handoff to `optimize-genie-space`.
