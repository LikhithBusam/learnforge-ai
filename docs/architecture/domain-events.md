# Domain Event Catalog — AI Study Companion

**Status:** Engineering contract for review.
**Purpose:** Define every event the system needs, each justified by requirements (FR-70–FR-74, PRD §12–13 workflows). Events are the **only** mechanism for cross-module downstream effects and background workflows; they carry ownership context so background processing stays isolated (NFR-03).

---

## 1. Envelope (every event)

| Field | Type | Notes |
|---|---|---|
| `event_id` | UUID | Globally unique; **the idempotency anchor** for consumers |
| `type` | string (TypeCase, e.g. `MaterialUploaded`) | Matches a catalogue row below |
| `schema_version` | int | Additive changes within a version; breaking change bumps version; consumers handle both for one release cycle |
| `occurred_at` | datetime (UTC, RFC 3339) | Producer-side timestamp |
| `user_id` | UUID | Owning user (ownership context; mandatory — events without it are invalid) |
| `project_id` | UUID? | Present for project-scoped events; null for user-level events (e.g. `user.registered`) |
| `correlation_id` | UUID/str | Ties the event to the originating request/trace chain |
| `causation_id` | UUID? | The event/ai_request/message that caused this event (lineage) |
| `payload` | JSON | Constrained by the per-event schema below; validated on produce **and** consume |
| `producer` | string | Module name (diagnostics) |

**Delivery semantics:** at-least-once. **Consumers must be idempotent** on `(consumer, event_id)` plus natural keys; the idempotency registry is **owned by Analytics** (schema/contract) with each consumer writing its row inside its own transaction (ADR-0021/Q1). Ordering is **not guaranteed across events**; any consumer that needs order-correct outcomes computes from append-only state (e.g. Mastery recomputes from its evidence trail) rather than trusting arrival order.

**Sensitive-data rule:** payloads carry **ids, counts, scores, and status codes — never document contents, message bodies, or learner free-text** (except where explicitly marked below). Events may be consumed by Analytics rollups and must remain safe for that purpose.

**Retry behavior (default):** exponential backoff with jitter, 3 attempts. Per-event overrides noted. **Failure/DLQ behavior (default):** after exhaustion → dead-letter with the job-run record (`dead_lettered`), admin visibility + replay. Event-specific deviations noted per row.

---

## 2. Catalog

### 2.1 Workspace

| Field | `ProjectCreated` |
|---|---|
| **Event name** | `ProjectCreated` |
| **Purpose** | Initialize per-project downstream state readiness; record activity; invalidate/seed project-scoped caches |
| **Producer** | Workspace |
| **Consumers** | Analytics (activity + rollups); cache invalidation |
| **Required payload** | `{project_id, space_id, name, learning_goal_category?}` |
| **user_id** | owner |
| **project_id** | yes |
| **Idempotency key** | `event_id`; natural: project creation is a single command (idempotency key at API layer) |
| **Sensitive data** | No (name only) |
| **Retry / DLQ** | Default |

### 2.2 Materials pipeline

| Field | `MaterialUploaded` |
|---|---|
| **Event name** | `MaterialUploaded` |
| **Purpose** | Trigger the document-processing pipeline (parse → OCR/vision → chunk → concepts → embeddings → ready) — FR-21, BP-01 |
| **Producer** | Materials (on confirmed upload) |
| **Consumers** | Document pipeline task (via Jobs → Knowledge/Materials status commands); Analytics |
| **Required payload** | `{material_id, project_id, storage_ref, checksum_sha256, size_bytes, page_count_hint?, upload_verified: true}` — **no file bytes** |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: `(project_id, checksum_sha256)` dedup at source — a duplicate upload re-emits nothing (returns existing material) |
| **Sensitive data** | No (checksums/refs only) |
| **Retry / DLQ** | Default; consumer must be safe to redeliver (pipeline re-runs are guarded per material) |

| Field | `MaterialProcessingStarted` |
|---|---|
| **Event name** | `MaterialProcessingStarted` |
| **Purpose** | Status transition for UI (`queued → processing`, FR-23); job telemetry |
| **Producer** | Document pipeline task (Materials status command) |
| **Consumers** | Analytics; job-status read model |
| **Required payload** | `{material_id, pipeline_version, attempt}` |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: `(material_id, attempt)` |
| **Sensitive data** | No |
| **Retry / DLQ** | Informational — failure to publish is logged, never blocks processing |

