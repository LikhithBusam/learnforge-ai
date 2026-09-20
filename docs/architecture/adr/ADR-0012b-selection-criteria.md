# Selection Criteria and Decision Method — AI Study Companion

**Status:** Applies to ADR-0013 through ADR-0020. Every Phase 0 technology decision below is scored against these criteria; where a choice wins, the record names which criteria dominated and which criteria the choice sacrifices.

## 1. Hard constraints (non-negotiable, from requirements)

| Constraint | Source | Effect on selection |
|---|---|---|
| Working, publicly deployed system within a 3–4 day prototype window | PRD §1, §18 | Eliminates options whose setup/operations exceed ~0.5 day; managed services preferred; no Kubernetes in Phase 0 (A-13) |
| Secrets never in the repository; config via environment | PRD §18 (NFR-07) | Any component requiring config-file secrets is rejected |
| Project-level isolation incl. database-level enforcement | PRD §15 (NFR-03), ADR-0002 | System of record **must** support row-level security keyed on a session variable |
| Tenant filter inside retrieval queries, transactional consistency of chunks+embeddings | ADR-0002, ADR-0003 | Vector search must support filtered ANN within the same transaction as relational data |
| Provider-neutral AI with per-call metering | PRD §14 (FR-80/81) | Model vendors selectable by config only; never hard-coded |
| Deterministic learning logic; idempotent background work | PRD §9; NFR-02 | Task framework needs retries + dedup keys + scheduled tasks; math lives in code |
| Evaluation discipline (FR-83/84) | Evaluation strategy | Testing must run without live provider calls (fixtures); CI must be provider-free |
| Modular monolith + worker plane (ADR-0001) | Architecture | One backend runtime shared by API and workers; one container image, two entrypoints |

## 2. Weighted criteria (applied to each ADR)

| # | Criterion | Weight | How it is judged |
|---|---|---|---|
| C1 | Prototype fit (3–4 day window incl. deployment) | **High** | Time from zero to working capability, including local setup and CI |
| C2 | Reliability under prototype traffic + graceful degradation | **High** | Failure modes are understood and bounded; dependencies have degraded modes |
| C3 | Isolation compatibility (RLS, in-query filters, session-scoped context) | **High** | Direct fit to ADR-0002's four-layer posture |
| C4 | AI ecosystem compatibility (embedding SDKs, PDF/OCR libraries, eval tooling, structured outputs) | **High** | Maturity of libraries needed by FR-21–24, FR-80 |
| C5 | Developer velocity (single small team; contracts already fixed) | **High** | Async streaming + typed validation + migrations + background tasks available as first-class features |
| C6 | Security posture (auth primitives, transport, secret handling) | **High** | Supports Argon2id-class hashing, RS256, HttpOnly cookies, private storage |
| C7 | Maintainability (small surface, boring components, typed contracts) | Medium | Fewer moving parts wins ties |
| C8 | Observability (structured logs, traces/metrics, correlation ids, queue depth visibility) | Medium | OTLP-compatible instrumentation available |
| C9 | Deployment simplicity (containerized, env-config, health checks, rolling restarts) | **High** | One image for API+workers preferred (ADR-0001) |
| C10 | Cost at prototype scale (low hundreds of users, A-11) | Medium | Free/low managed tiers acceptable; no license bombs |
| C11 | Future scalability (documented triggers, not premature scale) | Medium | Migration path exists and is contained (per ADR revisit triggers) |
| C12 | Local development experience (one-command stack, reproducible, provider-free tests) | Medium | Compose-able, fixture-driven CI |
| C13 | Team familiarity and hiring reality | Medium | Recognized, well-documented, stable tooling |

**Tie-breaker order:** C1 → C3 → C9 → C7. If two options remain indistinguishable on the weighted criteria, the **boring** one wins (principle §15: every component earns its place; novelty spent only where the requirements demand).

## 3. Explicit non-criteria (this phase)

- Peak-scale benchmarks (nothing measured; ADRs record triggers instead — see ADR-0013 §6).
- Multi-region, multi-team org concerns (no requirement).
- Vendor popularity/brand as an argument — only capability fit counts.

## 4. Decision records produced under these criteria

| ADR | Decision | Status |
|---|---|---|
| ADR-0013 | PostgreSQL 16 + pgvector + Postgres FTS as single system of record | DECIDED |
| ADR-0014 | Redis (cache/broker/rate-limit/idempotency) + Celery workers | DECIDED |
| ADR-0015 | Role-based AI provider strategy behind the AI Gateway (vendor-agnostic) | DECIDED (roles); specific vendors DEFERRED to build start |
| ADR-0016 | S3-compatible object storage (MinIO local, R2/S3-class hosted) | DECIDED |
| ADR-0017 | FastAPI backend + Next.js/TypeScript frontend | DECIDED |
| ADR-0018 | Self-hosted JWT auth (RS256 + rotating refresh), advanced features deferred | DECIDED (with explicit deferrals) |
| ADR-0019 | Managed container platform (Fly.io/Render-class) + Compose locally | DECIDED |
| ADR-0020 | Minimum-viable observability: structured logs + OTel + provider dashboards | DECIDED |
