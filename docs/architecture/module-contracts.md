# Module Contracts — AI Study Companion

**Status:** Engineering contract for review — conceptual only. No implementation, no framework or provider coupling.
**Purpose:** Make the architecture implementable without prematurely coupling modules to database tables, frameworks, or AI providers. Each contract is the **only** legal access path to a module. A contract change is an API change between teams and requires review of its consumers.

**Conventions used throughout:**
- **DTO** = technology-independent data structure (fields + types + invariants), to be mapped to Pydantic/JSON/etc. at the implementation layer. Types: `UUID`, `str`, `int`, `float`, `bool`, `datetime (UTC)`, `enum`, `JSON` (schema-constrained), arrays, optional (`?`).
- **Result pattern:** service methods either return the DTO or raise a typed domain error; **no null-as-error, no boolean-and-side-channel**. `*Exists?` queries return the DTO or `None`.
- **Scope:** a `Principal {user_id, role, session_id, request_id}` and, where required, a `ProjectScope {project_id, space_id, owner_id, principal}` are resolved at the edge and **passed in explicitly** — a service method without its scope parameter cannot be reached from an authorized route (enforced by review + future import rules).
- **Transaction boundary** is stated per module; one service method = at most one unit of work.
- **Events** reference the catalogue in `docs/architecture/domain-events.md` (names in `TypeCase`).
- Cross-module **reads** go through the owning module's query methods; **writes** to another module's state are never direct — always via events or an explicitly declared command (see per-module "must NOT be accessed directly").

**Reading example:** every module section below answers the same 16 questions in the same order: Responsibility · Non-responsibilities · Public service interface · Input DTOs · Output DTOs · Commands · Queries · Events emitted · Events consumed · Authorization · Project/user scope · Transaction boundary · Idempotency · Failure modes · Dependencies · Must NOT access directly.

**Coverage rule respected:** only the 14 modules already identified; no business module invented.

---

## 1. Identity

1. **Responsibility** — Registration, login, session lifecycle (issue/refresh/rotate/revoke), role resolution, principal construction. Owns `users`, `sessions` data.
2. **Non-responsibilities** — Resource-level authorization rules (ownership of spaces/projects lives with the owning module); password policy beyond hashing/verification; audit logging of other modules' actions; profile content moderation.
3. **Public service interface — `IdentityService`**
   - `register(register_input) -> AuthResult`
   - `login(credentials, context_meta) -> AuthResult`
   - `refresh(refresh_token, context_meta) -> AuthResult`
   - `logout(session_id, principal) -> None`
   - `resolve_principal(access_token) -> Principal`
   - `get_user(user_id) -> UserDto | None`
4. **Input DTOs** — `RegisterInput{email, password, display_name}`; `Credentials{email, password}`; `ContextMeta{ip_hash?, user_agent?}`.
5. **Output DTOs** — `AuthResult{access_token, refresh_token_expires_at, user: UserDto}`; `UserDto{user_id, email, display_name, role, status, email_verified, created_at}`. (Token transport details — headers/cookies — are an edge concern, not part of the contract.)
6. **Commands** — register; login; refresh (rotates); logout (revokes).
7. **Queries** — `resolve_principal`; `get_user`.
8. **Events emitted** — `ActivityRecorded` (type `user.registered`, `user.login_failed` — security telemetry via Analytics).
9. **Events consumed** — none.
10. **Authorization** — register/login are public (rate-limited at edge); refresh requires the refresh token itself; logout/`get_user` require an authenticated principal; user data is readable only for `user_id == principal.user_id` unless `role=admin` (admin path only via Admin module aggregates).
11. **Project/user scope** — user-scoped only; no project concept.
12. **Transaction boundary** — one method = one transaction (session rotation + user update commit together).
13. **Idempotency** — register is idempotent-failing (unique email → typed `EmailAlreadyRegistered`); refresh is **single-use** (replayed refresh token revokes the session family — reuse detection); logout idempotent (revoking twice is a no-op).
14. **Failure modes** — `InvalidCredentials` (generic, no enumeration), `EmailAlreadyRegistered`, `InvalidOrExpiredToken`, `AccountDisabled`; credential-stuffing protection is edge rate limiting + `login_failed` telemetry.
15. **Dependencies** — Platform only (secret config for token signing, clock).
16. **Must NOT access directly** — any other module's data; Identity never reads projects/quizzes to make authz decisions — it only answers "who is the caller".

---

## 2. Workspace

1. **Responsibility** — Space and Project lifecycle, ownership resolution, project dashboards, home dashboard aggregation. Owns `spaces`, `projects`.
2. **Non-responsibilities** — Any AI call; content processing; analytics rollup computation (consumes rollup read models from Analytics); recommendations content.
3. **Public service interface — `WorkspaceService`**
   - `create_space(principal, create_input) -> SpaceDto`
   - `list_spaces(principal) -> [SpaceDto]`
   - `get_space(principal, space_id) -> SpaceDto`
   - `update_space(principal, space_id, update_input) -> SpaceDto`
   - `delete_space(principal, space_id) -> None`
   - `create_project(principal, space_id, create_input) -> ProjectDto`
   - `list_projects(principal, space_id) -> [ProjectDto]`
   - `get_project(principal, project_id) -> ProjectDto`
   - `update_project(principal, project_id, update_input) -> ProjectDto`
   - `delete_project(principal, project_id) -> None`
   - `get_space_dashboard(principal, space_id) -> SpaceDashboardDto`
   - `get_project_dashboard(principal, project_id) -> ProjectDashboardDto`
   - `get_home_dashboard(principal) -> HomeDashboardDto`
   - `resolve_project_scope(principal, project_id) -> ProjectScope`
   - *cross-module queries (facade consumers):* `project_exists(project_id) -> bool`
