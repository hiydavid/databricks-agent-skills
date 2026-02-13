# Vector Search Python SDK Reference

Complete method signatures and code templates for all Vector Search operations.

## Table of Contents

- [Client Initialization](#client-initialization)
- [Endpoints](#endpoints)
- [Delta Sync Index — Managed Embeddings](#delta-sync-index--managed-embeddings)
- [Delta Sync Index — Self-Managed Embeddings](#delta-sync-index--self-managed-embeddings)
- [Direct Access Index](#direct-access-index)
- [Sync Operations](#sync-operations)
- [Upsert and Delete](#upsert-and-delete)
- [Wait for Ready](#wait-for-ready)

---

## Client Initialization

```python
from databricks.vector_search.client import VectorSearchClient

# Default: uses notebook auth or PAT from environment
vsc = VectorSearchClient()

# Service principal auth (production)
vsc = VectorSearchClient(
    service_principal_client_id="<CLIENT_ID>",
    service_principal_client_secret="<CLIENT_SECRET>"
)
```

Service principal auth improves query performance by ~100ms vs PAT.

---

## Endpoints

```python
vsc.create_endpoint(
    name="my_endpoint",
    endpoint_type="STANDARD"  # or "STORAGE_OPTIMIZED"
)
```

**Parameters:**
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | str | Yes | Endpoint identifier |
| `endpoint_type` | str | Yes | `STANDARD` or `STORAGE_OPTIMIZED` |

**Idempotent creation pattern:**
```python
try:
    vsc.create_endpoint(name="my_endpoint", endpoint_type="STANDARD")
except Exception as e:
    if "already exists" in str(e).lower():
        print("Endpoint already exists, reusing")
    else:
        raise
```

---

## Delta Sync Index — Managed Embeddings

Databricks computes embeddings from a text column.

```python
index = vsc.create_delta_sync_index(
    endpoint_name="my_endpoint",
    source_table_name="catalog.schema.source_table",
    index_name="catalog.schema.my_index",
    pipeline_type="TRIGGERED",
    primary_key="id",
    embedding_source_column="text",
    embedding_model_endpoint_name="databricks-gte-large-en",
)
```

**Parameters:**
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `endpoint_name` | str | Yes | Target endpoint |
| `source_table_name` | str | Yes | 3-level namespace: `catalog.schema.table` |
| `index_name` | str | Yes | 3-level namespace: `catalog.schema.index` |
| `pipeline_type` | str | Yes | `TRIGGERED` or `CONTINUOUS` |
| `primary_key` | str | Yes | Unique ID column |
| `embedding_source_column` | str | Yes | Text column to embed |
| `embedding_model_endpoint_name` | str | Yes | Model endpoint for ingestion |
| `model_endpoint_name_for_query` | str | No | Separate model for querying (optional) |
| `columns_to_sync` | list | No | Subset of columns; if omitted, all columns sync |

**With column selection:**
```python
index = vsc.create_delta_sync_index(
    endpoint_name="my_endpoint",
    source_table_name="catalog.schema.source_table",
    index_name="catalog.schema.my_index",
    pipeline_type="TRIGGERED",
    primary_key="id",
    embedding_source_column="text",
    embedding_model_endpoint_name="databricks-gte-large-en",
    columns_to_sync=["id", "text", "source_file", "metadata"]
)
```

---

## Delta Sync Index — Self-Managed Embeddings

Source table already contains pre-computed embedding vectors.

```python
index = vsc.create_delta_sync_index(
    endpoint_name="my_endpoint",
    source_table_name="catalog.schema.source_table",
    index_name="catalog.schema.my_index",
    pipeline_type="TRIGGERED",
    primary_key="id",
    embedding_dimension=1024,
    embedding_vector_column="text_vector"
)
```

**Additional parameters (vs managed):**
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `embedding_dimension` | int | Yes | Vector size (must be divisible by 16 for storage-optimized) |
| `embedding_vector_column` | str | Yes | Column containing `array<float>` vectors |

Do NOT set `embedding_source_column` or `embedding_model_endpoint_name` for self-managed.

---

## Direct Access Index

Manual read/write control — no source Delta table.

```python
index = vsc.create_direct_access_index(
    endpoint_name="my_endpoint",
    index_name="catalog.schema.my_index",
    primary_key="id",
    embedding_dimension=1024,
    embedding_vector_column="text_vector",
    schema={
        "id": "int",
        "text": "string",
        "source": "string",
        "text_vector": "array<float>"
    }
)
```

**Parameters:**
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `endpoint_name` | str | Yes | Target endpoint |
| `index_name` | str | Yes | 3-level namespace |
| `primary_key` | str | Yes | Unique ID column |
| `embedding_dimension` | int | Yes | Vector size |
| `embedding_vector_column` | str | Yes | Column containing vectors |
| `schema` | dict | Yes | Column name → type mapping |

**Supported schema types:** `int`, `long`, `float`, `double`, `boolean`, `string`, `array<float>`

---

## Sync Operations

For delta-sync indexes with `pipeline_type="TRIGGERED"`:

```python
index = vsc.get_index(index_name="catalog.schema.my_index")
index.sync()
```

Continuous sync indexes update automatically — no manual sync needed.

---

## Upsert and Delete

For **direct-access indexes** only.

**Upsert (insert or update):**
```python
index = vsc.get_index(index_name="catalog.schema.my_index")
index.upsert([
    {
        "id": 1,
        "text": "document content here",
        "source": "file.pdf",
        "text_vector": [0.1, 0.2, ...] # length must match embedding_dimension
    },
    {
        "id": 2,
        "text": "another document",
        "source": "other.pdf",
        "text_vector": [0.3, 0.4, ...]
    }
])
```

**Delete:**
```python
index = vsc.get_index(index_name="catalog.schema.my_index")
index.delete(["id_value_1", "id_value_2"])
```

**REST API upsert (alternative):**
```
POST /api/2.0/vector-search/indexes/{index_name}/upsert-data
Body: {"inputs_json": "[{\"id\": 1, \"text\": \"...\", \"text_vector\": [...]}]"}
```

**REST API delete:**
```
DELETE /api/2.0/vector-search/indexes/{index_name}/delete-data
Body: {"primary_keys": ["id_value_1", "id_value_2"]}
```

---

## Wait for Ready

Polling loop to wait for index sync to complete:

```python
import time

index = vsc.get_index(index_name="catalog.schema.my_index")

while True:
    status = index.describe()
    index_status = status.get("status", {})
    if index_status.get("ready", False):
        print("Index is ready!")
        break
    message = index_status.get("message", "syncing...")
    print(f"Index not ready: {message}")
    time.sleep(30)
```

**Note:** Initial sync can take minutes to hours depending on data size and embedding computation.
