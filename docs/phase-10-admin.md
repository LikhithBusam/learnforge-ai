# Phase 10 — Admin Dashboard & System Observability

## Overview

Phase 10 adds a **read-only, admin-only observability API** to the AI Study Companion modular monolith. It provides aggregated platform visibility — user metrics, project activity, material processing health, AI gateway analytics, background job telemetry, and system health checks — through a strictly bounded admin façade.

**Design posture**: The admin API is read-only and diagnostic. It aggregates data across users for operational oversight. It never exposes raw user content, credentials, or AI conversation bodies.

---

## API Endpoints

All endpoints are at `/api/v1/admin/` and require an authenticated admin JWT.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/overview` | Platform-wide usage summary |
| `GET` | `/api/v1/admin/users` | Paginated user directory |
| `GET` | `/api/v1/admin/users/{user_id}` | User detail with activity counts |
| `GET` | `/api/v1/admin/projects` | Paginated project directory |
| `GET` | `/api/v1/admin/projects/{project_id}` | Project detail with learning metrics |
| `GET` | `/api/v1/admin/materials/processing` | Material ingestion health |
| `GET` | `/api/v1/admin/ai/usage` | AI gateway usage analytics |
| `GET` | `/api/v1/admin/jobs` | Background job telemetry |
| `GET` | `/api/v1/admin/health` | System health (DB, cache, storage) |
| `GET` | `/api/v1/admin/audit` | Paginated admin audit log |

---

## Authentication & Authorization

Every endpoint uses `AdminPrincipal` — a typed FastAPI dependency that:

1. Extracts and verifies the Bearer JWT.
2. Checks `principal.is_admin == True` (role must be `"admin"`).
3. Raises `403 Forbidden` for authenticated non-admin callers.
4. Raises `401 Unauthorized` for invalid/missing tokens.

Non-admin callers never learn that admin endpoints exist (404-concealment posture for resource-level checks; 403 for role-level).

```python
# Usage in router
@router.get("/overview")
async def get_overview(principal: AdminPrincipal) -> AdminPlatformOverviewDto:
    ...