4. **Input DTOs** — `CreateSpaceInput{name, description?, color?, icon?}`; `CreateProjectInput{name, description?, learning_goal}`; `UpdateSpaceInput`, `UpdateProjectInput` (partial).
5. **Output DTOs** — `SpaceDto{id, owner_id, name, description, color, icon, created_at}`; `ProjectDto{id, space_id, owner_id, name, description, learning_goal, status, last_activity_at}`; `SpaceDashboardDto{projects: [ProjectSummaryDto], activity: [ActivityEntryDto], progress: ProgressSummaryDto, attention_areas: [ConceptAttentionDto]}`; `ProjectDashboardDto{progress, important_concepts: [ConceptDto], recent_activity, performance, latest_activity, recommended_next_action?}`; `HomeDashboardDto{continue_learning: [ProjectSummaryDto], overall_progress, attention_areas, recommended_next_action?}`. Dashboard DTOs are **composed read models**: Workspace aggregates via other modules' query facades + Analytics rollups.
6. **Commands** — create/update/delete space, project.
7. **Queries** — gets/lists, dashboards, `resolve_project_scope`.
8. **Events emitted** — `ProjectCreated`; `ActivityRecorded` (project.created/updated/deleted, space.created/…).
9. **Events consumed** — `RecommendationGenerated` (to surface "recommended next action" on dashboards via Analytics read models — consumed indirectly through Analytics queries, not direct storage access).
10. **Authorization** — owner-only CRUD (`owner_id == principal.user_id`, else **404-equivalent** typed `NotFound`); admin has no direct route (reads via Admin module); `resolve_project_scope` returns `NotFound` for non-owned.
11. **Project/user scope** — every method takes `principal`; project methods take `project_id` and resolve `ProjectScope` internally or accept one.
12. **Transaction boundary** — create project = project row + `ProjectCreated` event + `ActivityRecorded` in **one** transaction.
13. **Idempotency** — creates accept an idempotency key at the API layer; deletes idempotent (404 on second call is acceptable); updates naturally idempotent.
14. **Failure modes** — `NotFound`, `ValidationError` (learning_goal required), `SpaceNotFound` (on nested create).
15. **Dependencies** — Analytics (rollup queries for dashboards); Growth (read recommendations for "next action"); Mastery (mastery summary reads); Materials (status counts) — **all via their facades, read-only**.
16. **Must NOT access directly** — knowledge tables (chunks/concepts) — concepts reached via Knowledge facade; any conversation/quiz data beyond summarized read models; analytics event storage.

---

## 3. Materials

1. **Responsibility** — Material lifecycle: upload-intent issuance, upload confirmation/verification, status transitions, retry orchestration, deletion. Owns `materials` (+ page inventory metadata).
2. **Non-responsibilities** — Parsing/OCR/chunking/embedding/concept extraction (worker-side, via Knowledge + AI); citation preview rendering; storage bucket management (Platform).
3. **Public service interface — `MaterialsService`**
   - `create_upload_intent(principal, project_scope, upload_input) -> UploadIntentDto`
   - `confirm_upload(principal, project_scope, material_id, confirm_input) -> MaterialDto`
   - `get_material(principal, project_scope, material_id) -> MaterialDto`
   - `list_materials(principal, project_scope) -> [MaterialDto]`
   - `request_reprocess(principal, project_scope, material_id) -> MaterialDto`
   - `delete_material(principal, project_scope, material_id) -> None`
   - `get_job_status(principal, job_id) -> JobStatusDto` (delegates to Jobs facade)
   - `get_page_image_ref(principal, project_scope, material_id, page_number) -> PageImageRefDto`
   - *internal status-transition commands (ADR-0021/Q4; worker-plane callers only, never HTTP-exposed):* `begin_processing(ownership_context, material_id, pipeline_version) -> MaterialDto` · `mark_completed(ownership_context, material_id, completion) -> MaterialDto` · `mark_failed(ownership_context, material_id, failure) -> MaterialDto` — Materials is the **single status authority**; these methods emit the `MaterialProcessing*` events inside their own transactions
