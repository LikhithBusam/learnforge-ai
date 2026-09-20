# Admin Module Architecture (Phase 10)

## Module Position in the Modular Monolith

```
apps/api/src/app/
├── admin/              ← Phase 10 (this module)
│   ├── models.py       AdminAuditLog, JobExecutionRecord ORM models
│   ├── schemas.py      Read-only admin DTOs (no mutation types)
│   ├── policies.py     assert_admin_role (404 concealment posture)
│   ├── repository.py   SQL aggregation queries via raw text() — no cross-module ORM imports
│   ├── service.py      Service façade: orchestrates repo + audit + health + telemetry
│   └── router.py       9 HTTP endpoints, all use AdminPrincipal
├── identity/           Provides AdminPrincipal dependency
├── platform/           Provides admin_session_scope, db, health, cache
└── ai/                 Provides ai.telemetry spine
```

The admin module reads aggregated data across user and project domains without importing other modules' ORM models — maintaining the **no cross-module model imports** boundary enforced by `scripts/check_boundaries.py`.

---

## Database Strategy

### Privileged Engine for Admin Reads

Admin read-models must aggregate across all users, bypassing Row Level Security (RLS). The admin service uses `admin_session_scope()` (the privileged engine, role=`studycompanion_owner` or equivalent Supabase project role with `BYPASSRLS`).

This is an explicit, auditable escape hatch — **never used for learner request paths**.

```
Learner request path:  session_scope(user_id=...) → runtime engine (RLS enforced)
Admin request path:    admin_session_scope()       → admin engine   (BYPASSRLS)
```

### Raw SQL Aggregations

`admin/repository.py` uses `sqlalchemy.text()` with bind parameters exclusively. This avoids:
1. Cross-module ORM model imports (boundary violation).
2. SQLAlchemy ORM overhead for aggregation queries.
3. N+1 queries — all counts are computed in a single SQL statement.

Example pattern:
```python
row = await session.execute(
    text("""
        SELECT
            (SELECT count(*) FROM users WHERE role = 'admin') as admins_count,
            (SELECT count(*) FROM users) as total_users
    """)
)
```

### Admin-Specific Tables

| Table | Purpose |
|-------|---------|
| `admin_audit_logs` | Immutable audit trail. RLS enabled: actor sees only their own rows (runtime role). Admin engine bypasses RLS to write. |
| `job_executions` | Background job telemetry. No RLS — global operational view. |

---

## Service Orchestration

`admin/service.py` is the single interface to all admin capabilities:

```
AdminService
├── get_platform_overview(actor_id)   → AdminPlatformOverviewDto
├── list_users(actor_id, page, ...)   → AdminUserListDto
├── get_user_detail(actor_id, uid)    → AdminUserDetailDto
├── list_projects(actor_id, page)     → AdminProjectListDto
├── get_project_detail(actor_id, pid) → AdminProjectDetailDto
├── get_material_processing_health()  → AdminMaterialProcessingDto
├── get_ai_usage_analytics(range)     → AdminAIUsageDto        (from telemetry spine)
├── get_job_observability(limit)      → AdminJobObservabilityDto
├── get_system_health()               → AdminSystemHealthDto   (from platform.health)
├── list_audit_logs(actor_id, page)   → AdminAuditLogListDto
└── record_job_execution(...)         → AdminJobExecutionDto   (called by Celery tasks)
```

Every function that reads data on behalf of an admin first calls `record_audit_event()` to produce an immutable audit log entry before returning data.

---

## Security Architecture

### Four-Layer Model

| Layer | Mechanism |
|-------|-----------|
| 1. Identity | `AdminPrincipal` → Bearer JWT verification → `principal.is_admin` |
| 2. Application | `assert_admin_role(principal)` → raises `NotFound` on non-admin (404 concealment) |
| 3. Database | `admin_session_scope()` uses the privileged engine; `session_scope()` for learners |
| 4. RLS | `admin_audit_logs` has RLS; `job_executions` is global read |

### Rejection Posture

```
Anonymous caller   → 401 Unauthorized (no/invalid token)
Authenticated learner → 403 Forbidden (valid token, wrong role)
                       [policies.py uses NotFound → HTTP 404 for resource-level concealment;
                        require_admin dep in router returns 403 for role-level]
Admin → 200 OK
```

---

## Module Boundaries

The admin module is governed by the **module-contracts**: no cross-module service imports, no cross-module ORM model imports. Read via raw SQL `text()` only.

```python
# CORRECT — raw SQL read
row = await session.execute(text("SELECT count(*) FROM users"))

# FORBIDDEN — cross-module model import
from app.identity.models import User  # ← boundary violation
```

Verified continuously by `scripts/check_boundaries.py` (Boundary check: 0 violations).

---

## Job Telemetry Integration

Celery tasks in `app/jobs/tasks.py` call `_record_telemetry()` after each task completes (success or failure). This is a fire-and-forget helper:

```python
def _record_telemetry(*, task_name, queue, status, duration_ms, ...):
    try:
        run_coroutine_sync(admin_service.record_job_execution(...))
    except Exception:
        logger.warning("job_telemetry_record_failed", ...)
        # Never re-raises — DB unavailability must not affect task outcome
```

Tasks instrumented:
- `infrastructure_probe` → queue `default`
- `enqueue_ai_probe` → queue `default`
- `process_material_document` → queue `documents`
- `process_mastery_evidence` → queue `learning`
- `process_growth_evaluation` → queue `learning`
- `generate_project_recommendations` → queue `learning`
- `ingest_analytics_event` → queue `analytics`
- `refresh_project_analytics` → queue `analytics`
