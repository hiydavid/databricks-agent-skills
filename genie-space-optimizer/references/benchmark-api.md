# Benchmark Evaluation API Reference

The Benchmark API (Beta) enables programmatic evaluation of Genie Space benchmark questions. All endpoints are under `/api/2.0/genie/spaces/{space_id}/eval-runs/`.

## Workflow

```
1. Create eval run  →  POST /eval-runs
2. Poll for completion  →  GET /eval-runs/{eval_run_id}  (repeat until DONE)
3. List results  →  GET /eval-runs/{eval_run_id}/results  (paginate)
4. Get result details  →  GET /eval-runs/{eval_run_id}/results/{result_id}  (per failed question)
```

---

## 1. Create Eval Run

**`POST /api/2.0/genie/spaces/{space_id}/eval-runs`**

Creates and starts an evaluation run for benchmark questions.

**Request body:**
```json
{
  "benchmark_question_ids": ["id1", "id2"]  // optional — omit to evaluate ALL benchmarks
}
```

**Response:**
```json
{
  "eval_run_id": "uuid",
  "eval_run_status": "RUNNING",
  "num_questions": 25,
  "num_done": 0,
  "num_correct": 0,
  "num_needs_review": 0,
  "created_timestamp": 1711900000000,
  "last_updated_timestamp": 1711900000000,
  "run_by_user": 12345
}
```

---

## 2. Get Eval Run (Polling)

**`GET /api/2.0/genie/spaces/{space_id}/eval-runs/{eval_run_id}`**

Poll this endpoint until `eval_run_status` reaches a terminal state.

**Response:** Same schema as Create. Key fields for polling:
- `eval_run_status`: Current state
- `num_done` / `num_questions`: Progress tracking
- `num_correct`: Running accuracy count

---

## 3. List Eval Results

**`GET /api/2.0/genie/spaces/{space_id}/eval-runs/{eval_run_id}/results`**

Returns per-question result summaries. Paginated.

**Query params:**
- `page_size` (int, default 20, max 100)
- `page_token` (string, from previous response's `next_page_token`)

**Response:**
```json
{
  "eval_results": [
    {
      "result_id": "uuid",
      "benchmark_question_id": "uuid",
      "question": "What are the top 5 customers by spend?",
      "benchmark_answer": "SELECT ...",
      "status": "DONE",
      "space_id": "uuid",
      "created_by_user": 12345
    }
  ],
  "next_page_token": "..."
}
```

**Pagination:** Loop until `next_page_token` is absent or empty.

---

## 4. Get Eval Result Details

**`GET /api/2.0/genie/spaces/{space_id}/eval-runs/{eval_run_id}/results/{result_id}`**

Returns full details for a single benchmark result including generated SQL, expected SQL, assessment, and error classification.

**Response:**
```json
{
  "result_id": "uuid",
  "benchmark_question_id": "uuid",
  "space_id": "uuid",
  "eval_run_status": "DONE",
  "assessment": "BAD",
  "assessment_reasons": [
    "LLM_JUDGE_WRONG_FILTER",
    "RESULT_MISSING_ROWS"
  ],
  "manual_assessment": false,
  "expected_response": [
    {
      "response": "SELECT ... (expected SQL)",
      "response_type": "TEXT",
      "sql_execution_result": { "manifest": {...}, "result": {...}, "status": {...} }
    }
  ],
  "actual_response": [
    {
      "response": "SELECT ... (generated SQL)",
      "response_type": "TEXT",
      "sql_execution_result": { "manifest": {...}, "result": {...}, "status": {...} }
    }
  ]
}
```

---

## Eval Run Status Enum

| Status | Terminal? | Meaning |
|--------|-----------|---------|
| `NOT_STARTED` | No | Run created but not yet started |
| `RUNNING` | No | Evaluation in progress |
| `DONE` | Yes | All questions evaluated successfully |
| `EVALUATION_FAILED` | Yes | Run failed due to an error |
| `EVALUATION_CANCELLED` | Yes | Run was cancelled |
| `EVALUATION_TIMEOUT` | Yes | Run timed out |

## Assessment Enum

| Value | Meaning |
|-------|---------|
| `GOOD` | Generated SQL produces correct results |
| `BAD` | Generated SQL produces incorrect results |
| `NEEDS_REVIEW` | Automated assessment uncertain — manual review needed |

## Assessment Reasons

### Deterministic (result comparison)

| Reason | Description |
|--------|-------------|
| `EMPTY_RESULT` | Generated SQL returned no rows |
| `RESULT_MISSING_ROWS` | Output missing rows vs expected |
| `RESULT_EXTRA_ROWS` | Output has extra rows vs expected |
| `RESULT_MISSING_COLUMNS` | Output missing columns vs expected |
| `RESULT_EXTRA_COLUMNS` | Output has extra columns vs expected |
| `SINGLE_CELL_DIFFERENCE` | Single value differs from expected |
| `EMPTY_GOOD_SQL` | The benchmark's expected SQL returned empty results |
| `COLUMN_TYPE_DIFFERENCE` | Values match but column types differ |

### LLM Judge (semantic analysis)

| Reason | Description |
|--------|-------------|
| `LLM_JUDGE_MISSING_JOIN` | Missing a required join |
| `LLM_JUDGE_MISSING_OR_INCORRECT_JOIN` | Join is missing or uses wrong condition |
| `LLM_JUDGE_WRONG_FILTER` | Incorrect WHERE clause |
| `LLM_JUDGE_MISSING_OR_INCORRECT_FILTER` | Filter is missing or wrong |
| `LLM_JUDGE_WRONG_AGGREGATION` | Incorrect aggregate function |
| `LLM_JUDGE_MISSING_OR_INCORRECT_AGGREGATION` | Aggregation is missing or wrong |
| `LLM_JUDGE_WRONG_COLUMNS` | Wrong columns selected |
| `LLM_JUDGE_SYNTAX_ERROR` | SQL syntax error |
| `LLM_JUDGE_SEMANTIC_ERROR` | SQL is valid but logically wrong |
| `LLM_JUDGE_INCOMPLETE_OR_PARTIAL_OUTPUT` | Returns only some requested data |
| `LLM_JUDGE_MISINTERPRETATION_OF_USER_REQUEST` | Fundamentally misunderstands the question |
| `LLM_JUDGE_INSTRUCTION_COMPLIANCE_OR_MISSING_BUSINESS_LOGIC` | Fails to apply business rules |
| `LLM_JUDGE_INCORRECT_METRIC_CALCULATION` | Metric computed incorrectly |
| `LLM_JUDGE_INCORRECT_TABLE_OR_FIELD_USAGE` | Wrong tables or columns referenced |
| `LLM_JUDGE_INCORRECT_FUNCTION_USAGE` | SQL functions used incorrectly |
| `LLM_JUDGE_FORMATTING_ERROR` | Wrong ordering or presentation |
| `LLM_JUDGE_OTHER` | Uncategorized error |

---

## SQL Execution Result Structure

Both `actual_response` and `expected_response` include `sql_execution_result` with the standard Databricks Statement Execution format:

- `manifest.schema.columns[]` — column names and types
- `manifest.total_row_count` — total rows returned
- `result.data_array` — the actual data as array of string arrays
- `status.state` — execution state (e.g., `SUCCEEDED`, `FAILED`)
- `status.error` — error details if execution failed

Use `data_array` to compare actual vs expected output data when the assessment reasons alone don't fully explain the failure.
