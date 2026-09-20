# Analytics & Learner Progress Subsystem Architecture (Phase 9)

## 1. Overview & Objectives

The Analytics subsystem serves as the read-optimized aggregation and progress reporting layer of the AI Study Companion platform. It aggregates signals from:
- **Materials (Phase 3)**: Document ingestion, page/chunk extraction, processing reliability.
- **Knowledge / RAG (Phase 4)**: Vector/BM25 retrieval volume.
- **Tutor (Phase 4)**: Conversations, message volume, grounded answers, citations, and honest refusals.
- **Assessment (Phase 5)**: Quizzes, question attempts, MCQs, open-ended evaluations, and accuracy.
- **Mastery Engine (Phase 6)**: Cognitive tier distribution (`developing`, `progressing`, `mastered`).
- **Growth Engine (Phase 7)**: Trajectories (`improving`, `stable`, `declining`) and attention requirements.
- **Recommendations (Phase 8)**: Lifecycle funnels (`pending`, `viewed`, `started`, `completed`, `dismissed`).

---

## 2. Strict Architectural Boundaries

Analytics operates strictly as an **observer and consumer**:
```text
Materials ──┐
Knowledge ──┤
Assessment ─┤
Mastery ────┼──→ [Analytics Events & Service Facades]
Growth ─────┤                 │
Recommendations ──────────────┘
                              ↓
                  [Analytics Engine / Calculator]
                              ↓
                  [Read Models & API Dashboards]
```

### Boundary Guarantees:
- **No Domain Logic Duplication**: Analytics does not execute BKT mastery probability equations, calculate trajectory regressions, generate recommendations, or score quizzes.
- **No Direct Table/Repository Access**: Cross-domain data is accessed strictly through service facades (`mastery_service`, `growth_service`, `recommendation_service`, `assessment_service`, `materials_service`, `tutor_service`, `workspace_service`).

---

## 3. Data Storage & Rollup Strategy

### 3.1 Immutable Event Stream (`analytics_events`)
Records immutable domain and client events with UTC timestamps, user/project IDs, and JSON metadata. Idempotent insertions are guaranteed at the database level via `UNIQUE(id)`.

### 3.2 Precomputed Daily Rollups (`project_daily_metrics`)
Precomputes daily metrics per `(project_id, date, metric_category)` to enable sub-millisecond dashboard queries without recalculating over large raw event tables.

---

## 4. Multi-Tenant Isolation & Security

- **Row-Level Security (RLS)**: Enabled and forced on `analytics_events` and `project_daily_metrics` via `user_id/owner_id = app_user_id()`.
- **404 Posture**: Non-existent or non-owned projects return `404 Not Found` (ADR-0002).
