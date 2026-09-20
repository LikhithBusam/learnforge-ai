# ADR-0020: Observability — Minimum Viable, Correlation-First

**Status:** DECIDED (Phase 0) · **Criteria basis:** C2, C7, C8, C10 · **Contracts affected:** §M.11 (AI metering), §M.13 (job health), §M.14 (logging/tracing), §M.10 (admin reads telemetry)

## Decision

**Minimum viable observability** = structured logs + request/correlation ids + the AI telemetry spine (`ai_requests` + `AIRequestCompleted`) + job-run records + a small set of actionable alerts, instrumented **vendor-neutrally via OpenTelemetry** with hosted free-tier-class backends (Grafana Cloud / Sentry class). No self-hosted ELK, no Prometheus cluster to operate, no APM suite — nothing that costs setup days inside the window (C1) or requires its own runbook.

## Application observability

| Concern | Mechanism |
|---|---|
| **Structured logs** | JSON per line: `timestamp, level, message, service, env, version, request_id, trace_id, user_id, project_id, route, status, duration_ms`. Redaction enforced centrally in the formatter (passwords, tokens, cookies, keys — security-baseline §8) |
| **Request IDs** | Generated at the edge, returned as `X-Request-Id` on every response (and `X-AI-Request-Id` on AI responses) — the id a user can quote and support can trace |
| **Correlation IDs** | One W3C `trace_id` propagated: HTTP → OTel spans → Celery task headers (async work joins the same trace) → `ai_requests.trace_id` → event envelopes (`correlation_id` per §E). A click is reconstructable through to the provider call and the background job it triggered |
| **Errors** | Unhandled exceptions → structured log + Sentry-class aggregation with release/version tags; client sees only the typed problem+json with `request_id`, never stack traces |
| **Latency** | Per-route duration histogram + DB query p95 from span timing; exporter → hosted metrics backend |

## AI observability (the spine)

Every model call (success **and** failure) records: `provider`, `model`, `feature`, `prompt_id` + `prompt_version`, `latency_ms`, `time_to_first_token_ms`, `input/output_tokens`, `estimated_cost_usd` (configured price table — estimate, labelled), `status` (success/timeout/provider_error/invalid_output/rate_limited/budget_exhausted/cancelled), `fallback_from`, `retrieval_meta` (strategy, k, top score, sufficiency decision, chunk ids), `trace_id`/`request_id`.

- Primary store: Postgres (`ai_requests`-class) — **because the admin dashboard must query it relationally alongside users/projects** (FR-90); secondary feed: `AIRequestCompleted` event → analytics rollups (§E).
- Sampling: 100% of AI-feature requests and errors; 10% routine CRUD traces (prototype volume makes 100% AI affordable and the debugging value is the point — FR-82).
- The admin AI views (usage, cost per feature/user/day, error/fallback rates, evaluation results) read these records — no separate LLM-ops SaaS.

## Background job observability

| Concern | Mechanism |
|---|---|
| Job identity | `job_runs`: job id, task name, dedup key, ownership ids, correlation id |
| Lifecycle | `queued → running → succeeded | failed | dead_lettered` with timestamps and durations |
| Retries | Attempt count + last error type/message recorded per attempt |
| Failure | Failed tasks log structured error + Sentry; exhausted → DLQ + `dead_lettered` + admin visibility + replay action (§M.13) |
| Queue health | Depth per queue, oldest-message age, failure rate, worker heartbeat → metrics backend; drives the backlog alerts below |

## Alerting (small set, every alert has a first response)

| Alert | Condition | Severity | First response |
|---|---|---|---|
| API error rate | 5xx > 2% over 5 min | P1 | Recent deploy → DB → provider status |
| Readiness failing | `/readyz` failing > 2 min | P1 | DB/Redis connectivity |
| Processing backlog | `documents` oldest message > ~15 min | P2 | Scale workers; OCR/provider health |
| DLQ growth | Any new dead-lettered job | P2 | Inspect `job_runs`; replay or fix |
| AI provider errors | Feature error rate > 20% over 10 min | P2 | Circuit/fallback status; consider role swap |
| Cost anomaly | Hourly estimated spend > 3× trailing mean | P2 | Feature/user attribution; abuse or prompt regression |
| Grounding regression | Citation-validity/sufficiency rate drops > ~10 pts day-over-day | P2 | Diff prompt/model/retrieval config; run eval suite |
| Auth anomaly | Failed logins > 10× baseline | P2 | Credential-stuffing posture (ADR-0018) |

**Discipline:** an alert without a known first response is deleted, not muted. More alerts are added when a real incident proves the need — not speculatively.

## Options considered

1. **OTel SDK + hosted free-tier backends (Grafana Cloud / Sentry class) ✅** — vendor-neutral instrumentation, zero self-hosted ops, enough for FR-81/82 within the window.
2. **Self-hosted Prometheus + Grafana + Loki + Tempo** — full control, real dashboards; but operating the stack is its own day of work (violates C1); FUTURE TRIGGER at Phase 1 with real traffic.
3. **All-in-one commercial APM** — fast but cost + vendor lock on telemetry; re-evaluate at Phase 1 if budget allows.
4. **Logs-only (no metrics/tracing)** — insufficient for latency/queue/cost alerting; rejected.

## Dashboard set (minimal)

1. Service health: RED per route, container health, dependency status.
2. Async pipeline: queue depth/age, task durations, retries, DLQ, ingestion funnel (uploaded → processing → ready → failed).
3. AI operations: per feature volume/latency/TTFT/cost/error/fallback; AI quality: citation-validity, sufficiency, refusal rate vs prompt/model versions.

## Consequences

- (+) Every FR-82 investigation question is answerable from day one; zero observability-ops burden; telemetry is portable (OTel) if backends change.
- (−) Hosted free tiers have ingestion limits (acceptable at prototype volume; raising limits is config/cost); span-level DB detail is coarser than a dedicated APM (fine — the slow paths here are provider calls, which are fully instrumented).

## Revisit triggers

1. Real continuous traffic (Phase 1) → self-hosted or paid-tier metrics; add USE metrics per container, DB exporter detail.
2. An incident class that the minimal alert set misses → add the specific alert, not a platform.
3. Compliance requirement on log retention (A-06) → adjust log-stream retention config.
