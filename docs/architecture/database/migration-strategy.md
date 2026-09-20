# Migration Strategy — Database Schema Evolution

**Scope:** Alembic policy for all schema phases (Phase 1 is the implemented reference).

## Tooling

- **Alembic** with an async engine; `alembic/env.py` injects `DATABASE_URL` from the application settings — never hard-coded (`%` characters in URLs are escaped for configparser interpolation).
- **No blind autogenerate.** Phase 1's migration is fully hand-written; future phases may draft with autogenerate but must be manually inspected, pruned, deterministically named, and annotated with design-source references before commit. `target_metadata` remains unset until a phase explicitly opts into diffing.
- **Naming convention** (`app.platform.models.NAMING_CONVENTION`) makes constraint/index names stable and reviewable.

## Migration review

Every migration PR must show:

1. Upgrade path reviewed top-to-bottom (order: roles → tables/FKs → triggers/functions → RLS → grants).
2. Symmetric downgrade (or an explicit, documented "not safely reversible" note).
3. Idempotency notes for role/DDL creation (`DO $$ ... IF NOT EXISTS`).
4. No destructive DDL without a following §destructive-policy justification.
5. Design-source references (FR/ADR/assumption) per object.

## Upgrade / downgrade

- `alembic upgrade head` — forward only in normal operation.
- Downgrade is supported **where safely reversible**; Phase 1's downgrade drops policies/RLS → triggers/functions → tables (FK-reverse order) → default privileges. The runtime role is intentionally **not** dropped (revoking provisioned credentials would be an operator action, not a schema revert).
- `alembic_version` is readable/writable only by the migration role.

## Production migration policy

- Migrations run **before** deploying new application code (expand→contract when applicable).
- Transactional DDL is assumed (verified on Supabase PostgreSQL 17.6): a failed migration leaves zero footprint (observed during Phase 1 bring-up).
- Maintenance-window or lock-timeout parameters are considered per migration once tables carry production traffic (not applicable at prototype volume).

## Cloud migration workflow (primary environment)

1. Credentials come from the gitignored `.env.development` via the settings abstraction (Supabase pooler URL; the runtime-role URL is derived by `scripts/provision_runtime_role.py`).
2. `cd apps/api && python -m alembic upgrade head` runs as the **migration/admin role** (Supabase project owner) — the only role permitted to perform DDL.
3. Post-migration: `python scripts/provision_runtime_role.py` (idempotent) sets/rotates the runtime role password and writes `DATABASE_RUNTIME_URL` locally. Never commit its output; the script never prints credentials.

## Local reproduction (fallback environment)

The same migration runs unchanged against local Docker Compose PostgreSQL (`pgvector/pgvector:pg16`); the `postgres` superuser there plays the migration-role part. The only environment difference is **who the migration role is** — the schema, RLS policies, and runtime-role properties are identical (verified design; role DDL is environment-agnostic).

## Rollback limitations

- Downgrade reverts **schema**, not data. Rows written between upgrade and downgrade are lost on downgrade (acceptable: reverting a schema is a deliberate destructive act).
- Roles created by migrations are not dropped by downgrade (see above).
- After a downgrade, re-upgrading recreates empty structures.

## Destructive migration policy

Destructive DDL (`DROP TABLE/COLUMN`, type changes, index removal) requires:

1. A migration docstring section explaining why reversion is safe at that phase.
2. A pre-migration data-preservation decision (backup/export or documented data-loss acceptance).
3. Expand→contract preferred: add new, migrate, then remove old in a later migration.

## Role separation

| Role | Used by | Privileges |
|---|---|---|
| Migration/admin (`postgres` project owner on Supabase; local superuser) | Alembic, DDL, health/readiness probes | Full DDL; has BYPASSRLS on Supabase — **never used for application queries** |
| `studycompanion_runtime` | FastAPI request path, worker DB access | LOGIN; NO superuser, NO createdb/createrole, NO bypassrls; SELECT/INSERT/UPDATE/DELETE on business tables via RLS only |

`db.init_runtime_engine` refuses to boot if `DATABASE_RUNTIME_URL` equals `DATABASE_URL` (structural guarantee that the app cannot run on the privileged role).

## Schema compatibility

- All timestamps `timestamptz`; all PKs application-generated UUIDv7 (no DB sequences to coordinate).
- Later phases add tables/additive columns; alterations to Phase 1 tables require the destructive/expand-contract policy above.
- RLS policies are per-role; adding roles or tables re-runs the same grant/policy patterns (default privileges already cover future tables).
