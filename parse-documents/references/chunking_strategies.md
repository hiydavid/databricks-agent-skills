# Chunking Strategies

Decision guide and implementation details for the three chunking strategies.

## Table of Contents

- [Decision Guide](#decision-guide)
- [Page-Based](#page-based)
- [Token-Based](#token-based)
- [Semantic](#semantic)
- [Tuning Parameters](#tuning-parameters)

---

## Decision Guide

```
Is the document short (<10 pages) or a slide deck?
  → Page-based

Is the document long-form text (articles, reports, manuals)?
  → Token-based (512 tokens, 50 overlap)

Does the document have clear heading structure?
  → Semantic
  → Falls back to page-based if no headings detected
```

### Strategy Comparison

| Strategy | Avg chunk size | Preserves structure | Handles tables | Complexity |
|----------|---------------|-------------------|----------------|------------|
| Page-based | 1 page | Per-page | Yes (within page) | Low |
| Token-based | 512 tokens | No (splits anywhere) | May split tables | Medium |
| Semantic | Variable | Yes (by section) | Yes (within section) | Medium |

---

## Page-Based

**How it works:** Extract `page_id` from `try_element_at(element:bbox, 1):page_id`, then concatenate all elements for that page in deterministic order (`page_id`, `element_id`, fallback `element_ordinal`).

**Strengths:**
- Natural alignment with `ai_parse_document` output and bbox metadata
- Tables and figures stay with their surrounding context
- Simple, deterministic

**Weaknesses:**
- Chunk sizes vary widely (sparse page vs dense page)
- Very long pages may exceed embedding model token limits

**When to use:** Default choice. Works well for most document types, especially slide decks, forms, and short-to-medium documents.

---

## Token-Based

**How it works:** Concatenate each document's elements in deterministic order, then split text into fixed-size token chunks with configurable overlap.

**Default parameters:**
- `CHUNK_SIZE = 512` tokens
- `OVERLAP = 50` tokens

**Strengths:**
- Uniform chunk sizes — consistent retrieval quality
- Overlap prevents information loss at boundaries
- Works regardless of document structure

**Weaknesses:**
- May split mid-sentence or mid-table
- Loses page/section context
- Requires tokenizer support (`tiktoken`) or fallback to word-based chunking

**When to use:** Long documents where individual pages contain too much text, or when uniform chunk sizes are important for retrieval quality.

**tiktoken fallback:** If `tiktoken` is unavailable on the cluster, switch to executable whitespace chunking at ~1.3 words per token:
```python
words = text.split()
word_chunk_size = int(round(chunk_size * 1.3))
word_overlap = int(round(overlap * 1.3))
```

---

## Semantic

**How it works:** Use `ai_parse_document` element types to detect heading boundaries, assign sections with a cumulative sum over deterministic element order (`element_ordinal`), then group consecutive elements under each section.

**Heading element types detected:** `title`, `section_header`, `heading`

**Strengths:**
- Preserves logical document structure
- Chunks are topically coherent
- Better retrieval relevance for structured documents

**Weaknesses:**
- Chunk sizes vary significantly (short heading → small chunk, long section → large chunk)
- Falls back to page-based if no headings are detected
- Relies on `ai_parse_document` correctly identifying heading elements

**When to use:** Technical documentation, manuals, specs, or any document with clear heading hierarchy.

**Fallback behavior:** If zero heading elements are detected, the strategy automatically falls back to the same deterministic page-based chunking implementation and logs a warning.

---

## Tuning Parameters

### Token-Based Tuning

| Parameter | Default | Range | Effect |
|-----------|---------|-------|--------|
| `CHUNK_SIZE` | 512 | 256–1024 | Smaller = more precise retrieval, larger = more context per chunk |
| `OVERLAP` | 50 | 0–128 | Higher = less info loss at boundaries, more storage |

`OVERLAP` must be smaller than `CHUNK_SIZE`; enforce this to avoid infinite loops.

**Rule of thumb:** For `databricks-gte-large-en`, keep chunks under 512 tokens for optimal embedding quality.

### General Guidance

- If retrieval quality is poor, try a different strategy or reduce chunk size
- If too many irrelevant results, chunks may be too large — try smaller chunks
- If results lack context, chunks may be too small — try larger chunks or add overlap
- Monitor chunk count: very high counts (>10K) may slow VS index sync
