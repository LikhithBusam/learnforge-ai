# Phase 0 Verification Gate — Results

**Date:** 2026-09-19 · **Scope:** infrastructure verification only — no business tables, no product features.
**Verification classes:** `container verified` (run against the live Compose stack) · `locally verified` (run on the dev host against the live stack or in-process) · `CI verified` (executed by GitHub Actions) · `unverified` (not executed in this session).

**Rule honored:** PASS is recorded only where evidence exists. CI itself has **not** run yet (nothing has been pushed) — all CI results below are *local equivalents* of the gates.

---

## 1. Evidence table

| # | Check | Result | Evidence | Notes |
|---|---|---|---|---|
| 1.1 | PostgreSQL 16 + pgvector starts | **PASS** (container) | `pgvector/pgvector:pg16` → `healthy`; `SELECT … pg_available_extensions` → `vector 0.8.6` | Extension available; schema (and `CREATE EXTENSION`) belongs to the DB phase |
| 1.2 | Redis starts | **PASS** (container) | `redis:7-alpine` → `healthy`; `redis-cli ping` via Celery broker db1 | Broker/cache only — not exercised as a record (by design) |
| 1.3 | MinIO starts | **PASS** (container) | `quay.io/minio/minio` → `healthy` | Image source corrected — see Issue-3 |
| 1.4 | Healthchecks become healthy | **PASS** (container) | `docker compose ps` → all 3 `(healthy)` | `minio-init` one-shot exit 0 |
| 1.5 | Persistent volumes | **PASS** (container) | Named volumes `studycompanion_{postgres,redis,minio}_data`; containers restarted → `healthy` again, API readiness returned to `ok` | Restart-recovery of the SQLAlchemy pool observed live |
| 1.6 | Ports respond | **PASS** (container) | 5432 / 6379 / 9000 / 9001 reachable from host; 9001 console HTTP 200 | |
| 1.7 | Service-to-service networking | **PASS** (container) | `minio-init` created the bucket via `MC_HOST_local=http://…@minio:9000` (compose DNS) exit 0 | |
| 2.1 | Liveness `/healthz` | **PASS** (container) | `{"status":"ok"}` — zero dependency checks | A depressed DB cannot restart-loop healthy pods |
| 2.2 | Readiness `/readyz` reflects dependencies | **PASS** (container) | With live infra: `{"status":"ok","components":{"database":"ok","cache":"ok","storage":"ok"}}`; the degraded/unconfigured state is proven by `tests/integration` (no-infra fixture) | |
| 2.3 | Health endpoints leak no secrets | **PASS** (container) | Payload scan for `password/secret/key/token` → 0 hits; config `safe_summary()` masks credentials | |
| 3.1 | Real Celery worker vs live Redis (no eager) | **PASS** (container + locally) | Worker `celery@… ready`, `Connected to redis://localhost:6379/1`; `control.inspect().ping()` → `pong`; task `SUCCESS` via the Redis result backend | Solo pool on Windows dev — see Issue-2 |
| 3.2 | API → Redis → Worker → AI Gateway → stub | **PASS** (container) | Task `app.jobs.tasks.enqueue_ai_probe` received + succeeded in worker log; result carries `provider="stub", model="stub-generation"` | Stub provider only — no external AI calls |
| 4.1 | Correlation trace across all hops | **PASS** (container) | See §2 — one correlation id across API log, task envelope, worker logs, AI telemetry, task result | This was the consistency-audit item R-C17 |
| 4.2 | Worker-side structured logging | **PASS** (container) | Worker log lines are JSON with `request_id`/`correlation_id` fields | Fixed this gate — see Issue-4 |
| 5.1 | MinIO integration (provider-level) | **PASS** (container) | `MinioStorage` against :9000 — bucket `studycompanion-dev` ok; upload 24 B; `head_object` → size/etag/last_modified/content-type; round-trip `get_bytes`; presigned GET (`X-Amz-Signature` present, TTL); delete → `head_object` None | Harmless probe object under `phase0-verification/`, deleted afterwards; **no materials workflow built** |
| 6.1 | Format (black) | **PASS** (locally) | `108 files would be left unchanged` | Was drifting — Issue-5 |
| 6.2 | Lint (ruff) | **PASS** (locally) | `All checks passed!` | 138 auto-fixable + 4 real findings cleaned |
| 6.3 | Types (mypy, platform/ai/jobs/main) | **PASS** (locally) | `Success: no issues found in 108 source files` | Now a **blocking** CI gate — Issue-5 |
| 6.4 | Unit + boundary + integration tests | **PASS** (locally) | `20 passed` (unit incl. redaction/fail-safe, boundary negatives, vertical slice) | Provider-free, offline |
| 6.5 | Architecture boundary checker | **PASS** (locally) | `103 files, no violations`; negative cases in `tests/boundary` | See §3 |
| 6.6 | Dependency audit (pip-audit) | **PASS** (locally) | No known vulnerabilities reported; skips = editable installs + local `torch`/`torchvision` CPU builds (not on PyPI, by construction) | Gate added to CI — Issue-6 |
| 6.7 | Secret scan | **PASS** (locally) | Credential-pattern scan over source/configs/docs → only the *synthetic* token inside the redaction unit test | Gitleaks runs in CI on push (unverified here) |
| 6.8 | Environment hygiene | **PASS** (locally) | Only `.env.example` exists in the worktree; `CHANGE_ME` placeholders intact | `git ls-files` variant runs in CI — **not a git repository in this workspace**, so git-history checks are CI-only |
| 6.9 | CI itself | **UNVERIFIED** | No push/Actions run performed | Deliberately not claimed |
| 7.1 | Domain → foreign `repository/models` forbidden | **PASS** (locally) | Boundary checker R1 + negative tests (`tutor → knowledge.repository` style) | |
| 7.2 | Provider SDKs isolated in AI layer | **PASS** (locally) | R2/R5: `openai/anthropic/…/minio` imports allowed only in `app.ai`/`app.platform`; domain stubs import none | |
| 7.3 | AI Gateway boundary (no reverse deps) | **PASS** (locally) | R3: `app.ai` imports no domain modules; R4: `app.platform` imports no domain modules | |
| 7.4 | No new forbidden imports | **PASS** (locally) | Checker re-run after all changes: 0 violations | |
| 8.1 | No real keys / DB passwords in source | **PASS** (locally) | Compose contains only documented dev-only credentials (security-baseline §1); source has none | |
| 8.2 | Logs redact sensitive values | **PASS** (locally) | Redaction unit tests pass; live API access logs contain no `authorization/cookie/key` strings | Redaction lives in the shared JSON formatter, now also on the worker |
| 8.3 | Production fail-safe | **PASS** (locally) | `APP_ENV=production` without config → `RuntimeError: Refusing to boot: required production configuration missing: CELERY_BROKER_URL, DATABASE_URL, JWT_PRIVATE_KEY, REDIS_URL` | |

