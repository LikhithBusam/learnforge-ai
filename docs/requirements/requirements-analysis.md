# Requirements Analysis — AI Study Companion

**Status:** Planning artifact (no implementation)
**Source of truth:** Product Requirements Document v3.0 (Candidate Challenge Edition)
**Method note:** The PRD is referenced by section (§) throughout, matching the citation convention of the architecture baseline (`/architecture.md`). This document *analyzes* requirements; it does not restate or invent them. Where a requirement is unspecified in the PRD, it is recorded as an engineering assumption in `docs/engineering/assumptions.md` and marked `[A-xx]` here.

---

## 1. Project Objective

Build **AI Study Companion**, a context-scoped, evidence-grounded learning workspace in which a user:

1. Creates a **Space** (broad area) and a **Project** (focused learning journey with a learning goal).
2. Uploads **learning material** (PDF) to a Project.
3. The system asynchronously extracts knowledge (chunks, concepts, metadata, relationships, page references, embeddings).
4. Learns with an **AI Tutor** that answers **only** from that Project's evidence, with citations naming document and page, and refuses explicitly when evidence is insufficient.
5. Is assessed via **adaptive quizzes** (MCQ + open-ended), receives explanatory feedback, and builds **per-concept mastery** estimates.
6. Receives **growth analysis** (improving / stable / needs attention) and **actionable recommendations**.
7. An **admin plane** provides read-only platform visibility into users, learning activity, AI usage, AI quality, and system health.

The PRD frames this as a **3–4 day prototype** (§1, §18) that must be **publicly deployed and working end-to-end** (§18), while demanding architectural judgment suitable for production growth (§19). The build therefore distinguishes **architectural** work (done in Phase 0) from **operational** work (deferred with explicit triggers) — see §10.4 below and the ADR document.

### 1.1 Product principles and their engineering consequences

| PRD principle (§2) | Engineering consequence |
|---|---|
| **Context First** — unrelated Projects must not influence an answer | `project_id` mandatory on every content table, in every retrieval filter, in every tool-execution context; database-level isolation enforcement |
| **Evidence Over Guessing** | Retrieval returns an evidence set with a sufficiency decision; below threshold the Tutor refuses instead of generating; citations validated after generation |
| **Persistent but Relevant Context** | Context is *selected* under a token budget (conversation summary, structured learning-context facts, learner state, evidence) — never "send the whole history" |
| **Asynchronous by Design** | Long-running work (document processing, grading analysis, mastery chains, rollups) runs off the request path via a durable queue mechanism |
| **Observable AI** | Every AI call is recorded with model, feature, latency, tokens, cost estimate, and outcome |
| **Safe AI Interaction** | AI interacts with the application only through validated, permission-aware, audited tool interfaces |

---

## 2. User Journey (PRD §19)

The PRD defines the journey to be demonstrated end-to-end:

1. **Register / log in** (learner role by default).
2. **Create a Space**, then a **Project** with name, description, and learning goal.
3. **Upload material** (PDF) → observe async status: `queued → processing → ready` (or `failed` with reason).
4. **Tutor:** ask questions grounded in the Project's materials → receive answers with **citations (Document — Page N)**; ask an unsupported question → receive an **explicit insufficiency response**, not a fabrication.
5. **Quiz:** take an adaptive quiz (MCQ + open-ended) → receive explanatory feedback.
6. **Growth:** see mastery per concept, trends over time, and **recommendations** for what to do next.
7. **Analytics:** view project-level and global analytics.
8. **Admin:** authorized administrator views platform overview and can inspect a single user's learning journey.

Edge behaviours that are part of the journey (not extras): duplicate upload handling; processing failure with user-visible reason; browser may be closed during processing; follow-up questions and cross-session Tutor continuity.

---

## 3. Functional Requirements

Traceability IDs (FR-xx) are used throughout all planning artifacts and future code.

### 3.1 Identity & Access
| ID | Requirement | PRD |
|---|---|---|
| FR-01 | User registration, login, session management | §18 Must |
| FR-02 | Users access only their own Spaces/Projects | §15 |
| FR-03 | Administrator role with platform-level visibility | §16 |

