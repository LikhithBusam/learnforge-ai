# Authentication — Security Reference (Phase 2)

Implements ADR-0018 / ADR-0023. Verified against Supabase PostgreSQL 17.6 via the Supavisor pooler with the non-BYPASSRLS `studycompanion_runtime` role.

## Flow

```
POST /api/v1/auth/register|login
  → email canonicalization (trim + casefold)
  → Argon2id verify (login) / hash (register)
  → RS256 access JWT (sub, jti, iat, exp, iss, aud)   TTL 900s default
  → opaque 256-bit refresh token → SHA-256 hash persisted in refresh_sessions
  → refresh token returned ONLY as HttpOnly Secure SameSite=Strict cookie
       (Path=/api/v1/auth)

GET /api/v1/auth/me (any protected route)
  → Authorization: Bearer <JWT>
  → verify RS256 signature (alg pinned; none/HS256 confusion rejected)
  → validate iss, aud, exp, required claims
  → construct Principal(user_id, role)  — identity ONLY from the token
  → session_scope(user_id=…) → SET LOCAL app.current_user_id → PostgreSQL RLS
```

## Controls actually implemented

| Control | Implementation | Tested by |
|---|---|---|
| Password storage | Argon2id (`argon2-cffi`), never plaintext, never returned | `test_phase2_security.py`, unit tests |
| Password policy | min 10 / max 128 chars, validated before hashing | auth matrix |
| Email uniqueness | DB UNIQUE on canonical (casefolded) email; registration maps `IntegrityError` → generic conflict | auth matrix |
| Generic login failures | One generic 401 for unknown email / wrong password / absent account | auth matrix |
| Access token | RS256, iss/aud/exp/sub/jti/iat validated; TTL from `JWT_ACCESS_TOKEN_TTL_SECONDS` | JWT matrix |
| Algorithm confusion | `alg` header must equal RS256 exactly; `none`/HS256 rejected | security suite |
| Refresh tokens | `secrets.token_urlsafe(32)`; only SHA-256 hash stored; raw value never logged or persisted | security suite |
| Rotation | Transactional under `SELECT … FOR UPDATE`; old token revoked, new token same `family_id` | auth matrix |
| Reuse detection | Hash match on a revoked session ⇒ whole `family_id` revoked + `auth_refresh_reuse` audit event + generic 401 | auth matrix + E2E |
| Logout | Revokes presented session (caller's own principal) + denylists access `jti` in Redis until natural expiry | auth matrix |
| Refresh cookie | HttpOnly, Secure, SameSite=Strict, path-scoped; refresh/logout additionally require a non-ambient `X-Request-With` header (CSRF mitigation) | security suite |
| Identity spoofing | `X-User-ID`/`X-Admin`/`X-Role` headers never consulted; unknown request fields rejected (`extra="forbid"`) | security suite |
| Admin bootstrap | `scripts/bootstrap_admin.py`; requires `ADMIN_BOOTSTRAP_SECRET` match, env-gated, audited, idempotent; no API route can mint admins | security suite |
| RLS binding | User id for `SET LOCAL` comes only from the verified Principal; missing context fails closed | Phase 1 isolation suite |
| Error hygiene | 401/403/404 posture per ADR-0021/Q5; no token/hash/stack-trace leakage in responses | security suite |
| Log hygiene | No passwords, raw tokens, hashes, or keys in logs; auth events carry correlation ID + category only | code review + tests |

## Configuration (env)

`JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` (PEM; never logged/committed), `JWT_ALGORITHM=RS256`, `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_ACCESS_TTL_SECONDS=900`, `REFRESH_TTL_DAYS=30`, `REFRESH_COOKIE_SECURE`, `RATE_LIMIT_LOGIN_PER_MINUTE=10`, `ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_TOKEN`. Placeholders in `.env.example`; real values only in gitignored `.env.development`.

### Refresh TTL flow

```text
REFRESH_TTL_DAYS (Settings)
        ↓
identity/service._persist_session  →  expires_at = now + timedelta(days=REFRESH_TTL_DAYS)
        ↓                                    (rotation reuses the same value)
refresh_sessions.expires_at
        ↓
refresh validation  →  expired session ⇒ generic 401
        ↓
refresh-cookie expiry derives from the same expires_at
```

The variable name is `REFRESH_TTL_DAYS` (established in the architecture
baseline, `architecture.md` / security-baseline) — not
`JWT_REFRESH_TOKEN_TTL_SECONDS`. Changing the configured value changes the
`expires_at` of newly created sessions (read at call time, not cached).

### Login rate limiting

```text
RATE_LIMIT_LOGIN_PER_MINUTE (Settings, default 10)
        ↓
identity/ratelimit.enforce_login_limit  — Redis fixed-window counter
        ↓   key: auth:login:rl:{sha256(canonical_email)}:{unix_minute}  (TTL 60s;
        ↓   raw email/credentials are NEVER stored in Redis)
enforced in the login route BEFORE password verification
        ↓
threshold exceeded ⇒ RateLimitedError → HTTP 429 problem+json
```

Availability posture: Redis is loss-tolerant infrastructure (ADR-0014); if
Redis is unavailable the limiter fails OPEN with a logged warning — it is
abuse mitigation, not a correctness control. A value of `0` disables it.

## Known limitations

- Access-token revocation is best-effort: denylist check happens per-request in Redis; if Redis is unavailable the dependency fails open with a logged warning (the token is still signature+TTL-valid; RLS remains the data boundary). Documented trade-off per ADR-0018.
- Login brute-force mitigation is a fixed-window Redis counter (`RATE_LIMIT_LOGIN_PER_MINUTE`) — no persistent per-account lockout yet.
- `auth_credential_lookup` / `auth_session_lookup` are `SECURITY DEFINER` by necessity (pre-auth, no RLS context exists yet). They are column-minimal, `search_path`-pinned, granted EXECUTE only to the runtime role, and covered by tests; they must never be widened to return arbitrary columns.
