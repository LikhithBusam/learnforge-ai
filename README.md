# LearnForge AI — AI-Powered Learning & Growth Workspace

> An enterprise-grade, AI-native study companion that turns raw learning materials into an adaptive, evidence-grounded tutoring experience — from ingestion to mastery.

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB?style=flat-square&logo=react)](https://vitejs.dev/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%20%2B%20pgvector-336791?style=flat-square&logo=postgresql)](https://github.com/pgvector/pgvector)
[![Redis](https://img.shields.io/badge/Queue-Redis%20%2B%20Celery-DC382D?style=flat-square&logo=redis)](https://redis.io/)
[![Gemini](https://img.shields.io/badge/AI-Google%20Gemini%202.5%20Flash-4285F4?style=flat-square&logo=google)](https://deepmind.google/technologies/gemini/)

---

## What Is This?

**LearnForge AI** is a full-stack, production-quality learning platform where students upload their own study materials (PDFs, DOCX, text) and immediately gain access to:

- **AI Tutor** — Ask questions, get answers grounded in your materials with page-accurate citations. The tutor refuses to speculate when evidence is insufficient.
- **Adaptive Assessment** — Auto-generated quizzes with AI grading and detailed feedback.
- **Mastery Engine** — Bayesian Knowledge Tracing (BKT) tracks concept-level mastery over time.
- **Growth Analytics** — Learning velocity, streak tracking, and progress insights.
- **Recommendations** — Personalized next-step suggestions based on weak concepts and study patterns.

---

## Architecture Overview

```
React + Vite (packages/web)
        │
        ▼ HTTPS / REST + SSE
FastAPI (apps/api)  ◄──► Celery Worker (apps/worker)
        │                       │
        ├── PostgreSQL + pgvector  (vector + relational store)
        ├── Redis               (task queue + cache)
        ├── Supabase Storage    (file store)
        └── AI Gateway ──► Google Gemini 2.5 Flash
                           (generation · embeddings · structured output)
```

**Design principles:**
- **Project-isolated**: All data is scoped to `Space → Project`. Row-Level Security enforced throughout.
- **Evidence-grounded AI**: Every tutor answer cites source chunks; structural refusal when retrieval score is below threshold.
- **Hybrid RAG**: Dense (pgvector cosine) + Sparse (BM25) retrieval, fused and reranked before generation.
- **Modular monolith**: One deployable FastAPI service, module-per-contract under `src/app/<module>/`.
- **Observable**: Structured JSON logging, Celery task monitoring, admin dashboard with system health metrics.

---

## Repository Layout

```
apps/
  api/        FastAPI application (module-per-contract under src/app/<module>)
  worker/     Celery worker + Beat entrypoints (same codebase, different entry)
packages/
  contracts/  Shared, technology-neutral DTOs and protocol interfaces
  web/        React + Vite frontend (production-ready)
infra/        docker-compose (postgres+pgvector, redis) + env templates
tests/        unit · integration · boundary · E2E (Phase 11 & 13 suites)
docs/         Requirements, architecture, evaluation, and engineering docs
scripts/      Developer tooling (boundary enforcement, etc.)
```

---

## Phase Completion Status

| Phase | Capability | Status |
|-------|-----------|--------|
| 1 | Identity + Workspace (Spaces & Projects) | ✅ Complete |
| 2 | Authentication (JWT, refresh tokens) | ✅ Complete |
| 3 | Materials + RAG Ingestion (Celery pipeline) | ✅ Complete |
| 4 | Hybrid RAG + AI Tutor (pgvector + BM25 + Gemini) | ✅ Complete |
| 5 | Adaptive Assessment (generation + AI grading) | ✅ Complete |
| 6 | Mastery Engine (Bayesian Knowledge Tracing) | ✅ Complete |
| 7 | Growth Engine (streaks, velocity, milestones) | ✅ Complete |
| 8 | Recommendation Engine | ✅ Complete |
| 9 | Analytics + Learner Progress | ✅ Complete |
| 10 | Admin + System Observability | ✅ Complete |
| 11 | Full E2E Integration, AI Evaluation & Production Validation | ✅ Complete |
| 12 | Production Frontend & Full-Stack Integration | ✅ Complete |
| 13 | API Contract, Database & Real RAG Verification | ✅ Complete |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- A Google Gemini API key

### 1. Clone & Configure

```bash
git clone https://github.com/LikhithBusam/learnforge-ai.git
cd learnforge-ai
cp .env.example .env.development
# Fill in GEMINI_API_KEY, DATABASE_URL, REDIS_URL, and Supabase credentials
```

### 2. Start Infrastructure

```bash
docker compose -f infra/docker-compose.yml up -d
```

### 3. Run the Backend

```bash
cd apps/api
pip install -e ".[dev]"
uvicorn src.app.main:app --reload --port 8000
```

### 4. Run the Celery Worker

```bash
# In a separate terminal from the project root
celery -A apps.worker.celery_app worker --loglevel=info
```

### 5. Run the Frontend

```bash
cd packages/web
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) to access the application.

Backend API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Key Technical Highlights

| Area | Implementation |
|------|---------------|
| **Vector Search** | pgvector with 1536-dim Gemini embeddings, cosine similarity |
| **Hybrid Retrieval** | BM25 sparse + dense vector fusion with reciprocal rank fusion |
| **AI Provider** | Google Gemini 2.5 Flash via pluggable `ProviderAdapter` gateway |
| **Structured Output** | Gemini `response_schema` for deterministic JSON generation |
| **Mastery Tracking** | Bayesian Knowledge Tracing (BKT) per concept per learner |
| **Background Jobs** | Celery + Redis for document chunking, embedding, and ingestion |
| **Auth** | JWT access + refresh token rotation, bcrypt password hashing |
| **Storage** | Supabase Storage for uploaded learning materials |
| **Observability** | Structured JSON logging with correlation IDs throughout |

---

## Documentation

- Architecture decisions — `docs/architecture/architecture-decisions.md`
- Module contracts — `docs/architecture/module-contracts.md`
- Technology baseline — `docs/architecture/technology-baseline.md`
- Evaluation strategy — `docs/evaluation/evaluation-strategy.md`
- Security baseline — `docs/engineering/security-baseline.md`
- Full-stack integration report — `PHASE_13_FULL_STACK_INTEGRATION_VERIFICATION.md`

---

## License

MIT
