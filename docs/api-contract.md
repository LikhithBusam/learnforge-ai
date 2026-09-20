# Canonical API Contract Specification

This document defines the authoritative API contract between the React/Vite frontend and FastAPI backend for the **AI Study Companion** platform. All routes are prefixed with `/api/v1` except health and internal probes.

---

## 1. Authentication & Principal Management

| Endpoint | Method | Request Schema | Response Schema | Description |
|---|---|---|---|---|
| `/api/v1/auth/register` | `POST` | `{"email": str, "password": str, "display_name"?: str}` | `TokenResponse` (`access_token`, `user`) | Registers learner or admin, returns signed JWT |
| `/api/v1/auth/login` | `POST` | `{"email": str, "password": str}` | `TokenResponse` (`access_token`, `user`) | Authenticates credentials, returns signed JWT |
| `/api/v1/auth/me` | `GET` | *None* (Bearer token) | `User` (`id`, `email`, `role`, `display_name`) | Resolves authenticated principal from JWT claims |
| `/api/v1/auth/logout` | `POST` | *None* (Bearer token) | `{"status": "ok"}` | Revokes session / discards token context |

---

## 2. Workspaces, Spaces & Projects

| Endpoint | Method | Request Schema | Response Schema | Description |
|---|---|---|---|---|
| `/api/v1/spaces` | `POST` | `{"name": str, "description"?: str}` | `SpaceResponse` (201 Created) | Creates a tenant space owned by authenticated caller |
| `/api/v1/spaces` | `GET` | *None* | `SpaceListResponse` (`items: SpaceResponse[]`, `total`) | Lists all spaces owned by the caller |
| `/api/v1/spaces/{space_id}` | `GET` | *None* | `SpaceResponse` | Retrieves space details (enforces owner isolation) |
| `/api/v1/spaces/{space_id}/projects` | `POST` | `{"name": str, "description"?: str, "learning_goal"?: str}` | `ProjectResponse` (201 Created) | Creates project in specified space with atomic membership |
| `/api/v1/spaces/{space_id}/projects` | `GET` | *None* | `ProjectListResponse` (`items: ProjectResponse[]`, `total`) | Lists projects within a specific space |
| `/api/v1/projects` | `GET` | `?status=active|archived` (optional) | `ProjectListResponse` (`items: ProjectResponse[]`, `total`) | Lists all projects owned by caller |
| `/api/v1/projects/{project_id}` | `GET` | *None* | `ProjectResponse` | Retrieves single project scope |
| `/api/v1/projects/{project_id}` | `DELETE` | *None* | `204 No Content` | Sets project status to `archived` |
| `/api/v1/workspaces/me` | `GET` | *None* | `{"user_id": str, "spaces": [...], "projects": [...]}` | Legacy endpoint preserved for backward compatibility |

---

## 3. Materials & Document Storage

| Endpoint | Method | Request Schema | Response Schema | Description |
|---|---|---|---|---|
| `/api/v1/projects/{project_id}/materials` | `POST` | `{"title": str, "filename": str, "content_type": str, "size_bytes": int}` | `UploadIntentResponse` (`material_id`, `upload_url`, `storage_key`, `expires_in`) | Generates upload intent and presigned Storage URL |
| `/api/v1/projects/{project_id}/materials` | `GET` | *None* | `MaterialResponse[]` | Lists all materials uploaded to project |
| `/api/v1/projects/{project_id}/materials/{material_id}` | `GET` | *None* | `MaterialResponse` | Fetches material details and processing status |
| `/api/v1/projects/{project_id}/materials/{material_id}/complete` | `POST` | `{"checksum_sha256"?: str}` | `MaterialResponse` | Validates uploaded PDF, verifies magic bytes, enqueues Celery ingestion |
| `/api/v1/projects/{project_id}/materials/{material_id}` | `DELETE` | *None* | `204 No Content` | Deletes material record, knowledge chunks, and storage object |

---

## 4. Grounded Tutor & SSE Streaming

| Endpoint | Method | Request Schema | Response Schema | Description |
|---|---|---|---|---|
| `/api/v1/projects/{project_id}/tutor/conversations` | `POST` | `{"title"?: str}` | `ConversationDto` (201 Created) | Creates conversation thread for project |
| `/api/v1/projects/{project_id}/tutor/conversations` | `GET` | *None* | `ConversationDto[]` | Lists threads in project |
| `/api/v1/projects/{project_id}/tutor/conversations/{conv_id}/messages` | `GET` | *None* | `MessageDto[]` | Retrieves chronological message history |
| `/api/v1/projects/{project_id}/tutor/conversations/{conv_id}/messages` | `POST` | `{"content": str, "idempotency_key"?: str}` | `MessageDto` OR `text/event-stream` SSE | Sends query to Tutor. When `Accept: text/event-stream` is set, streams tokens and citations |