### 3.2 Workspace
| ID | Requirement | PRD |
|---|---|---|
| FR-10 | CRUD Spaces (name, description, optional visual customization) | §4 |
| FR-11 | Space dashboard: projects, activity, progress, attention areas | §4 |
| FR-12 | Create Projects within a Space (name, description, learning goal) | §4 |
| FR-13 | Project dashboard: progress, important concepts, recent activity, performance, latest activity, recommended next step | §4 |
| FR-14 | Navigation Materials → Tutor → Quiz → Growth → Analytics | §4 |
| FR-15 | Home dashboard: Continue Learning, recents, overall progress, attention areas, recommended next action | §16 |

### 3.3 Materials & Knowledge
| ID | Requirement | PRD |
|---|---|---|
| FR-20 | Upload learning material to a Project; PDF required | §5 |
| FR-21 | Async pipeline: Queued → Processing/OCR → Extraction → Knowledge Extraction → Retrieval representation → Ready | §5 |
| FR-22 | Handle text, tables, images, diagrams, scanned pages | §5 |
| FR-23 | User-visible document status (queued / processing / ready / failed) | §5 |
| FR-24 | Produce chunks, concepts, metadata, relationships, page references, embeddings | §5 |
| FR-25 | Retrieved information traceable to its source | §5 |
| FR-26 | Background processing with retry, failure, duplicate-job handling | §5, §13 |

### 3.4 AI Tutor
| ID | Requirement | PRD |
|---|---|---|
| FR-30 | Project-scoped conversational Tutor | §6 |
| FR-31 | Tutor understands goal, materials, concepts, prior conversation, assessment history, learning context | §6 |
| FR-32 | Follow-ups, simpler explanations, examples, concept exploration, revision guidance | §6 |
| FR-33 | Cross-session continuity without sending full history per request | §6 |
| FR-34 | Grounded answers with citations naming document and page | §7 |
| FR-35 | Explicit insufficient-evidence handling instead of fabrication | §7 |
| FR-36 | Streaming Tutor responses | §15, §18 Should |

### 3.5 AI / Application Interaction
| ID | Requirement | PRD |
|---|---|---|
| FR-40 | AI accesses capabilities only via controlled, validated, permission-aware interfaces | §8 |
| FR-41 | Backend validation + authorization before any tool execution | §8 |
| FR-42 | AI-generated structured data validated before persistence or state change | §8 |

### 3.6 Assessment
| ID | Requirement | PRD |
|---|---|---|
| FR-50 | Adaptive quiz over project material and learning state | §9 |
| FR-51 | MCQ and open-ended question types | §9 |
| FR-52 | Selection considers concepts, mastery, mistakes, recent performance, difficulty, history — not naive wrong→easy / correct→hard | §9 |
| FR-53 | AI evaluation of open-ended answers (understanding, accuracy, relevance, concepts covered/missing, reasoning) | §9 |
| FR-54 | Explanatory feedback, not a bare score | §9 |
| FR-55 | Results feed mastery and growth | §9 |

### 3.7 Mastery, Growth, Recommendations
| ID | Requirement | PRD |
|---|---|---|
| FR-60 | Per-concept mastery estimate evolving with evidence | §10 |
| FR-61 | Growth analysis over time: improving / stable / requiring attention | §10 |
| FR-62 | Recommendations from weaknesses, mistakes, goals, activity, history, materials, prior recommendations | §10 |
| FR-63 | Persistent learning context (goals, preferences, strengths, weaknesses, history, Tutor notes, mistakes) | §11 |
| FR-64 | Retrieve only context relevant to the current task | §11 |

### 3.8 Analytics & Events
| ID | Requirement | PRD |
|---|---|---|
| FR-70 | Emit learning events (project creation, upload/processing, Tutor interactions, quiz attempts, answers, assessments, mastery updates, recommendations, activity) | §12 |
| FR-71 | Project analytics: activity, performance, mastery, concept trends, AI activity | §12 |
| FR-72 | Global analytics across Projects/Spaces | §12 |
| FR-73 | Events trigger downstream workflows (quiz → evaluation → mastery → weakness → recommendation) | §12, §13 |
| FR-74 | Event processing with retries, duplicate handling, idempotency | §12 |

