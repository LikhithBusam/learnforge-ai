# Full-Stack Integration Architecture (Phase 12)

## 1. Interaction Diagram

```text
       REACT FRONTEND (Vite / TypeScript)
                    │
                    │ REST APIs / SSE Streaming
                    ▼
          FASTAPI MODULAR MONOLITH
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
PostgreSQL /     Redis &         MinIO /
 pgvector        Celery         Supabase
 (Domain & RLS)  (Worker Plane)  (PDF Chunks)
```

---

## 2. API Integration Matrix

| Subsystem | Backend Router | Frontend Integration Method | Response Contract |
| :--- | :--- | :--- | :--- |
| **Auth** | `/api/v1/auth/*` | `api.login()`, `api.register()` | `AuthTokens`, `User` |
| **Workspace** | `/api/v1/spaces`, `/projects` | `api.listSpaces()`, `api.createProject()` | `Space`, `Project` |
| **Materials** | `/api/v1/projects/{id}/materials` | `api.createUploadIntent()`, `api.listMaterials()` | `Material`, `UploadIntent` |
| **Tutor** | `/api/v1/projects/{id}/tutor` | `api.sendTutorMessage()` (SSE stream) | `TutorMessage`, `Citation` |
| **Assessment**| `/api/v1/projects/{id}/assessment` | `api.createQuiz()`, `api.submitAnswer()` | `Quiz`, `Question` |
| **Mastery** | `/api/v1/projects/{id}/mastery` | `api.getProjectMastery()` | `ConceptMastery` |
| **Growth** | `/api/v1/projects/{id}/growth` | `api.getProjectGrowth()` | `GrowthSnapshot` |
| **Recommendations** | `/api/v1/projects/{id}/recommendations` | `api.getRecommendations()`, `api.generateRecommendations()` | `Recommendation` |
| **Analytics** | `/api/v1/projects/{id}/analytics` | `api.getProjectAnalytics()` | `AnalyticsOverview` |
| **Admin** | `/api/v1/admin/*` | `api.getAdminOverview()`, `api.getAdminHealth()` | `AdminOverview`, `AdminSystemHealth` |
