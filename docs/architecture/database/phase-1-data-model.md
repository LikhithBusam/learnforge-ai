# Phase 1 Data Model — Identity + Workspace

**Status:** Implemented (migration `0001_phase1_identity_workspace`).
**Principle:** every column, index, and constraint below maps to a requirement (FR-x) or an approved architecture decision (ADR-x / assumption A-x). No speculative fields. Later-phase tables (materials, chunks, conversations, quizzes, mastery, analytics, AI-request persistence) are deliberately absent.

**Identifier strategy (Part 2):** all primary keys are **UUIDv7 (RFC 9562), generated application-side** by `app.platform.ids.uuid7()`. No database extension or function is required (portable across Supabase and local Compose). Properties: 48-bit big-endian Unix-ms timestamp ⇒ lexicographically sortable, B-tree-locality-friendly IDs; version nibble `7`; serialized as canonical lowercase hyphenated UUID strings in APIs; stored as native `uuid` in PostgreSQL. UUIDv7 is the *only* identifier system in this schema.

**Timestamps:** all `timestamptz` (UTC), server default `now()`. `spaces.updated_at` / `projects.updated_at` maintained by `touch_updated_at()` triggers.

**Security classification legend:** PII · SECRET-ADJACENT (hashes of secrets) · INTERNAL.

---

## 1. `users`

| Aspect | Design |
|---|---|
| Purpose | Identity root (FR-01; ADR-0018). One row per human account. |
| PK | `id uuid` (UUIDv7, app-generated) |
| Columns | `email text NOT NULL` — login identity, stored as provided (FR-01). `password_hash text NOT NULL` — Argon2id PHC string only; plaintext NEVER stored (Part 3). `role text NOT NULL DEFAULT 'learner'` CHECK `role IN ('learner','admin')` — authorization foundation (Part 16). `status text NOT NULL DEFAULT 'active'` CHECK `IN ('active','disabled')` — login-time deny switch (ADR-0018). `created_at`, `updated_at timestamptz NOT NULL`. |
| Uniqueness | `uq_users_email_lower (lower(email))` UNIQUE — case-insensitive email uniqueness **at the database level** (Part 3); service canonicalization (trim + casefold) is first-line normalization. |
| FKs | none (root table) |
| Indexes | `uq_users_email_lower`; PK. |
| Triggers | none (updated_at changes only via explicit UPDATE — acceptable: Phase 1 has no user-profile mutation path). |
| Ownership | `id = app_user_id()` — a row is visible/manageable only by its own user. |
| Project scope | **User-scoped, not project-scoped** (Part 13 exemption): identity has no project dimension; the RLS policy keys on the row itself, not on a project. |
| RLS | ENABLED. Policy `users_all_access FOR ALL TO studycompanion_runtime USING (id = app_user_id()) WITH CHECK (same)`. |
| Retention | Account lifetime. Deletion is a hard `DELETE` (cascades to sessions, spaces, projects, memberships). No soft-delete in Phase 1 (no requirement). |
| Classification | PII (email); SECRET-ADJACENT (password hash). `password_hash` is excluded from all repository records except `UserRepository.get_by_email_with_hash` (reserved for the future login path). |

## 2. `refresh_sessions`

