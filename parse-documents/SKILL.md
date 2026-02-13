---
name: parse-documents
description: "Parse documents and create a Databricks Vector Search index for RAG. Use when: (1) User wants to parse PDFs, DOCX, PPTX, or images into structured text, (2) User says 'parse documents', 'create vector search index', 'build RAG pipeline', 'chunk documents', (3) User needs to go from raw documents in a UC Volume to a searchable Vector Search index, (4) User asks about ai_parse_document or document chunking strategies. Generates a Databricks SQL notebook that runs the full pipeline: ai_parse_document → chunk → Delta table → Vector Search endpoint/index."
---

# Parse Documents → Vector Search Index

Generate a Databricks SQL notebook that parses documents from a UC Volume using `ai_parse_document`, chunks the extracted content, writes to a Delta table, and creates a Vector Search index.

## Prerequisites

- Documents stored in a Unity Catalog Volume
- Databricks Runtime 17.1+ (or serverless env version 3+)
- Workspace in US/EU region with AI Functions enabled
- Unity Catalog enabled with serverless compute

## Workflow

### Step 1: Gather User Inputs

Collect these before generating the notebook:

| Parameter | Example | Required |
|-----------|---------|----------|
| Source volume path | `/Volumes/catalog/schema/docs` | Yes |
| Target catalog.schema | `my_catalog.my_schema` | Yes |
| Target table name | `parsed_documents` | Yes |
| VS endpoint name | `vs_endpoint` | Yes (create or reuse) |
| VS index name | `catalog.schema.docs_index` | Yes |
| Chunking strategy | `page`, `token`, `semantic` | Yes |
| Embedding approach | `compute` (Databricks-managed) or `pre-computed` | Yes |
| Embedding model | `databricks-gte-large-en` | If compute |

### Step 2: Generate Notebook Cells

The notebook has 5 sections. See [references/notebook_cells.md](references/notebook_cells.md) for the complete SQL templates for each cell.

**Cell 1 — Configuration**: Parameters widget with all user inputs.

**Cell 2 — Parse**: Load binary files with `binaryFile` reader, apply `ai_parse_document`, extract elements array into a raw parsed table.

**Cell 3 — Chunk**: Apply the chosen chunking strategy to the parsed elements. See [references/chunking_strategies.md](references/chunking_strategies.md) for all three strategies.

**Cell 4 — Write Delta Table**: Create the final chunked table with `id`, `chunk_text`, `source_file`, `page_number`, and metadata columns. Enable Change Data Feed (required for delta-sync indexes).

**Cell 5 — Create VS Index**: Create endpoint (if new), create delta-sync index with managed embeddings, trigger sync.

### Step 3: Verify

After the user runs the notebook, verify the index is ready:

```sql
SELECT * FROM vector_search('catalog.schema.docs_index', 'test query', num_results => 3)
```

## Chunking Strategy Selection

| Strategy | Best for | How it works |
|----------|----------|-------------|
| **Page-based** | Short docs, slide decks, forms | One chunk per page. Natural fit since `ai_parse_document` returns per-page elements. |
| **Token-based** | Long-form text, articles, reports | Fixed token-size chunks (default 512) with configurable overlap (default 50). Splits across page boundaries. |
| **Semantic** | Structured docs with headings | Chunks by heading/section boundaries from parsed layout metadata. Falls back to page-based for docs without headings. |

Default recommendation: **page-based** for most use cases. Use token-based for long documents where pages contain too much text for effective retrieval.

## Embedding Options

| Approach | When to use | Notes |
|----------|------------|-------|
| **Compute (managed)** | Default. Let Databricks handle embeddings. | Use `databricks-gte-large-en` (recommended). No extra setup. |
| **Pre-computed** | Already have embeddings or need a custom model. | Must provide `embedding_dimension` and `embedding_vector_column`. |

## Supported File Formats

`ai_parse_document` accepts: **PDF, JPG/JPEG, PNG, DOC/DOCX, PPT/PPTX**

## Limitations

- Optimized for English text; non-Latin alphabets may have lower quality
- Dense, low-resolution content may cause errors or slow processing
- Tables are returned as HTML (version 2.0 schema)
- Digital signatures may not process accurately

## Next Steps

After the index is created:
1. **Add as agent tool** — See **add-tools** skill to wire the VS index into your agent and grant permissions in `databricks.yml`
2. **Discover the index** — Run `uv run discover-tools` to see the new index and its MCP URL
3. **Test retrieval** — Use the `vector_search()` SQL function or query via the agent