### 3.9 AI Engineering & Observability
| ID | Requirement | PRD |
|---|---|---|
| FR-80 | Abstract generation, structured generation, embeddings/retrieval, evaluation, document understanding behind provider-neutral interfaces | §14 |
| FR-81 | Track model, feature, latency, tokens, estimated cost, success/failure per AI request | §14 |
| FR-82 | Support investigation: why slow, which model, why poor retrieval, which workflow failed, what it cost, why processing failed | §14 |
| FR-83 | Evaluate Tutor, Retrieval, Assessment, Recommendations on named metrics | §14 |
| FR-84 | Prompt/model/retrieval changes can regress quality → regression evaluation | §14, §18 |

### 3.10 Admin
| ID | Requirement | PRD |
|---|---|---|
| FR-90 | Admin view: users, spaces, projects, activity, engagement, learning analytics, AI usage, AI evaluation, background processing, system health | §16 |
| FR-91 | Inspect an individual user's learning journey | §16 |
| FR-92 | Filter platform activity by user, space, project, type, period | §16 |

---

## 4. Non-Functional Requirements

| ID | Requirement | PRD | Engineering response (planned, not yet built) |
|---|---|---|---|
| NFR-01 | Graceful handling of AI timeouts, provider failures, processing failures, retrieval failures, DB errors, invalid AI output, rate limits, job failures | §15 | Failure-mode matrix per dependency; timeouts, bounded retries, circuit breakers, fallbacks, DLQ; documented degraded modes |
| NFR-02 | Retryable operations must not create duplicate state | §12, §15 | Idempotency keys on mutating endpoints; job dedup keys; consumer-side dedup; natural unique constraints |
| NFR-03 | Per-user and per-project data isolation, including retrieval and background jobs | §15 | Multi-layer isolation (route guard + repository scoping + DB-level enforcement + in-query filters); dedicated isolation test suite |
| NFR-04 | Authentication, authorization, input validation, secure APIs, secure document handling, AI-specific security | §15 | Security architecture documented in principles doc; threat-driven controls |
| NFR-05 | Learner materials and messages are data, never trusted instructions | §15 | Structural data/instruction separation; tool allow-lists; server-injected scope; output validation |
| NFR-06 | Prototype-appropriate performance: streaming, efficient retrieval, pagination, caching, async work, efficient analytics, avoid unnecessary AI calls | §15 | Streaming; precomputed aggregates; caching only where stale-tolerant; deterministic logic avoids model calls |
| NFR-07 | Secrets separated from source, never committed | §18 | Env-based config with startup validation; `.env.example` only; secret scanning in CI |
| NFR-08 | Meaningful tests over exhaustive coverage, in named areas | §18 | Unit (pure logic), integration, isolation, AI-behavioural golden sets, E2E loop; coverage deliberately unequal |
| NFR-09 | Publicly deployed, working end-to-end | §18 | Deployment is first-class from day 1; containerized, externally configured |
| NFR-10 | Architecture documentation and engineering decision records | §18–20 | This documentation set; ADRs per major decision |

**Unspecified by the PRD:** concurrent user counts, latency SLOs, availability targets, RTO/RPO, retention periods, cost ceilings. These are engineering assumptions, not requirements — see `assumptions.md` (A-10…A-14). **No benchmark figures are fabricated anywhere in the planning artifacts.**

---

## 5. AI Requirements

The AI subsystem carries the PRD's highest expectations (§6–§9, §14).

### 5.1 Capability abstraction (FR-80)
- All model interaction behind **provider-neutral interfaces**: generation, structured generation, embeddings/retrieval, evaluation, document understanding.
- Providers/models selected by **role** in configuration, not hard-coded in domain code `[A-07]`.

### 5.2 Grounded Tutor (FR-30…36, §6–§7)
- Project-scoped conversations; understands goal, materials, concepts, prior conversation, assessment history, learning context.
- **Grounding contract:** answers grounded in Project materials with citations naming document + page; every citation resolvable to a real retrieved chunk.
- **Insufficiency contract:** explicit refusal when evidence is insufficient — this is a **core evaluation requirement** (§7), decided structurally *before* generation, with a useful response (what the materials do cover, suggested actions, optional clearly-labelled general-knowledge answer).
- Streaming responses (FR-36); cross-session continuity without sending full history (FR-33).

