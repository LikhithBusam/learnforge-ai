# Admin Subsystem Security & Privacy Specification (Phase 10)

## 1. Authentication & Authorization Posture

### 1.1 RBAC Enforcement
All endpoints located under `/api/v1/admin/*` enforce strict Role-Based Access Control (RBAC):
- **Access Dependency**: `AdminPrincipal` (`app.identity.dependencies.AdminPrincipal`).
- **Mechanism**: The caller's Bearer JWT is cryptographically verified. The subject's role must equal `"admin"` (`principal.is_admin is True`).
- **Rejection Posture**:
  - Unauthenticated requests (no or invalid Bearer token) receive HTTP `401 Unauthorized`.
  - Non-admin authenticated users (e.g. learner / regular users) receive HTTP `403 Forbidden`.
  - For target resources that do not exist or belong to other domains, HTTP `404 Not Found` is returned.

### 1.2 No Client-Supplied Identity Bypass
All user identifiers, roles, and administrative claims are derived exclusively from the verified JWT token claims. Query parameters and headers representing client identity are rejected.

---

## 2. Data Minimization & Privacy Guarantees

### 2.1 Password & Secret Redaction
- `AdminUserDto` and `AdminUserDetailDto` schemas explicitly exclude `password_hash`, `refresh_token_hash`, and any session signing keys.
- ORM queries in `AdminRepository` select only safe projections: `id`, `email`, `role`, `status`, `created_at`, `updated_at`.

### 2.2 Content Privacy Protection
- Operational material inspection endpoints (`AdminMaterialProcessingDto`) return metadata only: material IDs, title, file size, status (`READY`, `FAILED`, `PENDING`), and sanitized ingestion error messages.
- Full PDF raw buffers, chunk embeddings, chunk text bodies, and tutor conversation prompts are never included in admin summary responses.

---

## 3. Immutable Audit Logging

Every administrative operation produces an audit entry in `admin_audit_logs`:
- **Actor Identification**: Recorded with `actor_user_id` and `actor_role`.
- **Action Semantics**: Action string (e.g. `view_overview`, `view_user_detail`, `view_project_detail`).
- **Target Tracking**: Resource category (`user`, `project`, `materials`, `platform`) and ID.
- **Traceability**: Correlation ID attached for end-to-end distributed tracing across API and background jobs.
- **Immutability**: No update or delete endpoints exist for audit logs; the repository provides append-only operations.

---

## 4. Operational Safety

- **Read-Only Posture**: The Phase 10 administrative API is strictly read-only and diagnostic. No destructive mutation endpoints (e.g. user deletion, score alteration, prompt manipulation) are exposed.
- **Query Bounding**: All collection endpoints enforce bounded pagination (`page >= 1`, `1 <= page_size <= 100`) to prevent denial-of-service or database memory exhaustion.
