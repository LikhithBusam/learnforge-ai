# ADR-0022: Cloud Provider Selection — Supabase (Postgres + Storage) and Upstash (Redis)

**Status:** DECIDED (operator-selected 2026-09-19, fulfilling the `DEFERRED` entries in the technology-baseline deferred-decision register).
**Context:** ADR-0019 deliberately deferred managed-provider choice to deploy time. The project is now cloud-first; the operator selected providers and supplied credentials through the operator channel (secrets live only in the gitignored `.env.development`).

## Decision

| Concern | Selection | Notes |
|---|---|---|
| Primary database | **Supabase PostgreSQL** (db.<ref>.supabase.co:5432, direct connection) | Managed Postgres; version/RLS/extension support verified in Phase-1 cloud verification; local Compose (`pgvector/pgvector:pg16`) remains the reproducibility/fallback environment |
| Cache / Celery broker / result backend | **Upstash Redis** (TLS via `rediss://`) | One logical database — Celery broker, result backend, and cache share db 0 (Upstash free tier does not support `SELECT`); namespace prefixing instead of DB-number separation |
| Object storage | **Supabase Storage**, private bucket `learning-materials` | Consumed via the existing `StorageProvider` abstraction (`SupabaseStorage`, REST + httpx, no new SDK); bytes-at-rest stay private; downloads via short-TTL signed URLs |

## Consequences

- **No RLS weakening:** the runtime DB role continues to be a non-superuser; RLS model (next phase) targets standard PostgreSQL semantics that Supabase's Postgres exposes unchanged.
- **Session context:** transaction-scoped `set_config(..., true)` remains the pooling-safe mechanism; Supabase poolers (PgBouncer-style) do not preserve session variables — transaction-scoped context is therefore mandatory, matching the architecture already chosen.
- **Redis multiplexing:** Upstash bills per command and restricts some commands; broker/result-backend/cache coexistence relies on Celery key prefixes + the cache `namespaced()` prefix. No db-number isolation is available.
- **One more secret** enters the env surface: `SUPABASE_SECRET_KEY` (service-role JWT). It is excluded from `safe_summary()`, logs, and health output; frontend never receives it.
- **Rotation required:** the credentials were shared through the operator chat channel; rotate the service-role key and DB password after the build stabilizes.

## Alternatives considered

- Neon / RDS-class Postgres — viable (pgvector + RLS), not selected by the operator; no advantage material enough to override the choice for this phase.
- Upstash Redis vs managed Redis on the same vendor — co-location would reduce provider count but Upstash was chosen for free-tier economics and TLS-native endpoints.

## Verified operational facts (live verification 2026-09-19)

- **Project region is `ap-southeast-2`** (Sydney). The Supavisor pooler host is region-specific:
  `aws-0-ap-southeast-2.pooler.supabase.com:5432` (Session mode). A wrong region yields
  `ENOTFOUND tenant/user … not found` — not a DNS error — which makes misconfiguration non-obvious.
- The direct-DB host `db.<ref>.supabase.co` is **IPv6-only**; IPv4-only clients must use the
  pooler. Session mode (5432) is used to preserve asyncpg prepared statements; transaction mode
  (6543) is the fallback if connection counts require it.
- PostgreSQL **17.6**; `vector` and `pg_trgm` available; `uuid-ossp`, `pgcrypto` installed.
- The `postgres` role on Supabase is non-superuser but **has `rolbypassrls`** (owner privilege).
  Phase 1 must provision a dedicated non-BYPASSRLS runtime role; RLS policies must be validated
  through that role, never through `postgres`.
- **Transaction-scoped context verified through the pooler**: `set_config('app.current_user_id', v,
  true)` inside a transaction, empty after commit — the mandated pooling-safe RLS mechanism.
- Upstash: TLS-only (`rediss://`). **Celery 5.3 requires an explicit `?ssl_cert_reqs=CERT_REQUIRED`
  on `rediss://` broker/backend URLs** (redis-py's direct client defaults safely; kombu does not).
  Free-tier Redis: single logical database — broker/backend/cache coexist via key prefixes.
- Supabase Storage returns **HTTP 400 with a `404` body** for missing buckets; the adapter
  normalizes this. Private-bucket signed GETs verified without credentials (200, correct body).

## Reversibility

Config-only swap: all provider specifics sit in env vars + the `SupabaseStorage` adapter behind `StorageProvider`. Revisiting (e.g., Postgres on another vendor) requires no domain-module changes.