| Aspect | Design |
|---|---|
| Purpose | Rotating refresh-token session persistence (ADR-0018; Part 4). |
| PK | `id uuid` (UUIDv7) |
| Columns | `user_id uuid NOT NULL` → `users.id ON DELETE CASCADE`. `token_hash varchar(64) NOT NULL` — SHA-256 hex of the raw token; **raw tokens are never stored** (Part 4); lookup is by hash only. `expires_at timestamptz NOT NULL` — REFRESH_TTL_DAYS. `revoked_at timestamptz NULL` — set on logout/rotation/reuse. `revoked_reason varchar(32) NULL` CHECK `NULL OR IN ('rotated','reuse_detected','logout','admin_revoke')` — reuse-detection provenance (Part 4). `parent_session_id uuid NULL` → `refresh_sessions.id ON DELETE SET NULL` — rotation chain; a presented token whose session has a successor ⇒ reuse detected (ADR-0018). `created_at timestamptz NOT NULL`. |
| Uniqueness | `uq_refresh_sessions_token_hash (token_hash)` UNIQUE — hash lookup is the only supported path; uniqueness also blocks hash collisions from double-use. |
| Indexes | `uq_refresh_sessions_token_hash` (lookup); `ix_refresh_sessions_user_id` (revoke-all, audit listing); `ix_refresh_sessions_active_expiry (expires_at) WHERE revoked_at IS NULL` (partial — expiration cleanup over live sessions only; avoids indexing revoked history, Part 19). |
| Constraints | FK user cascade; self-FK `SET NULL`; revoked_reason CHECK. |
| Ownership | `user_id = app_user_id()`. |
| Project scope | **User-scoped** (no project dimension; same documented exemption as `users`). |
| RLS | ENABLED. Policy `refresh_sessions_all_access FOR ALL TO studycompanion_runtime USING (user_id = app_user_id()) WITH CHECK (same)` — the runtime role can never read another user's session metadata even via direct SQL. |
| Retention | Purge after expiry (repository `purge_expired` hook; Beat schedule arrives with the auth phase). Rows are secrets-bearing only in hashed form. |
| Classification | SECRET-ADJACENT (token hashes); session metadata is security-relevant. |

## 3. `spaces`

| Aspect | Design |
|---|---|
| Purpose | Top-level learner workspace (FR-05). |
| PK | `id uuid` (UUIDv7) |
| Columns | `owner_id uuid NOT NULL` → `users.id ON DELETE CASCADE` — ownership is explicit and immutable in Phase 1 (no transfer requirement). `name text NOT NULL` — display name. `description text NULL`. `created_at`, `updated_at` (trigger-maintained). |
| Uniqueness | `uq_spaces_owner_name_lower (owner_id, lower(name))` UNIQUE — duplicate space names per owner are rejected (PRD journey: small personal list). |
| Indexes | PK; `uq_spaces_owner_name_lower` (serves both uniqueness AND `owner_id`-prefix lookups — no separate owner index needed, Part 19). |
| Constraints | FK owner cascade. |
| Ownership | `owner_id = app_user_id()`. |
| Project scope | Owner-keyed (a Space *contains* projects; it is not itself project-scoped). |
| RLS | ENABLED. Policy `spaces_all_access FOR ALL TO studycompanion_runtime USING (owner_id = app_user_id()) WITH CHECK (same)`. |
| Retention | Owner lifetime; cascade-deleted with the user. |
| Classification | PII-adjacent (user-authored names/descriptions). |

## 4. `projects`

| Aspect | Design |
|---|---|
| Purpose | Learning project within a space (FR-12) — the unit of isolation for every later phase (materials, tutor, mastery). |
| PK | `id uuid` (UUIDv7) |
| Columns | `space_id uuid NOT NULL` → `spaces.id ON DELETE CASCADE`. `owner_id uuid NOT NULL` → `users.id ON DELETE CASCADE` — **denormalized from `spaces.owner_id`** by design: (a) RLS predicate without joins, (b) owner-scoped queries without joins, (c) direct isolation semantics. Consistency with the owning space is enforced by trigger `trg_projects_owner_consistency` (exception on mismatch) — plain FKs cannot express this (Part 6). `name text NOT NULL`. `description text NULL` — project description (PRD §4 creation flow). `learning_goal text NULL` — the learner's stated goal (PRD §4; feeds later learning features). `status text NOT NULL DEFAULT 'active'` CHECK `IN ('active','archived')` — module-contracts `ProjectDto.status`. `created_at`, `updated_at` (trigger-maintained). |
| Uniqueness | `uq_projects_space_name_lower (space_id, lower(name))` UNIQUE — duplicate project names within a space rejected. |
| Indexes | PK; `uq_projects_space_name_lower`; `ix_projects_owner_id` (owner-scoped listings — the dominant access pattern). |
| Triggers | `trg_projects_owner_consistency BEFORE INSERT OR UPDATE OF space_id, owner_id` — raises if `projects.owner_id <> spaces.owner_id`; runs under the invoking role so RLS applies (fail closed). `trg_projects_touch_updated_at`. |
| Ownership | `owner_id = app_user_id()` (≡ space owner, trigger-enforced). |
| Project scope | The project IS the scope unit. Owner-keyed policy = project scope in Phase 1 (A-16: one learner per project ⇒ membership ≡ ownership today). |
| RLS | ENABLED. Policy `projects_all_access FOR ALL TO studycompanion_runtime USING (owner_id = app_user_id()) WITH CHECK (same)`. |
| Retention | Deleted with user (cascade) or with its space. `archived` is lifecycle, not deletion. |
| Classification | User-authored content (PII-adjacent). |

