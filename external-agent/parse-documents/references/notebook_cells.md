# Notebook Cell Templates

SQL + Python templates for each cell in the parse-documents notebook. Replace `${PARAM}` placeholders with user-provided values.

## Table of Contents

- [Cell 1: Configuration](#cell-1-configuration)
- [Cell 2: Parse Documents](#cell-2-parse-documents)
- [Cell 3: Chunk Content](#cell-3-chunk-content)
- [Cell 4: Write Delta Table](#cell-4-write-delta-table)
- [Cell 5: Create Vector Search Index](#cell-5-create-vector-search-index)

---

## Cell 1: Configuration

```sql
-- Configuration
-- Set parameters for the pipeline

CREATE WIDGET TEXT source_volume DEFAULT '${SOURCE_VOLUME}';
CREATE WIDGET TEXT target_catalog DEFAULT '${TARGET_CATALOG}';
CREATE WIDGET TEXT target_schema DEFAULT '${TARGET_SCHEMA}';
CREATE WIDGET TEXT target_table DEFAULT '${TARGET_TABLE}';
CREATE WIDGET TEXT vs_endpoint DEFAULT '${VS_ENDPOINT}';
CREATE WIDGET TEXT vs_index DEFAULT '${VS_INDEX}';
CREATE WIDGET TEXT chunk_strategy DEFAULT '${CHUNK_STRATEGY}'; -- page, token, semantic
CREATE WIDGET TEXT chunk_size DEFAULT '512';
CREATE WIDGET TEXT chunk_overlap DEFAULT '50';
CREATE WIDGET TEXT embedding_model DEFAULT 'databricks-gte-large-en';
```

---

## Cell 2: Parse Documents

Use PySpark to load binary files and apply `ai_parse_document` (schema version 2.0).

```python
# Parse documents from a UC Volume using ai_parse_document
from pyspark.sql import functions as F
from pyspark.sql.window import Window

source_volume = dbutils.widgets.get("source_volume")
target_catalog = dbutils.widgets.get("target_catalog")
target_schema = dbutils.widgets.get("target_schema")
target_table = dbutils.widgets.get("target_table")

raw_docs = (
    spark.read.format("binaryFile")
    .load(source_volume)
    .where(F.lower(F.col("path")).rlike(r".*\.(pdf|doc|docx|ppt|pptx|jpg|jpeg|png)$"))
)

# Official pattern: pin parser schema version and inspect parse status.
parsed_raw = raw_docs.selectExpr(
    "path AS source_path",
    "ai_parse_document(content, map('version', '2.0')) AS parsed"
)

parsed_success = parsed_raw.where("try_cast(parsed:error_status AS STRING) IS NULL")
parsed_errors = parsed_raw.where("try_cast(parsed:error_status AS STRING) IS NOT NULL")

# Official pattern: extract elements as ARRAY<VARIANT>.
elements = (
    parsed_success
    .selectExpr(
        "source_path",
        "regexp_extract(source_path, '[^/]+$', 0) AS source_file",
        "posexplode(try_cast(parsed:document:elements AS ARRAY<VARIANT>)) AS (element_position, element)"
    )
    .selectExpr(
        "source_path",
        "source_file",
        "element_position",
        "try_cast(element:id AS BIGINT) AS element_id",
        "try_cast(element:type AS STRING) AS element_type",
        "try_cast(element:content AS STRING) AS element_content",
        "try_cast(try_element_at(element:bbox, 1):page_id AS INT) AS page_id"
    )
    .where("element_content IS NOT NULL AND trim(element_content) <> ''")
)

# Add a deterministic ordering key for chunk assembly.
ordinal_window = Window.partitionBy("source_path").orderBy(
    F.col("page_id").asc_nulls_last(),
    F.col("element_id").asc_nulls_last(),
    F.col("element_position").asc_nulls_last(),
    F.col("element_type").asc_nulls_last(),
    F.col("element_content").asc_nulls_last()
)

elements = elements.withColumn("element_ordinal", F.row_number().over(ordinal_window))

raw_table = f"{target_catalog}.{target_schema}.{target_table}_raw"
elements.write.mode("overwrite").format("delta").saveAsTable(raw_table)

error_count = parsed_errors.count()
if error_count > 0:
    print(f"Skipped {error_count} files due to ai_parse_document errors (check parsed:error_status)")

print(f"Parsed {raw_docs.count()} files into {elements.count()} elements")
print(f"Saved parsed elements to {raw_table}")
```

---

## Cell 3: Chunk Content

Route to the correct strategy based on the `chunk_strategy` widget parameter. Generate a single Cell 3 that dispatches to the chosen strategy:

```python
strategy = dbutils.widgets.get("chunk_strategy").strip().lower()
if strategy not in ("page", "token", "semantic"):
    raise ValueError(f"Unknown chunk_strategy: '{strategy}'. Must be one of: page, token, semantic")
```

Then include ONLY the matching strategy code block below.

### Page-Based Chunking

Concatenate ordered elements per page into a single chunk.

```python
# Page-based chunking: one chunk per page with deterministic ordering
from pyspark.sql import functions as F

target_catalog = dbutils.widgets.get("target_catalog")
target_schema = dbutils.widgets.get("target_schema")
target_table = dbutils.widgets.get("target_table")

raw_table = f"{target_catalog}.{target_schema}.{target_table}_raw"
elements = spark.table(raw_table)

chunks = (
    elements
    .groupBy("source_path", "source_file", "page_id")
    .agg(
        F.sort_array(
            F.collect_list(F.struct("element_ordinal", "element_content"))
        ).alias("ordered_elements")
    )
    .withColumn(
        "chunk_text",
        F.expr("concat_ws('\\n\\n', transform(ordered_elements, x -> x.element_content))")
    )
    .where("chunk_text IS NOT NULL AND trim(chunk_text) <> ''")
    .select(
        F.monotonically_increasing_id().alias("chunk_id"),
        "chunk_text",
        "source_file",
        "page_id",
        "source_path",
        F.lit(None).cast("int").alias("chunk_index"),
        F.lit(None).cast("string").alias("section_heading")
    )
)

chunks.createOrReplaceTempView("chunked_documents")
print(f"Created {chunks.count()} page-based chunks")
```

### Token-Based Chunking

Split text into fixed-size token chunks with overlap.

```python
# Token-based chunking with deterministic document order and tokenizer fallback
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, StructField, StructType, StringType, IntegerType

chunk_size = int(dbutils.widgets.get("chunk_size") or "512")
overlap = int(dbutils.widgets.get("chunk_overlap") or "50")

if chunk_size <= 0:
    raise ValueError("chunk_size must be > 0")
if overlap < 0:
    raise ValueError("chunk_overlap must be >= 0")
if overlap >= chunk_size:
    raise ValueError("chunk_overlap must be smaller than chunk_size")

@F.udf(returnType=ArrayType(StructType([
    StructField("chunk_text", StringType()),
    StructField("chunk_index", IntegerType())
])))
def token_chunk(text):
    if text is None:
        return []

    text = text.strip()
    if not text:
        return []

    try:
        import tiktoken

        encoder = tiktoken.get_encoding("cl100k_base")
        tokens = encoder.encode(text)
        step = chunk_size - overlap

        chunks = []
        start = 0
        idx = 0
        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunk_text = encoder.decode(tokens[start:end]).strip()
            if chunk_text:
                chunks.append({"chunk_text": chunk_text, "chunk_index": idx})
            start += step
            idx += 1
        return chunks
    except Exception:
        # Fallback path for clusters where tiktoken is unavailable.
        words = text.split()
        word_chunk_size = max(1, int(round(chunk_size * 1.3)))
        word_overlap = max(0, int(round(overlap * 1.3)))
        word_step = max(1, word_chunk_size - word_overlap)

        chunks = []
        start = 0
        idx = 0
        while start < len(words):
            end = min(start + word_chunk_size, len(words))
            chunk_text = " ".join(words[start:end]).strip()
            if chunk_text:
                chunks.append({"chunk_text": chunk_text, "chunk_index": idx})
            start += word_step
            idx += 1
        return chunks


target_catalog = dbutils.widgets.get("target_catalog")
target_schema = dbutils.widgets.get("target_schema")
target_table = dbutils.widgets.get("target_table")

raw_table = f"{target_catalog}.{target_schema}.{target_table}_raw"
elements = spark.table(raw_table)

doc_text = (
    elements
    .groupBy("source_path", "source_file")
    .agg(
        F.sort_array(
            F.collect_list(F.struct("element_ordinal", "element_content", "page_id"))
        ).alias("ordered_elements")
    )
    .withColumn(
        "full_text",
        F.expr("concat_ws('\\n\\n', transform(ordered_elements, x -> x.element_content))")
    )
    .withColumn(
        "start_page_id",
        F.expr("try_element_at(transform(ordered_elements, x -> x.page_id), 1)")
    )
)

chunks = (
    doc_text
    .withColumn("chunks", F.explode(token_chunk("full_text")))
    .select(
        F.monotonically_increasing_id().alias("chunk_id"),
        F.col("chunks.chunk_text").alias("chunk_text"),
        "source_file",
        F.col("start_page_id").alias("page_id"),
        "source_path",
        F.col("chunks.chunk_index").alias("chunk_index"),
        F.lit(None).cast("string").alias("section_heading")
    )
    .where("chunk_text IS NOT NULL AND trim(chunk_text) <> ''")
)

chunks.createOrReplaceTempView("chunked_documents")
print(
    f"Created {chunks.count()} token-based chunks "
    f"(size={chunk_size}, overlap={overlap})"
)
```

### Semantic Chunking

Chunk by heading/section boundaries using parsed layout metadata.

```python
# Semantic chunking with deterministic ordering and page-based fallback
from pyspark.sql import functions as F
from pyspark.sql.window import Window

target_catalog = dbutils.widgets.get("target_catalog")
target_schema = dbutils.widgets.get("target_schema")
target_table = dbutils.widgets.get("target_table")

raw_table = f"{target_catalog}.{target_schema}.{target_table}_raw"
elements = spark.table(raw_table)

heading_window = Window.partitionBy("source_path").orderBy("element_ordinal")

sectioned = (
    elements
    .withColumn(
        "is_heading",
        F.when(
            F.lower(F.col("element_type")).isin("title", "section_header", "heading"),
            F.lit(1)
        ).otherwise(F.lit(0))
    )
    .withColumn("section_id", F.sum("is_heading").over(heading_window))
)

heading_count = sectioned.where(F.col("is_heading") == 1).limit(1).count()

if heading_count == 0:
    print("No headings detected; falling back to page-based chunking")
    chunks = (
        elements
        .groupBy("source_path", "source_file", "page_id")
        .agg(
            F.sort_array(
                F.collect_list(F.struct("element_ordinal", "element_content"))
            ).alias("ordered_elements")
        )
        .withColumn(
            "chunk_text",
            F.expr("concat_ws('\\n\\n', transform(ordered_elements, x -> x.element_content))")
        )
        .where("chunk_text IS NOT NULL AND trim(chunk_text) <> ''")
        .select(
            F.monotonically_increasing_id().alias("chunk_id"),
            "chunk_text",
            "source_file",
            "page_id",
            "source_path",
            F.lit(None).cast("int").alias("chunk_index"),
            F.lit(None).cast("string").alias("section_heading")
        )
    )
else:
    chunks = (
        sectioned
        .groupBy("source_path", "source_file", "section_id")
        .agg(
            F.sort_array(
                F.collect_list(
                    F.struct(
                        "element_ordinal",
                        "is_heading",
                        "element_content",
                        "page_id"
                    )
                )
            ).alias("ordered_elements")
        )
        .withColumn(
            "chunk_text",
            F.expr("concat_ws('\\n\\n', transform(ordered_elements, x -> x.element_content))")
        )
        .withColumn(
            "section_heading",
            F.expr(
                "try_element_at("
                "transform(filter(ordered_elements, x -> x.is_heading = 1), x -> x.element_content), 1"
                ")"
            )
        )
        .withColumn(
            "page_id",
            F.expr("try_element_at(transform(ordered_elements, x -> x.page_id), 1)")
        )
        .where("chunk_text IS NOT NULL AND trim(chunk_text) <> ''")
        .select(
            F.monotonically_increasing_id().alias("chunk_id"),
            "chunk_text",
            "source_file",
            "page_id",
            "source_path",
            F.lit(None).cast("int").alias("chunk_index"),
            "section_heading"
        )
    )

chunks.createOrReplaceTempView("chunked_documents")
print(f"Created {chunks.count()} semantic chunks")
```

---

## Cell 4: Write Delta Table

Write the chunked data as a Delta table with Change Data Feed enabled (required for VS delta-sync).

```sql
-- Create the final chunked documents table
CREATE OR REPLACE TABLE ${target_catalog}.${target_schema}.${target_table} (
  chunk_id BIGINT GENERATED ALWAYS AS IDENTITY,
  chunk_text STRING NOT NULL,
  source_file STRING,
  page_id INT,
  source_path STRING,
  chunk_index INT,
  section_heading STRING
)
TBLPROPERTIES (delta.enableChangeDataFeed = true);

-- Insert chunked data from the selected strategy
INSERT INTO ${target_catalog}.${target_schema}.${target_table}
  (chunk_text, source_file, page_id, source_path, chunk_index, section_heading)
SELECT chunk_text, source_file, page_id, source_path, chunk_index, section_heading
FROM chunked_documents;

SELECT count(*) AS total_chunks
FROM ${target_catalog}.${target_schema}.${target_table};
```

---

## Cell 5: Create Vector Search Index

### Option A: Managed Embeddings (Recommended)

```python
from databricks.vector_search.client import VectorSearchClient
import time

vs_endpoint = dbutils.widgets.get("vs_endpoint")
index_name = dbutils.widgets.get("vs_index")
embedding_model = dbutils.widgets.get("embedding_model")
target_catalog = dbutils.widgets.get("target_catalog")
target_schema = dbutils.widgets.get("target_schema")
target_table = dbutils.widgets.get("target_table")

source_table = f"{target_catalog}.{target_schema}.{target_table}"
vsc = VectorSearchClient()

# Create endpoint (or reuse if it already exists)
try:
    vsc.create_endpoint(name=vs_endpoint, endpoint_type="STANDARD")
    print(f"Created endpoint: {vs_endpoint}")
except Exception as e:
    if "already exists" in str(e).lower():
        print(f"Endpoint '{vs_endpoint}' already exists, reusing")
    else:
        raise

# Create index (or reuse) and trigger a sync
try:
    vsc.create_delta_sync_index(
        endpoint_name=vs_endpoint,
        source_table_name=source_table,
        index_name=index_name,
        pipeline_type="TRIGGERED",
        primary_key="chunk_id",
        embedding_source_column="chunk_text",
        embedding_model_endpoint_name=embedding_model,
        columns_to_sync=[
            "chunk_id",
            "chunk_text",
            "source_file",
            "page_id",
            "source_path",
            "chunk_index",
            "section_heading"
        ]
    )
    print(f"Created index: {index_name}")
except Exception as e:
    if "already exists" in str(e).lower():
        print(f"Index '{index_name}' already exists, reusing")
    else:
        raise

idx = vsc.get_index(index_name=index_name)
idx.sync()

MAX_WAIT_SECONDS = 1800  # 30-minute timeout
elapsed = 0
while elapsed < MAX_WAIT_SECONDS:
    status = idx.describe().get("status", {})
    if status.get("ready", False):
        print("Index is ready")
        break

    detailed_state = str(status.get("detailed_state", "")).upper()
    if detailed_state in {"FAILED", "ERROR"}:
        raise RuntimeError(f"Index sync failed: {status}")

    print(f"Index status: {status.get('message', 'syncing')} ({elapsed}s elapsed)")
    time.sleep(30)
    elapsed += 30
    idx = vsc.get_index(index_name=index_name)
else:
    raise TimeoutError(f"Index sync did not complete within {MAX_WAIT_SECONDS}s. Last status: {status}")
```

### Option B: Pre-Computed Embeddings

Use this when embeddings already exist in a source column.

```python
from databricks.vector_search.client import VectorSearchClient

vs_endpoint = dbutils.widgets.get("vs_endpoint")
index_name = dbutils.widgets.get("vs_index")
target_catalog = dbutils.widgets.get("target_catalog")
target_schema = dbutils.widgets.get("target_schema")
target_table = dbutils.widgets.get("target_table")

source_table = f"{target_catalog}.{target_schema}.{target_table}"
vsc = VectorSearchClient()

vsc.create_delta_sync_index(
    endpoint_name=vs_endpoint,
    source_table_name=source_table,
    index_name=index_name,
    pipeline_type="TRIGGERED",
    primary_key="chunk_id",
    embedding_dimension=1024,             # adjust for your embedding model
    embedding_vector_column="embedding"  # pre-computed vector column
)
```