### 5.3 Structured AI interaction (FR-40…42, §8)
- AI touches application capabilities **only** through controlled, validated, permission-aware interfaces; never the database, never raw SQL.
- Backend validates + authorizes every tool request; AI-generated structured data validated before persistence or state change.
- Authorization is **server-injected** — scope (`user_id`, `project_id`) is never an AI-supplied argument.

### 5.4 Assessment AI (FR-50…55, §9)
- Question generation grounded in project chunks at a requested concept + difficulty.
- Open-ended grading produces structured evaluation (understanding, accuracy, relevance, concepts covered/missing, reasoning) plus explanatory feedback.
- Adaptive selection is **deterministic logic over stored evidence**, not an LLM decision (PRD §9 rejects naive adaptivity).

### 5.5 Knowledge extraction (FR-24, §5)
- From uploaded material: chunks with page anchors, concepts, metadata, relationships, embeddings; extraction is idempotent and versioned (`pipeline_version`).

### 5.6 Observability & evaluation of AI (FR-80…84, §14)
- Per-request record: model, feature, latency, tokens, estimated cost, outcome, prompt version, retrieval metadata.
- Eval suites: **Tutor** (groundedness, citation validity, refusal correctness), **Retrieval** (relevance, source quality), **Assessment** (question/grading quality, structured-output reliability, adaptivity), **Recommendations** (relevance, actionability, alignment).
- Regression evaluation when prompts/models/retrieval change (FR-84).

---

## 6. Security Requirements

| Area | Requirement | PRD |
|---|---|---|
| Authentication | Registration, login, session management (FR-01) | §18 |
| Authorization | Users access only their own data (FR-02); admin visibility scoped to platform reads (FR-03, §16) | §15 |
| Data isolation | Per-user/per-project isolation including retrieval and background jobs (NFR-03) | §15 |
| Input validation | All API input validated; AI output treated as untrusted (FR-42) | §15 |
| Secure document handling | Uploads handled securely; malicious/bomb PDFs must not take down the system | §15 |
| Prompt-injection defence | Materials and user messages are **data, never trusted instructions** (NFR-05) | §15 |
| Secrets | Never in source control (NFR-07) | §18 |
| AI-specific security | No unauthorized AI actions; hallucinated citations blocked; cost abuse bounded | §15, §14 |

Engineering commitments (detailed in `project-principles.md`): authorization is explicit at every entry point; non-owned resources return **404, not 403** (avoid existence disclosure); isolation enforced at multiple layers including the database; AI scope is injected by the server; retrieved content can never trigger a tool call; model output is untrusted until schema-validated.

---

## 7. Background Processing Requirements

| ID | Requirement | PRD |
|---|---|---|
| BP-01 | Async document pipeline: Queued → Processing/OCR → Extraction → Knowledge Extraction → Retrieval representation → Ready (FR-21) | §5 |
| BP-02 | Retry, failure, and duplicate-job handling (FR-26) | §5, §13 |
| BP-03 | Browser may close; job state lives server-side (FR-23) | §13 |
| BP-04 | Events trigger downstream workflows; retries, duplicate handling, idempotency (FR-73, FR-74) | §12, §13 |
| BP-05 | Long-running work never blocks requests ("Asynchronous by Design") | §2 |

**Named async chains:** ingestion (parse → OCR/vision escalation → chunk → concepts → embeddings → ready); post-quiz chain (quiz completed → evaluation → mastery → weakness detection → insight → recommendation); repeated-mistake workflow; analytics rollups; AI eval sampling.

**Engineering response:** a durable event mechanism that commits state + events atomically (no dual-write), at-least-once delivery with consumer-side idempotency, job dedup keys, retry with backoff, dead-letter handling with admin visibility. Queue separation (bulkheads) so ingestion bursts cannot delay the learning loop.

---

## 8. Observability & Evaluation Requirements

