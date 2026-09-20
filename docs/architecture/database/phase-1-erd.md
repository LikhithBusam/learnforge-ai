# Phase 1 ERD — Identity + Workspace

**Status:** Implemented. All relationships cascade from `users` (account deletion removes all learner data — retention requirement).

```mermaid
erDiagram
    USERS ||--o{ REFRESH_SESSIONS : "owns sessions"
    USERS ||--o{ SPACES : "owns"
    USERS ||--o{ PROJECTS : "owns (denormalized, trigger-consistent)"
    SPACES ||--o{ PROJECTS : "contains"
    USERS ||--o{ PROJECT_MEMBERSHIPS : "member"
    PROJECTS ||--o{ PROJECT_MEMBERSHIPS : "has"

    USERS {
        uuid id PK "UUIDv7, app-generated"
        text email "unique (case-insensitive)"
        text password_hash "argon2id PHC"
        text role "learner|admin"
        text status "active|disabled"
        timestamptz created_at
        timestamptz updated_at
    }
    REFRESH_SESSIONS {
        uuid id PK
        uuid user_id FK "CASCADE"
        varchar token_hash "sha256 hex, unique"
        timestamptz expires_at
        timestamptz revoked_at "nullable"
        varchar revoked_reason "rotated|reuse_detected|logout|admin_revoke"
        uuid parent_session_id FK "rotation chain, SET NULL"
        timestamptz created_at
    }
    SPACES {
        uuid id PK
        uuid owner_id FK "CASCADE"
        text name "unique per owner (case-insensitive)"
        text description "nullable"
        timestamptz created_at
        timestamptz updated_at
    }
    PROJECTS {
        uuid id PK
        uuid space_id FK "CASCADE"
        uuid owner_id FK "must equal space owner (trigger)"
        text name "unique per space (case-insensitive)"
        text description "nullable"
        text learning_goal "nullable"
        text status "active|archived"
        timestamptz created_at
        timestamptz updated_at
    }
    PROJECT_MEMBERSHIPS {
        uuid id PK
        uuid project_id FK "CASCADE"
        uuid user_id FK "CASCADE"
        text role "owner only today (A-16)"
        timestamptz created_at
    }
```

## Relationships, cardinality, and boundaries

| Relationship | Cardinality | Ownership semantics | Authorization boundary | RLS boundary |
|---|---|---|---|---|
| User → RefreshSession | 1 : 0..N | Session belongs to its user | Login path (future phase) reads by token hash | `user_id = app_user_id()` — no cross-user reads even via raw SQL |
| User → Space | 1 : 0..N | Space owned by exactly one user | Service layer: owner-scoped reads/writes only (404 on mismatch) | `owner_id = app_user_id()` |
| Space → Project | 1 : 0..N | Project lives inside one space; owner equality trigger-enforced | Space owner = project owner (single ownership chain) | `owner_id = app_user_id()` |
| User → ProjectMembership | 1 : 0..N | Membership row bound to user + project | Membership created only as part of project creation (service) | `user_id = app_user_id()` |
| Project → ProjectMembership | 1 : 0..N (1 owner today) | Exactly one `owner` membership (partial unique index) | A-16: single learner per project; collaboration deferred | Row-keyed; `has_project_access()` prepared for future (unused) |

## Project-isolation boundary

`projects.owner_id` is the isolation key for every later-phase table (materials, conversations, mastery, … will carry `project_id` and key their RLS policies on the same `app.current_user_id` / membership model). In Phase 1, owner-keying IS project-scoping because A-16 (single learner per project) makes membership ≡ ownership. The chain is enforced at three independent layers:

1. **Service/repo** — every read/write takes an explicit owner/user scope; no unscoped query surface exists.
2. **Trigger** — `projects.owner_id` cannot drift from `spaces.owner_id`.
3. **RLS** — even raw SQL through the application role sees only the context-bound user's rows (proven by isolation tests 3–6, including the filter-removed case).
