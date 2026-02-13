# Notebook Cell Templates

SQL templates for each cell in the parse-documents notebook. Replace `${PARAM}` placeholders with user-provided values.

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
CREATE WIDGET TEXT embedding_model DEFAULT 'databricks-gte-large-en';
```

---

## Cell 2: Parse Documents

Use PySpark to load binary files and apply `ai_parse_document`.

```python
# Parse documents from UC Volume using ai_parse_document
from pyspark.sql import functions as F

# Load binary files from the volume
raw_docs = (
    spark.read.format("binaryFile")
    .option("pathGlobFilter", "*.{pdf,docx,pptx,doc,ppt,jpg,jpeg,png}")
    .load(getArgument("source_volume"))
)

# Apply ai_parse_document and extract elements
parsed = raw_docs.selectExpr(
    "path AS source_path",
    "ai_parse_document(content, map('version', '2.0')) AS parsed"
)

# Flatten to elements with page info
elements = parsed.selectExpr(
    "source_path",
    "regexp_extract(source_path, '[^/]+$', 0) AS source_file",
    "inline(parsed:document:elements)"
).select(
    "source_path",
    "source_file",
    F.col("type").alias("element_type"),
    F.col("content").alias("element_content"),
    F.col("page").alias("page_id")
)

# Save raw parsed elements
raw_table = f"{getArgument('target_catalog')}.{getArgument('target_schema')}.{getArgument('target_table')}_raw"
elements.write.mode("overwrite").saveAsTable(raw_table)

print(f"Parsed {raw_docs.count()} documents into {elements.count()} elements")
print(f"Saved to {raw_table}")
```

---

## Cell 3: Chunk Content

Choose ONE of the three strategies below based on the `chunk_strategy` parameter.

### Page-Based Chunking

Concatenate all elements per page into a single chunk.

```python
# Page-based chunking: one chunk per page
from pyspark.sql import functions as F
from pyspark.sql.window import Window

raw_table = f"{getArgument('target_catalog')}.{getArgument('target_schema')}.{getArgument('target_table')}_raw"
elements = spark.table(raw_table)

chunks = (
    elements
    .groupBy("source_path", "source_file", "page_id")
    .agg(
        F.concat_ws("\n\n", F.collect_list("element_content")).alias("chunk_text"),
        F.count("*").alias("element_count")
    )
    .withColumn("chunk_id", F.monotonically_increasing_id())
    .select("chunk_id", "chunk_text", "source_file", "page_id", "source_path")
)

chunks.createOrReplaceTempView("chunked_documents")
print(f"Created {chunks.count()} page-based chunks")
```

### Token-Based Chunking

Split text into fixed-size token chunks with overlap.

```python
# Token-based chunking with overlap
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType, StructType, StructField, StringType, IntegerType
import tiktoken

CHUNK_SIZE = 512    # tokens per chunk
OVERLAP = 50        # overlap tokens between chunks

@F.udf(returnType=ArrayType(StructType([
    StructField("chunk_text", StringType()),
    StructField("chunk_index", IntegerType())
])))
def token_chunk(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP):
    if not text:
        return []
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    start = 0
    idx = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_text = enc.decode(tokens[start:end])
        chunks.append({"chunk_text": chunk_text, "chunk_index": idx})
        start += chunk_size - overlap
        idx += 1
    return chunks

raw_table = f"{getArgument('target_catalog')}.{getArgument('target_schema')}.{getArgument('target_table')}_raw"
elements = spark.table(raw_table)

# Concatenate all elements per document, then chunk
doc_text = (
    elements
    .groupBy("source_path", "source_file")
    .agg(
        F.concat_ws("\n\n", F.collect_list("element_content")).alias("full_text"),
        F.min("page_id").alias("start_page")
    )
)

chunks = (
    doc_text
    .withColumn("chunks", F.explode(token_chunk("full_text")))
    .select(
        F.monotonically_increasing_id().alias("chunk_id"),
        F.col("chunks.chunk_text").alias("chunk_text"),
        "source_file",
        "source_path",
        F.col("chunks.chunk_index").alias("chunk_index")
    )
)

chunks.createOrReplaceTempView("chunked_documents")
print(f"Created {chunks.count()} token-based chunks (size={CHUNK_SIZE}, overlap={OVERLAP})")
```

**Note:** `tiktoken` must be installed on the cluster. If unavailable, fall back to whitespace-based splitting:
```python
# Fallback: approximate token count using whitespace split
words = text.split()
# ~1.3 words per token is a rough approximation
```

### Semantic Chunking

Chunk by heading/section boundaries using parsed layout metadata.

```python
# Semantic chunking: split by headings/sections
from pyspark.sql import functions as F
from pyspark.sql.window import Window