### 8.1 Observability (FR-81, FR-82)
- Structured logs, metrics, traces with one correlation id propagated across HTTP → background jobs → AI calls.
- **The AI question list (FR-82)** — the system must answer: why was an AI response slow? which model was used? why was retrieval poor? which workflow failed? what did a request cost? why did processing fail?
- Every AI call recorded: model, feature, latency, tokens, estimated cost, outcome (`ai_requests`-style spine).

### 8.2 Evaluation (FR-83, FR-84)
| Suite | Metrics (PRD §14) |
|---|---|
| Tutor | Accuracy, groundedness, citation correctness, unsupported-question handling |
| Retrieval | Relevance, source quality |
| Assessment | Question quality, grading quality, structured-output reliability, adaptivity |
| Recommendations | Relevance, actionability, alignment |

- Regression evaluation on prompt/model/retrieval changes (FR-84) — evaluation is part of the feature, not a side project.

---

## 9. MoSCoW Classification

**Method note:** The PRD states Must/Should/Nice priorities (§18) but the baseline does not enumerate them item-by-item; the classification below is derived from the PRD's §18 phrasing plus each FR's section context, and flags where a call is judgment. It is intended for review, not as an authoritative re-statement.

### 9.1 MUST HAVE (prototype is incomplete without these)
| ID | Requirement | Basis |
|---|---|---|
| FR-01 | Registration, login, session management | §18 explicitly Must |
| FR-02 | Users access only their own data | §15 core isolation |
| FR-03 | Admin role + platform visibility | §16 (§18 Must: "admin plane") |
| FR-10/11/12/13/14 | Spaces, Projects, dashboards, navigation | §4 core structure; §19 demo loop |
| FR-15 | Home dashboard | §16 |
| FR-20/21/23 | PDF upload, async pipeline, user-visible status | §18 Must: "document upload with status" |
| FR-24/25 | Chunks/concepts/embeddings with page-traceable retrieval | §5; grounding depends on it |
| FR-26 | Retry/failure/duplicate handling in ingestion | §5, §13 |
| FR-30/31/32/33 | Project-scoped Tutor with full context inputs, follow-ups, cross-session continuity | §6 core Tutor |
| FR-34 | Grounded answers + citations (document, page) | §7 "core evaluation requirement" |
| FR-35 | Explicit insufficiency handling | §7 "core evaluation requirement" |
| FR-40/41/42 | Controlled AI–application interaction, validated, authorized | §8 core |
| FR-50/51/53/54/55 | Adaptive quiz, both question types, AI grading, explanatory feedback, feeds mastery | §9 core |
| FR-52 | Adaptive selection beyond naive adaptivity | §9 explicitly rejects naive |
| FR-60/61/62 | Mastery evolving with evidence, growth trends, recommendations | §10 core |
| FR-63/64 | Persistent, relevant-only learning context | §11 |
| FR-70/71/72 | Events; project + global analytics | §12 core |
| FR-73/74 | Event-driven workflows with idempotency | §12, §13 |
| FR-80/81 | Provider-neutral abstraction; per-call AI telemetry | §14 core |
| FR-82 | AI investigation questions answerable | §14 |
| FR-83/84 | Eval suites + regression evaluation | §14; §18 Must: "AI evaluation" |
| FR-90/91/92 | Admin views incl. single-user journey + activity filters | §16 |
| NFR-02/03/04/05/07/09 | Idempotency, isolation, security, injection defence, secrets, deployed | §15, §18 |
| BP-01…BP-05 | Async processing chains with idempotency | §5, §12, §13, §2 |

### 9.2 SHOULD HAVE
| ID | Requirement | Basis |
|---|---|---|
| FR-36 | Streaming Tutor responses | §18 Should; §15 streaming |
| FR-22 | Full robustness: tables, images, diagrams, scanned pages | §5 (PDF required, robustness implied); prototype may degrade gracefully per-page with OCR/vision escalation — judged SHOULD with a Must floor: native text PDFs must work |
| FR-72 | Global analytics | §12 (project analytics is the Must core; global is the lighter layer) — **judgment call, review** |
| NFR-01 | Graceful failure for *every* named failure class | §15 — designed now, validated incrementally in the window |
| NFR-06 | Full performance posture | §15 "appropriate for a prototype" |

