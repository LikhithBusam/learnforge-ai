# Learning Evidence Schema (Phase 5 → Phase 6)

## Purpose

The `quiz_evidence` table is the **structured output of Phase 5** that feeds the
Phase 6 Mastery engine. Each row represents one completed, graded answer attempt.

## This is NOT Mastery

Phase 5 does not calculate:
- Mastery probability
- BKT (Bayesian Knowledge Tracing) parameters
- Growth classification
- Decay rates

It produces **raw evidence**. Phase 6 consumes this evidence to compute mastery.

## Schema

```sql
CREATE TABLE quiz_evidence (
    id            uuid PRIMARY KEY,
    attempt_id    uuid NOT NULL REFERENCES question_attempts(id),
    quiz_id       uuid NOT NULL REFERENCES quizzes(id),
    question_id   uuid NOT NULL REFERENCES questions(id),
    project_id    uuid NOT NULL REFERENCES projects(id),
    owner_id      uuid NOT NULL REFERENCES users(id),
    concept_id    uuid,              -- NULL in Phase 5; Phase 6 backfills
    result        text NOT NULL,     -- correct | incorrect | partial
    score         float NOT NULL,    -- 0.0..1.0
    difficulty    text NOT NULL,     -- easy | medium | hard
    question_type text NOT NULL,     -- mcq | open_ended
    grading_method text NOT NULL,    -- deterministic | ai
    source        text NOT NULL,     -- always 'assessment' in Phase 5
    attempted_at  timestamptz NOT NULL
);
```

## Emission Rules

Evidence is emitted **only** when:
- `grading_method != pending_review` (graded result available)
- One row per attempt (enforced by unique constraint on `attempt_id`)

Evidence is **not** emitted when:
- AI grading failed → `pending_review` (score unknown)

## JSON Representation

```json
{
  "evidence_id": "01930000-...",
  "user_id": "01920000-...",
  "project_id": "01910000-...",
  "quiz_id": "01900000-...",
  "question_id": "01890000-...",
  "concept_id": null,
  "result": "correct",
  "score": 1.0,
  "difficulty": "medium",
  "question_type": "mcq",
  "grading_method": "deterministic",
  "source": "assessment",
  "attempted_at": "2026-09-20T00:00:00Z"
}
```

## Phase 6 Contract

Phase 6 (Mastery) will:
1. Read `quiz_evidence` grouped by `(owner_id, project_id, concept_id)`
2. Apply BKT or equivalent mastery math
3. Backfill `concept_id` where null (via concept graph)
4. Never write to `quiz_evidence` (read-only from Phase 6's perspective)

Phase 5 guarantees:
- One row per completed attempt (idempotent)
- `result` is always `correct`, `incorrect`, or `partial`
- `score` is always `[0.0, 1.0]`
- `source = "assessment"` for Phase 5 rows
