# Assessment Architecture (Phase 5)

## Overview

The Assessment module produces **learning evidence** — structured records of what a
learner knows and doesn't know — for consumption by the Phase 6 Mastery engine. It
is NOT a quiz CRUD feature; it is a learning-evidence producer.

## Architecture

```
Project Materials
      ↓
Knowledge / RAG (retrieve_evidence)
      ↓
Evidence Chunks
      ↓
Question Generation (generation.py)
      ↓
Question Bank (quizzes + questions)
      ↓
Adaptive Question Selection (adaptive.py)
      ↓
Learner Answer
      ↓
Grading (grading.py)
      ↓
Learning Evidence (quiz_evidence table)
      ↓
[Phase 6: Mastery Engine reads quiz_evidence]
```

## Module Boundary

Assessment is a domain module. It:
- **Can import**: `knowledge.service` (retrieve_evidence facade), `ai.gateway` (via generation.py/grading.py)
- **Cannot import**: tutor, mastery, growth, analytics, materials (direct table access), or workspace
- **Does NOT duplicate**: retrieval logic (always delegates to KnowledgeService)

## Database Tables

| Table | Purpose |
|---|---|
| `quizzes` | Quiz session with state machine |
| `questions` | RAG-grounded questions (with answer keys) |
| `question_options` | MCQ options (1:N per question) |
| `question_attempts` | Immutable learner answers |
| `quiz_evidence` | Phase 6 learning evidence feed |

All tables have RLS enforced with `owner_id = app_user_id()`.

## State Machine

```
CREATED → ACTIVE (on first get_next_question)
ACTIVE  → COMPLETED (on complete_quiz)
ACTIVE  → ABANDONED (future: timeout)
COMPLETED → terminal (no further answers)
```

## Answer Key Security

`correct_option`, `reference_answer`, and `rubric` are stored in the database
and service layer only. They are **never** included in `QuestionDto` (the
learner-facing HTTP response schema). Two separate Pydantic models enforce this:

- `QuestionInternal` — carries answer keys, used only in service.py
- `QuestionDto` — learner-facing, explicitly omits all answer key fields

The service's `QuestionInternal.to_dto()` method is the only conversion path.

## Question Generation (Lazy, On-Demand)

Questions are generated **lazily** — one per `get_next_question` call. This enables:
- Fresh RAG retrieval per question (most current evidence)
- Adaptive difficulty selection per question
- No pre-computation at quiz creation time

Pipeline per question:
1. Call `KnowledgeService.retrieve_evidence(project_id, query)`
2. Call `generation.generate_mcq_question()` or `generate_open_ended_question()`
3. Validate Pydantic schema (reject invalid output)
4. Validate source_chunk_ids belong to current project
5. Persist (only if valid)

## Grading

| Question Type | Method | AI Involved |
|---|---|---|
| MCQ | Deterministic (`selected_option == correct_option`) | No |
| Open-ended | AI Gateway → `OpenEndedGradingPayload` | Yes |
| Open-ended (fallback) | `pending_review` (AI output invalid) | No |

## Learning Evidence for Phase 6

Every non-`pending_review` attempt produces one row in `quiz_evidence`:

```json
{
  "attempt_id": "...",
  "concept_id": null,
  "result": "correct|incorrect|partial",
  "score": 0.0..1.0,
  "difficulty": "easy|medium|hard",
  "question_type": "mcq|open_ended",
  "grading_method": "deterministic|ai",
  "source": "assessment"
}
```

`concept_id` is `null` in Phase 5. Phase 6 connects it once the concept graph exists.