## 2. Correlation trace (real request through the live broker)

| Hop | request_id | correlation_id | Artifact |
|---|---|---|---|
| HTTP request | `e1b69147-e694-4b20-9e2a-e216afbedf86` | `8d60336c-f59e-43b6-b001-b1496cd13a93` | Response headers `X-Request-ID`, `X-Correlation-ID` |
| API log | same | same | `http_request route=/internal/jobs/probe status=200` |
| Task envelope → worker | same | same | job_id `f338fc2b-b18d-4b49-8abb-f9b83048c9ac` |
| AI Gateway telemetry (worker side) | same | same | `ai_request provider=stub model=stub-generation ai_request_id=74188fb2-bad0-4774-b790-1f95f7cff942 status=success` |
| Task result (Redis backend) | same | same | `SUCCESS … ai_request_id=74188fb2…` |

## 3. Issues found during the gate (documented, not silently fixed)

| ID | Severity | Issue | Disposition |
|---|---|---|---|
| Issue-1 | **High** (build-breaking) | `celery_app.worker_main(...)` raised `ValueError: The worker sub-command must be specified` on Celery 5.3 — worker could not start at all | **Fixed** (`run_worker.py` passes the `worker` sub-command); verified live. The scaffold's local verification never started a real worker — this is exactly what the gate exists to catch |
| Issue-2 | Medium (platform) | Celery prefork/billiard pool unsupported on Windows dev hosts (`fast_trace_task` unpack error) | **Fixed**: `WORKER_POOL` env with `solo` default on win32 (prefork elsewhere); documented in `local-development.md`. Deployment-level choice only — ADR-0014 queue architecture unchanged |
| Issue-3 | Low (infra) | `minio/minio` no longer exists on docker.io → compose pull failed | **Fixed**: images pinned to `quay.io/minio/{minio,mc}`; bucket-provisioning `minio-init` job added; compose config validated |
| Issue-4 | Medium (observability) | Worker logs bypassed the JSON/redaction formatter (Celery's logging hijack) — correlation fields and redaction were lost on the worker plane | **Fixed**: `setup_logging` + `after_setup_logger`/`after_setup_task_logger` receivers enforce the app formatter; verified in live worker logs |
| Issue-5 | Medium (gate integrity) | Acceptance rows A4/A5 claimed mypy/black/ruff cleanliness that was not actually enforced (3 mypy errors, 116 ruff findings, 17 black refiles) | **Fixed**: all gates now genuinely clean; mypy made a **blocking** CI gate (was `|| true`); acceptance doc annotated |
| Issue-6 | Low (CI coverage) | Dependency audit was listed as a gate but absent from the workflow | **Fixed**: `pip-audit --skip-editable` gate added |
| Issue-7 | Low (hygiene) | Minor lint findings (unused vars/imports, mutable ContextVar default, missing import in the boundary script) | **Fixed**; behavior-preserving |

**No architectural decisions were modified.** Every fix above is implementation- or deployment-level; ADR-0013/0014/0016/0019/0020 decisions and all module contracts stand unchanged.

## 4. Unverified / deferred

1. **CI verified** — nothing has been pushed; GitHub Actions has not executed. All gate results above are local equivalents.
2. Git-history-based secret scanning (gitleaks on history) — requires a git remote; not applicable to this non-git workspace snapshot.
3. Prefork worker pool on Linux/CI — this session ran solo (Windows host); Linux behavior is expected-standard but unexercised here.
4. In-memory AI/job telemetry — persistence arrives with the schema phase (known Phase 0 limitation, unchanged).

## 5. Verdict

**Phase 0 acceptance criteria are satisfied** on the evidence above: infrastructure healthy and persistent, API liveness/readiness correct, a real broker round-trip with a single correlation id across all five hops, MinIO integration proven at the provider level, all static/test/security gates clean, and the production fail-safe intact. The gate surfaced and fixed four real defects (two of which — Issue-1 and Issue-4 — would have bitten the schema phase immediately). Database schema implementation may begin.
