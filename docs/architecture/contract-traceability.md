# Contract Traceability — Requirement → Module → Contract → Event/Tool → Test

**Status:** Proof-of-coverage map for review. Every important requirement is shown to have (1) an owning module, (2) a contract that defines its boundary, (3) the event(s)/tool(s) that carry its cross-module effects, and (4) the test/evaluation that validates it. Requirement IDs reference `docs/requirements/requirements-analysis.md` (PRD § references there).

**Legend:** Contracts = `module-contracts.md` (§M.n) · Events = `domain-events.md` (§E) · Tools = `ai-tool-contracts.md` (§T) · Tests = `test-strategy.md` (§TS.n) · Eval = `evaluation-strategy.md` (§ES.n) · Dataset = `golden-dataset.md`.

---

## 1. Functional requirements

| Requirement (PRD) | Module | Contract | Events / Tools | Test / Evaluation |
|---|---|---|---|---|
| **FR-01** auth, sessions (§18) | Identity | §M.1 `IdentityService` | `ActivityRecorded` (user.*) | TS2.2/2.4 (flows, rotation, reuse-detection) |
| **FR-02** own-data only (§15) | All (edge) + Workspace | §M.2 `resolve_project_scope`; every §M scope rule | — | **TS2.5 + TS2.6 (isolation gate)** |
| **FR-03** admin role (§16) | Identity + Admin | §M.1 role resolution; §M.10 read-only | audit trail | TS2.5 (admin matrix + audit; admin-route 404 posture per ADR-0021/Q5) |
| **FR-10/11** Spaces + dashboard (§4) | Workspace | §M.2 space methods, `SpaceDashboardDto` | `ActivityRecorded` | TS2.2/2.4 |
| **FR-12/13** Projects + dashboard (§4) | Workspace | §M.2 project methods, `ProjectDashboardDto` | `ProjectCreated` | TS2.2/2.4 |
| **FR-14** navigation (§4) | Frontend (routes per architecture §9) | — | — | TS2.11 (E2E traverses) |
| **FR-15** home dashboard (§16) | Workspace | §M.2 `get_home_dashboard` | `RecommendationGenerated` (feed) | TS2.2 |
| **FR-20** PDF upload (§5) | Materials | §M.3 upload intent/confirm | `MaterialUploaded` | TS2.2/2.3 (verification, caps) |
| **FR-21** async pipeline (§5) | Materials + Knowledge + Jobs | §M.3/§M.4/§M.13; `ingest_extracted_content`; Materials status authority via internal transition commands (ADR-0021/Q4) | `MaterialUploaded→Started→Completed` | TS2.9 (pipeline E2E at job level) |
| **FR-22** tables/images/scans (§5) | Knowledge (pipeline) + AI vision | §M.4 extraction DTO; AI §M.11 `understand_document` | `MaterialProcessingCompleted.extraction_stats` | Dataset §7 (corpus variety); TS2.8 |
| **FR-23** status visible (§5) | Materials | §M.3 status DTOs, `JobStatusDto` | `MaterialProcessingFailed` (reason) | TS2.4 (status API), TS2.11 |
| **FR-24** chunks/concepts/embeddings (§5) | Knowledge | §M.4 `ingest_extracted_content` (validated untrusted input) | `MaterialProcessingCompleted` (counts) | TS2.3 (constraints, replace-not-append) |
| **FR-25** traceable to source (§5) | Knowledge | §M.4 `ChunkRefDto` page anchors | — | TS2.1 (citation resolution rules); ES2.4 |
| **FR-26** retry/failure/dedup (§5,13) | Materials + Jobs | §M.3 reprocess; §M.13 relay/DLQ | `MaterialProcessingFailed` | **TS2.9/2.10** |
| **FR-30/31/32/33** Tutor + context (§6) | Tutor | §M.5 send/get/context methods; Context Composer | `TutorInteractionCreated`; tools 1–7 | TS2.2 (orchestration), ES2.1, Dataset §2 |
| **FR-34** citations doc+page (§7) | Tutor + Knowledge | §M.5 `CitationDto`; §M.4 `EvidenceSetDto` | — | **ES2.4 citation validity (100% gate)**; TS2.1 |
| **FR-35** insufficiency (§7 core) | Tutor + Knowledge | §M.4 `check_evidence_sufficiency`; §M.5 refusal path | — | **ES2.5 (fabrication = 0 gate)**; Dataset §2.2 |
| **FR-36** streaming (§15,18) | Tutor | §M.5 stream events contract | — | TS2.4 (SSE sequence) |
| **FR-40/41** controlled AI access (§8) | Tools | §M.12 executor + allow-list matrix | Tools §T.1–11 | TS2.5 (tool authz, scope injection) |
| **FR-42** validate AI structured data (§8) | AI Gateway + consuming modules | §M.11 `structured` (validate/repair/fallback) | `AIRequestCompleted` (invalid_output) | TS2.1/2.2 (fallbacks); ES2.6 validity rate |
| **FR-50/51** adaptive quiz, MCQ+open (§9) | Assessment | §M.6 quiz lifecycle, `QuestionDto` | `QuizCreated`, `QuizAttemptCompleted` | TS2.2; ES2.6 |
| **FR-52** non-naive adaptivity (§9) | Assessment | §M.6 selection policy (deterministic) | — | **TS2.1 property tests** (weights, decay, penalties) |
| **FR-53** open-ended AI grading (§9) | Assessment + AI | §M.6 `submit_answer` (structured evaluation); pending-review lifecycle with one idempotent re-grade (ADR-0021/Q3) | `AssessmentEvaluated` (attempted/superseding) | **ES2.7** (rubric agreement, coverage) |
| **FR-54** explanatory feedback (§9) | Assessment | §M.6 `AnswerResultDto.feedback` | — | ES2.7 feedback metrics |
| **FR-55** results feed mastery/growth (§9) | Assessment → Mastery/Growth | §M.6 events; §M.7 evidence; §M.8 | `AssessmentSubmitted/Evaluated` → `MasteryUpdated` | TS2.9 (chain), ES2.8 |
| **FR-60** mastery evolves (§10) | Mastery | §M.7 `record_learning_event`, `recompute_mastery`; weak tutor-signal evidence at config-declared sub-quiz strength (ADR-0021/Q2) | `MasteryUpdated`; consumes `TutorInteractionCreated` (weak signals) | **TS2.1 exact-match + order independence**; ES2.8 |
| **FR-61** growth trends (§10) | Growth | §M.8 `analyze_project_growth`, snapshots | `GrowthUpdated` | TS2.2 (classification windows) |
| **FR-62** recommendations (§10) | Growth | §M.8 `generate_recommendations`, dedup | `WeaknessDetected`, `MistakeRepeated`, `RecommendationGenerated` | **ES2.9** (targeting = 100% gate); Dataset §5 |
| **FR-63/64** learning context, relevant-only (§11) | Tutor (store + composer) | §M.5 `LearnerContextDto`; budgeted composition; tool 10 | `TutorInteractionCreated` (extraction) | TS2.1 (budget math); ES2.1 |
| **FR-70** events emitted (§12) | All modules | Every §M events-emitted row | Catalogue §E all | TS2.9 (payload/schema validation) |
| **FR-71/72** project/global analytics (§12) | Analytics | §M.9 queries, rollups | all events consumed | TS2.3/2.4 (rollup correctness) |
| **FR-73** event-driven workflows (§12,13) | Jobs + consumers | §M.13 chains | Quiz→Eval→Mastery→Weakness→Recommendation chain | **TS2.9** (full chain, idempotent) |
| **FR-74** event idempotency (§12) | Analytics + Jobs | §M.9 dedup registry; §M.13 relay | — | **TS2.10** (redelivery no-op) |
| **FR-80** provider-neutral abstraction (§14) | AI Gateway | §M.11 operation set, role routing | — | TS2.2 (stub gateways prove the seam) |
| **FR-81** per-call AI telemetry (§14) | AI Gateway | §M.11 metering | `AIRequestCompleted` | TS2.2/2.3 (record completeness) |
| **FR-82** investigation questions (§14) | AI + Platform (correlation) | §M.11 `get_request_trace`; trace propagation | correlation ids in all events | TS2.9 (id propagation request→job→AI) |
| **FR-83** eval suites (§14) | AI evaluation | — | sampling via `AIRequestCompleted` | **ES all** + Dataset |
| **FR-84** regression evaluation (§14,18) | AI evaluation + CI | — | — | **ES1 L1 merge gate** + baseline discipline |
| **FR-90/91/92** admin views (§16) | Admin | §M.10 read-only surface + audit | reads Analytics rollups | TS2.4/2.5 (role, filters, audit-on-read) |

