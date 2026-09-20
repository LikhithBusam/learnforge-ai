# Architecture Consistency Audit — Cross-Document Verification

**Status:** Audit performed after ADR-0021 resolutions, the provider-trial protocol, and the AI model configuration concept. Method: for each requirement chain, verify every link — Requirement → Architecture principle → Module → Service contract → Event/Tool → Persistence responsibility → Test → Evaluation. Statuses: **PASS** (all links present) · **WARNING** (link present but ambiguous/soft — flagged, no silent repair) · **GAP** (missing link — reported, not silently fixed).

**Documents verified:** requirements-analysis · architecture-decisions (+ ADR-0012b…0021) · module-contracts · domain-events · ai-tool-contracts · contract-traceability · technology-baseline · ai-model-configuration · evaluation-strategy · ai-provider-trial · golden-dataset · test-strategy · security-baseline · assumptions · project-principles.

---

## 1. Requirement chains (Requirement → … → Evaluation)

| Chain | P (principle) | M (module) | S (contract) | E/T (event/tool) | Pers (persistence) | T (test) | Eval | Status |
|---|---|---|---|---|---|---|---|---|
| FR-34/35 grounded answers + refusal | §3 grounding | Tutor + Knowledge | §M.5 send_message; §M.4 sufficiency | `TutorInteractionCreated`; tool 2 | chunks (page anchors) | TS2.1/2.2/2.7 | ES2.3/2.4/2.5; structural gates armed | **PASS** |
| FR-02 isolation | §2 invariant | All (scope rules) | every §M scope row; §M.2 `resolve_project_scope` | — (envelope user/project ids) | RLS + in-query filters (ADR-0013) | TS2.6 gate | structural gate (scope) | **PASS** |
| FR-40–42 controlled AI interaction | §5 no-privilege AI | Tools + AI Gateway | §M.12 executor; §M.11 structured | 11 tools; `AIRequestCompleted` | tool_invocations; ai_requests | TS2.5; TS2.1 (schema) | ES2.6; hard gates in trial protocol | **PASS** |
| FR-60/52 deterministic learning | §6 | Mastery + Assessment | §M.7 math; §M.6 selection | `MasteryUpdated`; `AssessmentEvaluated` | mastery_events append-only | TS2.1 exact/property | ES2.8 | **PASS** |
| FR-73/74 event workflows + idempotency | §7 async | Jobs + consumers | §M.13 relay; §M.9 registry (ADR-0021/Q1) | full catalogue | outbox_events + processed_events | TS2.9/2.10 | — (structural idempotency gates) | **PASS** |
| FR-81/82/83/84 AI observability + eval | §8/§9 | AI Gateway | §M.11 metering + interface envelopes | `AIRequestCompleted` | ai_requests/ai_evaluations | TS2.8 | ES all + provider-trial protocol | **PASS** |
| FR-01/03 auth + admin | §12 | Identity + Admin | §M.1; §M.10 (404 posture, ADR-0021/Q5) | audit trail | users/sessions; audit_log | TS2.5 (incl. admin 404 cases) | — (structural authz gates) | **PASS** |
| FR-21–26 ingestion | BP-01 | Materials + Knowledge + Jobs | §M.3 (status authority, ADR-0021/Q4); §M.4 ingest | `Material*` events | materials/chunks/embeddings | TS2.9/2.3 | ES2.2; dataset corpus | **PASS** |
| FR-63/64 context | §9 of ADR set | Tutor composer | §M.5 LearnerContextDto; tool 10 | `TutorInteractionCreated` | learning_context_items | TS2.1 (budget math) | ES2.1 | **PASS** |
| FR-71/72/90–92 analytics/admin views | §11 honesty | Analytics + Admin | §M.9; §M.10 | all events consumed | rollups (derived) | TS2.3/2.4 | — | **PASS** |
| NFR-07 secrets | §13 | Platform | §M.14 config | — | — | CI secret scan (gate) | — | **PASS** |
| A-04 email verification stub | — | Identity | §M.1; ADR-0018 deferrals | — | email_verified flag | — (deferred feature) | — | **PASS** (documented deferral) |

## 2. Cross-document consistency checks

