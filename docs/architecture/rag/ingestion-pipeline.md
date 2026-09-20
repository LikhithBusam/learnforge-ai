# Document Ingestion Pipeline — RAG Foundation

**Scope:** Phase 3 implementation of the asynchronous document parsing, chunking, and embedding architecture.

---

## 1. Pipeline Architecture

```text
Browser / Client
      ↓ (1. POST /api/v1/projects/{id}/materials)
API: Create Material (status='upload_pending') & Presigned PUT URL
      ↓ (2. Direct client PUT to private Supabase Storage)
Private Object Storage (learning-materials bucket)
      ↓ (3. POST /api/v1/projects/{id}/materials/{id}/complete)
API: Verify HEAD, %PDF- magic bytes, SHA-256
      ↓ (4. Celery Task: process_material_document)
Worker Plane (Queue: documents)
      ↓
PDF Extraction (PyMuPDF): page-level text extraction
      ↓
Durable Pages Persisted (document_pages, 1-indexed)
      ↓
Deterministic RAG Chunking (~500 tokens, 15% overlap)
      ↓
AI Gateway: Embedding generation (batch vector calculation)
      ↓
Atomic DB Commit: Document + Pages + Chunks + Embeddings
      ↓
Material Status → READY (Ready for retrieval in Phase 4)
```

---

## 2. Invariants & Guarantees

1. **Grounded Traceability:** Every chunk records `page_id`, `page_start`, and `page_end`. When future Tutor queries retrieve chunks, citations resolve instantly to `Material Title — Page N` without re-opening the PDF.
2. **PostgreSQL as Single Store of Record:** Relational structure, full-text search (`tsvector` with GIN), and semantic vectors (`pgvector` with HNSW cosine index) exist in the same database transaction.
3. **Multi-tenant Project Isolation:** Every table in the ingestion tree carries `project_id` and `owner_id`, strictly guarded by PostgreSQL Row-Level Security (`studycompanion_runtime` role).
4. **Idempotency & Re-processing:** Rerunning or retrying an ingestion cleans up previous parsed artifacts for that material in a single transaction, preventing stale or duplicate chunks.
