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

**How it works:** Concatenate all `ai_parse_document` elements belonging to the same page into a single chunk.

**Strengths:**
- Natural alignment with `ai_parse_document` output (elements already have page IDs)
- Tables and figures stay with their surrounding context
- Simple, deterministic

**Weaknesses:**
- Chunk sizes vary widely (sparse page vs dense page)
- Very long pages may exceed embedding model token limits

**When to use:** Default choice. Works well for most document types, especially slide decks, forms, and short-to-medium documents.

---

## Token-Based

**How it works:** Concatenate all document text, then split into fixed-size token chunks with configurable overlap.

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
- Requires tokenizer (tiktoken or fallback to word-based approximation)

**When to use:** Long documents where individual pages contain too much text, or when uniform chunk sizes are important for retrieval quality.

**tiktoken fallback:** If tiktoken is unavailable on the cluster, approximate with whitespace splitting at ~1.3 words per token:
```python
words = text.split()
approx_tokens = len(words) / 1.3
```

---

## Semantic

**How it works:** Use `ai_parse_document` element types to detect heading boundaries. Group consecutive elements under the same heading into a single chunk.

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

**Fallback behavior:** If zero heading elements are detected, the strategy automatically falls back to page-based chunking and logs a warning.

---

## Tuning Parameters

### Token-Based Tuning

| Parameter | Default | Range | Effect |
|-----------|---------|-------|--------|
| `CHUNK_SIZE` | 512 | 256–1024 | Smaller = more precise retrieval, larger = more context per chunk |
| `OVERLAP` | 50 | 0–128 | Higher = less info loss at boundaries, more storage |

**Rule of thumb:** For `databricks-gte-large-en`, keep chunks under 512 tokens for optimal embedding quality.

### General Guidance

- If retrieval quality is poor, try a different strategy or reduce chunk size
- If too many irrelevant results, chunks may be too large — try smaller chunks
- If results lack context, chunks may be too small — try larger chunks or add overlap
- Monitor chunk count: very high counts (>10K) may slow VS index sync
