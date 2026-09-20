# Authentication Test Matrix — Phase 2

Execution environment: Supabase PostgreSQL 17.6 via Supavisor pooler, `studycompanion_runtime` role (rolsuper=false, rolbypassrls=false), transaction-scoped RLS context.

## Files

| Suite | File | Scope |
|---|---|---|
| Auth matrix | `tests/integration/test_phase2_auth.py` | registration, login, JWT, refresh, logout |
| Phase 2 security | `tests/integration/test_phase2_security.py` | secret persistence, header spoofing, key exposure, log hygiene |
| Phase 1 isolation (regression) | `tests/integration/test_phase1_isolation.py` | 12 RLS proofs incl. filter-removed + fail-closed |
| Phase 1 security (regression) | `tests/integration/test_phase1_security.py` | 12 controls |
| Unit | `tests/unit/test_phase1_platform.py`, `tests/unit/test_phase2_tokens.py` | ids, canonicalization, tokens |

## Registration

| # | Case | Expected | Result |
|---|---|---|---|
| R1 | valid registration | 201, learner role | PASS |
| R2 | duplicate email (case-insensitive) | generic 409 | PASS |
| R3 | email canonicalization | stored casefolded; login with other case works | PASS |
| R4 | short password | 422 | PASS |
| R5 | password hashed (Argon2id, not plaintext) | hash starts `$argon2id$` | PASS |
| R6 | client supplies `role: admin` | 422 (extra fields forbidden) | PASS |
| R7 | malformed payload / missing fields | 422 | PASS |

## Login

| # | Case | Expected | Result |
|---|---|---|---|
| L1 | valid credentials | 200 + access JWT + refresh cookie | PASS |
| L2 | wrong password | generic 401 | PASS |
| L3 | unknown email | identical generic 401 | PASS |
| L4 | canonicalized email (different case) | 200 | PASS |
| L5 | response contains no hash/token internals | clean JSON | PASS |
| L6 | refresh session row created (hash only) | raw token absent from DB | PASS |

## JWT

| # | Case | Expected | Result |
|---|---|---|---|
| J1 | valid token | Principal constructed | PASS |
| J2 | expired token | 401 | PASS |
| J3 | invalid signature (wrong key) | 401 | PASS |
| J4 | wrong issuer | 401 | PASS |
| J5 | wrong audience | 401 | PASS |
| J6 | missing subject | 401 | PASS |
| J7 | malformed claims / garbage token | 401 | PASS |
| J8 | `alg: none` / HS256 confusion | 401 | PASS |
| J9 | malformed Authorization header | 401 | PASS |

## Refresh / rotation / reuse

| # | Case | Expected | Result |
|---|---|---|---|
| F1 | valid refresh | 200, new access + rotated cookie | PASS |
| F2 | rotation transactional; old token revoked | old token unusable | PASS |
| F3 | replay of rotated token | 401 + whole family revoked + `auth_refresh_reuse` audit event | PASS |
| F4 | subsequent token of same family after reuse | 401 | PASS |
| F5 | expired refresh session | 401 | PASS |
| F6 | unknown/garbage refresh token | generic 401 | PASS |
| F7 | concurrent refresh of same session | exactly one succeeds (FOR UPDATE lock) | PASS |
| F8 | refresh without non-ambient header | 401 (CSRF guard) | PASS |

## Logout

| # | Case | Expected | Result |
|---|---|---|---|
| O1 | authenticated logout | 200, session revoked | PASS |
| O2 | post-logout refresh | 401 | PASS |
| O3 | logout of another user's session | not possible (principal-scoped) | PASS |
| O4 | access jti denylisted until natural expiry | subsequent requests with that jti → 401 | PASS |

## RLS / isolation (regression + auth binding)

| # | Case | Expected | Result |
|---|---|---|---|
| I1–I12 | Phase 1 isolation suite (cross-project read/write/delete, filter-removed, fail-closed, pooled-connection isolation, worker context, role properties) | all blocked/allowed as specified | 12/12 PASS |
| I13 | User A Principal → RLS context A; B's project invisible via API | blocked | PASS (E2E) |
| I14 | Missing context → no rows | fail closed | PASS |

## Phase 2 security

| # | Case | Expected | Result |
|---|---|---|---|
| S1 | password hash is Argon2id | `$argon2id$` prefix, no plaintext column | PASS |
| S2 | refresh token stored hashed only | raw token not in DB | PASS |
| S3 | header identity spoofing (`X-User-ID` etc.) | ignored; 401 without valid JWT | PASS |
| S4 | JWT private key never exposed via API/logs | no key material in responses | PASS |
| S5 | registration with `role` field | 422 | PASS |
| S6 | auth errors contain no stack traces/hashes | generic bodies | PASS |

## Regression totals (executed)

- Phase 0 + unit + boundary: 29 passed
- Phase 1 isolation: 12 passed · Phase 1 security: 12 passed
- Phase 2 auth matrix: 24 passed · Phase 2 security: 9 passed
- Live cloud E2E smoke: 9/9 steps PASS (register → login → me → workspace/RLS → isolation → rotate → replay-revokes-family → logout → post-logout refresh 401)
