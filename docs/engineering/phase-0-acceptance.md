# Phase 0 — Goals, Acceptance Criteria, and Status

**Status:** Scaffold complete and locally verified. **No product features are implemented** — this phase establishes boundaries, infrastructure, and traceability only.

> **2026-09-19 — Verification gate:** the full live verification (Compose stack, real Celery broker run,
> MinIO integration, all CI-gate equivalents, security checks) is recorded in
> `phase-0-verification.md`. Acceptance rows A4/A5 are now *verified* (mypy/ruff/black clean); A10's
> live-broker exercise was performed with a real Redis-backed worker (solo pool on Windows dev).

## Goals

1. Establish the 14 module boundaries exactly as contracted (`module-contracts.md`), machine-enforced.
2. Stand up infrastructure foundations: PostgreSQL 16+pgvector, Redis (broker/cache only), MinIO (S3-compatible), Alembic, Celery (4 queues + Beat).
3. Provide the AI Gateway with provider-neutral interfaces and a deterministic `stub` provider — CI runs offline, no AI credentials anywhere.
4. Prove end-to-end **traceability** with one vertical slice: HTTP → correlation id → Celery → AI Gateway → stub → recorded telemetry.
5. Wire the CI gate order from the test strategy (format → lint → boundaries → types → unit → integration), provider-free.

## Acceptance criteria (all verified — see §verification)

| # | Criterion | Evidence |
|---|---|---|
| A1 | `pytest tests/unit tests/boundary tests/integration` green | Unit: gateway envelope/redaction/config fail-safe; Boundary: R1–R4 incl. negative cases; Integration: vertical slice |
| A2 | Vertical slice: one correlation id observable across API → task → gateway → telemetry | `tests/integration/test_vertical_slice_trace.py::test_vertical_slice_correlation_id_consistent` |
| A3 | `python scripts/check_boundaries.py` exits 0 | No violations across all backend files |
| A4 | `mypy` clean on platform/ai/jobs/main | Typed foundation; domain stubs excluded until implemented |
| A5 | `ruff` + `black --check` clean | Enforced in CI gate 2–3 |
| A6 | Config fails safely: `APP_ENV=production` without critical settings refuses to boot | `test_production_config_requires_critical_settings` |
| A7 | No secrets in repo: only `.env.example` (placeholders), gitleaks in CI, redaction formatter tested | `test_log_redaction_*`, CI gate 1 |
| A8 | AI provider labelled `stub` everywhere; no provider SDKs imported outside `app.ai`/`app.platform` | Boundary rules R2/R5 + `/internal/ai/status` |
| A9 | Health endpoints: liveness has zero dependency checks; readiness reports per-dependency status without leaking credentials | `test_health_endpoints` |
| A10 | Redis is not a system of record: outbox/durable records deferred to DB phase; broker loss = delay only (architecture, not yet exercised at scale) | ADR-0014; persistence phase pending |

## Vertical slice — expected correlation behavior

```text
POST /internal/jobs/probe   (X-Correlation-ID: <cid>)
  → middleware accepts <cid> (or creates one) and returns it in X-Correlation-ID
  → task envelope {request_id, correlation_id, user_id?, project_id?, event_id?}
  → Celery (eager in CI; real broker locally) → task_prerun re-binds context
  → worker calls AI Gateway.generate(feature="infrastructure.probe")
  → stub provider executes → result carries ai_request_id
  → telemetry records {correlation_id, request_id, feature, role, provider="stub",
                       model="stub-generation", status, latency, tokens, cost=0}
  → task result echoes correlation_id + ai_request_id
```

The test asserts the **same `<cid>`** at every hop, and that the AI record found
by `correlation_id` matches the `ai_request_id` returned to the caller (FR-82 shape).

## CI gates (order per test-strategy §4, Phase 0 subset)

1. Secret scan (gitleaks) + env-file hygiene
2. Format (black) 3. Lint (ruff)
4. Architecture boundaries (scripts/check_boundaries.py)
5. Types (mypy on platform/ai/jobs/main)
6. Unit + boundary tests 7. Integration (vertical slice)
*Deferred to later phases:* repository/API/isolation suites (need compose services), AI evaluation golden sets (need dataset), image build/scan/SBOM, E2E.

## Known limitations

1. **No application schema yet** — no business tables, no RLS policies (next phase per ADR-0013; `alembic/versions` is empty by design, autogenerate intentionally disabled until models exist).
2. **Telemetry is in-memory** — `ai_requests`-style persistence arrives with the schema phase; the record shape is already the contract.
3. **Single worker consumes all queues** — queue routing is pre-configured so splitting is config-only (ADR-0014).
4. **No auth** — identity module is a stub; `user_id`/`project_id` context plumbing is exercised via envelopes only.
5. **myis strict scope** — platform/ai/jobs/main are typed; domain stubs are excluded until implemented.
6. **AI_PROMPT_LOGGING policy** is implemented as redaction-in-formatter; the three-level policy switch lands with the Gateway persistence phase.
7. **Docker services** are verified via compose healthchecks in local dev; CI runs the test suite without services (eager/in-memory) — compose-in-CI arrives with the integration-DB suites.
