---
name: create-update-vector-search-index
description: "Create, update, and manage Databricks Vector Search endpoints and indexes using the Python SDK. Use when: (1) User wants to create a Vector Search endpoint or index, (2) User says 'create vector search', 'create index', 'update index', 'sync index', 'upsert vectors', (3) User needs to set up delta-sync or direct-access indexes, (4) User asks about embedding configuration, sync modes, or endpoint types, (5) User wants to manage index lifecycle (create, sync, upsert, delete records, schema changes). Covers endpoint creation, both index types (delta-sync and direct-access), managed vs self-managed embeddings, sync operations, and data upsert/delete."
---

# Create & Update Vector Search Index

Generate Python SDK code for managing Databricks Vector Search endpoints and indexes.

## Prerequisites

- `databricks-vectorsearch` package installed
- Unity Catalog enabled workspace with serverless compute
- CREATE TABLE privileges on target schema
- For delta-sync: source Delta table with Change Data Feed enabled

## Decision Tree

```
Need a VS endpoint?
  ├── Low-latency queries → Standard endpoint
  └── Batch/cost-optimized → Storage-Optimized endpoint

Need an index?
  ├── Source is a Delta table that updates over time → Delta Sync Index
  │     ├── Want Databricks to handle embeddings? → Managed embeddings
  │     └── Already have embedding vectors? → Self-managed embeddings
  └── Want manual control over inserts/updates → Direct Access Index

Sync mode? (delta-sync only)
  ├── Need real-time updates → Continuous (Standard endpoints only)
  └── Manual/scheduled updates → Triggered (both endpoint types)
```

## Workflow

### Step 1: Gather User Inputs

| Parameter | Options | Default |
|-----------|---------|---------|
| Endpoint name | Any string | Required |
| Endpoint type | `STANDARD`, `STORAGE_OPTIMIZED` | `STANDARD` |
| Index type | `delta_sync`, `direct_access` | `delta_sync` |
| Index name | `catalog.schema.index_name` | Required |
| Primary key | Column name | Required |
| Embedding approach | `managed`, `self_managed` | `managed` |
| Embedding model | Model endpoint name | `databricks-gte-large-en` |
| Sync mode | `TRIGGERED`, `CONTINUOUS` | `TRIGGERED` |
| Source table | `catalog.schema.table` | Required (delta-sync) |

### Step 2: Generate Code

See [references/sdk_reference.md](references/sdk_reference.md) for full SDK method signatures, parameters, and code templates for each operation:

- **Endpoints** — `create_endpoint()`
- **Delta Sync (managed embeddings)** — `create_delta_sync_index()` with `embedding_source_column`
- **Delta Sync (self-managed)** — `create_delta_sync_index()` with `embedding_vector_column`
- **Direct Access** — `create_direct_access_index()` + `upsert()` / `delete()`
- **Sync** — `index.sync()`
- **Wait for ready** — polling loop on `index.describe()`

### Step 3: Verify

After index creation + sync, generate a verification snippet:

```python
index = vsc.get_index(index_name="catalog.schema.index_name")
results = index.similarity_search(
    query_text="test query",
    columns=["primary_key_col", "text_col"],
    num_results=3
)
print(results)
```

## Key Constraints

**Storage-Optimized endpoints:**
- Triggered sync only (no continuous)
- Embedding dimension must be divisible by 16
- Full rebuild on first sync, partial on subsequent

**Delta-sync indexes:**
- Source table MUST have Change Data Feed enabled:
  `ALTER TABLE t SET TBLPROPERTIES (delta.enableChangeDataFeed = true)`
- Reserved column name `_id` — rename if present in source table

**Managed embeddings:**
- Recommended model: `databricks-gte-large-en`
- Remove "Scale to zero" on embedding endpoints to avoid query timeouts
- Generated embeddings saved to `{index_name}_writeback_table` (read-only)

**Schema changes:**
- Cannot modify existing columns on a live index
- Zero-downtime approach: create new index → switch traffic → delete old index

## Next Steps

After index is created:
1. **Wire into agent** — See **add-tools** skill for `databricks.yml` permissions
2. **Parse documents first?** — See **parse-documents** skill for the full doc → index pipeline
