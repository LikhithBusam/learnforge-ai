# Security & Secrets Baseline — AI Study Companion

**Status:** Binding for all implementation. Supports NFR-04/05/07, ADR-0018, ADR-0015/0016, and project-principles §1/§12/§13. **Rule zero: no real credential ever enters the repository** — not in code, config, tests, docs, or git history.

## 1. Configuration and environment variables

- **All configuration is environment-injected** and validated at startup by a typed settings object; the application **refuses to boot** on missing/malformed values (ADR-0012). No `if env == "production"` branches in domain logic — behaviour differences are config values.
- **`.env.example` is the only env file in git** — every key present with placeholder values and comments. `.gitignore` blocks all other `.env*` files; CI secret scanning (gitleaks-class) is the backstop that fails the build on credential-shaped strings.
- Files: `.env.development` (local, gitignored, dev-only throwaway keys), `.env.test` (CI defaults, no real secrets), staging/production values injected by the platform secrets facility — never on disk in the repo.

## 2. Environment variable catalogue (placeholders only)

```bash
# --- Core ---
APP_ENV=development|test|staging|production
APP_VERSION=                          # injected git SHA at build
LOG_LEVEL=INFO
FRONTEND_ORIGIN=
CORS_ALLOWED_ORIGINS=

# --- Database ---
DATABASE_URL=                         # postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB
DATABASE_POOL_SIZE=10
DATABASE_STATEMENT_TIMEOUT_MS=10000

# --- Redis ---
REDIS_URL=                            # rediss://:PASSWORD@HOST:6379/0

# --- Object storage ---
STORAGE_ENDPOINT=
STORAGE_BUCKET=
STORAGE_ACCESS_KEY_ID=
STORAGE_SECRET_ACCESS_KEY=
STORAGE_PRESIGN_TTL_SECONDS=900
MAX_UPLOAD_BYTES=52428800
MAX_PDF_PAGES=500

# --- Auth (ADR-0018) ---
JWT_PRIVATE_KEY=                      # RS256 PEM — secrets manager only
JWT_PUBLIC_KEY=
JWT_ACCESS_TTL_SECONDS=900
REFRESH_TTL_DAYS=30
ARGON2_TIME_COST=3
ARGON2_MEMORY_KIB=65536

# --- AI providers: roles per ADR-0015 (never vendors in code) ---
LLM_PRIMARY_PROVIDER=
LLM_PRIMARY_API_KEY=
LLM_PRIMARY_REASONING_MODEL=
LLM_PRIMARY_FALLBACK_PROVIDER=
LLM_PRIMARY_FALLBACK_API_KEY=
LLM_PRIMARY_FALLBACK_MODEL=
LLM_GRADING_MODEL=
LLM_MID_MODEL=
LLM_SMALL_MODEL=
EMBEDDING_PROVIDER=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
EMBEDDING_DIMENSIONS=1536
RERANK_PROVIDER=
RERANK_API_KEY=
RERANK_MODEL=
VISION_PROVIDER=
VISION_API_KEY=
VISION_MODEL=
AI_REQUEST_TIMEOUT_SECONDS=30
AI_GRADING_TIMEOUT_SECONDS=60
AI_USER_DAILY_TOKEN_BUDGET=
AI_PROMPT_LOGGING=redacted            # none|redacted|full — full never in production

# --- Retrieval policy (A-20: tuned, never magic) ---
RETRIEVAL_TOP_K=30
RETRIEVAL_RERANK_TO=6
RETRIEVAL_SUFFICIENCY_TAU=            # set via eval calibration
RETRIEVAL_MIN_SUPPORTING_CHUNKS=2
CHUNK_TARGET_TOKENS=500
CHUNK_OVERLAP_RATIO=0.15
CONTEXT_TOKEN_BUDGET=

# --- Background ---
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=
WORKER_CONCURRENCY_DOCUMENTS=2
WORKER_CONCURRENCY_LEARNING=4

# --- Rate limits ---
RATE_LIMIT_GLOBAL_PER_MINUTE=
RATE_LIMIT_AI_PER_MINUTE=
RATE_LIMIT_LOGIN_PER_MINUTE=

# --- Observability (ADR-0020) ---
OTEL_EXPORTER_OTLP_ENDPOINT=
SENTRY_DSN=
EVAL_SAMPLE_RATE=0.05
```

## 3. Secret management rules

1. Secrets exist **only** in the platform secrets facility and runtime memory — never in images, never in volumes, never in logs.
2. CI reads secrets from the CI provider's secret store; never echoed; logs masked.
3. **Rotation = config update + restart** (all secrets read at startup); no code change required.
4. Leaked-key runbook: **revoke first, investigate second** (providers and platform creds alike).
5. Local development uses throwaway keys with provider budgets capped; a leaked dev key is worthless by construction.
6. Tests never read real secrets — fixture values only; a test requiring a real credential is a defect.

## 4. Credential-class handling