## 2. Non-functional requirements

| Requirement | Boundary owner | Validation |
|---|---|---|
| **NFR-01** graceful failure (§15) | Every module's failure-mode row + Platform primitives | TS2.2 (scripted AI/dependency failures), TS2.9 (broker down, poison tasks), ES degradation flags in retrieval |
| **NFR-02** no duplicate state (§12,15) | Contracts' idempotency rows; Events envelope | **TS2.10 dedicated layer** |
| **NFR-03** isolation incl. jobs (§15) | Scope rules in every §M; task ownership context (§M.13) | **TS2.6 dedicated gate** (routes, tools, retrieval, jobs) |
| **NFR-04** security controls (§15) | Identity/AuthZ rows; Tools §T.4 order; Platform security; 404/403 error posture (ADR-0021/Q5) | TS2.5; upload verification TS2.2 |
| **NFR-05** content ≠ instructions (§15) | Tools boundary rules; Tutor evidence DATA-framing | TS2.5 (scope-injection + channel rules); ES2.5 (injection-adjacent refusal cases) |
| **NFR-06** performance posture (§15) | Contracts (rollups, caching, batching, budgets) | TS2.3/2.4 (pagination, cache behavior); targets tracked per assumptions A-10, not asserted here |
| **NFR-07** secrets (§18) | Platform config; project-principles §13 | CI secret scan (gate) |
| **NFR-08** meaningful tests (§18) | — | This strategy; TS gate order |
| **NFR-09** deployed E2E (§18) | Deployment (future phase) | TS2.11 E2E against staging |
| **NFR-10** docs + ADRs (§18–20) | docs/ tree | Review checklist |