```

---

## Endpoint Reference

### `GET /api/v1/admin/overview`

Returns a snapshot of platform-wide counters.

**Response** (`AdminPlatformOverviewDto`):
```json
{
  "users":     {"total": 150, "active": 120, "admins": 3},
  "spaces":    {"total": 200},
  "projects":  {"total": 480},
  "materials": {"total": 1200, "ready": 1180, "processing": 5, "failed": 15},
  "learning":  {"total_events": 52000, "active_projects": 95},
  "ai":        {"total_requests": 8400, "failed_requests": 42},
  "jobs":      {"total_executions": 3200, "failed_executions": 18},
  "timestamp": "2026-09-20T04:00:00Z"
}
```

### `GET /api/v1/admin/users?page=1&page_size=50`

Paginated list of all users. **No password hashes or session tokens are included.**

Query parameters:
- `page` (int, ≥1, default 1)
- `page_size` (int, 1–100, default 50)

**Response** (`AdminUserListDto`):
```json
{
  "items": [
    {"id": "...", "email": "user@example.com", "display_name": "...",
     "role": "learner", "status": "active", "created_at": "..."}
  ],
  "total": 150, "page": 1, "page_size": 50
}
```

### `GET /api/v1/admin/users/{user_id}`

User detail with aggregated activity counts.

**Response** (`AdminUserDetailDto`):
```json
{
  "id": "...", "email": "...", "display_name": "...",
  "role": "learner", "status": "active", "created_at": "...",
  "spaces_count": 3, "projects_count": 7,
  "study_events_count": 842, "last_activity_at": "..."
}
```

### `GET /api/v1/admin/materials/processing`

Aggregated material ingestion health across the platform.

**Response** (`AdminMaterialProcessingDto`):
```json
{
  "total": 1200, "ready": 1180, "processing": 5, "upload_pending": 0, "failed": 15,
  "recent_failures": [
    {"material_id": "...", "project_id": "...", "title": "Lecture 3.pdf",
     "status": "FAILED", "size_bytes": 2097152, "failure_reason": "...", "created_at": "..."}
  ]
}
```

### `GET /api/v1/admin/ai/usage?range=24h`

AI gateway usage analytics from the in-memory telemetry spine.

Query parameters:
- `range` (str, default `"24h"`) — time range label (informational)

**Response** (`AdminAIUsageDto`):
```json
{
  "range": "24h",
  "total_requests": 8400,
  "successful_requests": 8358,
  "failed_requests": 42,
  "total_input_tokens": 2100000,
  "total_output_tokens": 840000,
  "avg_latency_ms": 487.3,
  "by_feature": {"rag_generation": 5200, "assessment_generation": 3200},
  "by_model": {"gemini-2.5-pro": 8400},
  "estimated_cost_usd": 4.2
}
```

> [!NOTE]
> AI telemetry is sourced from the **in-process memory spine** (`app.ai.telemetry`), a ring buffer of up to 1000 entries. It resets on process restart. A persistent `ai_requests` table is planned for a future phase.

### `GET /api/v1/admin/jobs?limit=50`

Background job execution telemetry from the `job_executions` table.

**Response** (`AdminJobObservabilityDto`):
```json
{
  "total_executions": 3200,
  "succeeded_count": 3182,
  "failed_count": 18,
  "retrying_count": 0,
  "recent_executions": [
    {"id": "...", "task_name": "app.jobs.tasks.process_material_document",
     "queue": "documents", "status": "SUCCEEDED", "duration_ms": 1450,
     "attempt": 1, "correlation_id": "...", "error_message": null, "created_at": "..."}
  ]
}
```

### `GET /api/v1/admin/health`

System health based on infrastructure probes.

**Response** (`AdminSystemHealthDto`):
```json
{
  "status": "healthy",
  "checked_at": "...",
  "components": {
    "database": {"status": "ok"},
    "cache": {"status": "ok"},
    "storage": {"status": "ok"}
  }
}
```

Status values: `healthy` (all required infra OK) | `degraded` (DB or cache error).

### `GET /api/v1/admin/audit?page=1&page_size=50`

Paginated admin audit log. Append-only. Covers all actions performed by admins.

**Response** (`AdminAuditLogListDto`):
```json
{
  "items": [
    {"id": "...", "actor_user_id": "...", "actor_role": "admin",
     "action": "view_overview", "target_type": "platform", "target_id": null,
     "occurred_at": "...", "correlation_id": "...", "metadata_payload": {}}
  ],
  "total": 82, "page": 1, "page_size": 50
}
```

---

## Audit Actions

Every admin endpoint call produces an immutable audit log entry:

| Endpoint | Action String | Target Type |
|----------|--------------|-------------|
| `GET /overview` | `view_overview` | `platform` |
| `GET /users` | `list_users` | `user` |
| `GET /users/{id}` | `view_user_detail` | `user` |
| `GET /projects` | `list_projects` | `project` |
| `GET /projects/{id}` | `view_project_detail` | `project` |
| `GET /materials/processing` | `view_material_processing` | `materials` |
| `GET /ai/usage` | `view_ai_usage` | `ai` |
| `GET /jobs` | `view_job_observability` | `jobs` |
| `GET /health` | `view_system_health` | `platform` |
| `GET /audit` | `view_audit_log` | `audit` |

---

## Data Minimization Guarantees

- **User responses**: No `password_hash`, no `refresh_token_hash`, no session keys.
- **Material responses**: Metadata only — title, status, size, sanitized failure reason. No PDF bytes, chunk text, or embeddings.
- **AI responses**: Aggregated metrics only — counts, latency, tokens, cost. No prompts, completions, or user identifiers.
- **Project responses**: Aggregated counts only. No tutor conversation bodies.
