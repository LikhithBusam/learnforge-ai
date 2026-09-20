# Local Development & Service Architecture

This document describes how to run and develop the **AI Study Companion** application locally.

---

## 1. Prerequisites

* **Python 3.10+** (Virtual environment recommended)
* **Node.js 18+** / npm
* **PostgreSQL with pgvector** (or configured Supabase project)
* **Redis** (for Celery and cache)

---

## 2. Environment Configuration

Copy or edit `.env.development` in the project root:

```env
APP_ENV=development
LOG_LEVEL=INFO

# PostgreSQL Connection Strings
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>:5432/<dbname>
DATABASE_RUNTIME_URL=postgresql+asyncpg://<runtime_user>:<pass>@<host>:5432/<dbname>

# Redis & Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Storage Provider (Supabase Storage or MinIO)
STORAGE_PROVIDER=supabase
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_SECRET_KEY=<service-role-secret-key>
STORAGE_BUCKET=learning-materials

# AI Provider Configuration
AI_PROVIDER=gemini
GEMINI_API_KEY=<server-side-secret-key>
GEMINI_MODEL=gemini-2.5-flash
AI_EMBEDDING_DIMENSIONS=1536
```

> [!CAUTION]
> Never put `GEMINI_API_KEY`, database passwords, or `SUPABASE_SECRET_KEY` in frontend environment files (`packages/web/.env`). All AI Gateway calls must originate from the FastAPI backend.

---

## 3. Starting the Backend API

```bash
# In project root:
uvicorn apps.api.src.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify backend health:
```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/api/v1/spaces
```

---

## 4. Starting the Background Celery Worker

```bash
celery -A apps.api.src.app.jobs.tasks.celery_app worker -Q documents,learning,analytics,evaluation,default -l info
```

---

## 5. Starting the Frontend (Vite)

```bash
cd packages/web
npm install
npm run dev
```

The application will be accessible at: `http://localhost:5173`.
By default, Vite proxies `/api/v1` to `http://localhost:8000`. You can also configure `VITE_API_BASE_URL=http://localhost:8000/api/v1` in `packages/web/.env`.

---

## 6. Running Tests & Quality Gates

```bash
# Unit tests
pytest tests/unit

# Evaluation tests
pytest tests/evaluation

# Full End-to-End Integration Suite
pytest tests/integration/test_phase13_full_integration.py

# Linting & Typecheck
ruff check .
black --check apps/api/src tests
mypy --explicit-package-bases apps/api/src/app/workspace apps/api/src/app/assessment
python scripts/check_boundaries.py

# Frontend Build
cd packages/web && npm.cmd run build
```
