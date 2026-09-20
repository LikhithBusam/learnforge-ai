# Technology Baseline — AI Study Companion (Phase 0)

**Status:** DECIDED baseline produced by ADR-0013…0020 under the criteria in `ADR-0012b-selection-criteria.md`. This is the single page to read for "what will this system be built on."
**Status vocabulary:** `DECIDED` (architecture-fixed, build may start) · `DEFERRED` (a named decision made later) · `PROTOTYPE ONLY` (Phase 0 posture, changes at a trigger) · `FUTURE TRIGGER` (adopted only when a documented trigger fires).

## Selection criteria (summary — full record in ADR-0012b)

Prototype fit (C1) · isolation compatibility incl. RLS (C3) · AI ecosystem (C4) · developer velocity (C5) · security (C6) · deployment simplicity (C9) — with reliability, maintainability, cost, and local-dev experience as supporting weights. Popularity is explicitly not a criterion; tie-breaks go to the boring option.

## Final baseline

| Layer | Technology | Responsibility | Why selected | Alternative considered |
|---|---|---|---|---|
| **Frontend** | **Next.js (App Router) + TypeScript** — `DECIDED` | Dashboards (server components), Tutor chat with SSE, quiz runner, admin views; TanStack Query server-state + job polling; generated OpenAPI client | Server components fit aggregate-heavy read pages; one framework for SSR/routing/BFF cookie flow; streaming is ordinary HTTP (ADR-0017/0010) | React+Vite SPA (viable second choice), HTMX-class server templates |
| **Backend** | **Python 3.12 + FastAPI** — `DECIDED` | API + business logic as modular monolith (ADR-0001); Pydantic v2 validation for API/tools/LLM output; async SQLAlchemy 2.0 + Alembic behind Platform abstractions | Native async for SSE + provider fan-out; one schema language across all untrusted-input boundaries; Python-native AI/document ecosystem (ADR-0017) | Django+DRF, NestJS, Flask, Go |
| **Database** | **PostgreSQL 16** — `DECIDED` | System of record: relational learning state, outbox, dedup registries, AI telemetry, RLS-isolated tenant data | Native RLS (isolation invariant), transactional chunks+embeddings, outbox/idempotency semantics are native Postgres patterns (ADR-0013) | Postgres+external vector DB (deferred), MongoDB (fails RLS), MySQL |
| **Vector search** | **pgvector (HNSW, cosine)** — `DECIDED` | Embedding ANN with `project_id` filter **inside the query/transaction** | Same transaction + same security boundary as chunks; migration to a dedicated engine is contained to the Knowledge facade (ADR-0013 §6) | Qdrant/Pinecone/Weaviate — `FUTURE TRIGGER` T1–T4 (>5M chunks, p95>150 ms at target recall, inexpressible requirement, ingestion write saturation) |
| **Full-text search** | **Postgres FTS (`tsvector` + GIN)** — `DECIDED` | Lexical half of hybrid retrieval (acronyms, formulas, exact terms) | Free with the DB; hybrid + rerank compensates ranking weaknesses (ADR-0013) | Elasticsearch/OpenSearch — `FUTURE TRIGGER` only if FTS ranking measurably fails the retrieval eval gate |
| **Cache** | **Redis 7** — `DECIDED` (`PROTOTYPE ONLY` single instance) | Cache-aside for dashboards/mastery/retrieval/query-embeddings; rate-limit counters; idempotency records; SSE pub/sub | One component covers four responsibilities; loss = latency degradation only, never correctness (ADR-0014) | Memcached (no pub/sub), separate cache service |
| **Broker** | **Redis (Celery broker)** — `DECIDED` | Task delivery to workers | Durable record of events lives in Postgres outbox; broker loss = delay, not loss (ADR-0014) | RabbitMQ, SQS-class — `FUTURE TRIGGER` T3/T4 |
| **Workers** | **Celery 5 + Beat** — `DECIDED` | Queues: `documents`, `learning`, `analytics`, `evaluation`, `default`; retries/backoff; DLQ; scheduled rollups/eval sampling | Mature retry/scheduling semantics; same image as API; queue bulkheads (ADR-0014) | arq/Dramatiq, Postgres-only jobs, managed queues |
| **Object storage** | **S3-compatible** — MinIO `PROTOTYPE ONLY` (dev) → R2/S3-class `DECIDED` (prod) | Private PDFs + page images; presigned up/down; metadata (keys, checksums, status) in Postgres only | Bytes never touch the API; identical API from laptop to prod; private-by-default (ADR-0016) | Local filesystem (breaks statelessness), DB blobs (rejected) |
| **Authentication** | **Self-hosted JWT: RS256 access (~15 min) + rotating opaque refresh (30 d, hashed, HttpOnly/SameSite=Strict) + Argon2id** — `DECIDED` with named deferrals | Identity, sessions, roles; `Principal` seam feeds RLS user id | No vendor in the critical isolation path; OIDC swap later is localized (ADR-0018) | Managed IdP (Auth0/Clerk) — `FUTURE TRIGGER` on SSO/social requirement |
| **AI Gateway** | **In-house `AIGateway` module** (contract §M.11) — `DECIDED` | Single egress: generate/stream/structured/embed/rerank/evaluate/vision; metering; budgets; circuit breaking; prompt registry | Every call observable + attributable; vendor swap = config + adapter (ADR-0007/0015) | LangChain-class framework (rejected: hides what must be observable) |
| **LLM provider abstraction** | **Capability roles** (`generation.reasoning`, `.grading`, `.mid`, `.small`, `evaluate`) mapped to vendors **by config** — roles `DECIDED`; specific vendors `DEFERRED` to build kickoff | Domain code calls roles, never vendors | PRD leaves vendors open; selection is a budget/quality exercise against the golden set (ADR-0015) | Single-vendor hard-wiring (rejected) |
| **Embeddings** | Dedicated `embedding` role; fixed dimension pinned per schema; model stamped per row; batched + cached — role `DECIDED`, vendor `DEFERRED` | Chunk + query vectors | Regenerable derived data; dimension change = reprocessing job (ADR-0015) | — |
| **Reranking** | Dedicated `rerank` role; degraded mode = fused order + raised sufficiency threshold — role `DECIDED`, vendor `DEFERRED` | Top-k precision for trustworthy citations | Rerank is what makes citations trustworthy (ADR-0003 grounding design) | Small-LLM rerank fallback (acceptable degraded path) |
| **Vision/document** | `vision.document` role for OCR-escalation pages only — role `DECIDED`, vendor `DEFERRED` | Scans/diagrams/complex tables | Cost-ordered escalation: native → OCR → vision (A-19) | Vision for every page (rejected: cost) |
| **Observability** | **OTel SDK → hosted Grafana/Sentry-class free tier; structured JSON logs; ai_requests spine; job_runs** — `DECIDED` (`PROTOTYPE ONLY` posture) | Logs/trace/metrics with one correlation id; AI + job telemetry; 8 actionable alerts | Vendor-neutral instrumentation, zero self-hosted ops, FR-81/82 satisfied (ADR-0020) | Self-hosted Prometheus/Loki/Tempo stack — `FUTURE TRIGGER` Phase 1 |
| **Deployment** | **Managed container platform (Fly/Render class) + Compose locally** — `DECIDED` (`PROTOTYPE ONLY`) | api + worker (+beat) same image; frontend container; managed Postgres/Redis; platform TLS/secrets; rolling deploys + digest rollback | Git-to-HTTPS in hours; rollback = previous digest; K8s migration later is a manifest change (ADR-0019) | AWS IaC — `FUTURE TRIGGER` Phase 1; K8s — `FUTURE TRIGGER` per A-13; serverless, single VPS (rejected) |