| Credential class | Handling |
|---|---|
| Database credentials | Least-privilege app role (non-superuser, no `BYPASSRLS` — RLS cannot be bypassed by the app per ADR-0013); separate migration role used only by Alembic; TLS to DB |
| JWT keys | RS256 private key in secrets manager only; public key distributable; signing in `identity`, verification in middleware; denylisted `jti`s in Redis until natural expiry |
| Object storage keys | Platform-injected; presign-only permissions where the provider supports scoped keys; bucket private + SSE + block-public (ADR-0016) |
| AI provider keys | Injected at runtime into Gateway adapters only (import rule keeps SDKs — and therefore keys — out of domain code); per-key spend budgets configured at the provider where supported; keys never appear in `ai_requests` or logs |

## 5. Log redaction and PII

- **Redaction lives in the log formatter, not call sites** — one careless `log(body)` cannot leak: passwords, tokens, cookies, API keys, authorization headers are filtered centrally; prompt/completion bodies follow the `AI_PROMPT_LOGGING` policy (default `redacted`: truncated + scrubbed; `full` never in production).
- **PII minimization:** only email + display name are collected (A-09 posture). IP addresses stored as salted hashes in audit/session metadata. Learner content is sensitive-by-default: it leaves the boundary only as model input under the logging policy, and is never in event payloads (§E rule), never in admin views beyond metadata (A-05), never in client-visible error messages.
- Data minimization/deletion honored: account deletion cascades learner data; analytics/AI telemetry anonymized rather than deleted (assumptions A-06 disposition).

## 6. Uploaded document security

Per ADR-0016 + §M.3 verification pipeline: server-generated storage keys (client never chooses paths); presign-time content-type/size caps re-checked server-side on confirm; **magic-byte verification (`%PDF`)** — declared content type and extension are never trusted; SHA-256 checksum for integrity + duplicate detection; parsing happens **only in workers** with page/time/memory caps so a malicious or bomb PDF kills a task, not the API; downloads are short-lived presigned GETs with attachment disposition, never rendered inline from user-controlled origins; buckets private with SSE. Phase 1 (FUTURE TRIGGER): anti-malware scan step — the pipeline already has the insertion point.

## 7. Prompt-injection handling (structural, per principles §5 and ADR-0004)

- Retrieved material and tool results are inserted as **delimited, numbered DATA blocks** with framing that labels them reference data; the system prompt states instructions inside evidence are never followed.
- **Channel separation:** tool calls are honoured only from the model's tool-call channel — retrieved content cannot originate one.
- **Scope is server-injected:** a tenant id in tool arguments is rejected before validation and audited as a security signal (tool-contracts §4 order); allow-lists are per-feature.
- Input classifier flags known injection patterns → logged, metered, and write-tools disabled for that turn (flagged inputs do not silently fail).
- Even a *successful* injection cannot widen authorization (scope not model-controlled) — it can only produce a misleading answer, which the grounding gates (§8) bound into an insufficiency path, and which the audit trail records.

## 8. AI output validation (per principles §4, FR-42)

- Every AI-generated artifact crosses a **schema boundary before persistence or state change**: quiz questions, gradings, concept extractions, recommendation drafts, insufficiency decisions — Pydantic-validated, provider "structured mode" is never trusted alone.
- One bounded repair attempt with validation errors appended; second failure → typed `AIInvalidOutput` → documented per-feature fallback (skip question / `pending_review` grading / template recommendation). **Never persist unvalidated output.**
- Output checks: citation markers resolve to retrieved chunks (unresolvable → answer downgraded, never shipped); system-prompt-leak check; cross-project chunk-id assertion (mismatch raises + alerts, not silent filter); PII-echo check; sanitized markdown rendering in the UI (no raw HTML/script).
- `structured_output_validity_rate` tracked per feature — a sustained drop is an alert (model/prompt drift signal), per evaluation-strategy.

## 9. Transport and API surface

- TLS everywhere (platform-terminated, HSTS); app↔DB and app↔Redis TLS.
- CORS explicit origin allow-list; no wildcard with credentials.
- Bearer-token API (not CSRF-prone); the one cookie flow (refresh) is `HttpOnly; Secure; SameSite=Strict` + non-ambient-header check.
- Tiered rate limits (global/user/AI endpoints; login per IP **and** per account); request body caps per route; 404-not-403 on non-owned resources; RFC 9457 problem+json errors with `request_id` — no stack traces or provider errors to clients.

## 10. Security gates that cannot be skipped (CI)

1. Secret scan (credential-shaped strings fail the build).
2. Isolation suite (§M isolation gate — red blocks merge).
3. Dependency + image vulnerability scans; pinned dependencies; SBOM.
4. Import-boundary contracts (provider SDKs only in `ai/providers`; facade-only module access).
5. Authorization test matrix + IDOR fuzzing candidates (test-strategy TS2.5).

## 11. Prototype deferrals (explicit, per ADR-0018/0019 posture)

Email-verified accounts (A-04), MFA, session-management UI, progressive lockout, WAF tuning + DAST in CI, egress allow-listing at network level, anti-malware scanning, object versioning/lock. Each is a Phase 1 item with a trigger; none is silently absent.