| Field | `MaterialProcessingCompleted` |
|---|---|
| **Event name** | `MaterialProcessingCompleted` |
| **Purpose** | Status `ready`; downstream refresh: project readiness, recommendation re-evaluation, retrieval-cache purge, analytics (FR-73) |
| **Producer** | Document pipeline task (Materials status command, after Knowledge ingestion commits) |
| **Consumers** | Analytics; Growth (re-evaluate recommendations); cache invalidation; job-status read model |
| **Required payload** | `{material_id, project_id, page_count, chunk_count, concept_count, extraction_stats: {native_pages, ocr_pages, vision_pages}, pipeline_version}` |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: `(material_id, pipeline_version)` |
| **Sensitive data** | No (counts only) |
| **Retry / DLQ** | Default |

| Field | `MaterialProcessingFailed` |
|---|---|
| **Event name** | `MaterialProcessingFailed` |
| **Purpose** | Status `failed` + user-visible reason (FR-23); ops alerting; retry bookkeeping |
| **Producer** | Document pipeline task |
| **Consumers** | Analytics; alerting; job-status read model; UI (failure reason) |
| **Required payload** | `{material_id, project_id, failure_reason_code, failure_message (safe, user-displayable), attempt, retryable: bool}` |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: `(material_id, attempt)` |
| **Sensitive data** | No — failure messages must not embed raw provider errors or document excerpts |
| **Retry / DLQ** | Emitted on the pipeline task's **final** failure (post-DLQ) — itself never retried |

### 2.3 Tutor

| Field | `TutorInteractionCreated` |
|---|---|
| **Event name** | `TutorInteractionCreated` |
| **Purpose** | Post-turn async work: learning-context extraction, activity analytics, AI-quality eval sampling, mastery signals (FR-73; PRD §6/§11) |
| **Producer** | Tutor (at message finalization) |
| **Consumers** | Learning-context extractor (Tutor-side task); Analytics; Evaluation sampler; **Mastery (weak tutor signals only — ADR-0021/Q2)** |
| **Required payload** | `{conversation_id, message_id, answer_status: grounded|insufficient_evidence|general_knowledge|error, concept_ids_touched?: [uuid], citation_count, ai_request_id, sufficiency: {top_score, decision}}` — **no question/answer text** |
| **user_id / project_id** | asker / yes |
| **Idempotency key** | `event_id`; natural: `message_id` (one event per finalized message) |
| **Sensitive data** | No in payload; linked `ai_request`/`message` records hold content under their own retention/logging policy |
| **Retry / DLQ** | Default |

### 2.4 Assessment

| Field | `QuizCreated` |
|---|---|
| **Event name** | `QuizCreated` |
| **Purpose** | Activity record; analytics; (future) notification hooks |
| **Producer** | Assessment |
| **Consumers** | Analytics |
| **Required payload** | `{quiz_id, mode, target_question_count, concept_ids: [uuid]}` |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: quiz creation idempotency key |
| **Sensitive data** | No |
| **Retry / DLQ** | Default |

| Field | `AssessmentSubmitted` |
|---|---|
| **Event name** | `AssessmentSubmitted` |
| **Purpose** | Register a learner answer for evaluation + mastery evidence flow (FR-55, FR-73) |
| **Producer** | Assessment (on answer submit, before/with grading outcome) |
| **Consumers** | Mastery (evidence), Analytics |
| **Required payload** | `{quiz_id, question_id, answer_id, concept_id?, question_type, is_correct? (mcq), score? (0..1, when determined), time_taken_ms?}` — **no response text** |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: `answer_id` (unique per question) |
| **Sensitive data** | No |
| **Retry / DLQ** | Default |

| Field | `AssessmentEvaluated` |
|---|---|
| **Event name** | `AssessmentEvaluated` |
| **Purpose** | Grading outcome (incl. rubric scores + pending-review flag) → mastery evidence + mistake-pattern detection (FR-53/FR-73) |
| **Producer** | Assessment (after MCQ scoring or AI grading validated) |
| **Consumers** | Mastery; Growth (mistake patterns); Analytics |
| **Required payload** | `{answer_id, question_id, concept_id?, score, is_correct?, concepts_covered: [uuid], concepts_missing: [uuid], confidence, graded_by: deterministic|ai|pending_review, attempt, supersedes_answer_evaluation?}` — rubric detail summarized; no free text. Re-grade resolution re-emits with `attempt=2` + `supersedes_answer_evaluation` (ADR-0021/Q3) |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: `(answer_id, attempt)` |
| **Sensitive data** | No |
| **Retry / DLQ** | Default |
| **Extra consumers** | **Assessment re-grader** (idempotent, max 1 extra attempt below the calibrated confidence threshold — ADR-0021/Q3); **Mastery consumes only non-pending evaluations** |

