# Integration Testing & Verification Guide

This document describes the automated integration testing strategy, execution commands, and verification criteria for **AI Study Companion**.

---

## 1. Test Architecture & Principles

The test harness follows three core invariants:
1. **Zero Mocking in Integration Journeys**: All integration tests interact with real database connections, real RLS enforcement, real storage adapters, and verified AI Gateway paths.
2. **Deterministic Isolation**: Tests create synthetic users (`learner-<uuid>@example.com`) and clean up state without cross-polluting development data.
3. **Multi-Tenant Protection**: Every critical test verifies that User B cannot read or modify User A's projects, spaces, or documents (404 concealment posture).

---

## 2. Test Execution Commands

### Full-Stack End-to-End Suite (Phase 13)
```bash
pytest tests/integration/test_phase13_full_integration.py -v
```
This suite verifies:
* PostgreSQL connection, `pgvector` extension, and table-level RLS enablement
* Complete API Contract: `/auth/register`, `/auth/login`, `/auth/me`, `/spaces`, `/projects`
* PDF upload intent generation, presigned storage upload, checksum verification, and completion
* Knowledge ingestion hierarchy: `documents`, `document_pages`, `chunks`, and `chunk_embeddings`
* Dense vector + BM25 full-text lexical search combined with Reciprocal Rank Fusion (RRF)
* Grounded Tutor conversation with Server-Sent Events (SSE) streaming and citation integrity
* Honest refusal when queries are unsupported by evidence
* Prompt injection neutralization
* Assessment generation, question delivery without answer keys, deterministic MCQ scoring
* Bayesian Knowledge Tracing (BKT) concept mastery progression
* Concept growth trajectory calculation
* Adaptive recommendation generation
* Consolidated analytics event logging and daily rollups
* Error matrix handling (401 unauthenticated, 404 concealed, 422 invalid payload)

### Real Gemini Provider Integration Suite (Phase 12.2)
```bash
pytest tests/integration/test_gemini_provider.py -v
```
Requires `GEMINI_API_KEY` configured in `.env.development`. Verifies:
* Unstructured text generation with token tracking
* Structured JSON generation conforming to Pydantic schemas
* Grounded Tutor answer generation
* Honest refusal handling
* Structured MCQ question generation
* Open-ended answer grading with rubric evaluation
* Invalid API key authentication failure handling

---

## 3. Test Fixture Strategy

* `cloud_settings`: Loads configuration from `.env.development` and validates availability of database URLs.
* `engines`: Initializes async SQLAlchemy engines for both admin operations and user runtime execution.
* `admin_exec`: Provides DDL and administrative cleanup access.
* `seed_user`: Generates isolated, unique test users via the public identity registration API.
* `seed_project`: Atomically generates space and project scopes for the user.