## 3. AI tools ↔ requirements

| Tool (§T) | Serves | Validated by |
|---|---|---|
| `search_project_materials` (T.1) | §8 search capability; Tutor context | TS2.5 (authz/scope); ES2.2 (retrieval beneath it) |
| `retrieve_project_evidence` (T.2) | §7 grounding primitive | ES2.2/2.3/2.5 |
| `get_project_progress` (T.3) | §8 progress capability | TS2.2 |
| `get_mastery_summary` (T.4) | §10 visibility | TS2.1 (math beneath it) |
| `get_weak_concepts` (T.5) | §10 weakness identification | TS2.1 + ES2.9 targeting |
| `get_learning_context` (T.6) | §11 context retrieval | TS2.1 (salience math) |
| `get_assessment_history` (T.7) | §9 history capability | TS2.5 (no free-text exposure) |
| `generate_quiz` (T.8) | §8 quiz capability (write) | TS2.5 (justification, dedup, intent allow-list); ES2.6 |
| `record_learning_event` (T.9) | §8 event recording (write) | TS2.5 (enum lock, idempotency) |
| `update_learning_context` (T.10) | §11 persistence (write) | TS2.5 (hash-upsert idempotency) |
| `record_recommendation` (T.11) | §10 recommendation (write) | TS2.5 (dedup, scope) |

## 4. Events ↔ requirements

| Event (§E) | Serves | Validated by |
|---|---|---|
| `ProjectCreated` | FR-70/73, FR-13 | TS2.9 |
| `MaterialUploaded/Started/Completed/Failed` | FR-21/23/26, BP-01 | TS2.9/2.10; TS2.11 (status chip journey) |
| `TutorInteractionCreated` | FR-63/70/73, FR-83 sampling | TS2.9; ES sampling |
| `QuizCreated/Submitted/Evaluated/AttemptCompleted` | FR-50–55/70/73 | TS2.9 (chain) |
| `MasteryUpdated` | FR-60/73 | TS2.9; ES2.8 |
| `GrowthUpdated/WeaknessDetected/MistakeRepeated` | FR-61/62, §13 | TS2.9; ES2.9 |
| `RecommendationGenerated` | FR-62, FR-13/15 | TS2.9; ES2.9 |
| `ActivityRecorded` | FR-70/92 | TS2.4 (feed API) |
| `AIRequestCompleted` | FR-81/82/83 | TS2.2/2.3 (record completeness, cost fields) |

## 5. Invariants (cross-cutting proof)

| Invariant | Enforcing contracts | Proof artifacts |
|---|---|---|
| **Isolation** (G1) | Scope rules in §M.1–§M.13; RLS-capable role (Platform §M.14); server-injected tool scope (§M.12/§T.4) | TS2.6 dedicated gate; TS2.5 |
| **Grounding** (G2) | §M.4 sufficiency + §M.5 citation validation + refusal path | ES2.3/2.4/2.5 (structural zero-tolerance gates) |
| **Model has no privileges** | §M.11 (no domain deps), §M.12 (only tool path), §T catalogue closure | TS2.5; import contracts in CI |
| **Untrusted model output** | §M.11 structured validate/repair/fallback; §M.4 validates extraction payloads | TS2.2 fallback tests; ES2.6 validity rate |
| **Deterministic learning logic** | §M.6 selection, §M.7 math | TS2.1 exact/property tests |
| **Reliable async** | Outbox semantics §M.13 + consumer dedup §M.9 + natural keys | TS2.9/2.10 |
| **Observable AI** | §M.11 metering + `AIRequestCompleted` + correlation ids | TS2.2/TS2.9 propagation tests |

## 6. Coverage gaps (deliberate, with disposition)

| Area | Status | Disposition |
|---|---|---|
| Exact thresholds for AI quality gates | TBD by design | Calibrated via golden dataset run (ES §4 register) |
| Deployment/infra contracts (queues, DB specifics) | Deferred by ADR set | Phase 0 infrastructure ADRs; contracts above are technology-independent by intent |
| UI-level accessibility automation | Not yet specified | Phase 0 frontend task; E2E asserts keyboard/ARIA basics (TS2.11) |
| Load/performance testing | Phase 1 per assumptions | Not gated in prototype window |

Every FR/NFR row above resolves to a named boundary and a named validation — no requirement is left with "somewhere in the code" as its enforcement story.
