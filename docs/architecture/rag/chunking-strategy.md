# RAG Chunking Strategy

**Status:** Implemented in `app.knowledge.chunking`.

---

## 1. Objectives

- **Citation Accuracy:** A chunk must never span across page boundaries without explicitly recording `page_start` and `page_end`.
- **Semantic Coherence:** Split by logical paragraphs/blocks (`\n\n`) rather than arbitrary character cuts.
- **Deterministic Ordering:** Assign zero-indexed sequential `chunk_index` to guarantee reproducible ordering.
- **Multilingual Support:** Compatible with English and Arabic learning materials.

---

## 2. Configuration Parameters

| Parameter | Default | Description |
|---|---|---|
| `CHUNK_TARGET_TOKENS` | 500 | Target size for each chunk (~2000 characters). |
| `CHUNK_OVERLAP_RATIO` | 0.15 | Proportional overlap between adjacent chunks within a page (~75 tokens). |

---

## 3. Algorithm

1. **Page Input:** Extracted text is received per page (`page_id`, `page_number`, `text`). Empty or whitespace-only pages are cleanly skipped without generating empty chunks.
2. **Paragraph Segmentation:** Page text is divided into blocks by double newlines (`\n\s*\n`), falling back to single newlines if no double breaks exist.
3. **Block Accumulation:** Paragraphs are accumulated until the character budget (`target_tokens * 4`) is reached.
4. **Overlap Inclusion:** When splitting, the trailing paragraph is carried over into the next chunk if it satisfies the overlap budget (`target_chars * overlap_ratio`), maintaining semantic continuity.
5. **Metadata Assignment:** Each chunk is assigned a new `UUIDv7`, `page_id`, `page_start`, `page_end`, `chunk_index`, token count, and character count.