## Deferred-decision register (who decides what, when)

| Decision | Status | Decided at | Input |
|---|---|---|---|
| Specific LLM/embedding/rerank/vision vendors + models per role | `DEFERRED` | Build kickoff (ADR-0015 addendum) | Golden-set quality trial + price table (A-17) |
| Managed Postgres/Redis/storage vendors | `DEFERRED` | Deploy time (ADR-0019) | Platform choice; all config-only swaps |
| Exact HNSW parameters, retrieval thresholds | `DEFERRED` | Retrieval tuning phase | Eval set (A-20) — never magic numbers |
| UI kit final choice | `DEFERRED` | Frontend build start | shadcn/Radix-class default per ADR-0017 |
| Phase 1: split workers, read replica, self-hosted observability, AWS path, email delivery, MFA | `FUTURE TRIGGER` | Trigger tables in ADR-0013/0014/0019/0020 + ADR-0018 deferrals | Measured signals, not preferences |

## Consistency checks (this baseline vs prior artifacts)

- Module contracts (§M) remain **technology-independent** — this baseline names the implementations behind them, not changes to them.
- ADR-0002's four-layer isolation is satisfiable as specified: RLS (ADR-0013) + session-scoped user id (ADR-0018) + in-query filters + worker ownership context (ADR-0014).
- The evaluation strategy requires provider-free CI — satisfied by fixture-based gateway stubs (ADR-0015 adapters are the stub seams).
- No fabricated benchmarks anywhere: all scale claims are triggers with measurement methods.