### 9.3 NICE TO HAVE
| ID | Requirement | Basis |
|---|---|---|
| — | Flashcards/spaced repetition, concept maps, learning plans, multi-modal material, voice tutoring, notifications, collaboration, multi-tenancy | Not in PRD; architecture must not preclude (§42-style future work) |

**Cut protocol:** if scope pressure forces cuts, Must-Have items map to FR ids so cuts are **conscious and recorded** (risk R-12 style), not silent.

---

## 10. Requirement Traceability Table

Each requirement → the planned component(s) that will satisfy it. Components are the planned modules; none exist yet.

| Requirement(s) | PRD | Planned component(s) | Notes |
|---|---|---|---|
| FR-01, FR-03 | §18, §16 | identity module; admin router | Auth + role model [A-03, A-02] |
| FR-02 | §15 | Route guards + repo scoping + DB-level isolation + isolation test suite | Invariant G1 |
| FR-10–15 | §4, §16 | workspace module; home/dashboard read models (rollups) | |
| FR-20–23 | §5 | materials module + document worker queue | Presigned direct upload [A-18] |
| FR-24, FR-25 | §5 | knowledge module; ingestion pipeline with page-anchored chunks | |
| FR-26, BP-01–05 | §5, §12, §13 | jobs module; durable event mechanism; idempotent consumers | |
| FR-30–33 | §6 | tutor module; context composer | |
| FR-34, FR-35 | §7 | retrieval pipeline (hybrid → fuse → rerank → sufficiency gate); citation validator | Grounding is structural |
| FR-36 | §15, §18 | SSE streaming from tutor module | |
| FR-40–42 | §8 | tools module (capability layer) + schemas | Model has no DB access |
| FR-50–55 | §9 | assessment module; deterministic selection policy; structured grading | ADR-candidate: deterministic adaptivity |
| FR-60–62 | §10 | mastery, growth modules; evidence-derived mastery math | |
| FR-63, FR-64 | §11 | learning context store + context composer (budgeted selection) | |
| FR-70–74 | §12, §13 | analytics module; event catalogue; outbox-style durability | |
| FR-80, FR-81 | §14 | ai gateway module (single egress + metering) | |
| FR-82 | §14 | Correlation ids across request → job → AI call; `ai_requests`-style store | |
| FR-83, FR-84 | §14 | ai evaluation module; golden sets; CI regression gate | |
| FR-90–92 | §16 | admin module (read-only) | [A-01, A-05] |
| NFR-01 | §15 | Failure-mode matrix; timeouts/retries/circuits/fallbacks/DLQ | Should-have completeness in window |
| NFR-02 | §12, §15 | Idempotency keys; dedup keys; consumer dedup; unique constraints | |
| NFR-03 | §15 | 4-layer isolation + dedicated test suite | |
| NFR-04, NFR-05 | §15 | Security controls incl. structural injection defence | |
| NFR-06 | §15 | Streaming, rollups, caching, batching, small-model routing | |
| NFR-07 | §18 | Env config, startup validation, secret scanning | |
| NFR-08 | §18 | Test strategy by layer | |
| NFR-09 | §18 | Containers + platform deploy | [A-13] |
| NFR-10 | §18–20 | This doc set + ADRs + submission docs | |

---

## 11. Bounded Modules (planned)

