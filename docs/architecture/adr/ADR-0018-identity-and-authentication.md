# ADR-0018: Identity and Authentication — Self-Hosted JWT with Rotating Refresh Tokens

**Status:** DECIDED (Phase 0, with explicit deferrals) · **Criteria basis:** C1, C6, C3 dominant · **Resolves:** A-03 (assumption), ADR-0005 prior art · **Contracts affected:** §M.1 (Identity), §M.2 (`resolve_project_scope`), §M.14 (security primitives)

## Decision

**Self-hosted email/password authentication inside the `identity` module.** No external identity provider in Phase 0. All authorization derives from a single `Principal` resolution point; role + ownership decisions are made downstream (RBAC for learner/admin + ownership ABAC + project scope), never in the token layer.

## Design elements (contract-level, per §M.1)

| Element | Decision |
|---|---|
| **Password hashing** | Argon2id (memory-hard), parameters from config and benchmarked to a target cost — never defaults-guessing |
| **Access token** | JWT, **RS256** signature (asymmetric — verification can move to an edge/gateway later without sharing the signing secret), ~15 min TTL (config), claims: `sub`, `role`, `sid`, `iat`, `exp`, `jti` |
| **Refresh token** | Opaque, ~30-day TTL (config), stored **hashed** in `sessions`; delivered as `HttpOnly; Secure; SameSite=Strict` cookie; **rotated on every use** with family id — a replayed (already-used) refresh token revokes the whole session family (token-theft detection) |
| **Secure cookies** | The refresh cookie is the only cookie-authenticated flow; `/auth/refresh` additionally requires a non-ambient header check (CSRF belt-and-braces); the API itself is Bearer-header based (not CSRF-prone) |
| **RBAC** | `role ∈ {learner, admin}` claim; admin routes behind an admin dependency; A-01 keeps admin read-only; A-02: admin assigned out-of-band (seed), no self-service |
| **Ownership authorization** | Not in Identity — owning modules check `owner_id` via `resolve_project_scope`-class guards; non-owned → 404 (never 403) per ADR-0002 |
| **Project-level authorization** | `ProjectScope` constructed at the edge from the Principal; threaded into services, tools, and worker tasks (module-contracts scope rules) |
| **Token expiration** | Access TTL short; refresh TTL long but rotated; both config-driven; clock-skew margin in verification |
| **Logout / revocation** | Session row revoked + `jti` denylisted in Redis until natural expiry; logout idempotent; refresh reuse revokes the family |
| **Password reset** | Single-use, time-limited, hashed token; constant-time comparison; **no user-enumeration** in responses (generic messaging) |

**RLS binding:** the Principal's `user_id` is what the request sets as the session variable for row-level security (ADR-0002/0013) — identity and database isolation share one id, so there is no translation layer to get wrong.

## Options considered

### Option 1 — Self-hosted JWT (this decision) ✅
- **Advantages:** no external dependency in the critical login path; direct control of the `role` claim and the RLS user binding; no vendor cost/data-sharing question for a prototype; the `Principal` seam makes a later OIDC migration a localized swap.
- **Disadvantages:** we own password storage, reset, and session security — real responsibility, accepted because the surface is small and controls are standard; no MFA/social login without building it.

### Option 2 — Managed identity provider (Auth0/Clerk/Supabase Auth class)
- **Advantages:** fastest login box; MFA/social/magic-links included; fewer credential-handling mistakes.
- **Disadvantages:** external dependency + vendor cost in the most critical path; binding an external identity to RLS context and a custom `role=admin` model adds glue exactly where isolation is decided; another credential class to manage inside the window. Rejected for Phase 0; revisit trigger below.

### Option 3 — Session-cookie-only (server sessions, no JWT)
- **Advantages:** simplest revocation story; no token plumbing.
- **Disadvantages:** complicates the SSE/streaming + cross-service posture and the future edge-verification path; stateless API replicas (ADR-0014/0019 scaling posture) prefer short JWTs + DB-backed refresh. Rejected.

### Option 4 — Third-party passwordless (magic-link) as primary
- **Advantages:** no password storage at all.
- **Disadvantages:** depends on email deliverability — which is **stubbed in Phase 0** (A-04). Self-defeating in the prototype window. Rejected for Phase 0.

## Explicitly deferred for the prototype (PROTOTYPE ONLY → later)

| Deferred feature | Phase 0 posture | When |
|---|---|---|
| Email verification | Stubbed: account usable immediately, `email_verified=false` recorded (A-04) | Phase 1 (email provider + enforced gate) |
| Password reset **delivery** | Flow exists; delivery stubbed/logged — reset links not actually emailed | Phase 1 (same provider) |
| MFA / TOTP | Not built | When user base justifies |
| Social/OIDC login | Not built | On requirement; `Principal` seam keeps it localized |
| Session management UI (list/revoke devices) | Not built; sessions revocable data-wise | Phase 1 |
| Account lockout escalation flows | Edge rate limiting only (per-IP + per-account counters) | Phase 1 (progressive lockout + notify) |
| Password rotation policy / breach checks | Argon2id strength only | Phase 1 |

## Consequences

- (+) Isolation-critical path (identity → RLS id) has no vendor translation; login works offline in dev/CI without provider mocks; zero auth vendor cost.
- (−) Security responsibility is ours; the deferred list is explicit and reviewable — reviewers should challenge any of these deferrals they consider prototype-blocking.

## Revisit triggers

1. Social login or enterprise SSO requirement → evaluate managed OIDC; swap = replace token verification only (Principal unchanged).
2. MFA requirement → add TOTP step in Identity before token issue.
3. Auth-related incident class (credential stuffing beyond edge limits) → progressive lockout + anomaly alerts (ties to ADR-0020 security metrics).
