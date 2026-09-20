# ADR-0019: Deployment Platform — Managed Containers, No Kubernetes in Phase 0

**Status:** DECIDED (Phase 0) · **Criteria basis:** C1, C9, C10 dominant · **Resolves:** A-13, deferred "deployment platform" row · **Contracts affected:** §M.13 (worker deployment), §M.14 (config/secrets), ADR-0012 (config)

## Decision

Deploy Phase 0 to a **managed container platform** (Fly.io / Render / Railway class), with **Docker Compose** for local development. Three container images from one repository: `api` and `worker` from the **same backend image** (different entrypoints — ADR-0001), `frontend` as a Next.js standalone container. **No Kubernetes**, no bespoke AWS networking, no service mesh — the PRD requires a publicly deployed, working system inside the build window, and K8s would consume disproportionate budget while adding operational surface no requirement justifies (A-13).

## Topology (prototype)

| Component | Deployment | Notes |
|---|---|---|
| Frontend | 1 Next.js container (platform CDN in front) | Static/standalone; autoscale later if ever needed |
| API | 1–2 FastAPI containers behind platform router/TLS | Stateless (ADR-0014/§24 posture) |
| Workers | 1 worker container running **all queues** (routing pre-configured so splitting = config change) | Same image as API; Beat as separate process/entrypoint |
| PostgreSQL 16 + pgvector | Managed (Neon/Supabase/RDS-class — pick at deploy) | PITR class service; RLS-capable role |
| Redis | Managed (Upstash/platform equivalent) | Cache/broker per ADR-0014 |
| Object storage | Managed S3-compatible (ADR-0016) | Private bucket |
| Secrets | Platform env injection / secrets manager | Never in repo, never baked into images |
| HTTPS | Platform-terminated TLS; HSTS at app | Certificates auto-managed |

## Environments

| Environment | Purpose | Data | Deploy trigger |
|---|---|---|---|
| **Local** | Development | Compose: api, worker, beat, postgres+pgvector, redis, minio; seeded fixtures | Manual |
| **CI** | Tests + eval gates | Ephemeral containers per run; **no live provider calls** (fixtures); scheduled live contract checks separate | Every push |
| **Staging** | Pre-production verification | Synthetic/anonymized data; real provider keys with **low budgets** | Auto on merge to main |
| **Production (prototype)** | The public demo | Real | Manual approval |

Staging mirrors production topology at smaller scale — same image, same migration path; only scale/budgets/data differ.

## Migrations

Alembic migrations run as a **separate pre-deploy job/release command before the app rollout**, expand-only within a release (ADR-0012): the previous app version must keep working against the new schema, which is what makes rollback safe. `lock_timeout` guard on migrations; no destructive change in the same release that stops using an object.

## Worker deployment

- Same image as API; entrypoint runs the Celery worker subscribed to all queues + a Beat process for the relay/rollups/eval-sampling schedules.
- Worker health = heartbeat + queue-depth visibility (ADR-0020); platform restarts unhealthy containers; `acks_late`-equivalent semantics make worker restarts safe (in-flight tasks requeue; consumers idempotent per ADR-0014).

## Health checks

| Check | Endpoint/Signal | Gate |
|---|---|---|
| Liveness | `/healthz` — process up, **no dependency checks** | Platform restart on fail; DB blip must not restart-loop healthy pods |
| Readiness | `/readyz` — DB + Redis reachable (+ pending migration check) | Router stops sending traffic; deploy gate |
| Worker | Heartbeat / queue-age metrics | Alerting (ADR-0020), platform restart on heartbeat loss |
| Post-deploy verification | Automated smoke: register → create project → upload fixture → tutor grounded answer with citation → refusal case | Release gate; regression triggers rollback |

## Rollback approach

**Rollback = redeploy the previous image digest.** Always possible because: migrations are expand-only within a release (old code runs on new schema); config is externalized (no state in the replaced containers); the outbox retains undispatched events across restarts. Feature-flagged AI changes (prompt/model versions) revert by config without a deploy. A bad deploy caught by post-deploy verification auto-rolls back on regression signals (error-rate watch, per ADR-0020 alerts).

## Options considered

### Option 1 — Managed container platform (Fly.io/Render/Railway class) ✅
- **Advantages:** git-to-HTTPS in hours; managed Postgres+Redis add-ons or BYO managed services; multi-process (web/worker/beat) on one image; env/secret injection built in; cost fits prototype budgets; containerized portability means later migration is a manifest change, not a rewrite.
- **Disadvantages:** less infra control (no custom VPC/network policies); platform vendor lock is real but bounded by containers + externalized state.

### Option 2 — AWS full IaC (VPC, ALB, ECS Fargate, RDS, ElastiCache, S3)
- **Advantages:** the production-grade target (the architecture baseline's cloud mapping); full control.
- **Disadvantages:** Terraform + VPC + IAM setup is days of the 4-day window before any feature exists; violates C1 for Phase 0. **Deferred as the Phase 1 scaling path** — the Phase 2 FUTURE TRIGGER table in the baseline maps logical components to AWS when business justifies.

### Option 3 — Kubernetes (EKS/GKE)
- **Advantages:** sophisticated autoscaling, multi-team isolation, multi-region orchestration.
- **Disadvantages:** none of those requirements exist; cluster ops inside the window is negative-value work. Rejected for Phase 0; FUTURE TRIGGER per A-13.

### Option 4 — Serverless (Lambda-class) + managed everything
- **Advantages:** scale-to-zero cost.
- **Disadvantages:** cold starts hurt Tutor streaming; minutes-long OCR fights execution limits; long-lived SSE connections and Celery-style workers are unnatural. Rejected on C2 (ADR-0001 prior art).

### Option 5 — Single VPS (Compose in prod)
- **Advantages:** cheap, full control.
- **Disadvantages:** we become the HA story (backups, TLS, monitoring, restarts) — hidden ops cost inside the window; violates C2. Rejected.

## Consequences

- (+) Deployment is achievable inside the window; rollback is trivial and exercised by design; staging/prod parity via one image; every later migration (AWS/K8s) is a manifest change because containers + externalized config were non-negotiable from day one.
- (−) Platform dependency (mitigated: state lives in Postgres/Redis/S3, all swappable); no custom network-level egress allow-listing in Phase 0 (compensating controls: secrets hygiene, dependency scanning, provider keys with budgets; egress allow-list lands with the Phase 1 AWS path).

## Revisit triggers

| # | Trigger | Move to |
|---|---|---|
| T1 | Continuous real traffic + uptime expectations (Phase 1 gate) | AWS ECS/managed path per baseline cloud mapping; add WAF, read replica, PITR tier |
| T2 | Multi-region or data-residency requirement (A-09/A-14) | Multi-region IaC (Phase 2) |
| T3 | Multi-team deploy isolation needed | Kubernetes (A-13) |