raw_table = f"{getArgument('target_catalog')}.{getArgument('target_schema')}.{getArgument('target_table')}_raw"
elements = spark.table(raw_table)

# Assign section IDs: increment whenever a heading element appears
heading_window = Window.partitionBy("source_path").orderBy("page_id")

sectioned = (
    elements
    .withColumn(
        "is_heading",
        F.when(F.col("element_type").isin("title", "section_header", "heading"), 1).otherwise(0)
    )
    .withColumn("section_id", F.sum("is_heading").over(heading_window))
)

# Group elements by section
chunks = (
    sectioned
    .groupBy("source_path", "source_file", "section_id")
    .agg(
        F.concat_ws("\n\n", F.collect_list("element_content")).alias("chunk_text"),
        F.first("page_id").alias("page_id"),
        F.first(
            F.when(F.col("is_heading") == 1, F.col("element_content"))
        ).alias("section_heading")
    )
    .withColumn("chunk_id", F.monotonically_increasing_id())
    .select("chunk_id", "chunk_text", "source_file", "page_id", "section_heading", "source_path")
)

# If no headings were found, fall back to page-based
heading_count = sectioned.filter(F.col("is_heading") == 1).count()
if heading_count == 0:
    print("No headings detected — falling back to page-based chunking")
    chunks = (
        elements
        .groupBy("source_path", "source_file", "page_id")
        .agg(F.concat_ws("\n\n", F.collect_list("element_content")).alias("chunk_text"))
        .withColumn("chunk_id", F.monotonically_increasing_id())
        .select("chunk_id", "chunk_text", "source_file", "page_id", "source_path")
    )

chunks.createOrReplaceTempView("chunked_documents")
print(f"Created {chunks.count()} semantic chunks from {heading_count} sections")
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
  page_id STRING,
  source_path STRING
)
TBLPROPERTIES (delta.enableChangeDataFeed = true);

-- Insert chunked data
INSERT INTO ${target_catalog}.${target_schema}.${target_table}
  (chunk_text, source_file, page_id, source_path)
SELECT chunk_text, source_file, page_id, source_path
FROM chunked_documents;

SELECT count(*) AS total_chunks FROM ${target_catalog}.${target_schema}.${target_table};
```

---

## Cell 5: Create Vector Search Index

### Option A: Managed Embeddings (Recommended)

```python
from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient()

# Create endpoint (skip if reusing existing)
try:
    vsc.create_endpoint(
        name=getArgument("vs_endpoint"),
        endpoint_type="STANDARD"
    )
    print(f"Created endpoint: {getArgument('vs_endpoint')}")
except Exception as e:
    if "already exists" in str(e).lower():
        print(f"Endpoint '{getArgument('vs_endpoint')}' already exists, reusing")
    else:
        raise

# Create delta-sync index with managed embeddings
source_table = f"{getArgument('target_catalog')}.{getArgument('target_schema')}.{getArgument('target_table')}"
index_name = getArgument("vs_index")

index = vsc.create_delta_sync_index(
    endpoint_name=getArgument("vs_endpoint"),
    source_table_name=source_table,
    index_name=index_name,
    pipeline_type="TRIGGERED",
    primary_key="chunk_id",
    embedding_source_column="chunk_text",
    embedding_model_endpoint_name=getArgument("embedding_model"),
)

print(f"Created index: {index_name}")
print("Syncing... this may take several minutes depending on data size.")

# Wait for index to be ready
import time
idx = vsc.get_index(index_name=index_name)
while not idx.describe().get("status", {}).get("ready", False):
    print("Index syncing...")
    time.sleep(30)
    idx = vsc.get_index(index_name=index_name)

print("Index is ready!")
```

### Option B: Pre-Computed Embeddings

Use this if embeddings are already computed in a column.

```python
from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient()

source_table = f"{getArgument('target_catalog')}.{getArgument('target_schema')}.{getArgument('target_table')}"
index_name = getArgument("vs_index")

index = vsc.create_delta_sync_index(
    endpoint_name=getArgument("vs_endpoint"),
    source_table_name=source_table,
    index_name=index_name,
    pipeline_type="TRIGGERED",
    primary_key="chunk_id",
    embedding_dimension=1024,        # adjust to match your model
    embedding_vector_column="embedding"  # column containing vectors
)
```
