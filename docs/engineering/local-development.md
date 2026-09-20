# Local Development — Phase 0

## 1. Prerequisites

- **Python 3.10+** (3.12 recommended; CI uses 3.12)
- **Docker + Docker Compose** (infrastructure services)
- **make / bash** (scripts are plain shell commands)
- No AI provider keys are required — the Phase 0 AI registry is `stub` (deterministic, offline).

## 2. Environment setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pip install minio                # optional storage extras used by the MinIO provider
```

## 3. Environment files

`.env.example` is the only env file **committed** (placeholders only — security baseline §1).
Two modes (ADR-0022, cloud-first):

- **Cloud (primary):** create `.env.development` (gitignored) with Supabase Postgres/Storage and
  Upstash Redis values. See ADR-0022 §verified-operational-facts for provider quirks (pooler
  region, `rediss://` + `ssl_cert_reqs`, IPv4 pooler requirement).
- **Local (reproducibility/fallback):** point `DATABASE_URL`/`REDIS_URL` at the Compose services
  and set `STORAGE_PROVIDER=minio` (or clear it for the in-memory dev fallback).

Env files are resolved from the **project root regardless of CWD**, so `cd apps/api && alembic …`
sees the same configuration as the app.

```bash
cp .env.example .env.development  # then fill in your values; never commit this file
```

Dev-only defaults are documented in the file itself (Compose credentials like
`studycompanion_dev_password` are local-only and intentionally not secrets).

## 4. Starting infrastructure

```bash
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml ps   # wait until healthy
```

Services: `postgres` (pgvector/pg16, :5432), `redis` (:6379), `minio` (:9000 API, :9001 console).
Startup order is handled by healthchecks; volumes persist under named volumes (`infra/data/` is gitignored).

## 5. Starting the API

```bash
uvicorn app.main:app --reload --port 8000 --app-dir apps/api/src
```

- Liveness: `GET /healthz`
- Readiness: `GET /readyz` (reports degraded until postgres/redis are reachable)
- AI provider status: `GET /internal/ai/status` (shows `stub` roles)
- OpenAPI: `http://localhost:8000/docs`

## 6. Starting the worker

```bash
python apps/worker/run_worker.py
```

Consumes queues: `documents, learning, analytics, evaluation, default` (one worker in Phase 0;
splitting later is config-only, ADR-0014).

> **Windows note:** Celery's prefork pool is unsupported on Windows; the entrypoint defaults to
> `--pool=solo` there (override with `WORKER_POOL=threads|prefork`). This is a dev-host limitation,
> not an architecture change — CI/Linux uses the default prefork pool.

## 7. Starting Beat

```bash
python apps/worker/run_beat.py
```

Phase 0 schedule: infrastructure heartbeat every 5 minutes.

## 8. Running tests

```bash
pytest tests/unit tests/boundary      # fast gates
pytest tests/integration              # vertical slice (in-memory worker, stub AI — no broker needed)
pytest                                # everything
```

No AI credentials, no Docker required for the test suite (storage falls back to in-memory;
Celery runs `task_always_eager` in the slice test).

## 9. Running lint / type checks

```bash
ruff check apps/api/src tests scripts
black --check apps/api/src tests scripts
mypy apps/api/src/app/platform apps/api/src/app/ai apps/api/src/app/jobs apps/api/src/app/main.py
python scripts/check_boundaries.py    # architecture boundary enforcement
```

## 10. Shutting down infrastructure

```bash
docker compose -f infra/docker-compose.yml down       # keeps volumes
docker compose -f infra/docker-compose.yml down -v    # also wipes dev data
```

## Troubleshooting

- **`Refusing to boot` on API start** — required config missing; you are likely running with
  `APP_ENV=production` or an incomplete `.env`. Use `APP_ENV=development` locally.
- **Readiness degraded** — check `docker compose ps`; postgres/redis must be healthy.
- **Vertical slice fails with broker errors** — the test runs eagerly in-memory; make sure you did
  not set `CELERY_BROKER_URL` to a real Redis in the test environment (the fixture overrides it).
