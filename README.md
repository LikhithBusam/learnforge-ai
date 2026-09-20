# AI Study Companion — Engineering Workspace

Context-scoped, evidence-grounded learning workspace: Spaces → Projects → materials → AI Tutor with
page-accurate citations and structural refusal on insufficient evidence → adaptive assessment →
deterministic mastery → growth analytics → recommendations. Modular monolith (FastAPI) + Celery worker
plane + Next.js frontend (Phase 0 scaffold).

**Documentation is the source of truth.** Start here:

- Product requirements analysis — `docs/requirements/requirements-analysis.md`
- Architecture decisions — `docs/architecture/architecture-decisions.md` and `docs/architecture/adr/`
- Module contracts — `docs/architecture/module-contracts.md`
- Technology baseline — `docs/architecture/technology-baseline.md`
- Evaluation discipline — `docs/evaluation/evaluation-strategy.md`
- Engineering rules — `docs/engineering/project-principles.md`, `docs/engineering/security-baseline.md`
- **Phase 0 status & how to run — `docs/engineering/phase-0-acceptance.md`, `docs/engineering/local-development.md`**

## Repository layout

```text
apps/
  api/       FastAPI application (module-per-contract under src/app/<module>)
  worker/    Celery worker + Beat entrypoints (same codebase, different entry)
packages/
  contracts/ Shared, technology-neutral DTOs and protocol interfaces
  web/       Next.js frontend (scaffold; implementation is a later phase)
infra/       docker-compose (postgres+pgvector, redis, minio) + env templates
tests/       unit · integration (incl. the traceability vertical slice) · boundary
docs/        Requirements, architecture, evaluation, engineering docs (source of truth)
scripts/     Developer tooling (boundary enforcement, etc.)
```

## Status

**Phases 1–12 Complete & Verified**:
- Phase 1: Identity + Workspace
- Phase 2: Authentication
- Phase 3: Materials + RAG Ingestion
- Phase 4: Hybrid RAG + Tutor
- Phase 5: Assessment
- Phase 6: Mastery Engine (BKT)
- Phase 7: Growth Engine
- Phase 8: Recommendation Engine
- Phase 9: Analytics + Learner Progress
- Phase 10: Admin + System Observability
- Phase 11: Full E2E Integration, AI Evaluation & Production Validation
- Phase 12: Production Frontend & Full-Stack Integration

See `PHASE_12_VERIFICATION_REPORT.md` and `docs/frontend-architecture.md` for full verification details.

## Running the Web Frontend

```powershell
cd packages/web
npm.cmd install
npm.cmd run dev
```
Open `http://localhost:3000` to access the application.
