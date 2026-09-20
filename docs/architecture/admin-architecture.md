# Admin Dashboard & System Observability Architecture (Phase 10)

## 1. Overview & Architectural Role

The **Admin Subsystem (`app.admin`)** provides an operational, cross-domain observability surface for operators and platform engineers. It sits alongside domain modules as a read-oriented administrative facade, delivering:

- **Platform-wide health and activity aggregates** (Users, Spaces, Projects, Materials, AI Requests, Celery Jobs).
- **User inspection and management** with strict privacy guarantees and data minimization.
- **Project directory and operational summaries**.
- **Material ingestion processing status and failure diagnostics**.
- **AI Gateway telemetry** (token volume, latency p50/p95/p99, cache hits, error rates, provider distribution).
- **Background job execution observability** (task status, retry counts, execution durations, queue distribution).
- **Infrastructure dependency health** (Database, Redis cache, Object Storage readiness).
- **Immutable administrative audit logging** capturing every administrative query and event.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application Gateway                     │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                             (AdminPrincipal RBAC)
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │       app.admin.router          │
                    │   /api/v1/admin/* (Protected)   │
                    └────────────────┬────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │       app.admin.service         │
                    └───────┬─────────────────┬───────┘
                            │                 │
             ┌──────────────┴──────────┐      │
             ▼                         ▼      ▼
    ┌─────────────────┐      ┌─────────────────────────┐
    │  AdminRepository│      │   AI Gateway Telemetry  │
    │  Raw SQL Aggs   │      │   Platform Health Probe │
    └────────┬────────┘      └─────────────────────────┘
             │
             ▼
    ┌─────────────────────────┐
    │  PostgreSQL (Supabase)  │
    │  - admin_audit_logs     │
    │  - job_execution_records│
    │  - read-only domain dbs │
    └─────────────────────────┘
```

---

## 2. Architectural Boundaries & Data Isolation

### 2.1 Cross-Module Independence (R1 Boundary Enforcement)
- **Zero ORM Model Imports**: The `admin` module **NEVER** imports SQLAlchemy models or internal repositories from `identity`, `workspace`, `materials`, `knowledge`, `tutor`, `assessment`, `mastery`, `growth`, `recommendations`, or `analytics`.
- **Database Boundary Layer**: Aggregations across domain tables are executed using explicit SQL queries and views in `AdminRepository`, preventing tight schema-coupling and cyclic module dependencies.
- **Service-Level Delegation**: Where business logic exists, domain service facades are called rather than internal state.

### 2.2 Strict Data Minimization
Administrative DTOs strictly omit sensitive credentials and private learner content:
- **Never Exposed**: `password_hash`, `refresh_token_hash`, session secrets, API keys.
- **Learner Privacy**: Raw uploaded PDF binary buffers, chunk text bodies, and conversational prompt transcripts are excluded from admin listing views.

---

## 3. Database Schema

Phase 10 introduces two dedicated tables managed via Alembic migration `0010_phase10_admin_observability`:

### 3.1 `admin_audit_logs`
Immutable audit log recording every administrative inspection action:
- `id` (UUIDv7 primary key)
- `actor_user_id` (UUID foreign key -> `users.id`)
- `actor_role` (VARCHAR(32), e.g. "admin")
- `action` (VARCHAR(64), e.g. "view_overview", "view_user_detail")
- `target_type` (VARCHAR(64), e.g. "user", "project", "platform")
- `target_id` (VARCHAR(128) nullable)
- `occurred_at` (TIMESTAMPTZ, default UTC now)
- `correlation_id` (VARCHAR(128) nullable)
- `metadata_payload` (JSONB default '{}')
- **Indexes**: `ix_admin_audit_logs_actor_occurred (actor_user_id, occurred_at DESC)`, `ix_admin_audit_logs_action_occurred (action, occurred_at DESC)`.

### 3.2 `job_execution_records`
Telemetry log for Celery background tasks:
- `id` (UUIDv7 primary key)
- `task_name` (VARCHAR(128))
- `queue` (VARCHAR(64))
- `status` (VARCHAR(32), e.g. "SUCCESS", "FAILURE", "RETRY")
- `duration_ms` (INTEGER nullable)
- `attempt` (INTEGER, default 1)
- `correlation_id` (VARCHAR(128) nullable)
- `error_message` (TEXT nullable)
- `created_at` (TIMESTAMPTZ, default UTC now)
- **Indexes**: `ix_job_execution_records_task_created (task_name, created_at DESC)`, `ix_job_execution_records_status (status)`.

---

## 4. Endpoints Summary

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/v1/admin/overview` | Platform high-level totals & status | Admin (JWT role=admin) |
| `GET` | `/api/v1/admin/users` | Paginated user list | Admin |
| `GET` | `/api/v1/admin/users/{user_id}` | Detailed user record (minimized) | Admin |
| `GET` | `/api/v1/admin/projects` | Paginated project list | Admin |
| `GET` | `/api/v1/admin/projects/{project_id}` | Project operational summary | Admin |
| `GET` | `/api/v1/admin/materials/processing`| Ingestion health & failure diagnostics | Admin |
| `GET` | `/api/v1/admin/ai/usage` | AI Gateway token & latency analytics | Admin |
| `GET` | `/api/v1/admin/jobs` | Background task telemetry | Admin |
| `GET` | `/api/v1/admin/health` | Subsystem readiness & health probe | Admin |
| `GET` | `/api/v1/admin/audit` | Paginated audit trail | Admin |
