# ADR-0014: Cache, Broker, and Background Workers — Redis + Celery

**Status:** DECIDED (Phase 0) · **Criteria basis:** C1, C2, C9 dominant · **Resolves:** deferred "cache/broker" row in `architecture-decisions.md` · **Contracts affected:** §M.13 (Jobs), §M.14 (Platform cache), §M.9 (Analytics dedup)

## Decision

- **Redis 7** serves as cache, rate-limit counter store, idempotency-record store, Celery broker, and SSE fan-out pub/sub.
- **Celery 5** is the worker framework with **four partitioned queues** (`documents`, `learning`, `analytics`, `evaluation`) plus `default` (relay/cleanup), Celery Beat for scheduled work, `acks_late` semantics.
- **Postgres remains the durable source for everything** — Redis holds nothing that cannot be lost (outbox rows and consumer dedup live in Postgres per ADR-0006).

## The four responsibilities, explicitly separated

| Responsibility | Component | Durability contract |
|---|---|---|
| **Cache** (dashboards, mastery summaries, retrieval results, query embeddings, concept lists) | Redis, namespaced keys + global `CACHE_VERSION`, cache-aside | **Lossy by design.** A cache error is logged, counted, and falls through to Postgres; correctness never depends on cache contents |
| **Message broker** (task delivery to workers) | Redis (Celery broker) | **Delivery is at-least-once but not durable-of-record.** Broker loss = delay, never state loss, because all events of record sit in `outbox_events` (Postgres) and are re-dispatched when Redis returns |
| **Worker execution** (document pipeline, grading, mastery, recommendations, rollups, eval sampling) | Celery workers per queue; same codebase/image as API (ADR-0001), different entrypoint | Each task delegates into a service method; service transaction boundaries apply; tasks carry ownership context and **fail closed** without it (ADR-0002) |
| **Persistent event record** (what must never be lost) | **Postgres only**: `outbox_events`, `processed_events`, `job_runs` | The relay reads the outbox, claims with skip-locked semantics, dispatches to broker, marks published. Idempotency is anchored in Postgres, not Redis |

**Rule stated plainly: Redis is never the system of record.** Losing the Redis instance degrades latency and delays background work; it cannot lose events, dedup state, rate-limit fairness (falls back to DB unique constraints), or correctness.

## Options considered

### Option 1 — Redis + Celery ✅
- **Advantages:** mature retry/backoff/jitter; queue routing; Beat scheduling; task-state introspection; well-understood failure modes; works on every managed platform (C9); one dependency covers cache+broker+limits (C1, C10).
- **Disadvantages:** Redis persistence not relied upon (accepted: outbox design makes that safe); Celery is heavyweight for tiny workloads; worker-embedding of domain code requires import discipline.

### Option 2 — Redis + arq / Dramatiq (lighter Python workers)
- **Advantages:** smaller surface, async-native (arq).
- **Disadvantages:** thinner retry/DLQ/scheduling ecosystems; fewer documented failure modes; Beat-class scheduling absent or DIY; saves little because task *definitions* are one-line delegations either way. Rejected on C2/C7 (maturity outweighs lightness for reliability-critical plumbing).

### Option 3 — Managed queue (SQS-class) + custom polling workers
- **Advantages:** true managed durability; independent scaling.
- **Disadvantages:** adds vendor coupling and a second source of durable state that partially duplicates the outbox (dual delivery-record problem); visibility of per-queue depth/age requires extra wiring; CloudWatch/region coupling clashes with cloud-neutral posture (C9). Rejected — the outbox already provides durability where it belongs.

### Option 4 — RabbitMQ as broker
- **Advantages:** stronger routing/delivery semantics than Redis.
- **Disadvantages:** another service to run/secure for guarantees the outbox already provides; no cache role, so Redis would still be needed. Rejected on C7/C10.

### Option 5 — Postgres-only background jobs (skip-list / `FOR UPDATE SKIP LOCKED` polling)
- **Advantages:** zero new components; single durability story.
- **Disadvantages:** no bulkhead queue separation without significant hand-building; no mature retry/backoff/DLQ/scheduling semantics; exactly the infrastructure Celery already embodies. Rejected on C2 — but noted: the outbox relay *is* this pattern for the publishing half, which is intentional.

## Why this is the simplest architecture that satisfies the requirements

Requirement → mechanism mapping: background document processing (`documents` queue workers); quiz evaluation + mastery + recommendations (`learning` queue chain); analytics processing (`analytics` queue, scheduled rollups); retries (Celery retry + backoff/jitter per event policy); idempotency (Postgres `processed_events` + natural unique keys — deliberately **not** Redis); DLQ/failure handling (retry exhaustion → `dead_letter` routing + `job_runs.dead_lettered` + admin replay §M.13); bulkheads (queue separation so ingestion bursts cannot delay the learning loop).

## Prototype vs production

| Aspect | Phase 0 (PROTOTYPE ONLY) | Phase 1+ (FUTURE TRIGGER) |
|---|---|---|
| Topology | One worker container running all queues (routing pre-configured so splitting is config-only) | Split workers per queue; autoscale `documents` on queue depth/oldest-message age |
| Redis topology | Single managed instance | Primary + replica; Sentinel/managed failover if broker HA is required |
| Rate limiting | Redis token buckets (AI endpoints fail closed, reads fail open on Redis loss) | Distributed limit tiers at edge + app |

## Scaling triggers (revisit this ADR when)

| # | Trigger | Response |
|---|---|---|
| T1 | `documents` queue oldest-message age repeatedly breaches the processing-lag alert (15-min class, ADR-0020) | Split + autoscale document workers (config change by design) |
| T2 | Redis memory/eviction pressure from cache + broker contention | Separate cache and broker instances (config) |
| T3 | Event fan-out to external consumers needed, or volume exceeds Redis comfort | Durable broker (SQS/RabbitMQ-class) behind the relay — the outbox → relay seam absorbs the change |
| T4 | Broker-loss delay becomes unacceptable for a user-facing workflow | Move that workflow's queue to a durable broker; keep cache/limits on Redis |

## Consequences

- (+) One additional infrastructure component (Redis) covers four responsibilities; task framework mature; local dev is a single Compose service; the durability question is settled in Postgres where transactions already live.
- (−) Two runtimes to operate (API process + worker process) sharing one image; Celery worker-embedding requires the import-discipline contracts (facade-only); broker loss delays work (bounded by the outbox, visible via queue-age alerts).