4. **Input DTOs** — `UploadInput{filename, declared_content_type, size_bytes, checksum_sha256?}`; `ConfirmInput{storage_key, checksum_sha256, size_bytes}`.
5. **Output DTOs** — `UploadIntentDto{material_id, job_id?, upload_url_or_params (opaque to API consumer), expires_at}`; `MaterialDto{id, project_id, title, status: queued|processing|ready|failed, failure_reason?, page_count?, checksum, pipeline_version?, created_at, processed_at?}`; `PageImageRefDto{material_id, page_number, image_ref (opaque), expires_at}`.
6. **Commands** — create intent; confirm; reprocess; delete.
7. **Queries** — get/list, page image ref.
8. **Events emitted** — `MaterialUploaded` (on confirm), `MaterialProcessingStarted`/`MaterialProcessingCompleted`/`MaterialProcessingFailed` (worker-side status transitions), `ActivityRecorded`.
9. **Events consumed** — none (worker tasks are Jobs' domain; Materials provides status callbacks/commands to the pipeline via `Jobs` task definitions, keeping the dependency one-way).
10. **Authorization** — owner-scoped via `ProjectScope`; non-owned material → `NotFound`; page-image refs are short-lived and owner-only.
11. **Project/user scope** — every method requires `ProjectScope`; `project_id` never accepted from untrusted input (resolved from scope).
12. **Transaction boundary** — confirm = material row (status=queued) + `MaterialUploaded` event atomically; status transitions owned by the pipeline are separate transactions with advisory-style concurrency guard per material (conceptual: "one processing run at a time").
13. **Idempotency** — confirm requires idempotency key; duplicate checksum within project → typed `DuplicateMaterial` (returns existing material — no reprocessing); reprocess is dedup-keyed (no concurrent duplicate runs).
14. **Failure modes** — `NotFound`, `DuplicateMaterial`, `UploadNotVerified` (object missing/checksum/size/magic-bytes mismatch → fail fast, client retry), `InvalidUploadPolicy` (size/type caps from config).
15. **Dependencies** — Platform (storage abstraction, config caps); Jobs (dispatch + status); Knowledge (nothing directly — the pipeline calls Knowledge, not Materials).
16. **Must NOT access directly** — chunk/embedding/concept storage; AI providers; conversation data.

---

## 4. Knowledge

1. **Responsibility** — Retrieval representation of project content: chunks (page-anchored), concepts, embeddings; the retrieval pipeline (hybrid search, fusion, rerank orchestration, sufficiency decision); concept registry. Owns chunk/concept/embedding data.
2. **Non-responsibilities** — Prompt construction; answer generation; deciding *policy* defaults (thresholds are config); writing to conversations; mastery.
3. **Public service interface — `KnowledgeService`**
   - `retrieve_evidence(scope, query_input) -> EvidenceSetDto`
   - `search(scope, query, k?) -> [EvidenceHitDto]` (general project search; powers UI search + tools)
   - `check_evidence_sufficiency(evidence_set) -> SufficiencyDecisionDto`
   - `get_concepts(scope) -> [ConceptDto]`
   - `get_concept(scope, concept_id) -> ConceptDto | None`
   - `get_chunks_for_concept(scope, concept_id, limit?) -> [ChunkRefDto]`
   - `get_chunk_refs(scope, chunk_ids) -> [ChunkRefDto]` (citation resolution)
   - `get_material_readiness(scope, material_ids?) -> [MaterialReadinessDto]`
   - *pipeline-side (called by the document worker only):* `ingest_extracted_content(scope, material_id, extraction: ExtractionResultDto, pipeline_version) -> IngestionResultDto`
4. **Input DTOs** — `QueryInput{raw_query, conversation_context_ref? (for pronoun resolution), rewritten_query?}`; `ExtractionResultDto{pages: [PageContentDto], chunks: [ChunkContentDto{content, page_start, page_end, section_path?, content_type}], concepts: [ConceptCandidateDto], concept_links: [...], embedding_vectors: [[float]]}` — the worker produces this via AI; Knowledge validates it as **untrusted input** before persisting.
5. **Output DTOs** — `EvidenceSetDto{query_used, hits: [EvidenceHitDto{chunk_ref: ChunkRefDto, score, rank}], sufficiency: SufficiencyDecisionDto, retrieval_meta (for observability)}`; `ChunkRefDto{chunk_id, material_id, material_title, page_start, page_end, section_path?, content_type, content_excerpt}`; `SufficiencyDecisionDto{sufficient: bool, top_score, supporting_chunk_count, reason_code, threshold_ref (which config values decided)}`; `ConceptDto{id, name, description?, importance, source}`; `IngestionResultDto{chunks_written, concepts_upserted, material_version}`.
6. **Commands** — `ingest_extracted_content` (pipeline-only); concept upserts happen inside it.
7. **Queries** — retrieve, search, sufficiency, concepts, chunk refs, readiness.
8. **Events emitted** — `MaterialProcessingCompleted` **payload-completion details are emitted by Materials** — Knowledge emits none directly except contributing retrieval_meta on AI events; concept-extraction AI usage is recorded by AI via the AI Gateway call itself.
9. **Events consumed** — none directly (ingestion is invoked by the worker task, not event-driven within Knowledge).
10. **Authorization** — all methods take `ProjectScope`; retrieval filters are **inside the query** (never post-filtered); `get_chunk_refs` validates all requested ids belong to scope.
11. **Project/user scope** — mandatory on every method; cross-project chunk ids in a request → typed `ScopeViolation` (alert-worthy, not silently filtered).
12. **Transaction boundary** — `ingest_extracted_content` is one transaction (replaces prior pipeline_version rows — never partial append); queries are read-only.
13. **Idempotency** — ingestion is idempotent per `(material_id, pipeline_version)`: re-run replaces, never duplicates; concept upsert by normalized name.
14. **Failure modes** — `ScopeViolation`, `EmptyCorpus` (retrieval over no ready material → sufficiency=false), `ValidationError` on untrusted extraction payload; provider failures inside the retrieval pipeline are surfaced as `DependencyError` variants by AI, translated here to degraded-mode results (lexical-only flag in `retrieval_meta`).
15. **Dependencies** — AI (embed, rerank); Materials (read-only title/page metadata via facade); Platform.
16. **Must NOT access directly** — conversations, quizzes, mastery, storage bytes (it stores derived data, not source files); provider SDKs (AI module only).

---

## 5. Tutor

1. **Responsibility** — Conversation lifecycle, context composition, grounded answer generation, citation validation, insufficiency path, streaming delivery. Owns `conversations`, `messages`, `message_citations`, and learning-context items.
2. **Non-responsibilities** — Retrieval mechanics (Knowledge); model selection/provider policy (AI); mastery updates; quiz creation beyond the tool-mediated command.
3. **Public service interface — `TutorService`**
   - `create_conversation(principal, project_scope, title?) -> ConversationDto`
   - `list_conversations(principal, project_scope) -> [ConversationDto]`
   - `get_conversation(principal, project_scope, conversation_id) -> ConversationDto`
   - `get_messages(principal, project_scope, conversation_id, page?) -> [MessageDto]`
   - `send_message(principal, project_scope, conversation_id, send_input) -> (stream of TutorStreamEventDto, final MessageDto)` — streaming is a delivery mode over this single use case
   - `stop_generation(principal, conversation_id) -> None`
   - `get_project_context(principal, project_scope) -> LearnerContextDto` (read model of learning-context items; also used by tools)
   - `delete_learning_context_item(principal, project_scope, item_id) -> None`
4. **Input DTOs** — `SendMessageInput{content, idempotency_key}`; pagination params.
5. **Output DTOs** — `ConversationDto{id, project_id, title?, created_at, last_message_at}`; `MessageDto{id, role, content, answer_status: grounded|insufficient_evidence|general_knowledge|error, citations: [CitationDto], ai_request_id?, created_at}`; `CitationDto{marker, chunk_ref: ChunkRefDto, quote?}`; **`TutorStreamEventDto`** typed union: `message_start{message_id, ai_request_id}` | `token{delta}` | `citation{…}` | `insufficient{reason_code, suggestions[]}` | `message_end{usage, latency}` | `error{type, retryable, request_id}`; `LearnerContextDto{items: [LearningContextItemDto{id, kind, content, concept_id?, salience, source, last_reinforced_at}]}`.
6. **Commands** — create conversation; send message; stop; delete context item.
7. **Queries** — get conversation/messages; `get_project_context`.
8. **Events emitted** — `TutorInteractionCreated` (after finalization, incl. answer_status), `ActivityRecorded`.
9. **Events consumed** — `QuizAttemptCompleted`-derived learner-state changes arrive via composed queries (Mastery/Assessment facades at context-composition time), not by storing copies.
10. **Authorization** — owner-only via `ProjectScope` + conversation ownership; non-owned conversation → `NotFound`.
11. **Project/user scope** — scope threaded into context composition, retrieval, tool execution; scope is **never** model-supplied (see Tools).
12. **Transaction boundary** — send_message: the turn's work (retrieval, generation) is performed; **finalization commits message + citations + AI request linkage + outbox events atomically**, and runs even if the client disconnects (streaming is delivery, not source of truth).
13. **Idempotency** — send_message requires idempotency key (duplicate key replays the final persisted message, not a re-run).
14. **Failure modes** — `NotFound`; AI failures translated to typed stream `error` events with retryable flags; provider-down degraded path = evidence-list response (clearly labelled) per principles; citation-validation failure downgrades the message to insufficiency rather than shipping unvalidated citations.
15. **Dependencies** — Knowledge (evidence); AI (generate/stream, structured intent checks); Tools (if a turn invokes capabilities); Mastery/Assessment/Workspace (read-only context); Platform.
16. **Must NOT access directly** — chunks/concepts storage (only via Knowledge DTOs); quiz/mastery tables (via facades); provider SDKs.

---

## 6. Assessment

1. **Responsibility** — Quiz sessions, adaptive selection policy (deterministic), question generation orchestration, answer submission, MCQ scoring (deterministic), open-ended grading orchestration, quiz results. Owns `quizzes`, `questions`, `answers`.
2. **Non-responsibilities** — Mastery math (Mastery); recommendation generation (Growth); concept registry (Knowledge).
3. **Public service interface — `AssessmentService`**
   - `create_quiz(principal, project_scope, create_input) -> QuizDto`
   - `get_quiz(principal, project_scope, quiz_id) -> QuizDto`
   - `get_next_question(principal, project_scope, quiz_id) -> QuestionDto | QuizCompleteDto`
   - `submit_answer(principal, project_scope, quiz_id, question_id, answer_input) -> AnswerResultDto`
   - `complete_quiz(principal, project_scope, quiz_id) -> QuizResultDto`
   - `get_results(principal, project_scope, quiz_id) -> QuizResultDto`
   - `get_assessment_history(principal, project_scope, filters?) -> [AssessmentHistoryEntryDto]` (also tool-facing)
4. **Input DTOs** — `CreateQuizInput{target_question_count?, concept_ids? (scope-limiting), mode?}`; `AnswerInput{selected_option? (MCQ), response_text? (open-ended), idempotency_key}`.
5. **Output DTOs** — `QuizDto{id, status, target_question_count, score?, created_at}`; `QuestionDto{id, type: mcq|open_ended, prompt, options? (MCQ; correct answer never included), difficulty_band, concept_id?, source_chunk_ids (provenance), ordinal}`; `AnswerResultDto{answer_id, is_correct? (MCQ), score?, feedback, evaluation? (open-ended structured), mastery_delta_hint?}` — feedback is **explanatory** (FR-54); `QuizResultDto{quiz_id, per_concept: [ConceptResultDto], total_score?, graded_pending_review: bool}`; `AssessmentHistoryEntryDto{quiz_id, question_id, concept_id?, is_correct, score, answered_at}`.
6. **Commands** — create quiz; submit answer; complete quiz.
7. **Queries** — get quiz/question/results/history.
8. **Events emitted** — `QuizCreated`, `AssessmentSubmitted`, `AssessmentEvaluated` (per answer evaluation incl. pending_review flag, `attempt`, `supersedes_answer_evaluation`), `QuizAttemptCompleted` (quiz finalization), `ActivityRecorded`.
9. **Events consumed** — one idempotent **re-grading consumer** (ADR-0021/Q3): on `AssessmentEvaluated(graded_by='ai', confidence < calibrated threshold)` it re-grades once (dedup-keyed per answer, max 1 extra attempt; a resolved re-grade emits `AssessmentEvaluated(attempt=2, supersedes=…)`); unresolved grades stay `pending_review` and are **excluded from mastery evidence** (§M.7 rule).
10. **Authorization** — owner-only via `ProjectScope`; `QuestionDto` **never** exposes `correct_option` or rubric to the learner-facing surface.
11. **Project/user scope** — all methods scoped; question generation is grounded only in the project's chunks (via Knowledge).
12. **Transaction boundary** — submit_answer = answer row (unique per question) + `AssessmentSubmitted` event in one transaction; grading may extend the same transaction for MCQ (deterministic, instant) while open-ended AI grading finalizes within the request budget with a `pending_review` fallback.
13. **Idempotency** — submit_answer idempotency key + unique constraint (one answer per question; duplicate key returns the recorded result, no re-grading).
14. **Failure modes** — `NotFound`, `QuizAlreadyCompleted`, `QuestionAlreadyAnswered` (idempotent replay instead where key matches), `AIInvalidOutput` → per-feature fallback (skip/replace question; grading → `pending_review` flagged in results, learner sees explicitly provisional feedback); `EmptyCorpus` (no ready material for a concept → quiz creation refused with guidance).
15. **Dependencies** — Knowledge (chunks for grounding, concepts); Mastery (read mastery/confidence/mistakes for selection); AI (structured question generation, structured grading); Tools (when quiz creation originates from a tool call); Platform.
16. **Must NOT access directly** — mastery storage (only via facade reads; writes via `MasteryUpdated` events emitted by Mastery), conversations, provider SDKs.

---

## 7. Mastery

1. **Responsibility** — Per-(project, concept) mastery state; evidence recording; deterministic update math (BKT-style + decay, difficulty-weighted); recomputation as a pure function of the append-only evidence trail. Owns mastery state + mastery events.
2. **Non-responsibilities** — Deciding what to ask next (Assessment); trend/weakness classification (Growth); UI rendering.
3. **Public service interface — `MasteryService`**
   - `record_learning_event(scope, evidence_input) -> MasteryStateDto` (append evidence + recompute affected concept atomically)
   - `recompute_mastery(scope, concept_id) -> MasteryStateDto` (pure replay from evidence trail)
   - `get_project_mastery(principal, scope) -> [MasteryStateDto]`
   - `get_mastery_summary(principal, scope, concept_ids?) -> MasterySummaryDto` (dashboard/tool read model)
   - `get_evidence_trail(principal, scope, concept_id) -> [MasteryEventDto]`
4. **Input DTOs** — `EvidenceInput{source: quiz_answer|open_assessment|tutor_signal|manual, source_id, concept_id, evidence_strength, is_correct?, score?, occurred_at}`.
5. **Output DTOs** — `MasteryStateDto{project_id, concept_id, mastery, confidence, evidence_count, consecutive_correct, last_evidence_at}`; `MasteryEventDto{event_id, source, source_id, mastery_before, mastery_after, evidence_strength, occurred_at}`; `MasterySummaryDto{concepts: [MasteryStateDto], attention_concepts: [concept_id], generated_at}`.
6. **Commands** — `record_learning_event`; `recompute_mastery`.
7. **Queries** — project mastery, summary, evidence trail.
8. **Events emitted** — `MasteryUpdated` (before/after, source, concept).
9. **Events consumed** — `AssessmentSubmitted`/`AssessmentEvaluated` (converts evaluated answers into evidence; **skips `pending_review` grades until resolved** — ADR-0021/Q3), `TutorInteractionCreated` (tutor signals: **weak evidence only** — explicit machine-derived signals mapped to `source='tutor_signal'` at a fixed config-declared strength strictly below any quiz answer; free text is never evidence — ADR-0021/Q2).
10. **Authorization** — service-level `scope` required; HTTP surface read-only for owner; **no direct HTTP write** — evidence arrives via events/worker (source of writes is Assessment/Tutor flows).
11. **Project/user scope** — scope embedded in every state row; concurrency on the same concept is guarded (serialization retry policy).
12. **Transaction boundary** — `record_learning_event` = append event + upsert state in one transaction, plus `MasteryUpdated` outbox row.
13. **Idempotency** — natural unique key `(source, source_id, concept_id)` — retried events are no-ops; recompute is deterministic and safe to re-run.
14. **Failure modes** — `DuplicateEvidence` (idempotent skip), `UnknownConcept`, serialization conflict → bounded retry with jitter then `DependencyError`.
15. **Dependencies** — Knowledge (concept validation); Platform; events from Assessment/Tutor (via Jobs plumbing).
16. **Must NOT access directly** — quizzes/answers storage (works from event payloads + facade reads); growth tables.

---

## 8. Growth

1. **Responsibility** — Growth snapshots (trend classification), weakness detection, repeated-mistake pattern detection, recommendation generation + lifecycle (accept/dismiss, dedup, expiry). Owns growth snapshots + recommendations.
2. **Non-responsibilities** — Mastery math (consumes Mastery facade/events); phrasing content (AI, under deterministic targeting); quiz creation.
3. **Public service interface — `GrowthService`**
   - `analyze_project_growth(scope, window?) -> [GrowthSnapshotDto]` (worker-facing + scheduled)
   - `detect_weaknesses(scope) -> [WeaknessDto]`
   - `generate_recommendations(scope) -> [RecommendationDto]` (worker-facing; deterministic targeting, AI phrasing)
   - `list_recommendations(principal, scope) -> [RecommendationDto]`
   - `accept_recommendation(principal, recommendation_id) -> RecommendationDto`
   - `dismiss_recommendation(principal, recommendation_id) -> RecommendationDto`
4. **Input DTOs** — `WindowInput{start?, end?}` (defaults from config).
5. **Output DTOs** — `GrowthSnapshotDto{project_id, concept_id, window_start, window_end, mastery_start, mastery_end, delta, trend: improving|stable|needs_attention}`; `WeaknessDto{concept_id, evidence (mastery level, mistake pattern, recency), confidence}`; `RecommendationDto{id, kind: review_material|take_quiz|tutor_session|revisit_concept|new_material, title, rationale, target_concept_ids, target_material_id?, priority, status: active|accepted|dismissed|expired, created_at, expires_at?}`.
6. **Commands** — `generate_recommendations` (worker); accept/dismiss.
7. **Queries** — snapshots, weaknesses, list recommendations.
8. **Events emitted** — `GrowthUpdated`, `WeaknessDetected`, `MistakeRepeated`, `RecommendationGenerated`, `ActivityRecorded`.
9. **Events consumed** — `MasteryUpdated`, `QuizAttemptCompleted`, `MistakeRepeated`-precursors (mistake patterns from Assessment events).
10. **Authorization** — user-facing reads/actions owner-only; worker-facing analyze/generate require scope-bearing job context.
11. **Project/user scope** — all state project-scoped; recommendations carry dedup keys per project.
12. **Transaction boundary** — snapshot write / recommendation insert each one transaction with their outbox rows.
13. **Idempotency** — recommendations dedup-keyed (unique among *active* per project); snapshot upsert per `(project, concept, window_end)`; consumers idempotent via event ids.
14. **Failure modes** — `AIInvalidOutput` on phrasing → deterministic template fallback (recommendation still created, phrasing marked template); `NoEvidence` (new project → empty snapshots, no recommendations — a valid empty state, not an error).
15. **Dependencies** — Mastery (facade reads); Knowledge (concepts, materials for review targets); Assessment (mistake reads); AI (recommendation phrasing, structured); Platform.
16. **Must NOT access directly** — mastery tables (facade only); conversations; chunk storage.

---

## 9. Analytics

1. **Responsibility** — Event ingestion (append-only), the **consumer-side idempotency registry** (`(consumer, event_id)`; owned here per ADR-0021/Q1 — Analytics stewards the schema/contract, each consumer writes its registry row inside its own transaction), rollup maintenance (worker/scheduled), project/global activity + AI-usage read models. Owns event store, rollups, processed-events registry.
2. **Non-responsibilities** — Being the source of truth for domain state (that's the modules + outbox); business decisions; admin authorization.
3. **Public service interface — `AnalyticsService`**
   - `record_activity(scope, activity_input) -> None` (from outbox consumers)
   - `ingest_events(events: [EventEnvelopeDto]) -> IngestResultDto` (worker consumer entry)
   - `get_project_analytics(principal, scope, range?) -> ProjectAnalyticsDto`
   - `get_global_analytics(principal, range?) -> GlobalAnalyticsDto` (admin-plane or platform-level read)
   - `get_project_activity(principal, scope, filters?, page?) -> [ActivityEntryDto]`
   - `get_ai_usage_summary(filters?) -> [AiUsageRollupDto]` (admin/tooling read)
4. **Input DTOs** — `EventEnvelopeDto` (the canonical envelope from domain-events.md); filter/range/page params (allow-listed fields).
5. **Output DTOs** — `ProjectAnalyticsDto{activity_timeseries, assessment_performance, mastery_trends, concept_trends, ai_activity}`; `GlobalAnalyticsDto{users, projects, activity, engagement, ai_usage}`; `AiUsageRollupDto{feature, window, requests, tokens_in/out, estimated_cost, error_rate}`.
6. **Commands** — `ingest_events`; `record_activity`.
7. **Queries** — project/global analytics, activity feed, AI usage rollups.
8. **Events emitted** — none (terminal consumer; rollup refresh is internal).
9. **Events consumed** — `ActivityRecorded` and audit-consumes of all catalogue events for rollups (the **only** module that may observe every event type).
10. **Authorization** — project analytics: owner via scope; global analytics + AI usage: `role=admin` only (or explicit internal callers); activity feed owner-only.
11. **Project/user scope** — events carry user/project ids from the producing scope; queries enforce ownership or admin role.
12. **Transaction boundary** — batch ingestion = one transaction per batch with consumer dedup registry entries.
13. **Idempotency** — `(consumer, event_id)` registry — redelivery is a no-op; rollups are rebuildable from the append-only store (derived-data principle).
14. **Failure modes** — `MalformedEvent` (schema mismatch → DLQ, alert); overflow/backpressure → upstream shedding order defined in failure docs; queries degrade to stale rollups rather than erroring.
15. **Dependencies** — Platform only (no domain facades needed — events are self-contained payloads).
16. **Must NOT access directly** — any domain table (consumes events + serves rollups; if a rollup needs domain data, that data must arrive in the event payload).

---

## 10. Admin

1. **Responsibility** — Read-only platform views: overview, users, single-user journey, filterable activity, AI usage/requests/evaluations, job health, system health. Owns **no** domain tables (pure read-model composition).
2. **Non-responsibilities** — Any mutation of learner data (A-01); content access (A-05: metadata/analytics only); alert routing.
3. **Public service interface — `AdminService`**
   - `get_overview(principal) -> PlatformOverviewDto`
   - `list_users(principal, filters?, page?) -> [AdminUserDto]`
   - `get_user_journey(principal, user_id) -> UserJourneyDto`
   - `query_activity(filters) -> [AdminActivityDto]`
   - `get_ai_usage(filters?) -> [AiUsageRollupDto]`
   - `get_ai_request_detail(principal, ai_request_id) -> AiRequestDetailDto` (metadata + retrieval meta, not prompt bodies per logging policy)
   - `get_ai_evaluations(filters?) -> [AiEvaluationDto]`
   - `get_job_health() -> JobHealthDto`
   - `get_system_health() -> SystemHealthDto`
4. **Input DTOs** — filters (user/space/project/type/period), paging.
5. **Output DTOs** — aggregates and timelines; `UserJourneyDto{spaces, projects, activity_timeline, assessment_summaries, mastery_distribution, ai_usage_summary}` — **metadata/aggregates only**.
6. **Commands** — none (read-only module).
7. **Queries** — all of the above.
8. **Events emitted** — none; every admin read is **audit-logged** (security evidence, separate from activity events).
9. **Events consumed** — none directly (reads rollups via Analytics facade).
10. **Authorization** — every method requires `role=admin`; every call writes an audit entry with `target_user_id` where applicable; bulk-access anomaly is a monitoring concern fed by those audits.
11. **Project/user scope** — deliberately **cross-project** (that's its purpose) — bounded by role=admin + audit, not by ownership.
12. **Transaction boundary** — read-only; audit entry write is separate (must never fail the read).
13. **Idempotency** — n/a (queries).
14. **Failure modes** — `Forbidden` is reserved for capability/policy denials; **role failures on admin routes return 404** (ADR-0021/Q5: identity/existence questions → 404, capability questions → 403) with mandatory audit-log entries carrying the attempted route + principal so anomaly alerting (T13) keys on audit volume; degraded rollups on Analytics lag (stale-but-labelled data).
15. **Dependencies** — Analytics (rollups); Workspace/Identity (aggregate reads via facades); Jobs (job health read model); AI (telemetry reads via facade).
16. **Must NOT access directly** — domain tables for content (documents, message bodies, raw answers — A-05); anything writable.

---

## 11. AI (Gateway)

1. **Responsibility** — The **only** egress to model providers: generation, streaming, structured generation, embeddings, rerank, evaluation, document understanding; prompt registry (versioned); model routing by role; budget/rate enforcement; circuit breaking + fallback chains; structured-output validation; per-call metering persistence. Owns `ai_requests`, `ai_evaluations`, prompt registry.
2. **Non-responsibilities** — Business decisions; deciding *what* to ask (that's domain modules); tool execution (Tools); retrieval logic (Knowledge calls `embed`/`rerank`, owns the pipeline).
3. **Public service interface — `AIGateway`**
   - `generate(scope_ref, feature, request) -> GenerationResult`
   - `stream(scope_ref, feature, request) -> (stream of StreamChunk, finalizer)`
   - `structured(scope_ref, feature, request: StructuredRequest[SchemaT]) -> StructuredResult[SchemaT]`
   - `embed(feature, texts: [str]) -> EmbeddingResult` (batching + cache internally)
   - `rerank(feature, query, candidates) -> RerankResult`
   - `evaluate(feature, eval_request) -> EvaluationResult`
   - `understand_document(feature, document_part) -> VisionResult`
   - `get_request_trace(ai_request_id) -> AiRequestDetailDto` (admin/support path)
4. **Input DTOs** — `GenerationRequest{prompt_ref (id+version), variables, max_tokens?, temperature?, stream?}`; `StructuredRequest{prompt_ref, variables, output_schema (schema object, not a string), max_repair_attempts?}`; `EmbeddingRequest{texts, model_role?}`; scope_ref carries `{user_id?, project_id?, feature, correlation_id}` — **ids only**, never entities.
5. **Output DTOs** — `GenerationResult{text, usage, finish_reason}`; `StructuredResult{data (validated) | ValidationErrorSet after repair failure, usage, attempt_count}`; `EmbeddingResult{vectors, model, dimensions}`; `RerankResult{ranked: [{index, score}]}`; all results carry `ai_request_id`.
6. **Commands** — all the above are operations; no domain writes (metering writes are internal).
7. **Queries** — `get_request_trace`.
8. **Events emitted** — `AIRequestCompleted` (every call, success or failure, via outbox).
9. **Events consumed** — none.
10. **Authorization** — callers must be **domain modules** (import rule); `scope_ref` is server-derived; the gateway never accepts a caller-supplied tenant id as authoritative for metering (it records what the scope_ref claims but trust comes from the call chain).
11. **Project/user scope** — propagates scope_ref into metering + traces; enforces per-user/per-feature budgets.
12. **Transaction boundary** — metering write is its own transaction (must survive caller rollback to keep telemetry honest); generation itself is not transactional.
13. **Idempotency** — embedding cache by `(text-hash, model)`; retries only for idempotent operations (embed/rerank); generation retries are bounded and budget-aware.
14. **Failure modes** — typed `AITimeout`/`AIRateLimited`/`AIProviderDown`/`AIInvalidOutput`; circuit-open → fallback chain → caller-visible degradation; budget exceeded → graceful degrade policy (smaller model/shorter context) or typed `AIBudgetExhausted` for hard caps; **never** raises raw provider exceptions upward.
15. **Dependencies** — Platform (config, secrets, HTTP clients, telemetry); providers behind adapters (technology-independent here).
16. **Must NOT access directly** — domain modules' services or tables; Tools; it must remain **dependency-free of all domain modules** (they depend on it, never the reverse).

---

## 12. Tools (Application Capability Layer)

1. **Responsibility** — The AI capability boundary: tool registry (JSON-schema'd), argument validation, per-tool authorization, scope injection, execution via domain service facades, result shaping/size-capping/redaction, full audit. Detailed tool contracts: `docs/architecture/ai-tool-contracts.md`.
2. **Non-responsibilities** — Model reasoning; deciding *when* to call a tool (the model, within the bounded loop); policy authorship (registry contents are config + review).
3. **Public service interface — `ToolExecutor`**
   - `list_tools(feature) -> [ToolDescriptorDto]` (schemas for the model's tool-channel)
   - `invoke(scope: ProjectScope, ai_request_id, tool_invocation: ToolCallDto) -> ToolResultDto`
4. **Input DTOs** — `ToolCallDto{name, arguments (raw JSON), justification? (required for write tools)}`; `ToolDescriptorDto{name, description, input_schema, output_schema, write: bool}`.
5. **Output DTOs** — `ToolResultDto{status: success|validation_error|denied|execution_error, data? (size-capped, redacted), error{code, message}?, invocation_id}` — errors are **returned to the model as data**, never thrown into the model channel.
6. **Commands** — `invoke` (the only command; each tool's effect is defined in ai-tool-contracts.md).
7. **Queries** — `list_tools`.
8. **Events emitted** — `ActivityRecorded` (type `tool.invoked`, outcome incl. denials) — plus the dedicated audit trail owned here.
9. **Events consumed** — none.
10. **Authorization** — per-tool allow-list **per feature** (Tutor ≠ quiz-generator); write-tools require justification; scope is **server-injected** — any tenant id in tool arguments is rejected before validation; denied calls are audited and returned as error results.
11. **Project/user scope** — every invocation requires `ProjectScope`; executed domain methods receive the same scope (RLS-equivalent enforcement applies downstream).
12. **Transaction boundary** — execution delegates to the owning service (its boundary applies); audit write is separate.
13. **Idempotency** — per-tool (defined in ai-tool-contracts.md); write-tools are dedup-keyed where they create state.
14. **Failure modes** — unknown tool → denied; schema-invalid args → `validation_error` (one model-retry allowed by the orchestrator); authz denial → `denied`; execution error → `execution_error` with safe message; loop caps enforced by the Tutor orchestrator (step + wall-clock), Tools enforces per-invocation cost caps.
15. **Dependencies** — Workspace, Knowledge, Assessment, Mastery, Growth, Tutor (read/write facades per tool); Platform (audit, config).
16. **Must NOT access directly** — any table; AI providers (it shapes results for the model, it does not call them); Tools must never widen a tool's effect beyond the registered schema.

---

## 13. Jobs

1. **Responsibility** — Async execution plumbing: task definitions (thin entrypoints delegating into services), outbox relay, scheduling (beat-style), retry/backoff policy, DLQ handling, job status read model. Owns outbox + job-run records.
2. **Non-responsibilities** — Business logic (tasks are one-line delegations); ownership decisions (tasks carry context, services enforce); event schema design (catalogue-owned).
3. **Public service interface — `JobsService`**
   - `enqueue(task_ref, payload, dedup_key?, ownership_context) -> JobRefDto` (internal; normally via outbox)
   - `relay_outbox() -> RelayResultDto` (scheduled + post-commit nudge)
   - `get_job_status(principal, job_id) -> JobStatusDto`
   - `get_job_health() -> JobHealthDto` (admin read model)
   - `requeue_dead_lettered(principal, job_id) -> JobStatusDto` (admin action; audited)
4. **Input DTOs** — `TaskRef{name, queue}`, payload envelopes with `{user_id, project_id, correlation_id}` ownership context; dedup keys.
5. **Output DTOs** — `JobRefDto{job_id, queue, status}`; `JobStatusDto{job_id, status: queued|running|succeeded|failed|dead_lettered, attempt, error?, timestamps}`; `JobHealthDto{queues: [{name, depth, oldest_age, failure_rate}], dead_lettered_count}`; `RelayResultDto{claimed, dispatched, failed}`.
6. **Commands** — enqueue; relay; requeue (admin).
7. **Queries** — status; health.
8. **Events emitted** — none of its own (it is the transport for others').
9. **Events consumed** — all (relay dispatches; consumers are the domain modules).
10. **Authorization** — status readable by owner (job carries ownership context) or admin; requeue is admin-only + audited; tasks **fail closed** without a resolvable ownership context.
11. **Project/user scope** — every task payload carries ownership context; the worker session is opened under that context so isolation applies identically off-request.
12. **Transaction boundary** — relay claims with concurrency-safe claiming (skip-locked semantics) and marks published; each task execution is its own unit (inside the target service).
13. **Idempotency** — dedup-key uniqueness among queued/running; consumer dedup registry (Analytics-owned) is the second layer; `acks_late`-equivalent semantics so crashes redeliver rather than lose.
14. **Failure modes** — broker unavailable → events remain pending in the outbox (no loss, delay only); poison task → retry exhaustion → DLQ + `job_runs` status + admin visibility; scheduler outage → relay lag alerts.
15. **Dependencies** — Platform (broker abstraction, config); every domain module (via task registrations only); Analytics (dedup registry — or owns a local one; see open questions).
16. **Must NOT access directly** — no domain tables; business logic in tasks is a defect by definition.

---

## 14. Platform

1. **Responsibility** — Cross-cutting infrastructure: configuration (typed, startup-validated), secrets, database/units-of-work, cache, storage abstraction, clock, security primitives (hashing, tokens, crypto), error taxonomy + problem-mapping, structured logging with central redaction, tracing/metrics, audit-log writer.
2. **Non-responsibilities** — Any domain logic; authorization *decisions* (provides primitives, modules decide); event semantics.
3. **Public interface — `Platform` (set of infrastructure services, not a facade in the domain sense)**
   - `config` (validated settings; refuses boot on missing/malformed)
   - `unit_of_work` / transactional session provider (scope-variable aware)
   - `cache` (get/set/evict, namespaced, version-keyed)
   - `storage` (presign-put/get, head/verify, delete)
   - `security` (hash/verify, token sign/verify, constant-time compare)
   - `audit_writer.record(actor, action, target, metadata)`
   - `logger` / `tracer` / `metrics` (correlation-aware)
   - `clock`
4. **Input/Output DTOs** — infrastructure-level (connection refs, presign params, audit entries); no domain DTOs.
5. **Commands** — as above.
6. **Queries** — as above.
7. **Events emitted** — none.
8. **Events consumed** — none.
9. **Authorization** — primitives only; the app's DB role is least-privilege (isolation enforcement at the store layer stays possible); audit writer is append-only.
10. **Project/user scope** — provides the mechanism (session variables), modules provide the values.
11. **Transaction boundary** — provided per unit-of-work; cache/storage calls are non-transactional with fallback semantics (cache errors are never fatal).
12. **Idempotency** — n/a (infrastructure).
13. **Failure modes** — every primitive has a typed error; cache failures degrade (log + metric + fall through); storage failures are surfaced as `DependencyError` (retryable) or typed upload-verification errors.
14/15/16. **Dependencies** — external technologies only (behind these abstractions). **Must NOT be accessed directly by:** nothing — it is the base layer; but Platform must never import domain modules (one-way dependency, import-rule enforced).

---

## Cross-module rules (summary)

| Rule | Enforcement |
|---|---|
| Domain modules interact **only via these contracts** | Import rules in CI; code review |
| Scope objects are constructed once at the edge and passed down | Route-guard dependencies; contract signatures above |
| Events carry ownership context; consumers stay idempotent | Envelope schema (domain-events.md); dedup registry |
| AI providers are reachable only through `AIGateway`; Tools are the only path from AI to domain effects | Import rules; tool registry |
| Workers act under the owning user's context, fail closed without it | Task envelope contract; Jobs §11 |
| Admin is read-only and audited | Admin contract §10; audit writer |
| No module writes another module's tables | Per-module "Must NOT access directly" + ownership map |

## Open contract questions — RESOLVED

All previously open questions (dedup-registry ownership, tutor-signal mastery evidence, `pending_review` lifecycle, Materials↔Jobs callbacks, admin error posture) are resolved in **`ADR-0021-open-contract-resolutions.md`**; the contracts above were amended accordingly (per-section notes cite Q1–Q5).