| Field | `QuizAttemptCompleted` |
|---|---|
| **Event name** | `QuizAttemptCompleted` |
| **Purpose** | Trigger the post-quiz workflow chain: quiz-level evaluation → mastery recompute → weakness detection → recommendation (PRD §12/§13 chain; FR-73) |
| **Producer** | Assessment (on quiz completion) |
| **Consumers** | Post-quiz chain tasks: quiz-level evaluation, Mastery recompute, Growth weakness detection |
| **Required payload** | `{quiz_id, question_count, answered_count, total_score?, per_concept_summary: [{concept_id, correct, total, avg_score}]}` |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: `quiz_id` (completion is a one-time state transition) |
| **Sensitive data** | No |
| **Retry / DLQ** | Default; each chain step is itself an idempotent consumer |

### 2.5 Mastery & Growth

| Field | `MasteryUpdated` |
|---|---|
| **Event name** | `MasteryUpdated` |
| **Purpose** | Notify mastery change → growth analysis, recommendation triggers, dashboard cache invalidation, analytics (FR-73) |
| **Producer** | Mastery |
| **Consumers** | Growth; Analytics; cache invalidation |
| **Required payload** | `{concept_id, mastery_before, mastery_after, evidence_strength, source, source_id, confidence}` |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: `(source, source_id, concept_id)` — identical to the evidence-trail uniqueness, so redelivered evidence produces at most one state change |
| **Sensitive data** | No (scores only) |
| **Retry / DLQ** | Default |

| Field | `GrowthUpdated` |
|---|---|
| **Event name** | `GrowthUpdated` |
| **Purpose** | Growth snapshots refreshed for a project (trend classification committed) → dashboards/analytics |
| **Producer** | Growth (scheduled analysis or triggered by `MasteryUpdated` batches) |
| **Consumers** | Analytics; dashboards (via rollups); cache invalidation |
| **Required payload** | `{window_start, window_end, snapshot_count, trend_changes: [{concept_id, from?, to: improving|stable|needs_attention}]}` |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: `(project_id, window_end)` |
| **Sensitive data** | No |
| **Retry / DLQ** | Default |

| Field | `WeaknessDetected` |
|---|---|
| **Event name** | `WeaknessDetected` |
| **Purpose** | Weak concepts identified → targeted recommendation generation + learning-context update (PRD §13) |
| **Producer** | Growth |
| **Consumers** | Recommendation generator (Growth task); Tutor-side learning-context updater; Analytics |
| **Required payload** | `{concept_ids: [uuid], evidence: [{concept_id, mastery, confidence, mistake_count, last_mistake_at}]}` |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: `(project_id, detection_batch_id)` |
| **Sensitive data** | No |
| **Retry / DLQ** | Default |

| Field | `MistakeRepeated` |
|---|---|
| **Event name** | `MistakeRepeated` |
| **Purpose** | Repeated-mistake pattern detected → learning-context update + targeted recommendation (PRD §13 explicit workflow) |
| **Producer** | Growth (pattern detection over `AssessmentEvaluated` history) |
| **Consumers** | Learning-context updater; recommendation generator; Analytics |
| **Required payload** | `{concept_id, pattern: {occurrences, window_days, misconception_hint?}, evidence_answer_ids: [uuid]}` |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: `(project_id, concept_id, pattern_window)` |
| **Sensitive data** | No |
| **Retry / DLQ** | Default |

| Field | `RecommendationGenerated` |
|---|---|
| **Event name** | `RecommendationGenerated` |
| **Purpose** | New recommendation available → dashboard "next action" surfaces, analytics, UI badge |
| **Producer** | Growth |
| **Consumers** | Analytics; dashboards (read models); cache invalidation |
| **Required payload** | `{recommendation_id, kind, priority, target_concept_ids: [uuid], target_material_id?, dedup_key, generated_by: deterministic|ai_phrased|template_fallback}` |
| **user_id / project_id** | owner / yes |
| **Idempotency key** | `event_id`; natural: `dedup_key` (unique among active recommendations per project) |
| **Sensitive data** | No |
| **Retry / DLQ** | Default |

