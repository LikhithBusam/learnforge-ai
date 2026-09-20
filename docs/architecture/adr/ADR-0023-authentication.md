# ADR-0023: Authentication Architecture (JWT Access + Opaque Refresh Rotation)

**Status:** ACCEPTED (Phase 2 implementation; supersedes nothing, implements ADR-0018)
**Date:** 2026-09-19

## Context

ADR-0018 defined the identity/authentication strategy (RS256 access tokens, opaque hashed refresh tokens with rotation and family revocation, HttpOnly refresh cookie, denylist-based access-token revocation, out-of-band admin assignment). Phase 1 delivered the persistence substrate: `users`, `refresh_sessions`, Argon2id hashing helpers, `Principal`, the non-BYPASSRLS `studycompanion_runtime` role, and transaction-scoped RLS context (`app_user_id()` reading `app.current_user_id`).

Phase 2 must turn that substrate into a working authentication layer without weakening the Phase 1 isolation model.

## Decision

1. **Access tokens** are short-lived RS256 JWTs (`sub`, `jti`, `iat`, `exp`, `iss`, `aud`; no password/token/profile claims). Keys and TTLs are environment-driven (`JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_ACCESS_TOKEN_TTL_SECONDS=900`). Verification is strict: signature, issuer, audience, expiry, and required-claims validation; the `alg` header is pinned to RS256 so `none`/HS256 algorithm-confusion attacks are rejected by construction.
2. **Refresh tokens** are 256-bit opaque random values (`secrets.token_urlsafe`). Only a SHA-256 hash is persisted in `refresh_sessions`; the raw token exists only in the HttpOnly `Secure`/`SameSite=Strict`/`Path=/api/v1/auth` cookie returned to the client.
3. **Rotation** is transactional under `SELECT … FOR UPDATE` row locking: presenting a valid refresh token revokes it, mints the next token in the same `family_id`, and commits atomically. Concurrent refreshes of the same session serialize on the row lock; the loser observes a revoked row.
4. **Reuse detection**: the `auth_session_lookup` lookup returns the stored hash for *any* session matching the presented token hash, including revoked ones. A hash match on a revoked session is a reuse event: the whole `family_id` is revoked, an `auth_refresh_reuse` security event is logged, and a generic 401 is returned.
5. **Logout** revokes the presented refresh session (verified by the caller's own principal) and denylists the current access token's `jti` in Redis until natural expiry. Access tokens are otherwise stateless; revocation latency is bounded by TTL (documented trade-off).
6. **RLS chicken-and-egg**: credential/session lookups that must run *before* any user context exists use narrowly-scoped `SECURITY DEFINER` SQL functions (`auth_credential_lookup`, `auth_session_lookup`) that return only the columns required (id, hash, status, family, expiry) and are granted EXECUTE solely to `studycompanion_runtime`. All other access remains fail-closed RLS through the runtime role.
7. **Registration** always creates learners; the API rejects unknown/extra fields (`model_config = extra="forbid"`) so `role` or privilege-escalation payloads are 422 errors, not silently ignored. Admin assignment happens only via the env-gated operator CLI (`scripts/bootstrap_admin.py`), which requires `ADMIN_BOOTSTRAP_SECRET` to match configuration, is audited, and is idempotent.
8. **Identity source**: `Principal` is constructed exclusively from the verified JWT. `X-User-ID`/`X-Admin`/`X-Role` style headers are never consulted. RLS context is bound from `Principal.user_id` via transaction-scoped `SET LOCAL app.current_user_id` inside `session_scope`.

## Consequences

- Stolen refresh tokens are single-use; replay revokes the family.
- Access-token revocation on logout is best-effort (denylist + short TTL) — accepted per ADR-0018.
- The two `SECURITY DEFINER` functions are the only pre-auth database surface; both are column-minimal and audited by the isolation suite.
- Refresh cookie is non-ambient: refresh/logout additionally require a non-ambient custom header, mitigating CSRF.

## Verification

Isolation suite (12), security suites (Phase 1: 12, Phase 2: 9+), auth matrix (24), and a live cloud E2E smoke (register → login → me → workspace/RLS → rotate → replay-revokes-family → logout → post-logout refresh rejected) all executed against Supabase PostgreSQL 17.6 through the Supavisor pooler with the `studycompanion_runtime` role.
