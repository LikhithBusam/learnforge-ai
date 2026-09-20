# Phase 3 Materials & Ingestion Test Matrix

| Test Suite | File | Type | Coverage | Result |
|---|---|---|---|---|
| **Chunking Algorithm** | `tests/unit/test_phase3_chunking.py` | Unit | Token estimation, paragraph segmentation, page boundary preservation, sequential indexing. | **PASS** |
| **Upload Policy & Validation** | `tests/unit/test_phase3_materials.py` | Unit | Non-PDF rejection, invalid filename rejection, 0-byte & oversized upload rejection. | **PASS** |
| **End-to-End Ingestion** | `tests/integration/test_phase3_ingestion.py` | Integration (Cloud) | Full pipeline from upload intent to PDF storage, page extraction, chunking, pgvector embedding, and ready state. | **PASS** |
| **RAG Lineage & Traceability** | `tests/integration/test_phase3_rag_traceability.py` | Integration (Cloud) | Hierarchical lineage recovery (`chunk → page → document → material → project`) without reopening the PDF. | **PASS** |
| **Idempotency & Reprocessing** | `tests/integration/test_phase3_idempotency.py` | Integration (Cloud) | Verified zero duplicate chunks/embeddings on repeated document re-ingestion. | **PASS** |
| **RLS Isolation Proofs** | `tests/integration/test_phase3_isolation.py` | Integration (Cloud) | PostgreSQL RLS cross-project read and write blocking on all Phase 3 tables. | **PASS** |
| **Modular Boundaries** | `scripts/check_boundaries.py` | Boundary | Enforces R1-R5 modular architecture rules across all 108 backend files. | **PASS** (0 violations) |
| **Database Migration Cycle** | Alembic `0003` | Migration (Cloud) | Symmetric forward/reverse verification (`upgrade head → downgrade -1 → upgrade head`). | **PASS** |
| **Format & Lint Quality Gates** | `ruff`, `black`, `mypy` | Static Analysis | Code formatting, import hygiene, and strict type checking across implemented domains. | **PASS** |