---

## 5. Assessment & Quizzes

| Endpoint | Method | Request Schema | Response Schema | Description |
|---|---|---|---|---|
| `/api/v1/projects/{project_id}/quizzes` | `POST` | `{"target_question_count"?: int, "mode"?: str}` | `QuizDto` (201 Created) | Creates adaptive quiz session in `created` state |
| `/api/v1/projects/{project_id}/quizzes/{quiz_id}` | `GET` | *None* | `QuizDto` | Fetches quiz state and progress |
| `/api/v1/projects/{project_id}/quizzes/{quiz_id}/next` | `GET` | `?difficulty=easy|medium|hard` | `QuestionDto` or `QuizCompleteDto` | Retrieves or generates next unanswered question (answer keys stripped) |
| `/api/v1/projects/{project_id}/quizzes/{quiz_id}/answers` | `POST` | `{"question_id": str, "selected_option"?: str, "response_text"?: str}` | `AnswerResultDto` (201 Created) | Submits answer. Deterministic MCQ grading or AI open-ended evaluation |
| `/api/v1/projects/{project_id}/quizzes/{quiz_id}/complete` | `POST` | *None* | `QuizResultDto` | Finalizes quiz session |
| `/api/v1/projects/{project_id}/quizzes/{quiz_id}/results` | `GET` | *None* | `QuizResultDto` | Gets quiz result breakdown |
| `/api/v1/projects/{project_id}/assessment/history` | `GET` | `?limit=100` | `AssessmentHistoryEntryDto[]` | Historical assessment performance log |

---

## 6. Mastery, Growth & Recommendations

| Endpoint | Method | Request Schema | Response Schema | Description |
|---|---|---|---|---|
| `/api/v1/projects/{project_id}/mastery` | `GET` | *None* | `MasteryStateDto[]` | Returns all concept mastery states (BKT probability, confidence, tier) |
| `/api/v1/projects/{project_id}/mastery/summary` | `GET` | *None* | `MasterySummaryDto` | High-level mastery aggregates |
| `/api/v1/projects/{project_id}/growth` | `GET` | *None* | `ProjectGrowthSummaryDto` | Evaluated trajectory, velocity, and attention concepts |
| `/api/v1/projects/{project_id}/recommendations` | `GET` | `?limit=20` | `RecommendationListDto` (`items: RecommendationDto[]`, `total`) | Active personalized study recommendations |
| `/api/v1/projects/{project_id}/recommendations/generate` | `POST` | `{"source_growth_event_id"?: str}` | `RecommendationDto[]` | Triggers deterministic recommendation generation |

---

## 7. Analytics & System Admin

| Endpoint | Method | Request Schema | Response Schema | Description |
|---|---|---|---|---|
| `/api/v1/projects/{project_id}/analytics/overview` | `GET` | `?range=7d|30d|90d|all` | `ProjectAnalyticsOverviewDto` | Consolidated analytics across study activity, tutor, mastery, materials |
| `/api/v1/projects/{project_id}/analytics/events` | `POST` | `AnalyticsEventInput` | `AnalyticsEventDto` | Records learner activity event |
| `/api/v1/admin/overview` | `GET` | *None* (Admin Principal) | `AdminPlatformOverviewDto` | System-wide statistics for users, spaces, projects, materials, AI, jobs |
| `/api/v1/admin/users` | `GET` | `?page=1&page_size=50&query=...` | `AdminUserListDto` | Paginated user directory |
| `/api/v1/admin/projects` | `GET` | `?page=1&page_size=50&search=...` | `AdminProjectListDto` | Cross-tenant project listing for operations |
| `/api/v1/admin/ai/usage` | `GET` | `?range=24h` | `AdminAIUsageDto` | AI Gateway latency, tokens, error rates |
| `/api/v1/admin/jobs` | `GET` | `?limit=50` | `AdminJobObservabilityDto` | Background task execution telemetry |
| `/api/v1/admin/health` | `GET` | *None* | `AdminSystemHealthDto` | Deep health probe across PostgreSQL, Redis, Storage, AI Gateway |
| `/api/v1/admin/audit` | `GET` | `?page=1&page_size=50` | `AdminAuditLogListDto` | Immutable administrative audit log |
