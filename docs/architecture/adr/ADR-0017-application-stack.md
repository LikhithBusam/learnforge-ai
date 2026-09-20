# ADR-0017: Application Stack — FastAPI Backend + Next.js/TypeScript Frontend

**Status:** DECIDED (Phase 0) · **Criteria basis:** C1, C4, C5, C9 dominant · **Resolves:** deferred "application frameworks" rows · **Contracts affected:** all module contracts (implemented on this stack); Tutor streaming (§M.5 SSE events)

## Decision

- **Backend: Python 3.12 + FastAPI**, with Pydantic v2 for all boundary validation (API, tool arguments, and LLM structured output — one schema language, principle §4), async SQLAlchemy 2.0 + Alembic for data access/migrations (behind the Platform unit-of-work abstraction; module contracts stay storage-agnostic).
- **Frontend: Next.js (App Router) + TypeScript**, TanStack Query for server state (polling job status), native SSE for Tutor streaming, Tailwind + shadcn/Radix-class UI kit (UI kit final call is a build-start detail, not an architecture decision).
- **One language across API and workers (Python)**; the frontend is the only TypeScript surface.

## Backend options considered

### Option 1 — FastAPI ✅
- **Advantages:** native async — required for SSE streaming + concurrent provider fan-out (Tutor TTFT posture); Pydantic validation is first-class (the same validator guards API input and model output — a direct implementation of principle §4/FR-42); automatic OpenAPI feeds the generated frontend client (ADR-0011); dependency injection maps cleanly onto the auth/RLS scope guards (ADR-0002); the AI/document ecosystem (PyMuPDF-class parsing, OCR bindings, provider SDKs, eval tooling) is Python-native (C4).
- **Disadvantages:** team owns process management (Gunicorn/Uvicorn-class); fewer batteries than Django (admin UI, auth app) — irrelevant here since admin is a bespoke read-only plane and auth is self-hosted by explicit ADR (ADR-0018).

### Option 2 — Django + DRF
- **Advantages:** batteries included (ORM, admin, auth); mature.
- **Disadvantages:** async streaming is not its natural posture (SSE Tutor turns fight the framework); DRF's serializer layer duplicates the Pydantic validation story; heavier conventions to bend toward the module-facade architecture; admin auto-UI is the wrong shape (read-only analytic plane, A-01/A-05). Rejected on C5 (velocity toward *this* architecture) despite genuine maturity.

### Option 3 — Node/TypeScript end-to-end (NestJS-class)
- **Advantages:** one language across the whole stack.
- **Disadvantages:** document/AI toolchain (PDF layout parsing, OCR, eval harnesses) is Python-first — a split stack would duplicate domain models and validation across languages (the exact duplication the modular monolith exists to avoid); async provider fan-out is fine but the ingestion pipeline ecosystem is weaker. Rejected on C4.

### Option 4 — Flask (+ extensions)
- **Advantages:** minimal, familiar.
- **Disadvantages:** async/streaming/validation/OpenAPI/DI all hand-assembled from extensions — assembly cost inside a 4-day window with no compensating capability. Rejected on C1/C5.

### Option 5 — Go backend
- **Advantages:** raw throughput, single binary.
- **Disadvantages:** weakest AI/document ecosystem of the candidates (C4 fail); longer time-to-feature for validation-heavy contract code. Rejected.

## Frontend options considered

### Option 1 — Next.js (App Router) + TypeScript ✅
- **Advantages:** server components fit the dashboard-heavy read pages (home/space/project/admin are aggregation surfaces — fewer client round trips); one framework covers SSR + routing + a thin BFF for the refresh-cookie flow (ADR-0018); SSE via native fetch streams/EventSource; generated typed client from OpenAPI (contract-drift is a CI failure, not a runtime surprise); polling with backoff for job status is a first-class TanStack Query use case (FR-23/§13 "browser may close").
- **Disadvantages:** framework pace/churn; server/client component boundary is a discipline; more opinionated than a raw SPA.

### Option 2 — React + Vite + TypeScript (SPA)
- **Advantages:** simplest build; no server runtime to deploy (static hosting).
- **Disadvantages:** all dashboards become client-fetch pages (worse first paint on aggregate-heavy views); BFF/cookie handling must be built separately or abandoned in favor of header-token-only auth; no SSR benefits for the admin/analytics surfaces. Viable second choice — acceptable if team familiarity strongly favors it, but Next.js wins on the dashboard read model (C5) and the cookie-session flow.

### Option 3 — Server-rendered templates (HTMX-class)
- **Advantages:** minimal client complexity; fast for forms/dashboards.
- **Disadvantages:** streaming chat UI with citation events + optimistic updates is exactly where this approach fights back; quiz interactivity suffers. Rejected on C5 for *this* product shape.

## Reasoning made explicit (not "industry standard")

1. **Streaming is a first-class requirement** (FR-36) — FastAPI's async response model and Next.js's stream consumption both treat SSE as ordinary HTTP, matching ADR-0010's SSE-over-WebSockets decision.
2. **Validation uniformity is a security control** — Pydantic at API + tool + model-output boundaries means "untrusted input is schema-validated" has one implementation, one audit point (principles §4/§5).
3. **The ingestion pipeline dictates the backend language** — PyMuPDF-class parsing, Tesseract-class OCR escalation, and provider/eval SDKs are Python-native; choosing Python for the API keeps the monolith whole (ADR-0001) instead of splitting API and workers across languages.
4. **Dashboards are the UI's center of gravity** (FR-11/13/15/71/72/90) — server components + rollup-backed reads fit naturally; a client-heavy SPA re-creates this with more plumbing.
5. **Deployment shape** — both choices containerize cleanly; the same API image serves API and worker entrypoints (ADR-0019).

## Prototype vs production notes

| Aspect | Phase 0 (PROTOTYPE ONLY) | Later (FUTURE TRIGGER) |
|---|---|---|
| Frontend rendering | Next.js standalone container on the platform | Edge/CDN tuning, ISR for admin exports if ever needed |
| API process model | Uvicorn workers under a Gunicorn-class supervisor | Tuned worker/async mix under measured load (A-10 → measured) |
| Type sharing | OpenAPI → generated client in CI | Contract tests + client versioning if the API grows consumers |

## Consequences

- (+) Fastest correct path to the fixed contracts; one validation language; Python-native AI/document ecosystem; frontend typing generated, not hand-maintained.
- (−) Two languages in the repo (Python + TypeScript) with the contract bridged by generated client (accepted, bounded); FastAPI's minimalism means assembling middleware pieces deliberately (the middleware chain is already specified in the architecture baseline); Next.js churn risk pinned by lockfile + CI.
