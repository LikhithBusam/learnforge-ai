# RLS Security Model — Project Isolation at the Database Layer

**Status:** Implemented and verified against Supabase PostgreSQL 17.6 (migration `0001_phase1_identity_workspace`; isolation suite `tests/integration/test_phase1_isolation.py` — 12/12 PASS on the live cloud connection path).

## Defense-in-depth layers

1. **Route authorization** (future auth phase): verified JWT → `Principal`; 404/403 posture per ADR-0021/Q5.
2. **Service/repository scope** (Phase 1): every operation carries an explicit owner/user scope; no unscoped query surface exists in the repositories.
3. **PostgreSQL RLS** (this document): even code that bypasses layers 1–2 cannot read or write rows outside the transaction's bound context.
4. **Retrieval/query filtering** (later phases): application-level project filters remain in queries; RLS is the backstop, not the only gate.

## Database roles

| Role | Login | Superuser | BYPASSRLS | Used for |
|---|---|---|---|---|
| `postgres` (Supabase project owner) | yes | no* | **yes** | Migrations/DDL, readiness probes ONLY |
| `studycompanion_runtime` | yes | **no** | **no** | ALL normal application queries (API + worker) |

\* Supabase's `postgres` is not a true superuser (`rolsuper=false` — Supabase hardens it), but it owns the schema and holds BYPASSRLS, which is why it is treated as privileged throughout.

### Why the owner role never serves application requests

1. **BYPASSRLS makes RLS void.** Any query path using `postgres` would silently skip every policy — the second isolation boundary would exist only on paper.
2. **Blast radius.** A compromised application process holding the owner credential can read/modify/drop anything, including `alembic_version` and other schemas.
3. **Audit clarity.** Every row-level decision should be attributable to the RLS context, not to a role that ignores it.
4. **Structural enforcement.** `db.init_runtime_engine` refuses to boot when `DATABASE_RUNTIME_URL` is missing or equals `DATABASE_URL` — the application cannot accidentally run on the privileged role.

Runtime role properties (verified live, Part 8 output format):

```text
runtime_role: studycompanion_runtime
rolsuper: false
rolbypassrls: false
```

## Session context (the RLS contract)

Policies evaluate `app_user_id()`, which reads `current_setting('app.current_user_id', true)`:

- The application binds context **inside the same transaction** as the work:
  `SELECT set_config('app.current_user_id', :user_id, true)` — bind parameters only, never string interpolation.
- `is_local => true` makes the setting **transaction-scoped**: it vanishes on commit/rollback.
- Verified through the Supavisor **session pooler**: the setting does not survive the transaction, so pooled connection reuse cannot leak context between requests (isolation tests 11 + pooled-leak security test).

### Authenticated user

`app.current_user_id` is set exclusively from the server-verified principal (JWT `sub` in the future auth phase; explicit service parameters in Phase 1). **No client input ever reaches `set_config` unvalidated** — the context is derived from verified identity, never from headers the client can spoof.

### Project scope

In Phase 1, project scope ≡ owner scope (A-16: one learner per project). `app.current_project_id` is bound by `db.bind_rls_context` for future worker/probe use; Phase 1 policies key on the user id, which the ownership chain (space→project trigger) keeps equivalent.

## RLS policy behavior

All five tables use one permissive `FOR ALL` policy per table, scoped to `studycompanion_runtime`, with matching `USING` and `WITH CHECK` predicates:

| Table | Policy | USING / WITH CHECK |
|---|---|---|
| `users` | `users_all_access` | `id = app_user_id()` |
| `refresh_sessions` | `refresh_sessions_all_access` | `user_id = app_user_id()` |
| `spaces` | `spaces_all_access` | `owner_id = app_user_id()` |
| `projects` | `projects_all_access` | `owner_id = app_user_id()` |
| `project_memberships` | `project_memberships_all_access` | `user_id = app_user_id()` |

Design notes:

- `USING` filters reads/updates/deletes; `WITH CHECK` rejects writes of rows the caller cannot see (cross-project INSERT/UPDATE fail with RLS violations, not silent success).
- **No `USING (true)` policies exist.** `users`/`refresh_sessions` are user-scoped (not project-scoped) — their policies key on the row's own identity, which is the meaningful predicate for those tables (documented exemption, not a meaningless policy).
- **Fail closed:** missing/empty context ⇒ `app_user_id()` ⇒ NULL ⇒ every predicate is NULL/false ⇒ **zero rows** (test 10; empty-string context also fails closed — security suite).
- `FORCE ROW LEVEL SECURITY` is intentionally OFF: the table owner is the migration role, which must retain unrestricted access for DDL/backfills; the runtime role is not the owner, so RLS applies to it fully. The admin role's unrestricted access is confined to migration/probe paths.

## Worker / background-job context

Celery tasks carry an envelope with `user_id` / `project_id` / `correlation_id` (Phase 0 mechanism). Worker-side DB access:

1. Re-binds the envelope into contextvars (`task_prerun`), then
2. Opens `db.session_scope(user_id=…, project_id=…)` — the same transaction-scoped binding as the API path.

A task **without** ownership context runs fail-closed (zero project rows) — background jobs must explicitly carry the user/project they act for. Cross-task leakage is impossible because the binding is per-transaction (test 7).

## Privileged operations

The admin engine (`db.admin_session_scope`) is an explicit, auditable escape hatch for migrations, DDL backfills, and health probes only. Legitimate uses are enumerable; normal request handling and worker task logic must never import it (boundary checker + review). `alembic_version` is not granted to the runtime role.

## Connection pooling considerations

- **Supavisor (Supabase):** transaction-scoped `set_config` verified safe. Session state (other GUCs, `SET` commands) must NOT be relied upon.
- **Application pool:** SQLAlchemy pool with `pool_pre_ping` + `pool_recycle=1800` keeps checkouts healthy across pooler/server idle recycles.
- **Runtime vs admin pools are separate engines** — no credential or connection mixing.
- Runtime role authenticates as `studycompanion_runtime.<project-ref>` on the pooler (tenant-qualified username required by Supavisor; provisioning script derives this automatically).

## Failure behavior (summary)

| Condition | Behavior |
|---|---|
| No context bound | Zero rows (fail closed) |
| Empty-string context | Zero rows (fail closed) |
| Cross-user/cross-project read | Zero rows |
| Cross-user/cross-project write | RLS violation error (explicit rejection) |
| Runtime role attempts `SET ROLE` to privileged role | Permission denied (no membership) |
| `DATABASE_RUNTIME_URL` unset/equal to admin URL | Application refuses to serve DB traffic |