## 5. `project_memberships`

| Aspect | Design |
|---|---|
| Purpose | Authorization rows binding users to projects (Part 7). **Current supported behavior:** exactly one `owner` membership per project (A-16 single learner). **Future capability (documented, NOT implemented):** additional roles for collaboration — the `role` column and `has_project_access()` helper exist as the seam; relaxing requires an explicit, reviewed migration. |
| PK | `id uuid` (UUIDv7) |
| Columns | `project_id uuid NOT NULL` → `projects.id ON DELETE CASCADE`. `user_id uuid NOT NULL` → `users.id ON DELETE CASCADE`. `role varchar(16) NOT NULL DEFAULT 'owner'` CHECK `role IN ('owner')` — only the owner role is writable today. `created_at timestamptz NOT NULL`. |
| Uniqueness | `uq_project_memberships_owner_per_project (project_id) WHERE role='owner'` — partial unique: exactly one owner per project (current behavior, enforced in SQL). `uq_project_memberships_user_project (user_id, project_id)` — no duplicate membership rows. |
| Indexes | The two unique indexes above (they double as the membership lookup paths); PK. |
| Ownership | `user_id = app_user_id()` — a member sees their own membership rows. |
| Project scope | Row-keyed on `user_id`. When collaboration arrives, the policy extends with `has_project_access(project_id)` (function already deployed, unused by policies — deliberately not attached to avoid a dead/over-broad policy surface). |
| RLS | ENABLED. Policy `project_memberships_all_access FOR ALL TO studycompanion_runtime USING (user_id = app_user_id()) WITH CHECK (same)`. |
| Retention | Cascade with project/user. |
| Classification | INTERNAL (authorization data). |

## Index review (Part 19) — justification per index

| Index | Table/Columns | Query supported | Why it exists |
|---|---|---|---|
| `uq_users_email_lower` | users `(lower(email))` UNIQUE | login lookup, registration dedup (FR-01) | Required: DB-level case-insensitive email uniqueness |
| `uq_refresh_sessions_token_hash` | refresh_sessions `(token_hash)` UNIQUE | refresh-token rotation lookup (ADR-0018) | Required: only supported lookup path |
| `ix_refresh_sessions_user_id` | refresh_sessions `(user_id)` | revoke-all-for-user, per-user session audit | Access pattern: logout/logout-everywhere |
| `ix_refresh_sessions_active_expiry` | refresh_sessions `(expires_at) WHERE revoked_at IS NULL` | expiration cleanup | Partial: only live rows are purge candidates |
| `uq_spaces_owner_name_lower` | spaces `(owner_id, lower(name))` UNIQUE | owner space listing + duplicate rejection | Doubles as owner index (prefix) |
| `uq_projects_space_name_lower` | projects `(space_id, lower(name))` UNIQUE | duplicate rejection within space | Requirement: unique project names per space |
| `ix_projects_owner_id` | projects `(owner_id)` | owner-scoped project listings (dominant read) | Access pattern: every project listing |
| `uq_project_memberships_owner_per_project` | project_memberships `(project_id) WHERE role='owner'` | enforce single-owner invariant (A-16) | Constraint-as-index |
| `uq_project_memberships_user_project` | project_memberships `(user_id, project_id)` UNIQUE | membership lookup `get(project,user)` | Duplicate-prevention + lookup |

No speculative indexes (no full-text/vector/status indexes until their phases).

## Transaction boundary (Part 11)

Each service method = exactly one `db.session_scope()` transaction: BEGIN → bind RLS context (`set_config(..., true)`) → work → COMMIT; any exception ⇒ ROLLBACK. Services never commit; nested calls are plain function composition inside the same transaction. **Future outbox compatibility:** an `outbox` INSERT in the same scope commits atomically with the state change — the boundary is already the required unit of work; the outbox table arrives with the first event-producing phase (documented deferral, not a silent omission).