| # | Check | Status | Note |
|---|---|---|---|
| C1 | 404/403 posture consistent across ADR-0002, §M.10, principles §12, TS2.5, traceability | **PASS** | ADR-0021/Q5 fixed the one inconsistent row (§M.10 previously said `Forbidden` for non-admin) — now uniform: role/existence → 404; capability/policy → 403 |
| C2 | Dedup registry ownership stated once (Analytics, ADR-0021/Q1) across §M.9, §M.13, §E envelope | **PASS** | |
| C3 | Tutor-signal mastery rule (weak, config-strength, no free text) consistent across §M.7, §E, ADR-0021/Q2 | **PASS** | Strength *values* are config (A-23); fixture family added to golden-dataset |
| C4 | pending_review lifecycle consistent across §M.6, §M.7 (mastery exclusion), §E payload, ES2.7 | **PASS** | Confidence threshold is `TBD` (A-24) — semantic, calibrated later |
| C5 | Materials status authority (§M.3 internal commands) vs §M.13 thin-task rule | **PASS** | Dependency one-way; events emitted by Materials inside its own transactions |
| C6 | ADR-0015 interface envelopes vs §M.11 Gateway contract vs ai-model-configuration keys | **PASS** | Envelope fields (correlation/version/usage/cost/errors) match contract DTOs; role keys map 1:1 |
| C7 | Provider-trial hard gates vs evaluation-strategy structural gates | **PASS** | Trial hard gates ⊆ structural gate set; trial is a selection experiment, not a CI gate — no conflict |
| C8 | technology-baseline rows all trace to ADR-0013…0020; no orphan technology claims | **PASS** | Deferred register consistent with ADR-0015 addendum + ADR-0021 |
| C9 | Evaluation strategy gate taxonomy (§1.1/§4) vs test-strategy TS2.8 armed-gates description | **PASS** | Structural armed day one; semantic TBD — same rule in both docs |
| C10 | assumptions register vs new decisions (A-23 tutor-signal mapping, A-24 pending threshold) | **PASS** | Registered per maintenance rules |
| C11 | PRD §13 repeated-mistake workflow: `MistakeRepeated` producer is Growth, consuming AssessmentEvaluated history | **WARNING** | The producer/consumer split is coherent (Growth detects, tutor-context + recommendations react), but the *detection input* (mistake history source) relies on `AssessmentEvaluated` payload adequacy — acceptable, but first implementation must verify payload sufficiency before Growth's pattern detector is built |
| C12 | golden-dataset authoring depends on corpus selection (licensed docs) — not yet sourced | **WARNING** | Known build-kickoff task (§7 authoring plan); blocks threshold calibration, not structural gates |
| C13 | Admin AI views (FR-90) read `ai_requests` — schema detail (retrieval_meta shape) referenced by §M.11, §E, ES2.2 | **WARNING** | Shape is defined conceptually; exact JSON schema is a Phase 0 schema-design task — tracked, not a contradiction |
| C14 | SSE stream event names: §M.5 TutorStreamEventDto vs evaluation strategy's answer-status vocabulary | **PASS** | Same enum (`grounded|insufficient_evidence|general_knowledge|error`) |
| C15 | Traceability doc rows updated for ADR-0021 decisions | **PASS** | FR-03/21/53/60 + NFR-04 rows amended |
| C16 | Test-strategy environment rule (no live providers in merge gates) vs provider-trial live-provider runs | **PASS** | Trial is a scheduled/off-CI selection activity on staging — distinct pipeline |
| C17 | Observability correlation chain: request_id/trace_id propagation into Celery tasks | **WARNING** | Mechanism named everywhere (§M.14, ADR-0020, §E envelope) but the worker-side span-linking pattern is implementation-sensitive — first vertical slice must prove it; flagged for the Phase 0 scaffolding acceptance criteria |
| C18 | `update_learning_context` tool (write, AI-invoked) vs learning-context user deletion endpoint (FR-64 user control) | **PASS** | Tool writes are scoped, hashed-upsert; user deletion path exists in §M.5; no conflict |
| C19 | Golden-dataset tutor `answer_status` vocabulary vs §M.5 MessageDto | **PASS** | Identical enum |
| C20 | ai-model-configuration per-environment stub-adapters vs test-strategy E0/E1 stub requirement | **PASS** | Same mechanism, same registry |

## 3. Missing-link sweep (verification chains per architecture requirements)

| Area | Link checked | Status |
|---|---|---|
| Streaming contract (§M.5 events) → TS2.4 SSE sequence test → ES structural citation checks | present | **PASS** |
| Upload verification pipeline (§M.3) → TS2.2 tests → security-baseline §6 | present | **PASS** |
| Outbox → relay → consumer chain → TS2.9 → structural idempotency gate (ES §4.1) | present | **PASS** |
| Prompt versioning (ADR-0015) → prompt registry (§M.11) → ES baseline discipline → trial protocol | present | **PASS** |
| Retention/redaction (security-baseline §5) → assumptions A-06 → §M.11 logging policy | present | **PASS** |
| Circuit breaker/fallback states (ADR-0015/0020) → §M.11 failure modes → TS2.2 scripted failure tests | present | **PASS** |
| Admin read-only (A-01) → §M.10 → TS2.5 → ADR-0021/Q5 audit-on-denial | present | **PASS** |
| Budget enforcement (ADR-0015) → §M.11 `AIBudgetExhausted` → §M.5 degraded response | present | **PASS** |
| Isolation in worker plane (ADR-0002/0014) → §M.13 ownership context → TS2.6 fail-closed case | present | **PASS** |
| Rerank/embedding degraded modes → §M.4 retrieval_meta flags → ES2.2 metric capture | present | **PASS** |

## 4. Reported items (not silently repaired)

| ID | Item | Class | Disposition |
|---|---|---|---|
| R-C11 | `AssessmentEvaluated` payload sufficiency for Growth's mistake-pattern detector | WARNING | Verify at assessment/growth implementation design; payload extension is additive (`schema_version`) |
| R-C12 | Golden corpus documents not yet selected/licensed | WARNING | Build-kickoff task; gates semantic-threshold calibration only |
| R-C13 | `retrieval_meta` JSON schema not yet formalized | WARNING | Phase 0 schema-design task; conceptual shape agreed in three docs |
| R-C17 | Worker-side trace propagation pattern unproven | **RESOLVED in Phase 0** | Vertical slice implemented and verified: `tests/integration/test_vertical_slice_trace.py` proves request → Celery task → AI Gateway → telemetry with one correlation id (see `docs/engineering/phase-0-acceptance.md`) |
| — | **No GAP-class items found** | — | Every requirement chain resolves to named boundaries and validations |

## 5. Verdict

The documentation set is internally consistent: all requirement chains link requirement → principle → module → contract → event/tool → persistence → test → evaluation, with the four WARNINGs above being *implementation-time verifications* rather than contradictions. ADR-0021's resolutions were applied to every document its change log listed; the 404/403 posture, dedup ownership, tutor-signal rule, pending-review lifecycle, and Materials status authority are now stated identically across contracts, events, tests, principles, and traceability.