### 2.6 Cross-cutting

| Field | `ActivityRecorded` |
|---|---|
| **Event name** | `ActivityRecorded` |
| **Purpose** | Generic activity envelope for feeds/analytics (FR-70): project/space updates, uploads, quiz events, tutor activity, tool usage, user lifecycle |
| **Producer** | Any module (Workspace, Materials, Tutor, Assessment, Identity, Tools) |
| **Consumers** | Analytics (activity feed + rollups) |
| **Required payload** | `{activity_type (enum allow-list), resource_type?, resource_id?, summary (short, non-sensitive), occurred_at}` |
| **user_id / project_id** | actor / where applicable |
| **Idempotency key** | `event_id`; producers pass the causative action's natural key as part of payload dedup |
| **Sensitive data** | No — `summary` is a fixed short label, never user content |
| **Retry / DLQ** | Loss-tolerant (analytics-grade): 1 retry, then drop with a logged metric — never blocks the producing transaction beyond the outbox write |

| Field | `AIRequestCompleted` |
|---|---|
| **Event name** | `AIRequestCompleted` |
| **Purpose** | AI observability spine feed: per-call outcome → analytics rollups, cost tracking, eval sampling trigger (FR-81, FR-82) |
| **Producer** | AI Gateway (every call: success **and** failure) |
| **Consumers** | Analytics (AI usage/cost rollups); Evaluation sampler (sampling decision) |
| **Required payload** | `{ai_request_id, feature, operation, provider_role, model, prompt_id, prompt_version, status: success|timeout|provider_error|invalid_output|rate_limited|cancelled|budget_exhausted, input_tokens?, output_tokens?, estimated_cost_usd?, latency_ms?, time_to_first_token_ms?, retrieval_meta?: {strategy, k, top_score, sufficiency_decision}, fallback_from?}` — **no prompt/completion bodies** |
| **user_id / project_id** | from scope_ref (nullable for system-level calls) / where applicable |
| **Idempotency key** | `event_id`; natural: `ai_request_id` |
| **Sensitive data** | No — content stays in the `ai_requests` record under its own retention/redaction policy |
| **Retry / DLQ** | Default; loss here degrades analytics only (the authoritative record is the gateway's own write) |

---

## 3. Flow map (events → workflow chains)

```text
MaterialUploaded → [pipeline task] → MaterialProcessingStarted → … → MaterialProcessingCompleted
                                                  └→ (final failure) MaterialProcessingFailed

TutorInteractionCreated → [context extractor] + [eval sampler] + Analytics (+ Mastery signal)

AssessmentSubmitted → AssessmentEvaluated → Mastery.record → MasteryUpdated ─┐
QuizAttemptCompleted → [post-quiz chain] ────────────────────────────────────┤
                                                                              ▼
                                              Growth analysis → GrowthUpdated
                                                → WeaknessDetected / MistakeRepeated
                                                    → RecommendationGenerated → dashboards
```

Every arrow crosses an idempotent consumer boundary; every chain step re-runnable without duplicate state.

## 4. Justification check (PRD traceability)

| Event | Requirement served |
|---|---|
| `ProjectCreated` | FR-70, FR-73, FR-13 |
| `MaterialUploaded/Started/Completed/Failed` | FR-21, FR-23, FR-26, BP-01, FR-73 |
| `TutorInteractionCreated` | FR-63, FR-70, FR-73, FR-83 (eval sampling) |
| `QuizCreated` / `AssessmentSubmitted` / `AssessmentEvaluated` / `QuizAttemptCompleted` | FR-50–55, FR-70, FR-73 |
| `MasteryUpdated` | FR-60, FR-73 |
| `GrowthUpdated` / `WeaknessDetected` / `MistakeRepeated` | FR-61, FR-62, §13 workflows |
| `RecommendationGenerated` | FR-62, FR-13/FR-15 next-action surfaces |
| `ActivityRecorded` | FR-70, FR-92 (filterable activity) |
| `AIRequestCompleted` | FR-81, FR-82, FR-83 sampling |

**Deliberately absent** (would be speculative): notification/digest events, collaboration events, flashcard events, export events — no PRD requirement; the envelope and catalogue make adding one a reviewed, additive change.
