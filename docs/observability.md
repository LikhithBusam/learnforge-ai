# System Observability (Phase 10)

## Observability Architecture

The AI Study Companion uses a three-tier observability stack:

```
Tier 1: Structured Logs    — python-json-logger → stdout → log aggregator
Tier 2: In-Memory Telemetry — ai.telemetry spine (ring buffer, 1000 entries)
Tier 3: Database Telemetry  — admin_audit_logs + job_executions tables
```

---

## AI Gateway Telemetry

### Telemetry Spine (`app.ai.telemetry`)

Every call through the AI Gateway — success or failure — produces an `AIRequestRecord` and appends it to an in-process ring buffer:

```python
_records: deque[AIRequestRecord] = deque(maxlen=1000)
```

**Fields captured per request:**

| Field | Description |
|-------|-------------|
| `ai_request_id` | Unique request identifier (UUIDv7) |
| `correlation_id` | Cross-system correlation ID (from `X-Correlation-ID`) |
| `request_id` | HTTP request ID |
| `feature` | Logical feature tag (e.g. `rag_generation`, `assessment_generation`) |
| `model_role` | Role of the model (`generation`, `embedding`) |
| `provider` | AI provider name (`gemini`, `stub`) |
| `model` | Model identifier (e.g. `gemini-2.5-pro`) |
| `input_tokens` | Prompt token count |
| `output_tokens` | Completion token count |
| `latency_ms` | End-to-end call latency in milliseconds |
| `time_to_first_token_ms` | TTFT for streaming calls |
| `estimated_cost_usd` | Estimated cost at the provider's published rate |
| `status` | `success` or `failed` |
| `error_type` | Error classification on failure (e.g. `timeout`, `rate_limit`) |

### Limitations

- **Process-scoped**: The buffer is in-process memory. It resets on worker restart and is not shared between multiple processes.
- **Bounded**: Maximum 1000 entries (ring buffer). Old entries are evicted when full.
- **Not persisted**: No DB durability in Phase 10. Persistent `ai_requests` table is planned for a future phase.

### Admin API Surface

`GET /api/v1/admin/ai/usage` reads from the telemetry spine and computes:
- Total / successful / failed request counts
- Average latency across all records
- Token volume (input + output)
- Estimated total cost
- Breakdown by feature and model

---

## Health Checks

### Liveness Probe (`GET /healthz`)

**Never checks dependencies.** Returns `{"status": "ok"}` immediately.

Rationale: A database blip must not cause a liveness failure that triggers a restart loop on a healthy process.

### Readiness Probe (`GET /readyz`)

Checks required infrastructure before accepting traffic:

```json
{
  "status": "ok",
  "components": {
    "database": {"status": "ok"},
    "cache": {"status": "ok"},
    "storage": {"status": "ok"}
  }
}
```

**Status semantics:**

| Component Status | Meaning |
|-----------------|---------|
| `ok` | Dependency reachable and responsive |
| `unconfigured` | Dependency URL not set (dev/test default; not a failure) |
| `error` | Dependency unreachable or returned an error |

**Overall status:**

| Overall | Condition |
|---------|-----------|
| `ok` | All required components (database, cache) are `ok` or `unconfigured` |
| `degraded` | At least one required component is `error` |

> [!NOTE]
> Storage is checked but does not affect the primary `status` field — only database and cache are considered required infrastructure for request serving.

### Admin System Health (`GET /api/v1/admin/health`)

Admin-facing system health aggregates the readiness probe components:

```json
{
  "status": "healthy",
  "checked_at": "2026-09-20T04:00:00Z",
  "components": {
    "database": {"status": "ok"},
    "cache": {"status": "ok"},
    "storage": {"status": "ok"}
  }
}
```

Maps `ok` → `healthy`, `degraded` → `degraded` for human-readable admin display.

---

## Background Job Telemetry

### Job Execution Records (`job_executions` table)

Every Celery task records a `JobExecutionRecord` on completion (success or failure) via the `_record_telemetry` fire-and-forget helper:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | UUIDv7 job record identifier |
| `task_name` | string | Fully qualified Celery task name |
| `queue` | string | Queue the task ran on (`default`, `documents`, `learning`, `analytics`) |
| `status` | string | `SUCCEEDED`, `FAILED`, or `RETRYING` |
| `started_at` | datetime | Task start timestamp (when available) |
| `completed_at` | datetime | Task completion timestamp |
| `duration_ms` | int | Wall-clock duration in milliseconds |
| `attempt` | int | Attempt number (1 for first try, 2+ for retries) |
| `correlation_id` | string | Correlation ID propagated from the triggering request |
| `error_message` | text | Sanitized error description (type name only, no sensitive data) |

### Queue Taxonomy

| Queue | Tasks |
|-------|-------|
| `default` | `infrastructure_probe`, `enqueue_ai_probe` |
| `documents` | `process_material_document` |
| `learning` | `process_mastery_evidence`, `process_growth_evaluation`, `generate_project_recommendations` |
| `analytics` | `ingest_analytics_event`, `refresh_project_analytics` |

### Fire-and-Forget Contract

The `_record_telemetry` helper in `jobs/tasks.py` is **never allowed to raise**. DB unavailability must not affect task outcome:

```python
def _record_telemetry(...) -> None:
    try:
        run_coroutine_sync(admin_service.record_job_execution(...))
    except Exception:
        logger.warning("job_telemetry_record_failed", ...)
        # Swallowed — telemetry is best-effort
```

### Error Message Sanitization

Error messages stored in `job_executions` are sanitized to `f"Task type failed: {type(exc).__name__}"` — never the raw exception message, which may contain sensitive stack traces or data.

---

## Correlation ID Propagation

Every HTTP request generates (or inherits) a correlation ID from the `X-Correlation-ID` header. This propagates through:

```
HTTP Request
  → Middleware sets correlation_id in context var
    → Service calls pass correlation_id to AI Gateway
      → AI telemetry records correlation_id
    → Celery task context envelope carries correlation_id
      → Job execution record stores correlation_id
        → Audit log record stores correlation_id
```

This enables full cross-system tracing: given any `correlation_id`, you can find:
- The HTTP request that triggered it
- The AI Gateway calls made during it
- The background jobs spawned by it
- The admin actions correlated with it

---

## Structured Logging

All log entries use `python-json-logger` with the consistent `get_logger(__name__)` factory. Key admin observability log events:

| Event | Level | Where |
|-------|-------|-------|
| `ai_request` | INFO | `ai/telemetry.py` — one per AI gateway call |
| `http_request` | INFO | `platform/router.py` — one per HTTP request |
| `job_telemetry_record_failed` | WARNING | `jobs/tasks.py` — if job telemetry DB write fails |
| `document_processing_succeeded` | INFO | `jobs/tasks.py` — material ingestion success |
| `document_processing_failed` | ERROR | `jobs/tasks.py` — material ingestion failure |
