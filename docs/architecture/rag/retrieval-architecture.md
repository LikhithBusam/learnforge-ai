# RAG Retrieval Architecture (Phase 4)

## 1. Overview

The RAG Retrieval subsystem in the AI Study Companion provides a project-scoped, independently testable evidence retrieval engine.
It operates as an independent service in `app.knowledge.service` before context composition and Tutor generation.

```text
User Question
      ↓
Query Preprocessing (Unicode / Multilingual preserved)
      ↓
Hybrid Retrieval
   ↙          ↘
Vector Retrieval      PostgreSQL FTS
(pgvector cosine)       (tsvector + GIN)
   ↓                     ↓
   └────── Reciprocal Rank Fusion (k=60) ──────┘
                         ↓
                 Candidate Evidence
                         ↓
               AI Gateway Reranker
                         ↓
             Evidence Sufficiency Decision
                 ↙             ↘
            SUPPORTED       INSUFFICIENT
```

---

## 2. Invariants

1. **Strict Project Isolation:** Every retrieval query enforces `project_id` and `owner_id` inside SQL statements and PostgreSQL Row-Level Security (`studycompanion_runtime` role).
2. **First-Class Subsystem:** Retrieval does not depend on the LLM or Tutor. It can be invoked, benchmarked, and evaluated standalone.
3. **Multilingual Unicode Preservation:** The query preprocessor never forces ASCII conversion or destructive English-only lowercasing, ensuring Arabic and Latin learning materials remain searchable.
4. **Citation Grounding:** Returned evidence chunks preserve complete lineage: `chunk_id`, `document_id`, `material_id`, `page_start`, `page_end`, and `chunk_index`.