Dependency rule: `platform` ← everything; domain modules interact **only via service facades** (never each other's models/repositories), enforced later by import-linting in CI.

| Module | Responsibility | Explicitly not responsible for |
|---|---|---|
| `identity` | Auth, users, sessions, roles | Business authorization of other modules |
| `workspace` | Spaces, Projects, dashboards | Any AI call |
| `materials` | Upload, document lifecycle, status | Parsing (worker's job) |
| `knowledge` | Chunks, concepts, embeddings, retrieval, fusion, rerank, sufficiency | Prompt construction |
| `tutor` | Conversations, context composition, grounded answering, citations, streaming | Retrieval internals, model selection |
| `assessment` | Quizzes, adaptive selection, generation orchestration, MCQ scoring, grading orchestration | Mastery math |
| `mastery` | Mastery state + events + update math | Deciding what to ask next |
| `growth` | Trends, weakness detection, recommendations | Rendering |
| `analytics` | Event ingestion, rollups, queries | Being the event source of truth |
| `admin` | Read-only platform read models | Mutating learner data |
| `ai` | AI Gateway: providers, prompts, structured output, eval, cost | Business decisions |
| `tools` | Tool registry, schemas, authorization, execution, audit | Model reasoning |
| `jobs` | Task definitions, event relay, scheduling | Business logic |
| `platform` | Config, db, cache, storage, errors, logging, tracing, security | Domain logic |

---

## 12. Major Entities & Relationships

Planned domain model (no DDL yet — conceptual only).

- **User** —1..*→ **Space** —1..*→ **Project** (Project carries learning goal; owner denormalized for isolation predicates)
- **Project** —1..*→ **Material** —1..*→ **MaterialPage** (page text, extraction method, page image key)
- **Material** —1..*→ **Chunk** (content, token count, **page_start/page_end**, section path, content type, pipeline version) —1..1→ **ChunkEmbedding** (model-stamped)
- **Project** —1..*→ **Concept**; **Chunk** *..*→ **Concept** (mentions, relevance); **Concept** —→ **ConceptLink** (prerequisite_of / related_to / part_of)
- **Project** —1..*→ **Conversation** —1..*→ **Message** —1..*→ **MessageCitation** (→ Chunk, page, marker) — grounding provenance
- **Project** —1..*→ **Quiz** —1..*→ **Question** (type, difficulty, options/rubric, source chunk ids) —1..*→ **Answer** (evaluation JSON, feedback, graded_by)
- **(Project, Concept)** —→ **ConceptMastery** (estimate, confidence, evidence count); **Answer/MasteryEvent** —→ **MasteryEvent** (append-only evidence trail; uniqueness for idempotency)
- **(Project, Concept, window)** —→ **GrowthSnapshot** (trend classification)
- **Project** —1..*→ **Recommendation** (kind, rationale, targets, dedup key, status)
- **Project** —1..*→ **LearningContextItem** (kind, content, salience, source, expiry)
- **User/Project** —→ **ActivityEvent** (append-only, time-partition-able)
- **AIRequest** (feature, operation, provider, model, prompt version, tokens, cost, latency, status, retrieval meta) —1..*→ **AIEvaluation**
- **AIRequest** —1..*→ **ToolInvocation** (tool, arguments, authorized, outcome) — audit trail
- **OutboxEvent**, **ProcessedEvent**, **JobRun** — reliability infrastructure
- **AuditLog** — security evidence, separate from product telemetry

**Key relational intents** (to honour when designing schema later): unique `(project_id, checksum)` on materials (duplicate upload); unique `(project_id, normalized_name)` on concepts (idempotent extraction); unique `(source, source_id, concept_id)` on mastery events (retry-safe); one answer per question (idempotent submit); partial-unique active recommendations by dedup key; partial-unique queued/running jobs by dedup key.

---

## 13. External Dependencies & Services

| Dependency | Purpose | Notes |
|---|---|---|
| LLM provider(s) | Tutor answering, question generation, open-ended grading, recommendation phrasing, concept extraction | Role-based config; primary + fallback [A-07] |
| Embedding provider | Chunk + query embeddings | Fixed dimension pinned in schema; model stamped per row |
| Rerank provider | Top-k precision for trustworthy citations | Fallback: fused order + raised sufficiency threshold |
| OCR / vision | Scanned pages, diagrams, complex tables | Tesseract-class first pass, model escalation [A-19] |
| Object storage (S3-compatible) | Source PDFs, page images | Private, presigned direct transfer; MinIO locally |
| Secrets manager / platform env injection | Secrets at runtime | Never in repo |
| Error tracking (Sentry-class) | Exception aggregation | Fire-and-forget |
| Telemetry backend (OTLP → Grafana/Sentry-class) | Traces, metrics, logs | Vendor-neutral instrumentation |
| Relational DB (+ vector + FTS extensions) | System of record | Engine choice pending ADR — see architecture-decisions.md |
| Cache / broker / rate-limit store | Cache, idempotency, rate limits, queue broker, stream fan-out | Component choice pending ADR |
| Background task framework | Async pipelines, retries, scheduling | Choice pending ADR |
| Email provider *(Phase 1)* | Verification, password reset | Stubbed in Phase 0 [A-04] |

---

## 14. Architectural Constraints

1. **3–4 day prototype window** (§1, §18) — managed services over self-hosted; monorepo; one database engine; no Kubernetes in Phase 0 `[A-13]`.
2. **Publicly deployed and working end-to-end** (§18) — deployment is a first-class deliverable, not an afterthought.
3. **Secrets never in the repository** (§18).
4. **Technology choices must be justified** (§17, §19) — every dependency carries a reason and a rejected alternative.
5. **Evaluation rewards engineering reasoning over technology popularity** (§19) — deliberately boring components; novelty spent only where it buys something.
6. **Isolation is an invariant, not a feature** (§15) — enforced at multiple layers; dedicated test gate.
7. **Grounding is an invariant** (§7) — structural sufficiency gating + citation validation, not prompt-hope.
8. **Model output is untrusted input** (§8, §15) — schema-validated before state changes.
9. **Asynchronous by design** (§2, §13) — nothing slow on the user's path; durability via atomic state+event commit.
10. **Deterministic business logic where possible** (§9) — mastery math, adaptive selection, scoring are code; LLMs handle language, not arithmetic.

---

## 15. Key Risks (analysis-stage view)

| Risk | Impact | Mitigation direction |
|---|---|---|
| Retrieval quality poor on real documents → grounding claim fails | Core product claim | Structure-aware chunking with page anchors; hybrid retrieval + rerank; OCR/vision escalation; sufficiency gate; retrieval eval set |
| Model/prompt changes silently regress quality | Core quality | Prompt/model versioning per request; golden-set regression gate; online sampling |
| AI cost runs away | Budget | Context budgets, max tokens, per-user budgets, small-model routing, cost anomaly alert |
| Prompt injection via uploaded material | Security | Structural controls (server-injected scope, allow-lists, data/instruction separation, bounded loop, audit) |
| Cross-project leakage via a missed filter | Critical | Multi-layer isolation + dedicated test suite + post-retrieval assertion |
| Scope pressure in the 3–4 day window → skipped tests / hardcoded secrets | High | CI gates that cannot be skipped; conscious-cut protocol (§9.1 note) |
| Modular monolith erodes into mud | Maintainability | Facade-only access, import-linting, per-module table ownership |
| Mastery/grading misleads learner | Trust | Estimates with confidence signals; rubric-based grading at temperature 0; low-confidence flagging; agreement measured |

---

## 16. Required Final Submission Artifacts (PRD §20)

To be produced alongside implementation (listed now so nothing is discovered late):

1. **README** — overview, quickstart, demo credentials, live URL.
2. **Architecture documentation** (this set + ADRs).
3. **AI usage documentation** — AI used to *build* vs AI used *by* the product (PRD §20.5).
4. **Development prompts log** — prompts materially used with AI dev tools (PRD §20.6).
5. **Evaluation documentation** — approach, suites, baselines, results (PRD §20.7).
6. **Limitations** — known limitations (PRD §20.8).
7. **Future improvements** (PRD §20.9).

Plus a **publicly deployed, working end-to-end** instance (§18) and demo credentials for reviewers.

---

## 17. Open Points for Review

1. Confirm the MoSCoW calls flagged as judgment (§9.2): global analytics, streaming, and the Must floor for document robustness.
2. Confirm the 4-layer isolation posture (guard + repository + DB RLS + in-query filter) before schema work begins.
3. Confirm the adaptive-selection policy is deterministic code (ADR-candidate) — it shapes the assessment module's interface.
4. Confirm refusal path design: pre-generation sufficiency gate + post-generation citation validation as the grounding contract.
5. Approve assumptions A-01…A-19 or amend — especially A-01 (read-only admin), A-03 (auth approach), A-07 (role-based providers), A-16 (single learner per project).
