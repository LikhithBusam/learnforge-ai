# System Architecture

**Project:** AI Study Companion — AI-Powered Learning & Growth Workspace
**Source of truth:** Product Requirements Document v3.0 (Candidate Challenge Edition)
**Document status:** Architecture baseline, ready for implementation review
**Audience:** Engineering team, technical reviewers, senior/principal engineers

> **Reading note on scope.** The PRD targets a **3–4 day prototype** (§1, §18) while explicitly asking for *architectural judgment* and an architecture that a real system could grow into. This document therefore defines the **production-target architecture** and, for every component, marks what is **built in the prototype window (Phase 0)** versus what is **deferred to Phase 1/2** with an explicit trigger. Designing an architecture that cannot be built in four days would be a failure of judgment, not a display of it; so would designing one that collapses the moment a second user arrives. Every deferral is stated, never silently assumed.
>
> All statements that do not trace back to the PRD are labelled **[ASSUMPTION]** and carry a justification. Section 39 consolidates every assumption in one table.

---

## 1. Executive Summary

AI Study Companion is a **context-scoped, evidence-grounded learning workspace**. A user creates a Space (broad area) and a Project (focused learning journey), uploads material, learns with an AI Tutor that answers *only* from that Project's evidence, is assessed adaptively, and receives mastery estimates, growth analysis, and a recommended next action. An admin plane gives platform-level visibility into users, learning activity, AI usage, AI quality, and system health.

The architecture is a **modular monolith with an asynchronous worker plane**:

- One **FastAPI** application, internally partitioned into strictly-bounded modules (`identity`, `workspace`, `materials`, `knowledge`, `tutor`, `assessment`, `mastery`, `growth`, `analytics`, `admin`, `ai`, `jobs`) that communicate through typed service interfaces and domain events — never by reaching into each other's tables.
- A **Celery worker fleet** on dedicated queues handling document ingestion, quiz evaluation, mastery recomputation, recommendation generation, and analytics rollups. Long-running work never blocks a request (PRD §2 "Asynchronous by Design", §13).
- **PostgreSQL 16 as the single system of record**, carrying relational data, full-text search (`tsvector`), and vector embeddings (`pgvector`) — one database, three access patterns, one transaction boundary, one backup story. Multi-tenant isolation is enforced twice: in the application, and in the database via **Row-Level Security**.
- **Redis** for cache, rate limiting, idempotency keys, SSE fan-out, and as the Celery broker.
- **S3-compatible object storage** for uploaded PDFs, with presigned direct upload and private-by-default buckets.
- An **AI Gateway** module that is the only code path to any model provider. Every generation, embedding, rerank, and evaluation call passes through it and is recorded with model, feature, latency, tokens, cost, and outcome (PRD §14).
- An **Application Capability Layer** (tool layer): the AI never touches the database. It emits schema-validated tool requests that are authorized, scoped to the caller's project, executed by ordinary domain services, and audited (PRD §8).

The two hardest requirements — **grounded answers with citations plus honest refusal** (PRD §7, "a core evaluation requirement") and **project-level data isolation** (PRD §3, §15) — are treated as architectural invariants rather than features, and are enforced at multiple layers each (Sections 18, 12, 21, 22).

**Why a modular monolith:** one small team, a four-day first delivery, domain boundaries that are still hypotheses, and a workload whose only genuinely independent scaling axis is *background AI work* — which is already split out as a separate deployable worker process. Microservices would add distributed transactions, network failure modes, and deployment overhead in exchange for nothing the workload currently demands. Section 38, ADR-001 records this decision, its alternatives, and the concrete traffic/organizational triggers that would justify revisiting it.

---

## 2. Project Context

### 2.1 What the product is

A learning workspace that continuously answers three questions (PRD §2):

| Question | System answers it with |
|---|---|
| What am I learning? | Spaces, Projects, goals, materials, extracted concepts, conversations |
| How well am I learning it? | Quizzes, open-ended assessments, mistakes, Tutor interactions, mastery estimates |
| What should I do next? | Growth analysis over mastery history, weaknesses, goals, recent activity → recommendations |

### 2.2 Product principles and their architectural consequences

The PRD's principles are not decoration; each one constrains the design.

| PRD principle (§2) | Architectural consequence |
|---|---|
| **Context First** — unrelated Projects must not influence an answer | `project_id` is a mandatory column on every content table, a mandatory field in every retrieval filter, a mandatory element of the tool-execution context, and an RLS predicate. Cross-project leakage is a P1 security incident, not a relevance bug. |
| **Evidence Over Guessing** | Retrieval returns an evidence set with a sufficiency score; below threshold the Tutor takes the refusal path. A post-generation citation validator rejects answers citing chunks that were not retrieved. |
| **Persistent but Relevant Context** | No "send the whole history" design. A Context Composer selects from four context sources under a token budget; conversation history is summarized on a rolling window, and durable learner facts live in a structured `learning_context_items` table, not in a chat log. |
| **Asynchronous by Design** | Transactional Outbox + Celery. The request path does only what the user must wait for. |
| **Observable AI** | The AI Gateway is a mandatory chokepoint; every call is traced (OpenTelemetry) and recorded (`ai_requests`). |
| **Safe AI Interaction** | Tool layer with JSON-Schema validation, per-tool authorization, project-scoped execution, and audit logging. No raw SQL, no internal service access from a model. |

### 2.3 Constraints

| Constraint | Source | Impact |
|---|---|---|
| 3–4 day prototype build | PRD §1 | Managed services over self-hosted; single repo; one database engine; no Kubernetes in Phase 0 |
| Must be publicly deployed and working end-to-end | PRD §18 | Deployment is a first-class concern from day 1, not an afterthought |
| Secrets never in the repository | PRD §18 | Secrets manager / platform env injection; `.env.example` only in Git |
| Technology stack intentionally open; choices must be *justified* | PRD §17, §19 | Every technology in Section 37 carries a reason and a rejected alternative |
| Evaluation focuses on engineering reasoning, not technology popularity | PRD §19 | Deliberately boring, well-understood components; novelty spent only where it buys something |

### 2.4 Out of scope

Billing, subscriptions, multi-organization tenancy, collaboration/sharing between users, mobile native apps, content marketplaces, and proctoring. None appear in the PRD. Section 42 lists which of these the architecture leaves room for.

---

## 3. Requirements Analysis

### 3.1 Functional Requirements

Traceability IDs (FR-*) are referenced throughout the document.

#### Identity & Access

| ID | Requirement | PRD ref |
|---|---|---|
| FR-01 | User registration, login, session management | §18 Must Have |
| FR-02 | Users access only their own Spaces and Projects | §15 |
| FR-03 | Administrator role with platform-level visibility | §16 |

#### Workspace

| ID | Requirement | PRD ref |
|---|---|---|
| FR-10 | Create/read/update/delete Spaces (name, description, optional visual customization) | §4 |
| FR-11 | Space dashboard: projects, activity, progress, areas requiring attention | §4 |
| FR-12 | Create Projects within a Space (name, description, learning goal) | §4 |
| FR-13 | Project dashboard: progress, important concepts, recent activity, performance, latest activity, recommended next step | §4 |
| FR-14 | Navigation Materials → Tutor → Quiz → Growth → Analytics | §4 |
| FR-15 | Home dashboard: Continue Learning, recent projects, overall progress, attention areas, recommended next action | §16 |

#### Materials & Knowledge

| ID | Requirement | PRD ref |
|---|---|---|
| FR-20 | Upload learning material to a Project; PDF required | §5 |
| FR-21 | Asynchronous processing pipeline: Queued → Processing/OCR → Extraction → Knowledge Extraction → Retrieval representation → Ready | §5 |
| FR-22 | Handle text, tables, images, diagrams, scanned pages | §5 |
| FR-23 | User-visible document status (queued / processing / ready / failed) | §5 |
| FR-24 | Produce chunks, concepts, metadata, relationships, page references, embeddings | §5 |
| FR-25 | Retrieved information must be traceable to its source | §5 |
| FR-26 | Background processing with retry, failure, and duplicate-job handling | §5, §13 |

#### AI Tutor

| ID | Requirement | PRD ref |
|---|---|---|
| FR-30 | Project-scoped conversational Tutor | §6 |
| FR-31 | Tutor understands goal, materials, concepts, prior conversation, assessment history, learning context | §6 |
| FR-32 | Follow-ups, simpler explanations, examples, concept exploration, revision guidance | §6 |
| FR-33 | Cross-session continuity without sending full history per request | §6 |
| FR-34 | Answers grounded in Project materials, with citations naming document and page | §7 |
| FR-35 | Explicit insufficient-evidence handling instead of fabrication | §7 |
| FR-36 | Streaming Tutor responses | §15, §18 Should Have |

#### AI / Application Interaction

| ID | Requirement | PRD ref |
|---|---|---|
| FR-40 | AI accesses application capabilities only through controlled, validated, permission-aware interfaces | §8 |
| FR-41 | Backend validation + authorization before any tool execution | §8 |
| FR-42 | AI-generated structured data validated before persistence or state change | §8 |

#### Assessment

| ID | Requirement | PRD ref |
|---|---|---|
| FR-50 | Adaptive quiz over project material and learning state | §9 |
| FR-51 | Multiple-choice and open-ended question types | §9 |
| FR-52 | Selection considers concepts, mastery, prior mistakes, recent performance, difficulty, question history, recent activity — not naive wrong→easy/correct→hard | §9 |
| FR-53 | AI evaluation of open-ended answers: understanding, accuracy, relevance, concepts covered, concepts missing, reasoning | §9 |
| FR-54 | Explanatory feedback, not a bare score | §9 |
| FR-55 | Results feed mastery and growth | §9 |

#### Mastery, Growth, Recommendations

| ID | Requirement | PRD ref |
|---|---|---|
| FR-60 | Per-concept mastery estimate that evolves with evidence | §10 |
| FR-61 | Growth analysis over time: improving / stable / requiring attention | §10 |
| FR-62 | Actionable recommendations from weaknesses, mistakes, goals, activity, assessment history, materials, prior recommendations | §10 |
| FR-63 | Persistent learning context: goals, preferences, strengths, weaknesses, history, significant Tutor context, assessment history, repeated mistakes | §11 |
| FR-64 | Retrieve only context relevant to the current task | §11 |

#### Analytics & Events

| ID | Requirement | PRD ref |
|---|---|---|
| FR-70 | Emit learning events (project creation, upload/processing, Tutor interactions, quiz attempts, answers, assessments, mastery updates, recommendations, activity) | §12 |
| FR-71 | Project analytics: activity, assessment performance, mastery, concept trends, AI activity | §12 |
| FR-72 | Global analytics across Projects and Spaces | §12 |
| FR-73 | Events trigger downstream workflows (e.g. quiz completion → evaluation → mastery → weakness detection → recommendation) | §12, §13 |
| FR-74 | Event processing with retries, duplicate handling, idempotency | §12 |

#### AI Engineering & Observability

| ID | Requirement | PRD ref |
|---|---|---|
| FR-80 | Abstract text generation, structured generation, embeddings/retrieval, evaluation, document understanding behind provider-neutral interfaces | §14 |
| FR-81 | Track model, feature, latency, tokens, estimated cost, success/failure per AI request | §14 |
| FR-82 | Support investigation: why slow, which model, why poor retrieval, which workflow failed, what it cost, why processing failed | §14 |
| FR-83 | Evaluate Tutor (accuracy, groundedness, citation correctness, unsupported-question handling), Retrieval (relevance, source quality), Assessment (question/grading quality, structured-output reliability, adaptivity), Recommendations (relevance, actionability, alignment) | §14 |
| FR-84 | Awareness that prompt/model/retrieval changes cause regressions → regression evaluation | §14, §18 |

#### Admin

| ID | Requirement | PRD ref |
|---|---|---|
| FR-90 | Admin view of users, spaces, projects, activity, engagement, learning analytics, AI usage, AI evaluation, background processing, system health | §16 |
| FR-91 | Inspect an individual user's learning journey | §16 |
| FR-92 | Filter platform activity by user, space, project, activity type, time period | §16 |

### 3.2 Non-Functional Requirements

| ID | Requirement | PRD ref | Architectural response |
|---|---|---|---|
| NFR-01 | Graceful handling of AI timeouts, provider failures, document-processing failures, retrieval failures, DB errors, invalid AI output, rate limits, job failures | §15 | Section 25 (timeouts, retries, circuit breakers, fallback chains, DLQ, degradation matrix) |
| NFR-02 | Retryable operations must not create duplicate state | §12, §15 | Idempotency keys on mutating endpoints; unique job dedup keys; outbox consumer dedup table; `ON CONFLICT DO NOTHING` upserts |
| NFR-03 | Per-user and per-project data isolation, including in retrieval and background jobs | §15 | Postgres RLS + app-level scoping + job ownership context + retrieval filter (Section 12.4) |
| NFR-04 | Authentication, authorization, input validation, secure APIs, secure document handling, AI-specific security | §15 | Section 21 |
| NFR-05 | Learner materials and messages are data, never trusted instructions | §15 | Prompt-injection defence: structural separation, spotlighting, tool allow-listing, no tool invocation triggered by retrieved content, output validation (Section 21.7) |
| NFR-06 | Prototype-appropriate performance: streaming, efficient retrieval, pagination, caching, async work, efficient analytics, avoid unnecessary AI calls | §15 | Section 23 |
| NFR-07 | Secrets separated from source; never committed | §18 | Section 31 |
| NFR-08 | Meaningful tests over exhaustive coverage, in named areas | §18 | Section 30.3 |
| NFR-09 | Publicly deployed, working end-to-end | §18 | Sections 28–29 |
| NFR-10 | Architecture documentation and engineering decision records | §18, §19, §20 | This document; Section 38 |

**Not specified in the PRD:** concurrent user counts, latency SLOs, availability targets, RTO/RPO, data retention periods, cost ceilings. These are all supplied as clearly-labelled assumptions in Sections 23, 36, and 39. No benchmark figures are fabricated — targets are stated as targets, with the measurement method that would validate them.

### 3.3 User Roles

| Role | Capabilities | Enforcement |
|---|---|---|
| **Learner** (default) | Full CRUD on own Spaces/Projects/Materials; Tutor; Quiz; own analytics; own recommendations | JWT claim `role=learner`; ownership predicate on every resource; RLS |
| **Admin** | Read-only platform visibility: users, spaces, projects, activity, engagement, learning analytics, AI usage, AI evaluation, job health, system health; inspect a single user's journey | JWT claim `role=admin`; separate `/api/v1/admin/*` router with an admin dependency; every admin read written to `audit_log` |
| **System / Worker** *(internal)* | Background jobs acting on behalf of a user, carrying that user's ownership context | Signed internal job context, not a login; RLS session variable set per task (Section 12.5) |

> **[ASSUMPTION A-01]** Admin is **read-only** over learner content. The PRD says administrators "inspect" and describes the dashboard as "a lightweight operational and product analytics interface" (§16) — inspection, not mutation. *Why it matters:* a read-only admin plane removes an entire class of privilege-escalation and accidental-destruction risk, and lets admin queries be routed to a read replica later. *Alternative:* an admin with suspend/delete powers; deferred until an actual moderation requirement exists, and it would require a second approval step plus mandatory audit reason codes.

> **[ASSUMPTION A-02]** Admin role is assigned out-of-band (seeded/migration-set), not self-service. *Why:* the PRD names "authorized administrators" but no promotion flow; self-service admin would be a vulnerability. *Alternative:* an invitation flow, Phase 1.

### 3.4 Key Workflows

The PRD defines six workflows that drive the design. Full sequence diagrams are in Section 34.

1. **Core learning loop** (§1, §19): Space → Project → Material → Knowledge → Tutor → Grounded answer + citation → Unsupported-question handling → Adaptive Quiz → Assessment → Mastery → Growth → Analytics → Recommendation → Continue.
2. **Material ingestion** (§5, §13): Upload → Queued → Processing/OCR → Content & structure extraction → Knowledge extraction → Retrieval representation → Ready (or Failed, with reason).
3. **Grounded Tutor turn** (§6, §7): Question → Intent understanding → Project context → Evidence retrieval → Sufficiency decision → Answer + citation **or** explicit insufficiency.
4. **Adaptive quiz** (§9): Start → Read mastery → Select concept/difficulty → Generate question → Answer → Evaluate → Update mastery → Select next.
5. **Post-quiz learning workflow** (§12, §13): Quiz completed → Evaluate → Update mastery → Detect weakness → Generate insight → Recommend next action → Analytics.
6. **Repeated-mistake workflow** (§13): Repeated mistake → Identify pattern → Update learning context → Generate targeted recommendation.

---

## 4. Architecture Goals

Ordered by priority. When two goals conflict, the higher one wins, and Section 26 records the trade-off.

| # | Goal | Success test |
|---|---|---|
| **G1** | **Correct isolation.** A user's data, retrieval, and AI context never cross a project or user boundary. | Automated test suite attempts cross-project retrieval, cross-user API access, and cross-project tool invocation; all denied at both app and DB layers. |
| **G2** | **Grounded, honest AI.** Answers cite real retrieved sources; insufficient evidence produces an explicit refusal. | Eval set of answerable + unanswerable questions; groundedness and refusal-correctness measured, gated in CI. |
| **G3** | **The user is never blocked by slow work.** | Upload returns in <1s with a job id; browser can be closed; Tutor streams first token quickly. |
| **G4** | **AI is debuggable.** Any AI interaction can be reconstructed: inputs, retrieval set, model, latency, tokens, cost, outcome. | Given a `request_id` from the UI, an engineer retrieves the full trace and the exact retrieved chunk ids. |
| **G5** | **Safe failure.** Every external dependency can fail without taking down the product. | Chaos checklist (Section 35) — each row has a defined degraded behaviour. |
| **G6** | **Implementable by a small team, fast.** | Phase 0 buildable in the prototype window by one engineer with AI assistance. |
| **G7** | **Evolvable.** Module seams are extraction points, not rewrites. | Any module can be pulled into a service by replacing its facade with an HTTP/gRPC client. |
| **G8** | **Cost-aware.** AI spend is measured per feature and per user, and bounded. | `ai_requests` cost rollups in admin dashboard; per-user daily budget enforced. |

---

## 5. Architecture Principles

1. **Modules over services until the pain is real.** Enforce boundaries in code review and import linting; pay distribution costs only when a boundary demands independent scaling or ownership.
2. **The database is the system of record; everything else is derived.** Caches, search indexes, embeddings, and analytics rollups are rebuildable from Postgres and object storage.
3. **Isolation is enforced twice.** Application scoping can be forgotten in one query; RLS cannot. Defence in depth for the one invariant the product cannot violate.
4. **The AI is a component, not a layer of magic.** It sits behind one interface, is measured like any dependency, has timeouts, fallbacks, and a budget, and never holds privileges.
5. **Model output is untrusted input.** Validate with a schema before it touches state; validate citations before they reach the user.
6. **Retrieved content is data, never instruction.** Structural separation is a hard rule, not a prompt request.
7. **Synchronous only when the user is waiting for the result.** Everything else goes through the outbox to a worker.
8. **Idempotency is designed in, not retrofitted.** Anything retried has a natural or supplied key.
9. **Deterministic logic stays deterministic.** Mastery math, adaptive selection, and analytics are code, not prompts — LLMs are used for language understanding and generation, not arithmetic.
10. **Observability is part of the feature.** A feature without logs, metrics, traces, and an evaluation hook is unfinished.
11. **Boring technology, deliberately chosen.** Each component must justify its operational cost.
12. **Assumptions are written down.** Unstated assumptions are the main source of architecture drift.

---

## 6. High-Level Architecture

### 6.1 Shape of the system

Five planes:

| Plane | Contents | Deployment unit |
|---|---|---|
| **Edge** | CDN, TLS termination, WAF/rate limiting, routing | Managed (platform / CloudFront + ALB) |
| **Application** | Next.js frontend; FastAPI modular monolith (API + business logic + AI gateway + tool layer) | 2 containers, independently scaled |
| **Worker** | Celery workers on partitioned queues + Celery Beat scheduler | 1 container image, N replicas, queue-specific |
| **Data** | PostgreSQL (+ pgvector, + FTS), Redis, S3-compatible object storage | Managed services |
| **External** | LLM providers, embedding provider, rerank provider, OCR/vision, error tracking, metrics backend | Third-party |

### 6.2 Why this shape

- **Frontend and API separate:** the frontend is a static/SSR bundle with a totally different scaling and caching profile from the API. Splitting them costs nothing and buys CDN caching.
- **API and workers separate:** this is the *real* scaling boundary. Document ingestion is CPU-heavy (PDF parsing, OCR) and minutes long; API requests are IO-bound and seconds long. Running them in one process means one 90-second OCR job starving the event loop that is trying to stream a Tutor response. They share the same codebase and image — same domain services, different entrypoint — which keeps the monolith's development speed while getting the isolation that matters.
- **One database engine:** Postgres does relational, full-text, and vector work well enough at this scale that adding a second datastore would buy latency improvements the product cannot yet measure, in exchange for a second consistency model, a second backup story, and a dual-write problem. ADR-003 records the exact trigger for adding a dedicated vector store.
- **Redis is infrastructure glue, not a database:** cache, rate limits, idempotency, SSE pub/sub, Celery broker. Nothing in Redis is a system of record; losing it degrades performance, never correctness (Section 35).

### 6.3 Module map (inside the monolith)

```text
app/
├── identity/      auth, users, sessions, roles
├── workspace/     spaces, projects, dashboards
├── materials/     upload, documents, processing status
├── knowledge/     chunks, concepts, embeddings, retrieval, reranking
├── tutor/         conversations, context composition, grounded answering, citations
├── assessment/    quizzes, question generation, adaptive selection, grading
├── mastery/       mastery state, mastery events, BKT/decay math
├── growth/        trend analysis, weakness detection, recommendations
├── analytics/     event ingestion, rollups, project + global analytics
├── admin/         platform read models, user inspection, system health
├── ai/            AI Gateway: providers, prompts, structured output, eval, cost
├── tools/         Application Capability Layer (tool registry, authz, execution, audit)
├── jobs/          Celery app, task definitions, outbox relay, scheduling
└── platform/      db, cache, storage, config, errors, logging, tracing, security
```

**Dependency rule:** `platform` ← everything. Domain modules may depend on `platform`, `ai`, and each other **only through the target module's `service.py` facade**. No module imports another module's `models.py` or `repository.py`. Enforced by an import-linter configuration in CI (Section 30.2). This one rule is what makes the monolith modular rather than merely large.

---

## 7. Architecture Diagram

### 7.1 High-level system architecture

```mermaid
flowchart TB
    subgraph client["Client Layer"]
        BROWSER["Browser / PWA<br/>Next.js App Router"]
    end

    subgraph edge["Edge Layer"]
        CDN["CDN<br/>static assets, caching"]
        WAF["WAF + TLS + Global Rate Limit"]
        LB["Load Balancer"]
    end

    subgraph app["Application Layer"]
        WEB["Next.js Server<br/>SSR / BFF routes"]
        API["FastAPI Modular Monolith<br/>API + Business Logic"]
        TOOLS["Application Capability Layer<br/>validated, authorized tools"]
        GW["AI Gateway<br/>provider abstraction + metering"]
    end

    subgraph workers["Worker Plane"]
        WDOC["Queue: documents<br/>parse, OCR, chunk, embed"]
        WLEARN["Queue: learning<br/>grade, mastery, weakness, recommend"]
        WANALYTICS["Queue: analytics<br/>rollups, snapshots"]
        WEVAL["Queue: evaluation<br/>AI quality sampling"]
        BEAT["Celery Beat<br/>schedules"]
    end

    subgraph data["Data Layer"]
        PG[("PostgreSQL 16<br/>relational + pgvector + FTS<br/>RLS enabled")]
        REDIS[("Redis<br/>cache, rate limit,<br/>idempotency, broker, pub/sub")]
        S3[("Object Storage<br/>source PDFs, page images")]
    end

    subgraph external["External Services"]
        LLM["LLM Providers<br/>primary + fallback"]
        EMB["Embedding Provider"]
        RERANK["Reranker"]
        OCRV["OCR / Vision Model"]
        OTEL["Telemetry Backend<br/>traces, metrics, logs"]
    end

    BROWSER --> CDN --> WAF --> LB
    LB --> WEB
    LB --> API
    WEB -->|"server-side calls"| API

    API --> TOOLS
    API --> GW
    TOOLS --> PG
    API --> PG
    API --> REDIS
    API --> S3
    API -->|"outbox rows"| PG

    REDIS <-->|"broker"| WDOC
    REDIS <-->|"broker"| WLEARN
    REDIS <-->|"broker"| WANALYTICS
    REDIS <-->|"broker"| WEVAL
    BEAT --> REDIS

    WDOC --> PG
    WDOC --> S3
    WDOC --> GW
    WLEARN --> PG
    WLEARN --> GW
    WANALYTICS --> PG
    WEVAL --> PG
    WEVAL --> GW

    GW --> LLM
    GW --> EMB
    GW --> RERANK
    GW --> OCRV

    API -.->|"traces/metrics/logs"| OTEL
    WDOC -.-> OTEL
    WLEARN -.-> OTEL
```

### 7.2 Request / data flow (Tutor question — the critical path)

```mermaid
flowchart LR
    U["User asks question"] --> FE["Next.js client"]
    FE -->|"POST /tutor/messages<br/>Accept: text/event-stream"| GWY["Edge: TLS, WAF,<br/>rate limit"]
    GWY --> AUTH["Auth middleware<br/>verify JWT, load principal"]
    AUTH --> SCOPE["Project scope guard<br/>ownership + RLS session var"]
    SCOPE --> VAL["Request validation<br/>Pydantic schema"]
    VAL --> TSVC["Tutor Service"]

    TSVC --> CTX["Context Composer"]
    CTX --> C1["Conversation window<br/>+ rolling summary"]
    CTX --> C2["Learning context items<br/>goals, weaknesses, prefs"]
    CTX --> C3["Retrieval pipeline"]
    C3 --> HYB["Hybrid search<br/>pgvector + FTS, project-filtered"]
    HYB --> RRF["RRF fusion"] --> RR["Rerank top-k"]
    RR --> SUF{"Evidence<br/>sufficient?"}

    SUF -->|"No"| REFUSE["Insufficiency response<br/>+ suggested actions"]
    SUF -->|"Yes"| BUILD["Build prompt<br/>data/instruction separation"]
    BUILD --> LLM["AI Gateway → LLM<br/>streamed"]
    LLM --> CITE["Citation validator<br/>spans exist & were retrieved"]
    CITE --> STREAM["SSE stream to client"]
    REFUSE --> STREAM
    STREAM --> PERSIST["Persist message + citations<br/>+ ai_request + outbox event"]
    PERSIST --> DONE["User sees answer + sources"]
```

---

## 8. Component Architecture

```mermaid
flowchart TB
    subgraph edge["Edge"]
        E1["Rate limiter"]
        E2["Auth middleware"]
        E3["Request context<br/>request_id, trace_id, principal"]
    end

    subgraph domain["Domain Modules (facade-only access)"]
        M1["identity<br/>auth, users, roles"]
        M2["workspace<br/>spaces, projects"]
        M3["materials<br/>uploads, doc lifecycle"]
        M4["knowledge<br/>chunks, concepts, retrieval"]
        M5["tutor<br/>conversation, grounding"]
        M6["assessment<br/>quiz, grading"]
        M7["mastery<br/>estimates, events"]
        M8["growth<br/>trends, recommendations"]
        M9["analytics<br/>events, rollups"]
        M10["admin<br/>read models"]
    end

    subgraph shared["Shared Services"]
        AIGW["AI Gateway<br/>generate / structured / embed /<br/>rerank / evaluate"]
        TOOLR["Tool Registry + Executor<br/>schema, authz, audit"]
        OUTBOX["Outbox Publisher"]
        CTXC["Context Composer"]
    end

    subgraph plat["Platform"]
        DB["DB session + RLS context"]
        CACHE["Cache + rate limit + idempotency"]
        OBJ["Object storage client"]
        OBS["Logging / metrics / tracing"]
        SEC["Crypto, secrets, validation"]
    end

    edge --> domain
    M5 --> CTXC
    M5 --> AIGW
    M6 --> AIGW
    M4 --> AIGW
    M8 --> AIGW
    M3 --> OUTBOX
    M5 --> OUTBOX
    M6 --> OUTBOX
    M7 --> OUTBOX
    CTXC --> M4
    CTXC --> M7
    CTXC --> M6
    AIGW --> TOOLR
    TOOLR --> M2
    TOOLR --> M4
    TOOLR --> M6
    TOOLR --> M7
    TOOLR --> M8
    domain --> plat
    shared --> plat
```

### 8.1 Component responsibilities

| Component | Responsibility | Explicitly *not* responsible for |
|---|---|---|
| **identity** | Registration, login, password hashing (Argon2id), token issue/rotation/revocation, role resolution | Business authorization rules of other modules |
| **workspace** | Space/Project lifecycle, ownership, dashboard aggregation | Any AI call |
| **materials** | Presigned upload issuance, document records, status transitions, job dispatch, failure reasons | Parsing (that's the worker) |
| **knowledge** | Chunk/concept storage, embedding orchestration, hybrid retrieval, fusion, reranking, sufficiency scoring | Prompt construction |
| **tutor** | Conversation lifecycle, context composition, grounded answer generation, citation validation, streaming | Retrieval internals, model selection |
| **assessment** | Quiz sessions, adaptive selection policy, question generation orchestration, MCQ scoring (deterministic), open-ended grading orchestration | Mastery math |
| **mastery** | Mastery state per (project, concept), evidence-driven updates, confidence, decay | Deciding what to ask next |
| **growth** | Trend classification (improving/stable/attention), weakness detection, recommendation generation and dedup | Rendering |
| **analytics** | Event ingestion, idempotent consumption, rollup tables, project/global queries | Being the event source of truth (that's the outbox + `activity_events`) |
| **admin** | Read-only platform aggregates, per-user inspection, job and AI health views | Mutating learner data |
| **AI Gateway** | Single egress for all model calls: provider routing, prompt/version resolution, timeouts, retries, circuit breaking, structured-output validation, token/cost metering, tracing, caching | Business decisions |
| **Tool layer** | Tool schema registry, argument validation, authorization, scoped execution, result shaping, audit | Model reasoning |
| **Context Composer** | Selecting and budgeting the four context sources | Calling the model |
| **Outbox publisher** | Reading `outbox_events`, dispatching to Celery, marking published | Business logic |

---

## 9. Frontend Architecture

### 9.1 Stack

| Concern | Choice | Reason |
|---|---|---|
| Framework | **Next.js 15 (App Router) + TypeScript** | Server components for dashboard-heavy read pages (fewer round trips, less client JS), client components where interactivity is needed; a single framework covering SSR, routing, and a thin BFF for cookie-based session handling |
| Server state | **TanStack Query** | Caching, background refetch, and — critically — **polling for async job status** (document processing) with automatic backoff |
| Streaming | **SSE via native `EventSource` / fetch streams** | Tutor streaming is strictly server→client; SSE works through standard HTTP infrastructure, reconnects automatically, and avoids the operational weight of WebSockets. Chosen over WebSockets in ADR-008 |
| UI | **Tailwind CSS + shadcn/ui + Radix primitives** | Accessible primitives, no design-system build time, consistent with a 4-day window |
| Charts | **Recharts** | Mastery bars, growth trendlines, analytics — declarative and small |
| Forms/validation | **React Hook Form + Zod** | Zod schemas mirror backend Pydantic schemas; validation errors match server contract |
| Upload | **Direct-to-S3 presigned PUT + progress** | Keeps large PDFs off the API process entirely |

### 9.2 Route structure

```text
/                                   Home dashboard (continue, recents, attention, next action)
/spaces                             Space list
/spaces/[spaceId]                   Space dashboard
/spaces/[spaceId]/projects/[id]     Project dashboard
  ├── /materials                    Upload + document status list
  ├── /tutor                        Chat with citations panel
  ├── /quiz                         Adaptive quiz runner + results
  ├── /growth                       Mastery bars + trends + recommendations
  └── /analytics                    Project analytics
/analytics                          Global analytics
/admin                              Admin overview
  ├── /users, /users/[id]           Platform users + single-user journey
  ├── /activity                     Filterable activity explorer
  ├── /ai                           AI usage, cost, evaluation results
  └── /system                       Job health, queue depth, error rates
```

### 9.3 Frontend patterns that matter here

- **Async-aware UI.** Every long-running operation returns a `job_id`; the UI renders a status chip (`queued → processing → ready → failed`) driven by a polled job endpoint with exponential backoff, capped. The PRD requires that the browser need not stay open (§13) — so job state lives server-side and the UI merely reflects it. A user returning hours later sees the correct state.
- **Citations are first-class UI.** A Tutor answer renders inline markers linked to a source panel showing `Document — Page N` and a snippet, with a deep link to the page image. This is the visible half of FR-25/FR-34.
- **Insufficiency is a distinct render state**, visually different from an answer — not grey italic text the user skims past. FR-35 is an evaluation requirement, so it must be unmistakable.
- **Optimistic updates only where safe** (message send, quiz answer selection); never for mastery or grading results, which are server-computed.
- **Error boundaries per route segment** so a failing analytics widget does not blank the project dashboard (graceful degradation, NFR-01).
- **Accessibility baseline:** keyboard-navigable quiz, ARIA live region for streaming answers, visible focus, contrast-checked mastery bars (colour is never the only signal).

---

## 10. Backend Architecture

### 10.1 Stack

| Concern | Choice | Reason |
|---|---|---|
| Language/runtime | **Python 3.12** | The AI/ML ecosystem (PDF parsing, OCR, provider SDKs, eval tooling) is Python-native; a second language for AI work would fragment a small team |
| Framework | **FastAPI** | Native async (essential for streaming + high-IO fan-out to providers), Pydantic v2 validation as a first-class citizen, automatic OpenAPI, dependency injection that maps cleanly onto auth/scoping guards |
| ORM/migrations | **SQLAlchemy 2.0 (async) + Alembic** | Explicit, typed, supports raw SQL where analytics needs it; Alembic gives reviewable, reversible migrations |
| Validation | **Pydantic v2** | One schema language for API requests, tool arguments, **and LLM structured output** — the same validator that guards the API guards model output (Principle 5) |
| Background | **Celery 5 + Redis broker** | Mature retry/backoff semantics, queue routing, scheduled tasks, visibility into state; well-understood failure modes |
| Server | **Uvicorn workers under Gunicorn** | Standard, predictable process management |

> **Why not Node/NestJS for the API?** It would unify language with the frontend, but every AI-adjacent library the ingestion pipeline needs (PyMuPDF, OCR bindings, eval harnesses) is Python. Splitting API and workers across languages would duplicate domain models and validation logic. ADR-002 records this.

### 10.2 Layering inside a module

```text
router.py        HTTP concerns only: schema binding, status codes, auth dependencies
  ↓
service.py       Business logic, transactions, authorization checks, event emission  ← the only public surface
  ↓
repository.py    Data access, query construction, no business rules
  ↓
models.py        SQLAlchemy ORM models
schemas.py       Pydantic request/response/DTO models
policies.py      Authorization predicates + domain rules (e.g. adaptive selection policy)
tasks.py         Celery task entrypoints delegating straight into service.py
```

**Transaction boundary = one service method.** A service method opens a unit of work, performs its writes *including the outbox row*, and commits once. No cross-service transactions; cross-module consistency is eventual, via events.

### 10.3 Request middleware chain

```text
1. Request ID + trace context         (generate/propagate request_id, W3C traceparent)
2. Structured logging context         (bind request_id, user_id, project_id)
3. CORS                               (explicit origin allow-list)
4. Security headers                   (HSTS, CSP, X-Content-Type-Options, Referrer-Policy)
5. Body size limit                    (reject oversized payloads before parsing)
6. Rate limiting                      (Redis, tiered: global / per-user / per-AI-endpoint)
7. Authentication                     (JWT verify → Principal)
8. RLS context                        (SET LOCAL app.current_user_id on the DB session)
9. Idempotency                        (for POSTs carrying Idempotency-Key)
10. Route handler                     (Pydantic validation → service)
11. Exception mapping                 (domain errors → RFC 9457 problem+json)
12. Metrics + access log
```

Steps 7 and 8 together are the isolation invariant: even a buggy repository query cannot escape the tenant boundary because the database itself rejects it.

### 10.4 Error handling contract

All errors return **RFC 9457 `application/problem+json`**:

```json
{
  "type": "https://api.studycompanion.app/errors/evidence-insufficient",
  "title": "Insufficient evidence in project materials",
  "status": 422,
  "detail": "No material in this project covers the requested topic with sufficient confidence.",
  "instance": "/api/v1/projects/9f3.../tutor/messages",
  "request_id": "req_01HW...",
  "errors": [],
  "retryable": false
}
```

Internal exception taxonomy: `DomainError` (4xx, safe to show), `AuthorizationError` (403/404 — 404 when revealing existence would leak), `ValidationError` (422 with field errors), `DependencyError` (502/503, retryable flag set), `AIError` subtypes (`AITimeout`, `AIRateLimited`, `AIInvalidOutput`, `AIProviderDown`). **No stack traces or provider error text ever reach the client**; they go to logs with the `request_id` that the client *is* given, which is how support and the admin dashboard tie a user complaint to a trace (FR-82).

---

## 11. API Architecture

### 11.1 Style decision

**REST over HTTP/JSON, with SSE for streaming.** GraphQL was considered and rejected (ADR-004): the client surface is small and known, GraphQL's flexible query surface complicates per-field authorization for a strict-isolation product, and query-cost control would be extra work. gRPC is inappropriate for a browser-first product with one backend.

### 11.2 Conventions

| Concern | Convention |
|---|---|
| Versioning | URI prefix `/api/v1/`. Breaking changes → `/v2` with both live during a deprecation window; additive changes never bump the version |
| Auth | `Authorization: Bearer <access_jwt>`; refresh token in `HttpOnly; Secure; SameSite=Strict` cookie |
| Identifiers | UUIDv7 (time-ordered → index-friendly, non-enumerable) |
| Pagination | Cursor-based: `?limit=&cursor=`; responses return `{items, next_cursor, has_more}`. Offset pagination only in admin exports |
| Filtering/sorting | Explicit allow-listed fields: `?status=&concept_id=&sort=-created_at`. Never pass user strings into SQL ordering |
| Idempotency | `Idempotency-Key` header required on POSTs that create state or spend money (uploads, quiz submissions, tutor messages). Key + user + route hashed into Redis with the stored response for 24h |
| Errors | RFC 9457 problem+json (Section 10.4) |
| Time | RFC 3339 UTC everywhere |
| Docs | OpenAPI 3.1 auto-generated, served at `/docs`; schema exported in CI and diffed to catch unintended contract changes |
| Observability | Every response carries `X-Request-Id`; AI responses also carry `X-AI-Request-Id` |

### 11.3 Endpoint surface

Only endpoints traceable to a requirement are listed.

```text
# Identity  (FR-01)
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
GET    /api/v1/me

# Spaces  (FR-10, FR-11)
POST   /api/v1/spaces
GET    /api/v1/spaces
GET    /api/v1/spaces/{space_id}
PATCH  /api/v1/spaces/{space_id}
DELETE /api/v1/spaces/{space_id}
GET    /api/v1/spaces/{space_id}/dashboard

# Projects  (FR-12, FR-13, FR-14)
POST   /api/v1/spaces/{space_id}/projects
GET    /api/v1/spaces/{space_id}/projects
GET    /api/v1/projects/{project_id}
PATCH  /api/v1/projects/{project_id}
DELETE /api/v1/projects/{project_id}
GET    /api/v1/projects/{project_id}/dashboard

# Home  (FR-15)
GET    /api/v1/home

# Materials  (FR-20 … FR-26)
POST   /api/v1/projects/{project_id}/materials/upload-url     -> presigned PUT + material_id
POST   /api/v1/projects/{project_id}/materials                -> confirm upload, enqueue processing
GET    /api/v1/projects/{project_id}/materials
GET    /api/v1/materials/{material_id}                        -> status, pages, failure_reason
GET    /api/v1/materials/{material_id}/download-url           -> short-lived presigned GET
POST   /api/v1/materials/{material_id}/reprocess              -> idempotent retry
DELETE /api/v1/materials/{material_id}
GET    /api/v1/materials/{material_id}/pages/{page}/image-url

# Jobs  (FR-23, FR-26)
GET    /api/v1/jobs/{job_id}

# Tutor  (FR-30 … FR-36)
POST   /api/v1/projects/{project_id}/conversations
GET    /api/v1/projects/{project_id}/conversations
GET    /api/v1/conversations/{conversation_id}/messages
POST   /api/v1/conversations/{conversation_id}/messages       -> SSE stream (answer + citations)
POST   /api/v1/conversations/{conversation_id}/stop

# Knowledge / search  (FR-24, FR-25)
GET    /api/v1/projects/{project_id}/concepts
GET    /api/v1/projects/{project_id}/search?q=                -> evidence search, used by UI + tools

# Assessment  (FR-50 … FR-55)
POST   /api/v1/projects/{project_id}/quizzes                  -> start adaptive session
GET    /api/v1/quizzes/{quiz_id}
GET    /api/v1/quizzes/{quiz_id}/next-question                -> adaptive selection
POST   /api/v1/quizzes/{quiz_id}/questions/{question_id}/answer
POST   /api/v1/quizzes/{quiz_id}/complete
GET    /api/v1/quizzes/{quiz_id}/results

# Mastery & growth  (FR-60 … FR-62)
GET    /api/v1/projects/{project_id}/mastery
GET    /api/v1/projects/{project_id}/growth
GET    /api/v1/projects/{project_id}/recommendations
POST   /api/v1/recommendations/{recommendation_id}/accept
POST   /api/v1/recommendations/{recommendation_id}/dismiss

# Learning context  (FR-63, FR-64)
GET    /api/v1/projects/{project_id}/learning-context
DELETE /api/v1/learning-context/{item_id}                     -> user control over stored context

# Analytics  (FR-71, FR-72)
GET    /api/v1/projects/{project_id}/analytics
GET    /api/v1/analytics/global
GET    /api/v1/projects/{project_id}/activity

# Admin  (FR-90 … FR-92)  — role=admin, read-only
GET    /api/v1/admin/overview
GET    /api/v1/admin/users
GET    /api/v1/admin/users/{user_id}
GET    /api/v1/admin/users/{user_id}/journey
GET    /api/v1/admin/activity?user_id=&space_id=&project_id=&type=&from=&to=
GET    /api/v1/admin/ai/usage
GET    /api/v1/admin/ai/requests/{ai_request_id}
GET    /api/v1/admin/ai/evaluations
GET    /api/v1/admin/jobs
GET    /api/v1/admin/system/health

# Operational
GET    /healthz        liveness  (process up)
GET    /readyz         readiness (DB + Redis reachable)
GET    /metrics        Prometheus (internal network only)
```

### 11.4 Streaming contract (Tutor)

`POST /conversations/{id}/messages` with `Accept: text/event-stream` returns typed SSE events:

```text
event: message_start     data: {"message_id":"...","ai_request_id":"..."}
event: token             data: {"delta":"Gradient descent "}
event: citation          data: {"marker":1,"material_id":"...","title":"ML Notes","page":14,"chunk_id":"..."}
event: insufficient      data: {"reason":"no_supporting_evidence","suggestions":[...]}
event: message_end       data: {"message_id":"...","tokens":{...},"latency_ms":2410}
event: error             data: {"type":"ai_timeout","retryable":true,"request_id":"..."}
```

The client can render partial answers and attach citations as they resolve. If the connection drops mid-stream, the message is still persisted server-side by the finalizer, so a refresh shows the completed answer — streaming is a delivery optimization, not the source of truth.

---

## 12. Authentication & Authorization

### 12.1 Authentication

**Choice: self-hosted JWT authentication inside the `identity` module.** (ADR-005.)

| Element | Design |
|---|---|
| Credentials | Email + password, **Argon2id** hashing (memory-hard; correct 2026 default over bcrypt) |
| Access token | JWT, **15 min** TTL, claims: `sub`, `role`, `sid` (session id), `iat`, `exp`, `jti`. Signed **RS256** so verification can later move to an edge/gateway without sharing a signing secret |
| Refresh token | Opaque, 30-day TTL, stored **hashed** in `sessions`, delivered as `HttpOnly; Secure; SameSite=Strict` cookie, **rotated on every use** with reuse detection (a replayed refresh token revokes the whole session family — detects token theft) |
| Logout | Session row revoked; `jti` added to a Redis denylist until natural expiry |
| Password reset | Single-use, time-limited, hashed token; constant-time comparison; no user-enumeration in responses |

> **[ASSUMPTION A-03]** Email/password rather than a managed identity provider. *Why:* the PRD requires authentication (§18) but names no provider, and self-hosting avoids a vendor dependency in a 4-day build while keeping the admin-role model simple. *Alternative:* Auth0/Clerk/Supabase Auth — faster still, but adds an external dependency in the critical login path and complicates the `role=admin` claim and the RLS user-id binding. **Migration path:** because all authorization derives from a `Principal` object resolved in one dependency, swapping to OIDC means replacing token verification only; nothing downstream changes.

> **[ASSUMPTION A-04]** Email verification is stubbed in Phase 0 (account usable immediately, flag recorded) and enforced in Phase 1. *Why:* no transactional email provider is specified, and blocking the demo path on email delivery is poor prototype judgment. This is stated, not hidden.

### 12.2 Authorization model

**RBAC for the role split (learner/admin) + ownership-based ABAC for resources.** Full ABAC policy engines are overkill for two roles; ownership is the real predicate.

Every request resolves a `Principal`:

```python
@dataclass(frozen=True)
class Principal:
    user_id: UUID
    role: Literal["learner", "admin"]
    session_id: UUID
    request_id: str
```

and every project-scoped route passes through one dependency:

```python
async def require_project(project_id: UUID, principal: Principal, db) -> ProjectScope:
    project = await workspace_service.get_owned_project(db, project_id, principal.user_id)
    if project is None:
        raise NotFound()          # 404, never 403 — do not confirm existence
    return ProjectScope(project_id=project.id, space_id=project.space_id,
                        owner_id=project.owner_id, principal=principal)
```

`ProjectScope` is then threaded into retrieval, context composition, and tool execution. **There is no code path that reaches project content without one.**

### 12.3 Authorization matrix

| Resource | Learner (owner) | Learner (non-owner) | Admin |
|---|---|---|---|
| Space / Project | CRUD | 404 | Read (metadata + aggregates) |
| Material file (S3 object) | Read via short-lived presigned URL | 404 | No direct file access *(see A-05)* |
| Chunks / embeddings | Read via retrieval only | Denied | Aggregate counts only |
| Conversation / messages | CRUD | 404 | Read metadata + AI request records |
| Quiz / answers | CRUD own | 404 | Read results, not raw free-text answers *(A-05)* |
| Mastery / growth / recommendations | Read | 404 | Read |
| Learning context items | Read, delete | 404 | Read categories/counts |
| AI usage, evaluations, jobs, health | — | — | Read |

> **[ASSUMPTION A-05]** Admins see learning *metadata and analytics*, not raw learner documents or free-text answers. The PRD asks admins to understand a user's "learning journey… Projects, activity, assessments, progress, and AI usage" (§16) — that is satisfiable without exposing document contents, and minimizing privileged data access is a privacy default. *Alternative:* full content access behind a break-glass flow with mandatory reason codes and audit — deferrable, and the audit machinery already exists if needed.

### 12.4 Data isolation (the invariant)

Isolation is enforced at **four** layers because a single miss is a breach:

1. **Route guard** — `require_project` ownership check (above).
2. **Repository** — every query for tenant data takes `project_id`/`user_id`; an import-linter rule plus code review forbids unscoped selects on tenant tables.
3. **Database RLS** — policies on all tenant tables, keyed on `current_setting('app.current_user_id')`, set per session/transaction:

```sql
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY chunks_owner ON chunks
  USING (project_id IN (
    SELECT id FROM projects WHERE owner_id = current_setting('app.current_user_id')::uuid
  ));
```

The application connects as a **non-superuser, non-`BYPASSRLS`** role. A migration/admin role with bypass exists but is used only by Alembic and the analytics rollup jobs, which aggregate rather than serve.

4. **Retrieval filter** — vector and FTS queries carry `WHERE project_id = :project_id` *inside* the query, never as post-filtering. Post-filtering an ANN result set is both a correctness bug (top-k gets consumed by other projects' chunks) and a leak risk.

**Tests (NFR-03):** a dedicated `tests/isolation/` suite creates two users with two projects each and asserts denial across every endpoint, every tool, every retrieval path, and every background job.

### 12.5 Background job ownership context

The PRD requires background jobs to preserve ownership context (§15). Every task payload carries `{user_id, project_id, correlation_id}`; the worker's session opens with the same `SET LOCAL app.current_user_id`, so **RLS applies identically in workers**. Tasks never accept an "admin mode" flag. A job that cannot resolve its ownership context fails closed.

```mermaid
sequenceDiagram
    participant C as Client
    participant E as Edge
    participant A as API (auth mw)
    participant G as Project Guard
    participant S as Service
    participant D as Postgres (RLS)

    C->>E: POST /projects/{id}/tutor/messages (Bearer JWT)
    E->>E: TLS, WAF, rate limit
    E->>A: forward
    A->>A: verify RS256, check jti denylist -> Principal
    A->>D: SET LOCAL app.current_user_id = principal.user_id
    A->>G: require_project(project_id, principal)
    G->>D: SELECT project WHERE id AND owner_id
    D-->>G: row or none
    alt not owned
        G-->>C: 404 problem+json
    else owned
        G->>S: ProjectScope
        S->>D: all queries filtered by scope AND RLS
        D-->>S: rows
        S-->>C: 200 / SSE stream
    end
```

---

## 13. Data Architecture

### 13.1 Principles

- **Postgres is the system of record.** Chunks, embeddings, mastery, events — all of it. Redis and any future search index are derived and rebuildable.
- **Source documents live in object storage, never in the database.** The DB stores keys, checksums, page counts, and status.
- **Derived data is versioned and regenerable.** Chunks and embeddings carry `embedding_model` and `pipeline_version`; changing either is a reprocessing job, not a migration.
- **Events are append-only.** `activity_events` is never updated, only inserted and read; rollups are separate tables.
- **Ownership is denormalized deliberately.** Tenant tables carry `project_id` (and `owner_id` where it saves a join) so isolation filters and RLS predicates stay cheap. The write cost is trivial; the read and safety benefit is not.

### 13.2 Data ownership by module

| Data | Owning module | Others access via |
|---|---|---|
| users, sessions | identity | `identity.service` |
| spaces, projects | workspace | `workspace.service` |
| materials, material_pages | materials | `materials.service` |
| chunks, chunk_embeddings, concepts, concept_links | knowledge | `knowledge.service` (retrieval API) |
| conversations, messages, message_citations | tutor | `tutor.service` |
| quizzes, questions, answers | assessment | `assessment.service` |
| concept_mastery, mastery_events | mastery | `mastery.service` |
| growth_snapshots, recommendations | growth | `growth.service` |
| learning_context_items | tutor (writer) / all readers | `context_composer` |
| activity_events, analytics rollups | analytics | `analytics.service` |
| ai_requests, ai_evaluations, prompt_versions | ai | `ai.gateway` |
| outbox_events, job_runs | jobs | `jobs` |
| audit_log, tool_invocations | platform/tools | append-only writer |

### 13.3 Why one database (and when that changes)

| Candidate store | Verdict | Reasoning |
|---|---|---|
| PostgreSQL (relational) | **Yes** | Strong relational model, transactions across learning state, mature operations |
| pgvector (vectors) | **Yes** | Prototype corpus is small (tens of thousands of chunks). HNSW in pgvector gives ANN with **`project_id` filtering inside the same query and inside the same transaction** — exactly what isolation requires. A separate vector DB would introduce dual-write consistency problems between chunks and their embeddings |
| Postgres FTS (`tsvector`) | **Yes** | Lexical half of hybrid retrieval — critical for exact terms, acronyms, formulas, code. Free with the existing database |
| Redis | **Yes** | Cache, rate limiting, idempotency, broker, SSE pub/sub. Not a system of record |
| Object storage | **Yes** | PDFs and rendered page images; wrong data for a database |
| MongoDB | **No** | Nothing here is genuinely schemaless; JSONB covers flexible fields (AI metadata, event payloads) inside the transactional store |
| Dedicated vector DB (Qdrant/Pinecone) | **Not yet** | ADR-003 trigger: >5M chunks, p95 vector search >150 ms at target recall, or a need for quantization/multi-tenant sharding/advanced payload filtering |
| Elasticsearch/OpenSearch | **No** | Postgres FTS covers the search requirement at this scale; ES would be a second cluster to operate, secure, and back up for no measured benefit |
| ClickHouse / warehouse | **Not yet** | Trigger: `activity_events` beyond ~100M rows or analytics p95 >2 s after partitioning and rollups |

### 13.4 Read/write patterns

| Pattern | Volume profile | Design |
|---|---|---|
| Dashboard reads (home, space, project) | Frequent, aggregate-heavy | Served from **rollup tables** maintained by workers, not live aggregates over events; cached in Redis 60 s |
| Tutor turn | Moderate, latency-sensitive | 1 vector query + 1 FTS query (parallel) + small relational reads; writes at end of turn |
| Retrieval | Read-heavy on `chunks`/`chunk_embeddings` | HNSW index; partial index per project not needed at this scale (composite `(project_id)` filter + HNSW) |
| Ingestion | Bursty, write-heavy | Batched inserts (`COPY`/`executemany`), embeddings written in batches of 64–128 |
| Analytics | Range scans over time | `activity_events` partitioned monthly by `occurred_at`; BRIN index on time, B-tree on `(project_id, occurred_at)` |
| Quiz | Small, transactional | Straight relational reads/writes |

### 13.5 Transactions

- **Strict ACID within a module operation.** Example: "submit quiz answer" writes `answers`, `mastery_events`, updated `concept_mastery`, and an `outbox_events` row in **one transaction** — so a crash cannot leave mastery updated but the downstream workflow never triggered, nor vice versa. This is the reason for the outbox rather than publishing to Celery inline (Section 16.2).
- **No distributed transactions.** Cross-module effects (recommendations, analytics) are eventual.
- **Isolation level:** `READ COMMITTED` default; `SERIALIZABLE` for mastery updates on the same `(project_id, concept_id)` where concurrent quiz and background recomputation could interleave — with a retry-on-serialization-failure decorator (bounded, jittered).
- **Advisory locks** (`pg_advisory_xact_lock` on a hash of `material_id`) prevent two concurrent processing runs for the same document.

### 13.6 Data lifecycle, retention, archival

| Data | Hot | Archive | Delete |
|---|---|---|---|
| Source PDFs | Object storage standard tier | Infrequent-access after 90 days (lifecycle rule) | On user delete of material: object + chunks + embeddings purged |
| Chunks / embeddings | Postgres | — | Cascade with material; regenerable from source |
| Conversations | Postgres | Messages older than 180 days compacted into rolling summaries *(A-06)* | On project delete |
| activity_events | Monthly partitions, 12 months hot | Partitions older than 12 months detached and exported to object storage as Parquet | After export |
| ai_requests | 90 days full detail incl. truncated prompts | Aggregated into daily cost/latency rollups, detail dropped | After 90 days |
| audit_log | 12 months | Exported, retained 24 months | — |
| Backups | See Section 36 | | |

> **[ASSUMPTION A-06]** Retention periods are not specified in the PRD. These values balance the product need ("persistent but relevant context", §2) against storage cost and privacy-minimization. All are configuration, not code. A real deployment would set them from legal/compliance input.

**User deletion:** account deletion cascades to spaces → projects → materials (object storage objects deleted via a reconciliation job that also catches orphans), conversations, quizzes, mastery, recommendations, and learning context. `activity_events` and `ai_requests` are **anonymized rather than deleted** (user id replaced with a tombstone id) so platform analytics and cost history stay correct — a privacy-defensible middle ground, recorded here explicitly.

### 13.7 Migration strategy

Alembic, with **expand/contract**:

1. *Expand* — add nullable column / new table / new index (`CREATE INDEX CONCURRENTLY`), deploy.
2. *Backfill* — batched background job, resumable, rate-limited, never a single long transaction.
3. *Switch* — code reads new shape; deploy.
4. *Contract* — drop old column in a later release.

Rules: no destructive migration in the same release that stops using the column; every migration has a tested `downgrade`; migrations run as a **separate job before** the app rollout (Section 29.4); locks are guarded with `SET lock_timeout = '3s'` so a migration fails fast rather than freezing the table.

---

## 14. Database Design

### 14.1 Entity-relationship model

```mermaid
erDiagram
    USERS ||--o{ SPACES : owns
    USERS ||--o{ SESSIONS : has
    SPACES ||--o{ PROJECTS : contains
    PROJECTS ||--o{ MATERIALS : has
    PROJECTS ||--o{ CONCEPTS : has
    PROJECTS ||--o{ CONVERSATIONS : has
    PROJECTS ||--o{ QUIZZES : has
    PROJECTS ||--o{ CONCEPT_MASTERY : tracks
    PROJECTS ||--o{ RECOMMENDATIONS : receives
    PROJECTS ||--o{ LEARNING_CONTEXT_ITEMS : accumulates
    PROJECTS ||--o{ GROWTH_SNAPSHOTS : records

    MATERIALS ||--o{ MATERIAL_PAGES : contains
    MATERIALS ||--o{ CHUNKS : split_into
    CHUNKS ||--|| CHUNK_EMBEDDINGS : embedded_as
    CHUNKS }o--o{ CONCEPTS : mentions

    CONVERSATIONS ||--o{ MESSAGES : contains
    MESSAGES ||--o{ MESSAGE_CITATIONS : cites
    MESSAGE_CITATIONS }o--|| CHUNKS : references

    QUIZZES ||--o{ QUESTIONS : contains
    QUESTIONS ||--o{ ANSWERS : answered_by
    QUESTIONS }o--|| CONCEPTS : targets
    ANSWERS ||--o{ MASTERY_EVENTS : produces
    MASTERY_EVENTS }o--|| CONCEPT_MASTERY : updates

    USERS ||--o{ ACTIVITY_EVENTS : generates
    USERS ||--o{ AI_REQUESTS : triggers
    AI_REQUESTS ||--o{ AI_EVALUATIONS : scored_by
    AI_REQUESTS ||--o{ TOOL_INVOCATIONS : performs
```

### 14.2 Core tables (abridged DDL)

```sql
-- ============ Identity ============
CREATE TABLE users (
  id             UUID PRIMARY KEY,
  email          CITEXT UNIQUE NOT NULL,
  password_hash  TEXT NOT NULL,
  display_name   TEXT NOT NULL,
  role           TEXT NOT NULL DEFAULT 'learner' CHECK (role IN ('learner','admin')),
  email_verified BOOLEAN NOT NULL DEFAULT FALSE,
  status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled','deleted')),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_active_at TIMESTAMPTZ
);

CREATE TABLE sessions (
  id                 UUID PRIMARY KEY,
  user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_token_hash TEXT NOT NULL,
  family_id          UUID NOT NULL,           -- rotation family, for reuse detection
  user_agent         TEXT, ip_hash TEXT,
  expires_at         TIMESTAMPTZ NOT NULL,
  revoked_at         TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON sessions (user_id) WHERE revoked_at IS NULL;

-- ============ Workspace ============
CREATE TABLE spaces (
  id UUID PRIMARY KEY,
  owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, description TEXT,
  color TEXT, icon TEXT,                       -- optional visual customization (PRD 4)
  archived_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON spaces (owner_id, created_at DESC);

CREATE TABLE projects (
  id UUID PRIMARY KEY,
  space_id UUID NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,  -- denormalized for RLS/filters
  name TEXT NOT NULL, description TEXT,
  learning_goal TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  last_activity_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON projects (owner_id, last_activity_at DESC);
CREATE INDEX ON projects (space_id);

-- ============ Materials ============
CREATE TABLE materials (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  owner_id   UUID NOT NULL,
  title TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  storage_key TEXT NOT NULL,
  checksum_sha256 TEXT NOT NULL,
  page_count INT,
  status TEXT NOT NULL DEFAULT 'queued'
         CHECK (status IN ('queued','processing','ready','failed')),
  failure_reason TEXT,
  processing_started_at TIMESTAMPTZ, processed_at TIMESTAMPTZ,
  pipeline_version TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, checksum_sha256)          -- duplicate-upload handling (PRD 5)
);
CREATE INDEX ON materials (project_id, status);

CREATE TABLE material_pages (
  id UUID PRIMARY KEY,
  material_id UUID NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
  project_id  UUID NOT NULL,
  page_number INT NOT NULL,
  text_content TEXT,
  extraction_method TEXT CHECK (extraction_method IN ('native','ocr','vision')),
  has_tables BOOLEAN DEFAULT FALSE, has_images BOOLEAN DEFAULT FALSE,
  image_key TEXT,                               -- rendered page image for citation preview
  UNIQUE (material_id, page_number)
);

-- ============ Knowledge ============
CREATE TABLE chunks (
  id UUID PRIMARY KEY,
  material_id UUID NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
  project_id  UUID NOT NULL,
  ordinal INT NOT NULL,
  content TEXT NOT NULL,
  token_count INT NOT NULL,
  page_start INT NOT NULL, page_end INT NOT NULL,   -- citation anchors (PRD 7)
  section_path TEXT,                                -- e.g. "3 > 3.2 Gradient Descent"
  content_type TEXT DEFAULT 'text'
       CHECK (content_type IN ('text','table','figure_caption','code','ocr')),
  content_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  pipeline_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX chunks_tsv_idx  ON chunks USING GIN (content_tsv);
CREATE INDEX chunks_proj_idx ON chunks (project_id, material_id, ordinal);

CREATE TABLE chunk_embeddings (
  chunk_id UUID PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  embedding VECTOR(1536) NOT NULL,
  model TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX chunk_emb_hnsw ON chunk_embeddings
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX chunk_emb_proj ON chunk_embeddings (project_id);

CREATE TABLE concepts (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  description TEXT,
  importance REAL DEFAULT 0.5 CHECK (importance BETWEEN 0 AND 1),
  source TEXT NOT NULL DEFAULT 'extracted' CHECK (source IN ('extracted','user','inferred')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, normalized_name)          -- idempotent concept extraction
);

CREATE TABLE chunk_concepts (
  chunk_id UUID REFERENCES chunks(id) ON DELETE CASCADE,
  concept_id UUID REFERENCES concepts(id) ON DELETE CASCADE,
  relevance REAL NOT NULL DEFAULT 0.5,
  PRIMARY KEY (chunk_id, concept_id)
);

CREATE TABLE concept_links (                     -- prerequisite / related graph (PRD 5)
  from_concept_id UUID REFERENCES concepts(id) ON DELETE CASCADE,
  to_concept_id   UUID REFERENCES concepts(id) ON DELETE CASCADE,
  relation TEXT NOT NULL CHECK (relation IN ('prerequisite_of','related_to','part_of')),
  confidence REAL DEFAULT 0.5,
  PRIMARY KEY (from_concept_id, to_concept_id, relation)
);

-- ============ Tutor ============
CREATE TABLE conversations (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  owner_id UUID NOT NULL,
  title TEXT,
  rolling_summary TEXT,                          -- cross-session continuity (PRD 6)
  summary_through_message_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_message_at TIMESTAMPTZ
);

CREATE TABLE messages (
  id UUID PRIMARY KEY,
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
  content TEXT NOT NULL,
  answer_status TEXT CHECK (answer_status IN ('grounded','insufficient_evidence','general_knowledge','error')),
  ai_request_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON messages (conversation_id, created_at);

CREATE TABLE message_citations (
  id UUID PRIMARY KEY,
  message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  material_id UUID NOT NULL,
  page_number INT NOT NULL,
  marker INT NOT NULL,                           -- [1], [2] in the answer
  quote TEXT,
  UNIQUE (message_id, marker)
);

-- ============ Assessment ============
CREATE TABLE quizzes (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  owner_id UUID NOT NULL,
  mode TEXT NOT NULL DEFAULT 'adaptive',
  target_question_count INT NOT NULL DEFAULT 10,
  status TEXT NOT NULL DEFAULT 'in_progress'
         CHECK (status IN ('in_progress','completed','abandoned')),
  score REAL, started_at TIMESTAMPTZ NOT NULL DEFAULT now(), completed_at TIMESTAMPTZ
);

CREATE TABLE questions (
  id UUID PRIMARY KEY,
  quiz_id UUID NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  concept_id UUID REFERENCES concepts(id) ON DELETE SET NULL,
  type TEXT NOT NULL CHECK (type IN ('mcq','open_ended')),
  difficulty REAL NOT NULL CHECK (difficulty BETWEEN 0 AND 1),
  prompt TEXT NOT NULL,
  options JSONB,                                 -- mcq only
  correct_option INT,                            -- mcq only
  rubric JSONB,                                  -- open-ended grading rubric
  source_chunk_ids UUID[],                       -- provenance: questions are grounded too
  ordinal INT NOT NULL,
  ai_request_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE answers (
  id UUID PRIMARY KEY,
  question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  quiz_id UUID NOT NULL, project_id UUID NOT NULL, owner_id UUID NOT NULL,
  response_text TEXT, selected_option INT,
  is_correct BOOLEAN,
  score REAL CHECK (score BETWEEN 0 AND 1),
  evaluation JSONB,                              -- {understanding, accuracy, relevance,
                                                 --  concepts_covered[], concepts_missing[], reasoning}
  feedback TEXT,
  graded_by TEXT CHECK (graded_by IN ('deterministic','ai','human')),
  ai_request_id UUID,
  answered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  time_taken_ms INT,
  UNIQUE (question_id)                           -- one answer per question: idempotent submit
);

-- ============ Mastery & Growth ============
CREATE TABLE concept_mastery (
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  owner_id UUID NOT NULL,
  mastery REAL NOT NULL DEFAULT 0.3 CHECK (mastery BETWEEN 0 AND 1),
  confidence REAL NOT NULL DEFAULT 0.1,          -- evidence volume, not certainty of the learner
  evidence_count INT NOT NULL DEFAULT 0,
  consecutive_correct INT NOT NULL DEFAULT 0,
  last_evidence_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, concept_id)
);

CREATE TABLE mastery_events (                    -- append-only evidence trail
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL, concept_id UUID NOT NULL, owner_id UUID NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('quiz_answer','open_assessment','tutor_signal','decay','manual')),
  source_id UUID,
  mastery_before REAL NOT NULL, mastery_after REAL NOT NULL,
  evidence_strength REAL NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source, source_id, concept_id)         -- idempotency under retry (NFR-02)
);
CREATE INDEX ON mastery_events (project_id, concept_id, occurred_at DESC);

CREATE TABLE growth_snapshots (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL, concept_id UUID NOT NULL,
  window_start DATE NOT NULL, window_end DATE NOT NULL,
  mastery_start REAL, mastery_end REAL, delta REAL,
  trend TEXT CHECK (trend IN ('improving','stable','needs_attention')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, concept_id, window_end)
);

CREATE TABLE recommendations (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  owner_id UUID NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('review_material','take_quiz','tutor_session','revisit_concept','new_material')),
  title TEXT NOT NULL, rationale TEXT NOT NULL,
  target_concept_ids UUID[], target_material_id UUID,
  priority REAL NOT NULL DEFAULT 0.5,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','accepted','dismissed','expired')),
  dedup_key TEXT NOT NULL,
  ai_request_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX ON recommendations (project_id, dedup_key) WHERE status = 'active';

-- ============ Persistent learning context (PRD 11) ============
CREATE TABLE learning_context_items (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  owner_id UUID NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN
      ('goal','preference','strength','weakness','misconception','history','tutor_note')),
  content TEXT NOT NULL,
  concept_id UUID REFERENCES concepts(id) ON DELETE SET NULL,
  salience REAL NOT NULL DEFAULT 0.5,             -- relevance-first, not store-everything
  evidence_count INT NOT NULL DEFAULT 1,
  source TEXT NOT NULL CHECK (source IN ('tutor','assessment','workflow','user')),
  last_reinforced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ,
  UNIQUE (project_id, kind, md5(content))         -- no duplicate facts
);
CREATE INDEX ON learning_context_items (project_id, salience DESC, last_reinforced_at DESC);

-- ============ Events, jobs, AI ============
CREATE TABLE activity_events (
  id UUID NOT NULL,
  user_id UUID NOT NULL, space_id UUID, project_id UUID,
  type TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);
CREATE INDEX ON activity_events (project_id, occurred_at DESC);
CREATE INDEX ON activity_events (user_id, type, occurred_at DESC);

CREATE TABLE outbox_events (
  id UUID PRIMARY KEY,
  aggregate_type TEXT NOT NULL, aggregate_id UUID NOT NULL,
  type TEXT NOT NULL, schema_version INT NOT NULL DEFAULT 1,
  payload JSONB NOT NULL,
  user_id UUID NOT NULL, project_id UUID,        -- ownership context for workers (PRD 15)
  status TEXT NOT NULL DEFAULT 'pending'
         CHECK (status IN ('pending','published','failed')),
  attempts INT NOT NULL DEFAULT 0,
  available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), published_at TIMESTAMPTZ
);
CREATE INDEX ON outbox_events (status, available_at) WHERE status <> 'published';

CREATE TABLE processed_events (                   -- consumer-side idempotency (NFR-02)
  consumer TEXT NOT NULL, event_id UUID NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (consumer, event_id)
);

CREATE TABLE job_runs (
  id UUID PRIMARY KEY,
  task_name TEXT NOT NULL,
  dedup_key TEXT,
  user_id UUID, project_id UUID, resource_id UUID,
  status TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed','dead_lettered')),
  attempt INT NOT NULL DEFAULT 1, max_attempts INT NOT NULL DEFAULT 3,
  error_type TEXT, error_message TEXT,
  queued_at TIMESTAMPTZ NOT NULL DEFAULT now(), started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX ON job_runs (dedup_key) WHERE status IN ('queued','running');

CREATE TABLE ai_requests (                        -- PRD 14: the AI observability spine
  id UUID PRIMARY KEY,
  user_id UUID, project_id UUID,
  feature TEXT NOT NULL,                          -- tutor_answer, quiz_generate, grade_open, recommend, embed, rerank, concept_extract, eval
  operation TEXT NOT NULL CHECK (operation IN ('generate','structured','embed','rerank','evaluate','vision')),
  provider TEXT NOT NULL, model TEXT NOT NULL,
  prompt_id TEXT, prompt_version TEXT,
  input_tokens INT, output_tokens INT,
  estimated_cost_usd NUMERIC(10,6),
  latency_ms INT, time_to_first_token_ms INT,
  status TEXT NOT NULL CHECK (status IN ('success','timeout','provider_error','invalid_output','rate_limited','cancelled')),
  error_type TEXT,
  retrieval_meta JSONB,                           -- {k, scores, chunk_ids, strategy, sufficiency}
  fallback_from TEXT,
  trace_id TEXT, request_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON ai_requests (created_at DESC);
CREATE INDEX ON ai_requests (feature, status, created_at DESC);
CREATE INDEX ON ai_requests (user_id, created_at DESC);

CREATE TABLE ai_evaluations (
  id UUID PRIMARY KEY,
  ai_request_id UUID REFERENCES ai_requests(id) ON DELETE CASCADE,
  suite TEXT NOT NULL,                            -- tutor | retrieval | assessment | recommendation
  metric TEXT NOT NULL,                           -- groundedness | citation_validity | refusal_correctness | ndcg | rubric_agreement ...
  score REAL NOT NULL,
  method TEXT NOT NULL CHECK (method IN ('rule','model','human')),
  details JSONB,
  evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tool_invocations (                   -- PRD 8 audit trail
  id UUID PRIMARY KEY,
  ai_request_id UUID, user_id UUID NOT NULL, project_id UUID NOT NULL,
  tool_name TEXT NOT NULL,
  arguments JSONB NOT NULL,
  authorized BOOLEAN NOT NULL, denial_reason TEXT,
  status TEXT NOT NULL CHECK (status IN ('success','validation_error','denied','execution_error')),
  latency_ms INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
  id UUID PRIMARY KEY,
  actor_user_id UUID, actor_role TEXT,
  action TEXT NOT NULL, resource_type TEXT, resource_id UUID,
  target_user_id UUID,
  ip_hash TEXT, request_id TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 14.3 Indexing strategy

| Index | Purpose |
|---|---|
| `chunk_emb_hnsw` (HNSW, cosine) | ANN retrieval; `ef_search` tuned at query time (default 40, raised for eval runs) |
| `chunks_tsv_idx` (GIN) | Lexical half of hybrid retrieval |
| `chunks_proj_idx` | Project-filtered scans and citation lookups |
| `projects (owner_id, last_activity_at DESC)` | Home "Continue Learning" |
| `materials (project_id, status)` | Materials list + processing dashboard |
| `messages (conversation_id, created_at)` | Conversation window load |
| `mastery_events (project_id, concept_id, occurred_at DESC)` | Growth trend queries |
| `activity_events (project_id, occurred_at DESC)` + monthly partitions | Project analytics and activity feed |
| `ai_requests (feature, status, created_at DESC)` | Admin AI health, error-rate queries |
| Partial unique `recommendations (project_id, dedup_key) WHERE active` | No duplicate live recommendations |
| Partial unique `job_runs (dedup_key) WHERE queued/running` | Duplicate-job prevention (PRD §5) |

**Index discipline:** each index above exists to serve a named query. Index bloat is reviewed by checking `pg_stat_user_indexes` for unused indexes before each release.

---

## 15. Caching Strategy

The PRD asks for "caching where useful" (§15) — a deliberately narrow mandate. Cache only what is expensive and tolerant of staleness.

| Cache | Key | TTL | Invalidation | Why |
|---|---|---|---|---|
| Dashboard aggregates (home/space/project) | `dash:{scope}:{id}:v{n}` | 60 s | Version bump on relevant event | Dashboards are read constantly and re-render identical aggregates |
| Mastery summary | `mastery:{project_id}` | 120 s | Deleted on `mastery.updated` | Rendered on several screens per session |
| Retrieval results | `retr:{project_id}:{sha1(normalized_query)}:{k}` | 10 min | Purged on material ready/delete | Identical follow-up questions are common; saves an embedding call + two queries |
| Embedding of query text | `emb:q:{sha1(text)}:{model}` | 24 h | Model version in key | Same question text re-embedded across users is pure waste |
| Concept list per project | `concepts:{project_id}` | 5 min | Purged on concept extraction | Read by quiz generation, tutor context, analytics |
| Rate-limit counters | `rl:{scope}:{id}:{window}` | window | — | Token bucket state |
| Idempotency records | `idem:{user}:{route}:{key}` | 24 h | — | Stored response replay |
| SSE session channel | `sse:{conversation_id}` | ephemeral | — | Pub/sub for multi-replica streaming |

**Explicitly not cached:** LLM answers (personalized and context-dependent — caching them risks serving one learner's grounded answer to another, an isolation hazard for negligible gain), mastery *writes*, quiz questions (must be fresh and adaptive), and anything in the admin plane (accuracy over speed).

**Patterns:** cache-aside everywhere; single-flight locking on retrieval cache fill to prevent stampedes; jittered TTLs; every cache key namespaced with a global `CACHE_VERSION` so a bad deploy can be invalidated wholesale with an env change.

**Correctness rule:** losing Redis entirely must degrade latency only. Every cache read is wrapped so that a Redis error logs, increments a metric, and falls through to Postgres (Section 35).

---

## 16. Messaging & Event Architecture

### 16.1 What is synchronous vs asynchronous

| Operation | Mode | Reason |
|---|---|---|
| Auth, CRUD on spaces/projects | Sync | Instant, transactional |
| Upload confirmation | Sync (returns `job_id`) | User needs confirmation; work itself is async |
| Document parse/OCR/chunk/embed/concepts | **Async** | Minutes long, CPU-heavy (PRD §5, §13) |
| Tutor turn | Sync + streamed | The user is waiting for exactly this |
| Tutor post-processing (context extraction, activity event, salience update) | **Async** | Not needed for the answer |
| MCQ scoring | Sync | Deterministic and instant — making it async would be gratuitous |
| Open-ended grading | Sync if the user is waiting on that question's feedback; **async re-evaluation** for quiz-level analysis | Immediate feedback matters pedagogically; deeper analysis does not block |
| Quiz completion → mastery → weakness → insight → recommendation | **Async chain** | PRD §12, §13 describe exactly this workflow |
| Analytics rollups, growth snapshots | **Async, scheduled** | Aggregation should never be on a request path |
| AI evaluation sampling | **Async, scheduled** | Quality measurement, not user-facing |

### 16.2 Transactional Outbox (the key reliability decision)

Publishing to Celery directly inside a request creates a dual-write: the DB commit and the broker publish can disagree. Under failure you get either mastery updated with no downstream workflow, or a workflow for a transaction that rolled back. Both are real bugs that appear only under load, which is the worst kind.

Instead: the business transaction writes its domain rows **and** an `outbox_events` row atomically. A relay (Celery Beat, every 2 s; plus an in-process nudge after commit for latency) claims pending rows with `SELECT ... FOR UPDATE SKIP LOCKED`, dispatches them to the appropriate queue, and marks them published.

```mermaid
flowchart LR
    SVC["Service method<br/>(single transaction)"] --> DB[("Postgres:<br/>domain rows + outbox row")]
    DB --> RELAY["Outbox Relay<br/>FOR UPDATE SKIP LOCKED"]
    RELAY --> BROKER[("Redis broker")]
    BROKER --> Q1["documents"]
    BROKER --> Q2["learning"]
    BROKER --> Q3["analytics"]
    BROKER --> Q4["evaluation"]
    Q1 --> W["Worker: consume<br/>check processed_events"]
    Q2 --> W
    Q3 --> W
    Q4 --> W
    W -->|"already processed"| SKIP["ack, no-op"]
    W -->|"new"| EXEC["execute + record<br/>processed_events"]
    EXEC --> DB
    EXEC -->|"retries exhausted"| DLQ[("dead_letter queue<br/>+ job_runs status")]
```

This gives **at-least-once delivery with consumer-side idempotency**, which is the right guarantee for this workload and exactly what PRD §12 asks for ("retries, duplicate events, and idempotency").

### 16.3 Event catalogue

| Event | Producer | Consumers | Payload (core fields) |
|---|---|---|---|
| `material.uploaded` | materials | document pipeline, analytics | material_id, project_id, storage_key, checksum |
| `material.processed` | worker | project state, analytics, recommendations | material_id, chunk_count, concept_count |
| `material.failed` | worker | notification/UI state, analytics | material_id, failure_reason, attempt |
| `tutor.message_completed` | tutor | learning-context extraction, analytics, eval sampling | message_id, ai_request_id, answer_status, concepts_touched |
| `quiz.completed` | assessment | evaluation, mastery, weakness detection | quiz_id, project_id, answers summary |
| `answer.submitted` | assessment | mastery update, mistake detection | answer_id, question_id, concept_id, score |
| `mastery.updated` | mastery | growth, recommendations, analytics, cache invalidation | project_id, concept_id, before, after |
| `weakness.detected` | growth | recommendation generation, learning context | project_id, concept_id[], evidence |
| `mistake.repeated` | growth | learning context update, targeted recommendation (PRD §13) | project_id, concept_id, pattern |
| `recommendation.created` | growth | analytics, UI badge | recommendation_id, kind, priority |
| `project.activity` | all | analytics rollups | generic activity envelope |

### 16.4 Event schema, versioning, ordering

- **Envelope:** `{event_id, type, schema_version, occurred_at, user_id, project_id, correlation_id, causation_id, payload}`. Validated with Pydantic on both ends.
- **Versioning:** additive fields only within a version; breaking change → `schema_version + 1`, with consumers handling both for one release cycle. `event_id` is the idempotency key.
- **Ordering:** no global ordering guarantee. Where order matters (mastery updates for the same concept), correctness is achieved by *design* instead: `mastery_events` has a natural unique key, and mastery recomputation is a **pure function of the ordered evidence trail**, not an increment. Replaying events out of order therefore converges to the same state. This is more robust than depending on broker ordering.
- **Retries:** exponential backoff with jitter, `max_retries=3` (documents: 5, since OCR failures are often transient), `acks_late=True`, `task_reject_on_worker_lost=True`.
- **DLQ:** exhausted tasks move to a `dead_letter` queue and are recorded in `job_runs` as `dead_lettered`, surfaced in the admin dashboard with a manual replay action.

### 16.5 Queues and workers

| Queue | Tasks | Concurrency | Notes |
|---|---|---|---|
| `documents` | parse, OCR, chunk, embed, extract concepts | Low (2–4), CPU-bound | Prefetch 1; long `time_limit` (10 min hard / 8 min soft) |
| `learning` | grade open answers, update mastery, detect weakness, generate recommendation | Medium (4–8), IO-bound on LLM | Rate-limited by AI budget |
| `analytics` | rollups, growth snapshots, activity aggregation | Low (2) | Scheduled, off-peak |
| `evaluation` | eval sampling and scoring | Low (1–2) | Lowest priority; must never starve the others |
| `default` | outbox relay, cleanup, reconciliation | Low | |

Separating queues means a burst of 50 document uploads cannot delay a learner's post-quiz recommendation — **bulkhead isolation** at the queue level (Section 25).

---

## 17. AI/ML Architecture

This is where the PRD concentrates its expectations (§6, §7, §8, §9, §14), so the AI subsystem gets real engineering structure rather than scattered API calls.

### 17.1 The AI Gateway

**One module is the only path to any model.** Nothing outside `app/ai/` may import a provider SDK — enforced by import-linter.

```python
class AIGateway(Protocol):
    async def generate(self, req: GenerationRequest) -> GenerationResult: ...
    async def stream(self, req: GenerationRequest) -> AsyncIterator[StreamChunk]: ...
    async def structured(self, req: StructuredRequest[T]) -> StructuredResult[T]: ...
    async def embed(self, req: EmbeddingRequest) -> EmbeddingResult: ...
    async def rerank(self, req: RerankRequest) -> RerankResult: ...
    async def evaluate(self, req: EvaluationRequest) -> EvaluationResult: ...
    async def understand_document(self, req: VisionRequest) -> VisionResult: ...
```

Every call, regardless of provider, passes through this pipeline:

```mermaid
flowchart TB
    CALLER["Caller module<br/>(tutor / assessment / knowledge / growth)"] --> REQ["Typed request<br/>+ feature tag + ProjectScope"]
    REQ --> BUDGET["Budget & rate check<br/>per user / per feature"]
    BUDGET --> PROMPT["Prompt resolver<br/>id + version + variables"]
    PROMPT --> CACHE{"Cacheable?<br/>(embeddings only)"}
    CACHE -->|hit| DONE["Return cached"]
    CACHE -->|miss| ROUTE["Model router<br/>capability + cost tier"]
    ROUTE --> CB{"Circuit breaker<br/>closed?"}
    CB -->|open| FB["Fallback provider/model"]
    CB -->|closed| CALL["Provider call<br/>timeout + retry(backoff, jitter)"]
    FB --> CALL
    CALL --> VALID["Output validation<br/>schema / citation / safety"]
    VALID -->|invalid| REPAIR["1 repair attempt<br/>with validation errors"]
    REPAIR --> VALID
    VALID -->|still invalid| FAIL["AIInvalidOutput -> caller fallback"]
    VALID -->|valid| METER["Record ai_requests:<br/>model, tokens, cost, latency, status"]
    METER --> TRACE["OTel span + metrics"]
    TRACE --> RETURN["Result to caller"]
```

### 17.2 Model selection

Models are selected **per feature by capability and cost tier**, expressed in configuration, not hard-coded:

| Feature | Tier | Why |
|---|---|---|
| Tutor answering | Strong reasoning model, streaming | Quality of explanation is the product; streaming is required (FR-36) |
| Open-ended grading | Strong reasoning model, structured output, temperature 0 | Grading must be consistent and rubric-faithful |
| Question generation | Mid-tier, structured output | Templated, constrained task — a frontier model is not needed |
| Concept extraction | Mid/small, structured output, batched | High volume during ingestion; cost matters |
| Query rewriting / routing | Small, fast | Sub-second budget, trivial task |
| Recommendation phrasing | Mid-tier | Deterministic logic decides *what*; the model phrases *how* |
| Embeddings | Dedicated embedding model, 1536-d | Fixed dimension pinned in schema; model name stored per row |
| Reranking | Cross-encoder rerank API (or a small-LLM rerank fallback) | Precision at top-k is what makes citations correct |
| Scanned/diagram pages | Vision-capable model | Only for pages where native extraction and OCR both fall short |

> **[ASSUMPTION A-07]** Specific providers/models are not named in the PRD ("the exact models and providers are left to the candidate", §14). The architecture therefore names **roles**, with configuration mapping roles → provider/model, plus a per-role fallback. *Why:* provider lock-in inside domain code is the single most expensive AI mistake; the indirection costs one interface. *Trade-off:* a thin abstraction cannot expose every provider-specific feature — provider-unique capabilities must be adopted deliberately and reflected in the interface, not smuggled in.

### 17.3 Prompt management

- Prompts live in **version-controlled files** (`ai/prompts/<feature>/<name>.v{n}.md`) with front-matter (`id`, `version`, `model_role`, `variables`, `output_schema`), loaded at startup into a registry.
- Every `ai_requests` row stores `prompt_id` + `prompt_version` — so a quality regression can be tied to the exact prompt that produced it (FR-84).
- Variables are injected through a strict renderer that **escapes and delimits** untrusted content; user/material text can never terminate a prompt section (Section 21.7).
- Changing a prompt requires the evaluation suite to pass in CI (Section 17.6).

### 17.4 Structured generation

All structured outputs (quiz questions, grading results, concept extraction, recommendation drafts, insufficiency decisions) are defined as Pydantic models, converted to JSON Schema, and enforced via provider structured-output/tool-schema modes. Then:

1. Parse and validate against the schema.
2. On failure, **one** repair attempt with the validation errors appended.
3. On second failure, raise `AIInvalidOutput`; caller applies its documented fallback (skip the question, mark grading as `pending_review`, degrade the recommendation to a deterministic template).
4. `structured_output_validity_rate` is a tracked metric per feature; a sustained drop is an alert, because it usually means a model or prompt change.

This directly implements FR-42: AI-generated structured data is validated before it is persisted or changes application state.

### 17.5 Cost control and rate limiting

- Per-request `max_tokens` caps by feature.
- Per-user daily token/cost budget in Redis; exceeding it degrades gracefully (smaller model, shorter context, clear user message) rather than erroring.
- Context budget enforced by the Context Composer *before* the call — the prompt is assembled to a token ceiling, never "send everything and hope".
- Embedding batching (64–128 chunks per call) and embedding cache.
- Small-model routing for cheap tasks.
- `estimated_cost_usd` computed from a per-model price table in config; surfaced per feature/user/day in the admin dashboard (FR-81).

> Cost figures are **estimates derived from a configured price table**, explicitly labelled as such in the UI. No benchmark or spend numbers are invented in this document.

### 17.6 AI evaluation (FR-83, FR-84)

Three layers:

| Layer | When | What |
|---|---|---|
| **Offline regression suite** | CI on any change to prompts, models, retrieval, or chunking | Curated golden sets per suite, scored by rule-based checks + model-based grading; thresholds gate the merge |
| **Online sampling** | Continuous, ~5% of production AI requests *(configurable)* | Same metrics computed asynchronously on the `evaluation` queue; results into `ai_evaluations` |
| **Human review** | Ad hoc, via admin dashboard | Reviewer marks a sampled interaction; stored as `method='human'` — the ground truth that calibrates model-based grading |

Metrics by suite:

| Suite | Metrics |
|---|---|
| **Tutor** | Groundedness (claims supported by cited chunks), citation validity (cited chunk exists, was retrieved, page correct), answer relevance, **refusal correctness** on a deliberately unanswerable set |
| **Retrieval** | Recall@k and nDCG@k against labelled question→chunk pairs; source quality; sufficiency-classifier precision/recall |
| **Assessment** | Question quality (answerable from material, single defensible answer, difficulty calibration), grading agreement with human-labelled rubric scores, structured-output validity rate, **adaptivity check** (selected concepts correlate with low mastery, not with randomness) |
| **Recommendation** | Relevance to detected weaknesses, actionability (names a concrete artifact), alignment with learner state, non-repetition |

**Regression gate:** the CI job fails if any suite drops more than a configured delta against the stored baseline. This is the concrete answer to "changes to prompts, models, or retrieval can cause regressions" (§14).

**Guardrails and safety checks:** input classification for prompt-injection patterns; output checks for leaked system prompt, cross-project content (chunk ids outside the scope), PII echo, and unsupported claims. Violations are logged, blocked, and counted.

**Human-in-the-loop:** grading below a confidence threshold is flagged `pending_review` and the learner sees explicitly provisional feedback rather than a confident wrong score.

---

## 18. RAG Architecture

The Tutor's grounding pipeline. This is the requirement the PRD calls "a core evaluation requirement" (§7), so it is specified end to end.

### 18.1 Ingestion (build side)

```mermaid
flowchart TB
    UP["Upload confirmed<br/>(checksum, project_id)"] --> DEDUP{"Duplicate<br/>checksum in project?"}
    DEDUP -->|yes| REUSE["Link to existing material<br/>no reprocessing"]
    DEDUP -->|no| LOCK["Advisory lock on material_id"]
    LOCK --> FETCH["Fetch object from storage<br/>verify checksum + magic bytes"]
    FETCH --> PARSE["Native extraction (PyMuPDF)<br/>text, layout, tables, images, page map"]
    PARSE --> QC{"Page text<br/>sufficient?"}
    QC -->|no| OCR["OCR page image"]
    OCR --> QC2{"OCR sufficient?"}
    QC2 -->|no| VIS["Vision model:<br/>diagrams, scans, complex tables"]
    QC -->|yes| STRUCT
    QC2 -->|yes| STRUCT
    VIS --> STRUCT["Structure assembly<br/>sections, headings, tables, page anchors"]
    STRUCT --> CHUNK["Structure-aware chunking<br/>~500 tokens, 15% overlap,<br/>never across page without recording both pages"]
    CHUNK --> CONC["Concept extraction<br/>structured output, deduped per project"]
    CONC --> EMB["Batch embeddings<br/>store model + pipeline_version"]
    EMB --> IDX["Write chunks + tsvector + HNSW rows"]
    IDX --> READY["status = ready<br/>emit material.processed"]

    FETCH -.->|failure| FAIL["status = failed + reason<br/>retry w/ backoff, then DLQ"]
    PARSE -.->|failure| FAIL
    EMB -.->|failure| FAIL
```

**Chunking decisions that matter for citations:** chunks carry `page_start`/`page_end` and `section_path`. A citation is therefore always resolvable to a real page (`Source: Machine Learning Notes — Page 14`, exactly the PRD's example format), and the UI can deep-link to the rendered page image. Tables are chunked as units with their caption; figure captions are separate chunks tagged `figure_caption` so a question about a diagram retrieves the caption rather than a random paragraph.

**Idempotency:** re-running ingestion for a material deletes chunks of the old `pipeline_version` and rewrites — never partially appends. The advisory lock plus `job_runs.dedup_key` prevents concurrent duplicate runs (PRD §5).

### 18.2 Query side

```mermaid
flowchart TB
    Q["User question"] --> SAN["Sanitize + classify<br/>(injection patterns, intent)"]
    SAN --> ROUTE{"Needs retrieval?"}
    ROUTE -->|"meta/chit-chat/<br/>progress question"| NORET["Answer from learner state<br/>or tool call, no retrieval"]
    ROUTE -->|yes| REW["Query processing:<br/>resolve pronouns from conversation,<br/>expand acronyms, extract concept terms"]
    REW --> EMBQ["Embed query (cached)"]
    REW --> FTS["FTS query (tsquery)"]
    EMBQ --> VEC["Vector search<br/>WHERE project_id = :p<br/>HNSW top 30"]
    FTS --> LEX["Lexical search<br/>WHERE project_id = :p<br/>top 30"]
    VEC --> FUSE["Reciprocal Rank Fusion"]
    LEX --> FUSE
    FUSE --> DIV["Diversity filter:<br/>cap chunks per material/page"]
    DIV --> RR["Rerank top 30 -> top 6"]
    RR --> SUFF{"Sufficiency:<br/>top score >= tau AND<br/>>= 2 supporting chunks?"}
    SUFF -->|no| INSUFF["Insufficient-evidence path"]
    SUFF -->|yes| CTX["Context construction<br/>token budget, dedup, page labels"]
    CTX --> GEN["LLM generation<br/>citation contract enforced"]
    GEN --> VALC["Response validation:<br/>every [n] maps to a retrieved chunk"]
    VALC -->|invalid citation| STRIP["Drop/repair citation;<br/>if unsupported claims remain -> insufficiency"]
    VALC -->|valid| OUT["Answer + citations + sources panel"]
    INSUFF --> OUT2["Explicit: not covered by your materials<br/>+ what would help + optional general-knowledge offer"]
```

### 18.3 Why hybrid retrieval, not pure vector

Learning material is dense with **exact tokens** — formula names, acronyms (`ReLU`, `SGD`, `CAP`), API names, defined terms. Pure dense retrieval reliably misses exact-term matches; pure lexical misses paraphrase ("how does the model learn step by step?" → "gradient descent"). RRF fusion needs no score normalization between the two systems and is robust to scale differences. Reranking then fixes the precision problem that fusion leaves behind: the top-6 the model actually reads are chosen by a cross-encoder that sees the query and passage together, which is what makes citations trustworthy.

### 18.4 The insufficiency decision (FR-35)

Fabrication is prevented **structurally**, in three places, because prompt instructions alone are not a control:

1. **Pre-generation gate.** If the reranked top score is below threshold `tau`, or fewer than *N* chunks clear a floor, generation for a grounded answer never happens. The model is not given the chance to improvise.
2. **Prompt contract.** The system prompt states that every claim must be attributable to a numbered evidence block, and that the correct response to missing evidence is to say so. Output includes a machine-readable `answer_status`.
3. **Post-generation validation.** Every `[n]` marker is checked against the retrieved set; claims without citation markers in a grounded answer are flagged. If validation fails, the answer is downgraded to the insufficiency response rather than shipped.

The insufficiency response is *useful*, not a dead end: it names what the materials do cover, suggests uploading relevant material, offers a related concept that *is* covered, and offers an explicitly-labelled general-knowledge answer that the user must opt into — marked `answer_status='general_knowledge'` and visually distinct, never mixed with cited content.

**Thresholds** (`tau`, minimum supporting chunks, top-k, rerank depth) are configuration, tuned against the labelled evaluation set, never guessed in code. Their current values are recorded in `ai/config/retrieval.yaml` and every change must pass the regression gate.

### 18.5 Context construction and budget

Four sources, composed under an explicit token budget:

| Source | Budget share *(A-08)* | Selection |
|---|---|---|
| Retrieved evidence | ~55% | Reranked top-k, deduped, each block labelled `[n] {material title}, p.{page}` |
| Conversation | ~20% | Last N turns verbatim + rolling summary of everything earlier |
| Learning context | ~15% | Top `learning_context_items` by salience × recency, filtered to concepts relevant to this query |
| Learner state | ~10% | Goal, mastery for the concepts in play, recent mistakes on those concepts |

> **[ASSUMPTION A-08]** Budget proportions are a starting point, not a measured optimum. They are configuration and are tuned against the Tutor evaluation suite. *Why stated:* an unexplained magic ratio in code is exactly the kind of hidden assumption that makes later debugging hard.

This is the direct implementation of PRD §11: identify required context → select from Project / Knowledge / Conversation / Learning / Assessment → compose → generate. Nothing sends "the entire user history".

---

## 19. Agent Architecture

The PRD (§8) does not ask for an autonomous multi-agent system; it asks for **controlled AI–application interaction**. Over-engineering this into a fleet of agents would add nondeterminism, cost, and failure modes for no product benefit. The design is therefore a **single-agent, bounded tool-use loop** with a hard capability boundary.

```mermaid
flowchart TB
    U["User message"] --> ORCH["Tutor Orchestrator<br/>(bounded loop, max 4 steps)"]
    ORCH --> REASON["Model reasoning step<br/>with tool schemas"]
    REASON --> DECIDE{"Tool required?"}
    DECIDE -->|no| GENERATE["Generate grounded answer"]
    DECIDE -->|yes| REQ["Structured tool request<br/>{name, arguments}"]
    REQ --> REG{"Tool in registry<br/>and allow-listed for<br/>this feature?"}
    REG -->|no| DENY["Denied -> error result<br/>logged to tool_invocations"]
    REG -->|yes| SCHEMA{"Arguments valid<br/>against JSON Schema?"}
    SCHEMA -->|no| VERR["Validation error returned<br/>to model (1 retry)"]
    SCHEMA -->|yes| AUTHZ{"Authorized?<br/>principal + ProjectScope<br/>+ per-tool policy"}
    AUTHZ -->|no| DENY
    AUTHZ -->|yes| EXEC["Execute via ordinary<br/>domain service (RLS applies)"]
    EXEC --> VALRES["Validate + shape result<br/>(size cap, redact, mark as DATA)"]
    VALRES --> AUDIT["Record tool_invocations"]
    AUDIT --> ORCH
    GENERATE --> OUT["Response to user"]
    DENY --> ORCH
    VERR --> ORCH
```

### 19.1 The capability boundary

The model **never** receives a database connection, an internal service object, raw SQL, or a generic "run this" tool. It sees a fixed catalogue of narrow, typed capabilities:

| Tool | Arguments | Authorization | Effect |
|---|---|---|---|
| `search_materials` | query, k≤10, material_id? | project read | Read-only retrieval within scope |
| `get_learning_progress` | concept_ids? | project read | Mastery summary |
| `get_assessment_history` | limit≤20, concept_id? | project read | Past quiz performance |
| `identify_weak_concepts` | limit≤10 | project read | Deterministic weakness query |
| `generate_quiz` | concept_ids, count≤10, types | project write | Creates a quiz session (idempotent by dedup key) |
| `record_learning_event` | type, payload (enum-constrained) | project write | Appends an activity event |
| `update_learning_context` | kind, content, concept_id?, salience | project write, **content length-capped, schema-validated** | Upserts a learning context item |
| `generate_recommendation` | concept_ids, kind, rationale | project write, dedup-keyed | Creates a recommendation draft |

Each maps one-to-one to a capability the PRD lists in §8. There are no others.

### 19.2 Control rules

1. **Bounded loop.** Maximum tool steps per turn (default 4) and a wall-clock budget; exceeding either ends the turn with the best available answer plus a note.
2. **Feature-scoped allow-lists.** The Tutor may not call `generate_quiz` unless the user asked for practice; the quiz generator cannot call `update_learning_context`. The allow-list is per feature, not global.
3. **Read before write.** Write-capable tools require the reasoning step to have produced a justification field that is persisted with the invocation.
4. **Scope is injected, never argued.** `project_id` and `user_id` come from `ProjectScope` on the server. A model-supplied `project_id` argument is rejected outright — this closes the obvious confused-deputy path.
5. **Results are data.** Tool results are inserted into the conversation inside a delimited, labelled block with instruction-neutralizing framing; a tool result can never introduce new instructions.
6. **No tool call may originate from retrieved content.** If retrieved material contains something resembling a tool directive, it is inert text — the loop only considers tool calls emitted in the model's own tool-call channel, and retrieved content never reaches that channel.
7. **Everything audited.** Every invocation — authorized or denied — lands in `tool_invocations` with arguments, outcome, and latency (FR-40, FR-41).

> Pattern honesty: this loop is deliberately *less* agentic than it could be. Adding planner/critic agents would improve nothing the PRD asks for, and each extra model call multiplies latency, cost, and the surface for nondeterministic failure. Section 42 records what would justify a richer agent design.

### 19.3 Adaptive selection is code, not an agent

The PRD explicitly rejects naive adaptivity (§9). The selection policy is deterministic and testable:

```text
score(concept) =
      w1 * (1 - mastery)                      # prefer weak areas
    + w2 * uncertainty(confidence)            # prefer low-evidence concepts (information gain)
    + w3 * recency_decay(last_evidence_at)    # revisit fading knowledge (spaced repetition)
    + w4 * importance(concept)                # material-weighted importance
    + w5 * mistake_recency(concept)           # recent errors matter more
    - w6 * over_practice_penalty(concept)     # avoid hammering one concept
    - w7 * question_history_penalty(concept)  # avoid repeating near-identical questions

difficulty_target = clamp(mastery + delta, 0, 1)   # slightly above current estimate
```

Concept selection and difficulty targeting are pure functions over stored evidence — unit-testable, explainable in the UI ("asked because X"), and stable across model changes. The LLM's job is only to *write* a question at the requested concept and difficulty, grounded in that concept's chunks. This separation is the difference between an adaptive system and a system that merely feels random.

Mastery updating likewise uses a **Bayesian-Knowledge-Tracing-style update** with evidence strength weighting (question difficulty, answer quality, partial credit from open-ended rubric scores) and time decay, recomputed as a pure function of `mastery_events`. Deterministic, replayable, and auditable — mastery never depends on what a model felt like outputting.

---

## 20. External Integrations

| Integration | Purpose | Failure mode | Mitigation |
|---|---|---|---|
| **LLM provider (primary)** | Tutor, grading, question generation, recommendations | Timeout, 429, 5xx, degraded quality | Timeout + bounded retry with jitter; circuit breaker; fallback to secondary provider/model; user-visible degradation; async work retried later |
| **LLM provider (fallback)** | Continuity when primary is down | Same | Different vendor where possible so outages are uncorrelated; `fallback_from` recorded for transparency |
| **Embedding provider** | Chunk + query embeddings | Outage blocks ingestion and dense retrieval | Ingestion queued and retried (no data loss); **retrieval degrades to lexical-only** and the answer is marked reduced-confidence |
| **Reranker** | Precision of top-k | Outage | Skip rerank, use fused order, raise sufficiency threshold to compensate; metric recorded |
| **OCR / vision** | Scanned pages, diagrams, complex tables | Outage or poor output | Page marked `extraction_method` failure; document still processes with available pages; partial-quality flag on the material |
| **Object storage** | Source PDFs, page images | Outage | Uploads fail fast with a clear message; existing chunks still serve the Tutor (text is in Postgres), only source previews degrade |
| **Error tracking (Sentry or equivalent)** | Exception aggregation | Outage | Fire-and-forget; never blocks a request |
| **Telemetry backend (OTLP)** | Traces/metrics/logs | Outage | Buffered export, drop on overflow; never blocks |
| **Email provider** *(Phase 1)* | Verification, password reset | Outage | Queue and retry; account usable pending verification per A-04 |

**Integration rules:** every external call goes through a client wrapper with timeout, retry policy, circuit breaker, and metrics — no bare SDK calls in domain code. All provider credentials come from the secrets manager. Every integration has a documented degraded mode (Section 35); "the provider is down so the product is down" is not an acceptable answer for anything except Postgres.


---

## 21. Security Architecture

Security is a stated core requirement (PRD §15). Controls are organized by layer; each one exists for a named reason.

```mermaid
flowchart TB
    subgraph zone0["Public Zone"]
        USR["User browser"]
    end
    subgraph zone1["Edge / DMZ"]
        TLS["TLS 1.3 termination"]
        WAF["WAF: OWASP rules, bot + DDoS controls"]
        RL["Global rate limiting"]
    end
    subgraph zone2["Application Zone (private subnet)"]
        AUTHN["Authentication<br/>JWT RS256 verify, session denylist"]
        AUTHZ["Authorization<br/>role + ownership + ProjectScope"]
        VALID["Input validation<br/>Pydantic, size caps, content-type checks"]
        SVC["Domain services"]
        TOOLG["Tool guard<br/>schema + allow-list + audit"]
        AIG["AI Gateway<br/>injection defence, output validation"]
    end
    subgraph zone3["Data Zone (private subnet, no internet ingress)"]
        PGS[("Postgres<br/>RLS, TLS, encrypted at rest")]
        RDS[("Redis<br/>auth, TLS, private")]
        OBJ[("Object storage<br/>private bucket, SSE, presigned only")]
    end
    subgraph zone4["External"]
        PROV["Model providers"]
    end

    USR -->|HTTPS| TLS --> WAF --> RL --> AUTHN --> AUTHZ --> VALID --> SVC
    SVC --> TOOLG --> PGS
    SVC --> AIG -->|egress allow-list| PROV
    SVC --> PGS
    SVC --> RDS
    SVC -->|presigned URL issuance| OBJ
    USR -.->|"direct upload/download<br/>via short-lived presigned URL"| OBJ
```

### 21.1 Authentication and session security

Covered in Section 12.1. Additional controls: login rate limiting per IP **and** per account (credential stuffing), constant-time comparisons, generic error messages (no user enumeration), Argon2id parameters set from a benchmarked target, refresh-token reuse detection revoking the session family, and session listing/revocation in user settings *(Phase 1)*.

### 21.2 Authorization

RBAC + ownership ABAC (Section 12.2), enforced in route guards, service methods, the tool layer, background jobs, and Postgres RLS. `404` instead of `403` on non-owned resources so existence is not disclosed.

### 21.3 API security

| Control | Implementation |
|---|---|
| Transport | TLS 1.3 only; HSTS with preload; no plaintext listener |
| CORS | Explicit origin allow-list per environment; credentials allowed only for the known frontend origin; no wildcard |
| CSRF | Access token is a Bearer header (not ambient), so the primary API surface is not CSRF-prone. The **refresh cookie is `SameSite=Strict`** and `/auth/refresh` additionally requires an `X-Requested-With` header — belt and braces for the one cookie-authenticated endpoint |
| Rate limiting | Redis token bucket, tiered: global per IP, per user, and stricter per-AI-endpoint (Tutor/quiz) because those cost money as well as CPU |
| Request size | Body caps per route; PDF size cap enforced at presign time and re-checked server-side |
| Security headers | CSP (no inline scripts, nonce-based), X-Content-Type-Options, Referrer-Policy, Permissions-Policy, X-Frame-Options |
| Injection | SQLAlchemy parameterization exclusively; no string-built SQL; allow-listed sort/filter fields; JSONB values never interpolated |
| Mass assignment | Separate input schemas from ORM models; server-controlled fields (`owner_id`, `role`, `status`) never bindable from a request body |

### 21.4 File upload security (PRD §15 "secure document handling")

1. Presigned PUT with **content-type and size constraints in the policy**, short expiry, and a server-generated key (`projects/{project_id}/{uuid}.pdf`) — the client never chooses a path.
2. On confirmation: verify object exists, size matches, **magic bytes are `%PDF`** (never trust the declared content type or extension), and compute a checksum.
3. Parse in the worker with resource limits (page cap, time limit, memory limit) so a decompression-bomb or deeply nested PDF kills a task, not the API.
4. PDFs are never rendered inline from a user-controlled origin; downloads use short-lived presigned URLs with `Content-Disposition: attachment` and a separate storage domain.
5. Buckets are private, block-public-access on, server-side encrypted; no object is ever world-readable.
6. *(Phase 1)* Anti-malware scan step before processing; the pipeline already has the right insertion point.

### 21.5 Data protection

- **In transit:** TLS everywhere including app↔Postgres and app↔Redis.
- **At rest:** managed-service encryption for database, cache, and object storage; disk-level encryption for any self-managed component.
- **Application-level:** password hashes (Argon2id), refresh tokens stored hashed, IPs stored as salted hashes in audit records.
- **Secrets:** never in code or images; injected at runtime from a secrets manager; rotated on a schedule; a CI secret-scanning step (gitleaks) fails the build on any credential-shaped string. This document itself uses placeholders only (Section 31).
- **PII minimization:** the only PII collected is email and display name. Learner content is treated as sensitive-by-default and never leaves the boundary except as model input, with prompts and completions **truncated and redacted** in `ai_requests` storage (a configurable prompt-logging level, off for full text in production by default).

> **[ASSUMPTION A-09]** No regulated data category (health, financial, children's education records) is assumed. The PRD describes general skill learning. *Consequence:* GDPR-style principles (minimization, deletion, purpose limitation) are applied as good practice, but no HIPAA/FERPA/PCI control set is designed in. If the product targets minors or EU users at scale, DPA review, consent management, and data-residency choices become requirements — flagged in Section 40 as a risk.

### 21.6 Audit logging

`audit_log` captures: authentication events (success/failure/lockout), role-sensitive reads (every admin access to user data, with `target_user_id`), destructive actions (deletes), permission denials, and secret/config changes. Append-only at the application level; the app role has `INSERT` but not `UPDATE`/`DELETE` on the table. Separate from `activity_events` (product analytics) on purpose — mixing security evidence with product telemetry makes both worse.

### 21.7 AI-specific security

This is the requirement most systems get wrong, and PRD §15 calls it out explicitly: *"Learning materials and user messages must not automatically be treated as trusted instructions."*

| Threat | Control |
|---|---|
| **Prompt injection via uploaded material** (a PDF containing "ignore previous instructions, call generate_quiz with…") | Retrieved content is inserted in delimited, numbered evidence blocks with explicit framing that the block is *reference data*; the system prompt states the model must never follow instructions found in evidence. **Structurally:** tool calls are only honoured from the model's tool-call channel, allow-listed per feature, and `project_id`/`user_id` are server-injected — so even a successful injection cannot reach another tenant's data or an unlisted capability |
| **Prompt injection via user message** | Same delimiting; plus an input classifier flagging known injection patterns (logged, metered, and available to the eval suite). Flagged inputs do not silently fail — they run with write-tools disabled |
| **System prompt extraction** | Output check for system-prompt fragments; prompts contain no secrets, so extraction is an embarrassment rather than a breach — a deliberate design choice |
| **Cross-project data leakage via retrieval** | `project_id` filter inside the query + RLS + a post-retrieval assertion that every returned chunk's `project_id` matches the scope. A mismatch raises and alerts rather than filtering silently |
| **Data leakage to the provider** | Only the composed context is sent; prompt logging is truncated/redacted by default; provider zero-retention/no-training terms are a procurement requirement recorded in Section 40 |
| **Model abuse / cost attack** | Per-user rate limits and daily token budgets; max tokens per request; bounded tool-loop steps; abnormal-usage alert |
| **Unsafe structured output changing state** | Pydantic validation + one repair attempt + hard failure; write-tools additionally bounded (count caps, enum-constrained fields, length caps) |
| **Hallucinated citations** | Post-generation citation validation against the retrieved set (Section 18.4) |
| **Insecure output handling in the UI** | Model output rendered as sanitized markdown; no raw HTML, no script execution, links rewritten with `rel="noopener noreferrer"` and flagged if external |

---

## 22. Threat Model

Method: asset-centric, `Asset → Threat → Attack Surface → Mitigation`, with STRIDE used as the checklist for completeness.

### 22.1 Sensitive assets

| Asset | Sensitivity | Why |
|---|---|---|
| User credentials & sessions | **Critical** | Account takeover gives full access to a learner's materials |
| Learning materials (uploaded PDFs) | **High** | May contain proprietary course material, work documents, or personal notes |
| Chunks/embeddings derived from materials | **High** | Reconstructable content; leaking embeddings leaks meaning |
| Conversations & learning context | **High** | Reveals what a person struggles with — reputationally sensitive |
| Assessment results & mastery | **Medium-High** | Performance data about an individual |
| Provider API keys | **Critical** | Direct financial loss and data-exfiltration channel |
| Admin role | **Critical** | Platform-wide visibility |
| AI request logs | **Medium** | May contain excerpts of learner content |

### 22.2 Threat table

| # | Asset | Threat | Attack surface | Mitigation |
|---|---|---|---|---|
| T1 | Credentials | Credential stuffing / brute force | `/auth/login` | Per-IP + per-account rate limits, Argon2id, generic errors, lockout with backoff, alerting on failure spikes |
| T2 | Sessions | Token theft / replay | Refresh cookie, XSS | HttpOnly+Secure+SameSite=Strict, rotation with reuse detection, short access TTL, strict CSP, sanitized rendering |
| T3 | Any tenant data | **Horizontal privilege escalation** (IDOR) | Every `/{resource_id}` route | Ownership guard → 404, RLS at the DB, isolation test suite covering every endpoint |
| T4 | Chunks | Cross-project retrieval leakage | Retrieval filters, tool args | Filter inside query, server-injected scope, post-retrieval assertion, alert on mismatch |
| T5 | Database | SQL injection | Any user-influenced query | Parameterized ORM, allow-listed sort/filter, no dynamic SQL, SAST in CI |
| T6 | Upload pipeline | Malicious/bomb PDF, path traversal | Presigned upload + worker parse | Server-generated keys, magic-byte check, size/page/time/memory limits in an isolated worker, private bucket, (Phase 1) AV scan |
| T7 | AI layer | **Prompt injection → unauthorized action** | Material content, user messages, tool results | Instruction/data separation, tool allow-list, server-injected scope, bounded loop, audit; injection cannot widen authorization because authorization is not model-controlled |
| T8 | AI layer | Data exfiltration via crafted prompt | Tutor | Scope-filtered retrieval, no tool returning other users' data exists, output cross-project assertion |
| T9 | Provider budget | Cost/DoS abuse | Tutor and quiz endpoints | Per-user budgets, endpoint rate limits, max tokens, anomaly alerting, circuit breaker |
| T10 | Availability | Application-layer DDoS | Public endpoints | WAF, edge rate limiting, autoscaling, cheap `/healthz`, expensive endpoints authenticated only |
| T11 | Secrets | Key leakage | Repo, images, logs | Secrets manager, gitleaks in CI, redacting log formatter, no secrets in images, rotation |
| T12 | Supply chain | Malicious dependency / base image | `requirements`, `package.json`, Docker base | Pinned versions + lockfiles, `pip-audit`/`npm audit`, Trivy image scan, Dependabot, SBOM generated at build |
| T13 | Admin plane | Insider abuse / over-broad access | `/admin/*` | Read-only (A-01), metadata-only over content (A-05), every access audited with `target_user_id`, alert on bulk access patterns |
| T14 | Integrity of learning state | Forged mastery/progress | Tool writes, API writes | Server-computed mastery only, tool writes constrained and audited, mastery derived from append-only evidence |
| T15 | Backups | Backup exfiltration | Snapshot storage | Encrypted at rest, access-controlled, separate credentials, restore drills logged |

### 22.3 STRIDE coverage check

| STRIDE | Covered by |
|---|---|
| Spoofing | T1, T2 (auth, session rotation) |
| Tampering | T5, T6, T14 (validation, immutability, server-computed state) |
| Repudiation | Audit log, `tool_invocations`, `ai_requests` with request/trace ids |
| Information disclosure | T3, T4, T8, T13 (isolation at four layers, admin minimization) |
| Denial of service | T9, T10 (rate limits, budgets, bulkheads, circuit breakers) |
| Elevation of privilege | T3, T7, T13 (server-injected scope, allow-lists, read-only admin) |

---

## 23. Performance Architecture

**No benchmark numbers are invented.** The PRD specifies no performance requirements ("performance should be appropriate for a prototype", §15), so what follows is a set of **targets with a stated basis and a measurement method**.

### 23.1 Latency targets

| Operation | Target (p95) | Basis | Measurement |
|---|---|---|---|
| Auth, CRUD, dashboard reads | < 300 ms | Interactive UI feel; achievable with indexed queries + rollups | API histogram by route |
| Upload confirmation (returns job id) | < 500 ms | Only a DB write + enqueue | API histogram |
| Retrieval pipeline (embed + hybrid + rerank) | < 800 ms | Dominated by two network calls (embed, rerank) + two indexed queries | Span-level timing in trace |
| Tutor **time to first token** | < 2.5 s | Retrieval + provider TTFT; the number users actually feel | `ai_requests.time_to_first_token_ms` |
| Tutor full answer | Streamed; no hard target | Length-dependent; TTFT is the meaningful metric | — |
| MCQ scoring | < 150 ms | Deterministic, no model call | API histogram |
| Open-ended grading | < 6 s | Single structured model call | `ai_requests.latency_ms` |
| Document processing (≤50 pages, native text) | < 2 min | Parse + chunk + batched embeddings | Job duration metric |
| Document processing (scanned, OCR) | < 8 min | OCR is the dominant cost | Job duration metric |
| Analytics queries | < 1 s | Served from rollups, not live aggregation | API histogram |

> **[ASSUMPTION A-10]** These are engineering targets set from the interaction model, not measured results and not contractual SLOs. They exist so that regressions are detectable. Each becomes a dashboard panel on day one; any that proves unrealistic is revised with the measurement that disproved it, not quietly dropped.

### 23.2 Throughput and concurrency

> **[ASSUMPTION A-11]** No user-count requirement exists. The architecture is sized for **low hundreds of concurrent users** in Phase 0 (a prototype with reviewers and demo traffic), with a clear scaling path (Section 24) rather than a fixed capacity claim. *Why this matters architecturally:* it justifies a modular monolith, a single Postgres instance, and Redis-backed Celery — all of which would be wrong at 10,000 concurrent users and are right here.

Concurrency notes:
- FastAPI async means one worker process handles many in-flight provider calls; the bottleneck is provider rate limits, not local CPU.
- Streaming responses hold a connection for the duration of an answer; connection concurrency, not CPU, sizes the API tier. Keep-alive and timeouts are tuned accordingly (Section 28).
- DB connection pool is sized against Postgres `max_connections` with headroom; **PgBouncer in transaction mode** is introduced when replica count grows (Section 24.3), not before.

### 23.3 Techniques applied

| Technique | Where | Effect |
|---|---|---|
| Streaming | Tutor | Turns a multi-second wait into a sub-3-second perceived response |
| Precomputed rollups | All dashboards/analytics | Removes aggregation from the request path |
| Cursor pagination | Lists, activity feeds | Constant-cost paging; no deep-offset scans |
| Parallel retrieval | Vector + lexical issued concurrently | Roughly halves retrieval wall time |
| Embedding + retrieval caching | Repeated/similar queries | Removes an entire provider round trip |
| Batched embeddings | Ingestion | Far fewer provider calls per document |
| Small-model routing | Rewriting, routing, extraction | Cuts latency and cost where quality headroom exists |
| Avoiding unnecessary AI calls (PRD §15) | Intent router; deterministic paths for MCQ scoring, mastery, adaptive selection, trend classification | The cheapest model call is the one not made |
| Async offloading | Ingestion, post-quiz chain, analytics | Nothing slow is on the user's path |
| Index discipline | Section 14.3 | Every hot query has a matching index |

### 23.4 Large file and batch processing

Documents stream from object storage to the worker's temp dir, are processed page-by-page (bounded memory), and produce batched inserts. Page caps and time limits are enforced; oversized documents fail fast with an actionable message rather than silently consuming a worker for an hour. Embedding generation is chunked into batches with backpressure — if the provider rate-limits, the task retries with backoff rather than hammering.

---

## 24. Scalability Architecture

### 24.1 Scaling axes and the response to each

| Axis | Symptom | Response | Type |
|---|---|---|---|
| **More users / requests** | API CPU or connection saturation | Add API replicas behind the load balancer; the API is stateless (sessions in DB/Redis, no local files, SSE state in Redis pub/sub) | Horizontal |
| **More documents** | `documents` queue depth grows, processing lag | Add `documents` workers; they scale independently of the API | Horizontal |
| **More AI workload** | Provider rate limits, cost spikes, `learning` queue lag | Add `learning` workers up to provider limits, then: request coalescing, tiered models, per-user budgets, provider capacity increase | Horizontal + policy |
| **More data** | Slower retrieval and analytics | HNSW parameter tuning → per-project partial indexes → table partitioning → dedicated vector store (ADR-003) | Vertical → architectural |
| **More concurrent streams** | Connection exhaustion on API | Raise per-replica connection limits, add replicas, tune keep-alive; SSE is cheap per connection | Horizontal |
| **Heavier analytics** | Dashboard latency | Deeper rollups → read replica for analytics → columnar store (trigger in 13.3) | Vertical → architectural |

### 24.2 Horizontal vs vertical, stated plainly

- **Horizontal first for compute** (API and workers): both are stateless, so replicas are a configuration change. This is the cheap axis and the one used for ordinary growth.
- **Vertical first for Postgres**: a single well-tuned Postgres handles this workload far beyond the prototype, and vertical scaling costs no architectural complexity. Sharding is a last resort, not a milestone.
- **Read replicas before sharding**: analytics and admin reads move to a replica (they tolerate replication lag); transactional reads stay on the primary.
- **What is deliberately *not* scaled**: the number of services. Adding services is an organizational and operational decision (ADR-001), not a performance one.

### 24.3 Statelessness checklist

| Component | State | Where it lives |
|---|---|---|
| API | none local | Postgres, Redis, object storage |
| Worker | none local | task payload + Postgres; temp files deleted per task |
| SSE stream | conversation channel | Redis pub/sub, so any replica can serve a reconnect |
| Sessions | refresh tokens | Postgres (hashed) + Redis denylist |
| Rate limits / idempotency | counters, records | Redis |
| Uploads | file bytes | Object storage (never the app disk) |

### 24.4 Bottleneck order (honest assessment)

In this design, the limits are hit in this order: **(1) provider rate limits and cost**, (2) `documents` worker CPU during ingestion bursts, (3) Postgres write throughput on `activity_events`, (4) vector search latency as chunk count grows, (5) API CPU. This ordering is why cost controls, queue separation, event partitioning, and the vector-store trigger appear early in the design and API autoscaling appears late.

---

## 25. Reliability & Resilience

### 25.1 Patterns and where each is used

| Pattern | Applied at | Why there |
|---|---|---|
| **Timeout** | Every external call: LLM (30 s generate / 60 s grade), embeddings (15 s), rerank (5 s), OCR (120 s/page), DB statement (`statement_timeout` 10 s API / 300 s worker), HTTP client defaults | An unbounded wait is how one slow dependency becomes total unavailability |
| **Retry with exponential backoff + jitter** | Idempotent provider calls (max 2 in-request), Celery tasks (3–5 attempts), transient DB serialization failures | Most provider failures are transient; jitter prevents synchronized retry storms |
| **Circuit breaker** | Per provider per operation (open after N failures in a window, half-open probe) | Stops burning latency and budget on a dependency that is already down; enables fast fallback |
| **Fallback chain** | LLM: primary model → secondary model → different provider → deterministic/degraded response; Rerank: skip with raised threshold; Embedding: lexical-only retrieval | The PRD requires graceful handling of provider failure (§15) |
| **Bulkhead** | Separate Celery queues; separate worker deployments; separate connection pools for API vs workers; tool-loop step cap | One overloaded workload cannot starve another |
| **Rate limiter** | Edge, per-user, per-AI-endpoint, per-provider client | Protects both the system and the budget |
| **Idempotency** | `Idempotency-Key` on mutating POSTs; `job_runs.dedup_key`; `processed_events`; unique constraints on `mastery_events`, `answers`, `recommendations` | Retries are guaranteed to happen; duplicate state must not be (NFR-02) |
| **Dead-letter queue** | After max attempts, with `job_runs.status='dead_lettered'` and admin replay | Failures become visible work items instead of silence |
| **Graceful degradation** | Section 35 matrix | The product should lose features, not availability |
| **Health checks** | `/healthz` (liveness, no dependencies), `/readyz` (DB + Redis), worker heartbeat | Correct separation prevents a DB blip from restart-looping healthy pods |
| **Backpressure** | Queue depth thresholds pause non-critical producers (eval sampling first, then analytics); upload accepted but queued with a visible wait estimate | Shedding the right load keeps the core loop alive |
| **Failover** | Managed Postgres with standby; multi-AZ; Redis with replica | Infrastructure-level redundancy without application complexity |

### 25.2 Timeout budget (Tutor turn)

Timeouts are composed so that the outer budget is never exceeded by inner retries:

```text
Client request budget          60 s (SSE)
└─ API handler budget          50 s
   ├─ Retrieval                 6 s   (embed 15s cap → 4s budget; searches 1s; rerank 5s cap → 2s budget)
   ├─ Context composition       1 s
   └─ Generation               35 s   (30 s primary; on circuit-open, fallback gets the remainder)
   └─ Persistence + events      2 s   (finalizer runs even if the client disconnects)
```

Inner retries are only permitted when the remaining budget allows a full attempt — otherwise the call fails fast into the fallback. This "deadline propagation" is what stops retries from turning a 30-second timeout into a three-minute hang.

### 25.3 Availability design

> **[ASSUMPTION A-12]** No availability target is given in the PRD. Targets: **Phase 0 (prototype) ~99% — single-region, managed services, brief deploy interruptions acceptable**; **Phase 1 (production) 99.9% monthly for the core learning loop**, with AI-dependent features excluded from the target since they depend on third parties whose availability we do not control. Stating this separation is deliberate: promising 99.9% on a feature that calls an external LLM would be a promise about someone else's uptime.

Failure isolation: API and workers fail independently; a worker crash delays background work but never breaks browsing or the Tutor; a provider outage degrades AI features while CRUD, analytics, mastery, and history continue to work.

---

## 26. Observability

The three pillars, wired to the PRD's actual investigative questions (§14).

```mermaid
flowchart LR
    subgraph sources["Instrumented Sources"]
        A["FastAPI"]
        W["Celery workers"]
        G["AI Gateway"]
        DB["Postgres exporter"]
        R["Redis exporter"]
    end
    subgraph pipeline["Collection"]
        OC["OpenTelemetry SDK<br/>+ OTLP exporter"]
    end
    subgraph backends["Backends"]
        TR["Traces"]
        ME["Metrics"]
        LO["Logs"]
        SEN["Error tracking"]
        AIDB[("ai_requests / ai_evaluations<br/>in Postgres")]
    end
    subgraph consumers["Consumers"]
        DASH["Ops dashboards"]
        ALERT["Alerting"]
        ADMIN["Admin Dashboard<br/>(AI usage, eval, jobs, health)"]
    end

    A --> OC
    W --> OC
    G --> OC
    G --> AIDB
    DB --> ME
    R --> ME
    OC --> TR
    OC --> ME
    OC --> LO
    A --> SEN
    W --> SEN
    TR --> DASH
    ME --> DASH
    LO --> DASH
    ME --> ALERT
    LO --> ALERT
    AIDB --> ADMIN
    ME --> ADMIN
```

### 26.1 Correlation model

One `request_id` and one W3C `trace_id` are generated at the edge and propagated through: HTTP response headers → structured logs → OTel spans → **Celery task headers** (so async work joins the same trace) → `ai_requests.trace_id` → `activity_events` correlation id. Given anything a user can see (a request id in an error message), an engineer can reconstruct the whole causal chain including background work. That is what makes FR-82 answerable rather than aspirational.

### 26.2 Distributed tracing

Even in a monolith, tracing matters here because a single user action fans out across provider calls and later background tasks. Span structure for a Tutor turn:

```text
POST /conversations/{id}/messages            [root span]
├── auth.verify
├── authz.project_scope
├── context.compose
│   ├── retrieval.embed_query          (ai.operation=embed, model, tokens)
│   ├── retrieval.vector_search        (db, k, latency)
│   ├── retrieval.lexical_search
│   ├── retrieval.fuse_rerank          (ai.operation=rerank, scores)
│   ├── retrieval.sufficiency          (decision, top_score, tau)
│   ├── context.conversation_window
│   └── context.learning_items         (count, salience range)
├── ai.generate                        (provider, model, prompt_version, ttft, tokens, cost)
├── validation.citations               (markers, valid, dropped)
└── persist.message                    (+ outbox event id)
    └── [async, linked span] tutor.post_process → analytics.record → eval.sample
```

Sampling: 100% of errors, 100% of AI-feature requests *(prototype volume makes this affordable and the debugging value is high)*, 10% of routine CRUD.

### 26.3 The AI observability question list (FR-82)

| Question | Answered by |
|---|---|
| Why was an AI response slow? | Trace span breakdown: retrieval vs provider TTFT vs validation; `ai_requests.latency_ms` and `time_to_first_token_ms` |
| Which model was used? | `ai_requests.provider/model/prompt_version`, including `fallback_from` if it fell back |
| Why did retrieval return poor context? | `retrieval_meta`: query used, strategy, k, chunk ids, scores, rerank order, sufficiency decision — replayable against the same corpus |
| Which AI workflow failed? | `ai_requests.status` + `error_type`, joined to `job_runs` and trace |
| How much did a request cost? | `estimated_cost_usd`, rolled up by feature/user/day |
| Why did document processing fail? | `materials.failure_reason` + `job_runs.error_type` + worker span + page-level extraction method |

---

## 27. Logging & Monitoring

### 27.1 Logs

**Format:** structured JSON, one event per line, with `timestamp, level, message, service, env, version, request_id, trace_id, span_id, user_id, project_id, route, status, duration_ms`. Never free-text-only logs — they cannot be queried.

| Stream | Contents | Retention *(A-06)* |
|---|---|---|
| Application | Request lifecycle, service decisions, degradations, cache/circuit state changes | 30 days |
| Error | Unhandled exceptions with stack traces and correlation ids (also to error tracking) | 90 days |
| Security | Auth outcomes, denials, rate-limit trips, injection-classifier hits, admin access | 12 months |
| Audit | `audit_log` table (queryable, not just log lines) | 12 months hot |
| AI | One record per model call in `ai_requests` + a log line with the identifiers | 90 days detail |
| Job | Task start/finish/retry/DLQ in `job_runs` + log lines | 30 days |

**Redaction is enforced in the log formatter**, not left to call sites: passwords, tokens, cookies, API keys, and (per config) prompt/completion bodies are filtered centrally. A single careless `logger.info(request.body)` should not be able to leak a credential.

### 27.2 Metrics

| Category | Metrics |
|---|---|
| **RED (per route)** | Request rate, error rate (4xx/5xx separated), duration histogram |
| **USE (per container)** | CPU, memory, restarts, event-loop lag |
| **Database** | Connection pool usage/saturation, query duration p95, slow-query count, deadlocks, replication lag, table/index bloat |
| **Cache** | Hit ratio per cache namespace, evictions, latency, connection errors |
| **Queues** | Depth per queue, oldest-message age, task duration, retry count, failure rate, DLQ size, worker heartbeat |
| **AI** | Requests per feature, latency p50/p95, TTFT, tokens in/out, estimated cost per feature/hour, error rate by type, fallback rate, circuit state, structured-output validity rate, **retrieval sufficiency rate**, **citation validity rate**, refusal rate |
| **Learning (product)** | Documents processed, processing success rate, tutor turns, quizzes completed, mastery updates, recommendations generated/accepted |
| **Security** | Failed logins, lockouts, 403/404-on-owned-resource anomalies, injection-classifier hits, rate-limit trips, admin access volume |

Product metrics sit alongside system metrics deliberately: a drop in "documents processed successfully" is an incident even when CPU and error rates look perfect.

### 27.3 Alerts

| Alert | Condition | Severity | First response |
|---|---|---|---|
| API error rate | 5xx > 2% over 5 min | **P1** | Check recent deploy, DB health, provider status |
| Readiness failing | `/readyz` failing on >1 replica for 2 min | **P1** | Check Postgres/Redis connectivity |
| Database saturation | Pool usage > 85% for 5 min, or replication lag > 30 s | **P1** | Check slow queries, connection leaks |
| Queue backlog | `documents` oldest message age > 15 min | **P2** | Scale workers; check provider/OCR health |
| DLQ growth | Any new dead-lettered job | **P2** | Inspect `job_runs`, decide replay vs fix |
| AI provider errors | Error rate > 20% over 10 min for a feature | **P2** | Confirm circuit breaker opened and fallback engaged |
| Circuit breaker open | Any provider circuit open > 5 min | **P2** | Provider status; consider switching primary |
| Cost anomaly | Hourly estimated spend > 3× trailing 7-day hourly mean | **P2** | Identify feature/user; check for abuse or a prompt regression |
| Grounding regression | Citation validity or sufficiency rate drops > 10 pts day-over-day | **P2** | Diff prompt/model/retrieval config; run eval suite |
| Structured-output validity | < 95% for a feature over 1 h | **P2** | Check model/schema drift |
| Auth anomaly | Failed logins > 10× baseline, or one account > 20 failures/10 min | **P2** | Possible credential stuffing; tighten limits |
| Admin bulk access | One admin reads > 50 distinct users in 10 min | **P2** | Insider-threat check (T13) |
| Certificate expiry | < 14 days | **P3** | Renew |

Alert discipline: every alert names a first response. An alert nobody knows how to act on gets deleted, not muted.

### 27.4 Dashboards

1. **Service health** — RED per route, container USE, dependency status.
2. **Data layer** — connections, slow queries, cache hit ratio, replication lag.
3. **Async pipeline** — queue depths, task durations, retries, DLQ, processing funnel (uploaded → processing → ready → failed).
4. **AI operations** — per feature: volume, latency, TTFT, cost, error and fallback rates, circuit state.
5. **AI quality** — groundedness, citation validity, refusal correctness, retrieval nDCG, grading agreement — trended against prompt/model versions.
6. **Product/learning** — active users, projects created, tutor turns, quizzes, mastery movement, recommendation acceptance.

Dashboards 4–6 are also the data source for the Admin Dashboard's AI and system-health views (FR-90), which reads aggregates from Postgres rather than embedding an external monitoring tool — consistent with the PRD's framing of the admin panel as a lightweight operational and product view, not an infrastructure monitoring replacement (§16).

---

## 28. Infrastructure Architecture

Designed **cloud-neutral**, with an AWS mapping given because the PRD does not specify a cloud.

### 28.1 Logical infrastructure

```mermaid
flowchart TB
    subgraph internet["Internet"]
        USERS["Users"]
    end
    subgraph edgez["Edge"]
        DNS["DNS"]
        CDNX["CDN (static assets, images)"]
        WAFX["WAF + TLS"]
        LBX["Load Balancer"]
    end
    subgraph vpc["VPC"]
        subgraph pub["Public subnets"]
            LBN["LB nodes / NAT gateway"]
        end
        subgraph privapp["Private subnets — application"]
            FE1["Frontend container xN"]
            API1["API container xN"]
            WRK1["Worker containers<br/>documents / learning / analytics / evaluation"]
            BEATX["Scheduler (single instance)"]
        end
        subgraph privdata["Private subnets — data"]
            PGP[("Postgres primary")]
            PGS[("Postgres standby (multi-AZ)")]
            RED[("Redis primary + replica")]
        end
    end
    subgraph managed["Managed / External"]
        OBJX[("Object storage + lifecycle rules")]
        SECX["Secrets manager"]
        REGX["Container registry"]
        OBSX["Observability backend"]
        AIX["AI providers"]
    end

    USERS --> DNS --> CDNX --> WAFX --> LBX --> LBN
    LBN --> FE1
    LBN --> API1
    API1 --> PGP
    API1 --> RED
    API1 --> OBJX
    WRK1 --> PGP
    WRK1 --> RED
    WRK1 --> OBJX
    BEATX --> RED
    PGP --> PGS
    API1 -->|NAT, egress allow-list| AIX
    WRK1 -->|NAT, egress allow-list| AIX
    API1 --> SECX
    API1 --> OBSX
    WRK1 --> OBSX
    REGX -.->|images| API1
    REGX -.->|images| WRK1
```

### 28.2 Networking and isolation

- **Public subnets** hold only the load balancer and NAT gateway.
- **Application subnets** are private: no inbound internet; ingress only from the load balancer's security group.
- **Data subnets** accept connections only from application security groups — Postgres and Redis have **no public endpoint**, ever.
- **Egress** from application subnets goes through NAT with a destination allow-list (model providers, telemetry, package mirrors in build only). A compromised dependency should not be able to exfiltrate to an arbitrary host.
- **Security groups reference other security groups**, not CIDR ranges, so rules stay correct as the fleet changes.

### 28.3 Cloud mapping

| Logical | AWS | Azure | GCP | Prototype (Phase 0) |
|---|---|---|---|---|
| CDN | CloudFront | Front Door | Cloud CDN | Platform CDN (Vercel/Fly) |
| WAF | AWS WAF | Azure WAF | Cloud Armor | Platform WAF / Cloudflare |
| Load balancer | ALB | App Gateway | Cloud LB | Platform router |
| Containers | ECS Fargate → EKS | Container Apps → AKS | Cloud Run → GKE | Fly.io / Render / Railway containers |
| Postgres + pgvector | RDS/Aurora PostgreSQL | Azure DB for PostgreSQL | Cloud SQL | Neon / Supabase / managed Postgres |
| Redis | ElastiCache | Azure Cache | Memorystore | Upstash / managed Redis |
| Object storage | S3 | Blob Storage | GCS | Cloudflare R2 / S3 |
| Secrets | Secrets Manager | Key Vault | Secret Manager | Platform secrets |
| Registry | ECR | ACR | Artifact Registry | GHCR |
| Observability | CloudWatch + Managed Grafana/Tempo | Monitor | Cloud Ops | Grafana Cloud free tier + Sentry |

> **[ASSUMPTION A-13]** Phase 0 deploys to a managed container platform (Fly.io/Render class) rather than Kubernetes. *Why:* the PRD requires a publicly accessible working deployment within a 3–4 day build (§18); Kubernetes would consume a disproportionate share of that budget and add operational surface no requirement justifies. *Alternative and trigger:* move to EKS/GKE when multi-region, sophisticated autoscaling policies, or multi-team deployment isolation is needed. **Because everything runs as containers with externalized config, this migration is a deployment-manifest change, not an application rewrite** — which is precisely why containerization is non-negotiable from day one.

### 28.4 Containers

| Image | Base | Notes |
|---|---|---|
| `api` | `python:3.12-slim`, multi-stage | Non-root user, no build toolchain in the final layer, `HEALTHCHECK`, tini as PID 1 |
| `worker` | Same image as `api`, different entrypoint | Guarantees identical domain code; adds OCR/system libs in a build stage |
| `frontend` | `node:22-alpine` build → static/standalone runtime | Non-root, read-only filesystem |

All images are pinned by digest in production manifests, scanned by Trivy in CI, and carry an SBOM and the git SHA as a label.

---

## 29. Deployment Architecture

```mermaid
flowchart TB
    DEV["Developer"] --> GIT["Git push / PR"]
    GIT --> CI["CI pipeline"]
    CI --> IMG["Container image<br/>tagged with git SHA + digest"]
    IMG --> REG["Container registry"]
    REG --> CD["CD pipeline"]
    CD --> MIG["Migration job<br/>(expand-only, runs first)"]
    MIG --> STG["Staging deploy<br/>rolling, health-gated"]
    STG --> SMOKE["Automated smoke + E2E"]
    SMOKE --> APPR["Manual approval"]
    APPR --> PRODMIG["Production migration job"]
    PRODMIG --> PROD["Production rolling deploy"]
    PROD --> VERIFY["Post-deploy verification<br/>health, error rate, key metrics"]
    VERIFY -->|regression| RB["Rollback:<br/>redeploy previous digest"]
    VERIFY -->|healthy| DONE["Release complete"]
```

### 29.1 Strategy

**Rolling deployment with health gates** for Phase 0/1; blue-green reserved for high-risk releases (major migration, auth change).

| Aspect | Design |
|---|---|
| Zero downtime | Rolling replacement; new replica must pass `/readyz` before old one drains; graceful shutdown with `SIGTERM` handling |
| Connection draining | API drains in-flight requests (including open SSE streams) up to a 60 s grace period |
| Worker shutdown | `warm_shutdown`: stop prefetching, finish current task, requeue the rest (`acks_late` makes this safe) |
| Migrations | Separate job, expand-only, always backward-compatible with the running version (Section 13.7) |
| Config/secrets | Injected as environment variables from the secrets manager at container start; never baked into images |
| Rollback | Redeploy the previous image digest — always possible because migrations never break the previous version within a release |
| Feature flags | Environment-driven flags for risky AI changes (new prompt version, new model) so a regression is switched off without a deploy |
| Post-deploy verification | Automated: `/healthz`, `/readyz`, smoke suite (login → create project → upload fixture → tutor answer with citation), plus a 15-minute watch on error rate, latency, and AI failure rate |

### 29.2 Why rolling rather than blue-green by default

Blue-green needs a full duplicate environment and a shared database that both versions can serve — the database is the hard part, and expand/contract migrations already solve it. Rolling with health gates gives most of the safety at a fraction of the cost, and the rollback path (previous digest) is equally fast. For the two release types where a bad version is expensive to undo (auth changes, destructive migrations), blue-green is used explicitly.

### 29.3 Environments

| Environment | Purpose | Data | Deploys |
|---|---|---|---|
| **Local** | Development | Docker Compose: Postgres+pgvector, Redis, MinIO; seeded fixtures | Manual |
| **Test/CI** | Automated tests | Ephemeral containers per run; no real provider calls (recorded fixtures + a contract-test job that hits providers on a schedule) | Every push |
| **Staging** | Pre-production verification | Anonymized/synthetic data only; real provider keys with low budgets | Auto on merge to `main` |
| **Production** | Live | Real | Manual approval |

Staging mirrors production topology at smaller size, with the **same** image and the same migration path — the only differences are scale, budgets, and data.

---

## 30. CI/CD Architecture

```text
Developer
   ↓ push / PR
Git repository (protected main, required reviews, signed commits optional)
   ↓
CI Pipeline
   ├── Lint            ruff, black --check, eslint, prettier
   ├── Type check      mypy (strict on domain modules), tsc --noEmit
   ├── Import rules    import-linter (module boundary enforcement)
   ├── Unit tests      pytest -m "not integration", vitest
   ├── Integration     pytest -m integration (Postgres + Redis + MinIO service containers)
   ├── AI eval (fast)  golden-set regression on prompts/retrieval, gated thresholds
   ├── Static analysis bandit, semgrep
   ├── Secret scan     gitleaks
   ├── Dependency scan pip-audit, npm audit --omit=dev
   ├── Build           multi-stage Docker build (api/worker/frontend)
   ├── Image scan      trivy (fail on HIGH/CRITICAL, with documented allow-list)
   ├── SBOM            syft
   └── IaC validation  terraform validate/plan, checkov
   ↓ (main only)
Container registry (immutable tag = git SHA, pinned digest)
   ↓
CD Pipeline
   ├── Migration job (staging)
   ├── Staging rolling deploy
   ├── Smoke + E2E (Playwright: full learning loop)
   ├── Manual approval
   ├── Migration job (production)
   ├── Production rolling deploy
   └── Post-deploy verification + auto-rollback on regression
```

### 30.1 Branching and review

Trunk-based: short-lived `feat/*` and `fix/*` branches off `main`, squash-merged. `main` is always deployable and protected (CI green + one approving review + up-to-date branch). Conventional Commits drive the changelog. Long-running release branches are avoided — with feature flags they buy nothing.

### 30.2 Module boundary enforcement

The modular monolith only stays modular if the boundary is machine-checked. `importlinter` contracts in CI:

```ini
[importlinter:contract:module-independence]
name = Domain modules must not import each other's internals
type = forbidden
source_modules = app.tutor, app.assessment, app.mastery, app.growth, app.analytics, app.workspace, app.materials, app.knowledge
forbidden_modules = app.*.models, app.*.repository

[importlinter:contract:ai-isolation]
name = Only app.ai may import provider SDKs
type = forbidden
source_modules = app.tutor, app.assessment, app.growth, app.knowledge, app.workspace, app.analytics
forbidden_modules = anthropic, openai, cohere
```

This is the single cheapest control that keeps ADR-001's extraction path viable.

### 30.3 Testing strategy (NFR-08 — the PRD names the areas)

| Layer | Scope | Examples |
|---|---|---|
| **Unit** | Pure logic, no IO | Mastery update math (BKT + decay), adaptive selection scoring, RRF fusion, sufficiency thresholds, context budget allocation, citation parsing/validation |
| **Integration** | Real Postgres/Redis/MinIO | Auth flows incl. refresh rotation and reuse detection; **project isolation suite** (every endpoint, tool, retrieval path, job); idempotent quiz submission; outbox → task → consumer dedup; document pipeline on fixture PDFs (native text, scanned, table-heavy, corrupt) |
| **Contract** | Provider interfaces | Recorded fixtures for deterministic CI; a scheduled live job detecting provider contract drift |
| **AI behavioural** | Golden sets | Grounded answers cite retrievable sources; **unanswerable questions produce refusal, not invention**; structured outputs validate; grading is rubric-consistent across reruns; adaptive selection favours weak concepts |
| **E2E** | Playwright against staging | The whole PRD §19 loop: register → space → project → upload → wait for ready → ask (grounded + citation) → ask unsupported (refusal) → quiz (MCQ + open) → mastery → growth → recommendation → analytics → admin view |
| **Load** *(Phase 1)* | k6 | Concurrent tutor streams, ingestion bursts |
| **Security** | Automated | SAST/DAST baseline, dependency and image scans, authorization fuzzing over IDOR candidates |

Coverage targets are deliberately unequal: domain logic and isolation are near-exhaustive; UI and glue code are covered by E2E. The PRD asks for "meaningful tests rather than exhaustive coverage" — this is what that means in practice.

---

## 31. Environment Strategy

### 31.1 Configuration principles

12-factor: all configuration in the environment, validated at startup by a Pydantic `Settings` object. **The application refuses to boot on missing or malformed config** rather than failing mysteriously at 3 a.m. on the first request that touches it. No environment-conditional code paths (`if env == "production"`) in domain logic — behaviour differences are expressed as configuration values.

### 31.2 Files

```text
.env.example          committed — every key, placeholder values, comments  ← the only env file in Git
.env.development      local, gitignored
.env.test             CI defaults, no real secrets
.env.staging          injected from secrets manager, never on disk in the repo
.env.production       injected from secrets manager, never on disk in the repo
```

`.gitignore` blocks `.env*` except `.env.example`; gitleaks in CI is the backstop.

### 31.3 Variable catalogue (placeholders only — never real values)

```bash
# --- Core ---
APP_ENV=development|test|staging|production
APP_VERSION=                      # injected as git SHA at build
LOG_LEVEL=INFO
API_BASE_URL=
FRONTEND_ORIGIN=
CORS_ALLOWED_ORIGINS=

# --- Data ---
DATABASE_URL=                     # postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=5
DATABASE_STATEMENT_TIMEOUT_MS=10000
REDIS_URL=                        # rediss://:PASSWORD@HOST:6379/0

# --- Object storage ---
STORAGE_ENDPOINT=
STORAGE_BUCKET=
STORAGE_ACCESS_KEY_ID=
STORAGE_SECRET_ACCESS_KEY=
STORAGE_PRESIGN_TTL_SECONDS=900
MAX_UPLOAD_BYTES=52428800
MAX_PDF_PAGES=500

# --- Auth ---
JWT_PRIVATE_KEY=                  # RS256 private key (PEM), from secrets manager
JWT_PUBLIC_KEY=
JWT_ACCESS_TTL_SECONDS=900
REFRESH_TTL_DAYS=30
PASSWORD_HASH_TIME_COST=3
PASSWORD_HASH_MEMORY_KIB=65536

# --- AI providers (roles, not hard-coded vendors) ---
LLM_PRIMARY_PROVIDER=
LLM_PRIMARY_API_KEY=
LLM_PRIMARY_REASONING_MODEL=
LLM_PRIMARY_FAST_MODEL=
LLM_FALLBACK_PROVIDER=
LLM_FALLBACK_API_KEY=
LLM_FALLBACK_MODEL=
EMBEDDING_PROVIDER=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
EMBEDDING_DIMENSIONS=1536
RERANK_PROVIDER=
RERANK_API_KEY=
RERANK_MODEL=
VISION_MODEL=

# --- AI policy ---
AI_REQUEST_TIMEOUT_SECONDS=30
AI_GRADING_TIMEOUT_SECONDS=60
AI_MAX_RETRIES=2
AI_CIRCUIT_FAILURE_THRESHOLD=5
AI_CIRCUIT_RESET_SECONDS=60
AI_USER_DAILY_TOKEN_BUDGET=
AI_PROMPT_LOGGING=redacted        # none|redacted|full (full never in production)
EVAL_SAMPLE_RATE=0.05

# --- Retrieval policy ---
RETRIEVAL_TOP_K=30
RETRIEVAL_RERANK_TO=6
RETRIEVAL_SUFFICIENCY_TAU=
RETRIEVAL_MIN_SUPPORTING_CHUNKS=2
CHUNK_TARGET_TOKENS=500
CHUNK_OVERLAP_RATIO=0.15
CONTEXT_TOKEN_BUDGET=

# --- Background ---
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=
WORKER_CONCURRENCY_DOCUMENTS=2
WORKER_CONCURRENCY_LEARNING=4
TASK_MAX_RETRIES=3

# --- Limits ---
RATE_LIMIT_GLOBAL_PER_MINUTE=
RATE_LIMIT_AI_PER_MINUTE=
RATE_LIMIT_LOGIN_PER_MINUTE=

# --- Observability ---
OTEL_EXPORTER_OTLP_ENDPOINT=
OTEL_SERVICE_NAME=
SENTRY_DSN=
TRACE_SAMPLE_RATE=0.1
```

### 31.4 Secret handling rules

1. Secrets exist only in the secrets manager and in memory at runtime.
2. CI reads secrets from the CI provider's secret store; they are never echoed, and logs are masked.
3. Rotation is possible without a code change (all secrets read at startup; rotation = restart).
4. Local development uses non-production keys with low provider budgets.
5. A leaked key is revoked first and investigated second; the runbook says so explicitly.
6. This document, the repository, and all diagrams contain **placeholders only**.


---

## 32. Repository Structure

A single repository. With one team, shared domain types between API and workers, and a frontend that consumes a generated OpenAPI client, splitting repos would add coordination cost and buy nothing.

```text
ai-study-companion/
├── README.md                     Overview, quickstart, demo credentials, live URL
├── architecture.md               This document
├── docs/
│   ├── adr/                      One file per ADR (Section 38)
│   ├── ai-usage.md               AI used to BUILD vs AI used BY the product (PRD §20.5)
│   ├── development-prompts.md    Prompts materially used with AI dev tools (PRD §20.6)
│   ├── evaluation.md             Eval approach, suites, baselines, results (PRD §20.7)
│   ├── limitations.md            Known limitations (PRD §20.8)
│   ├── future-improvements.md    (PRD §20.9)
│   ├── api.md                    Generated OpenAPI reference
│   └── runbooks/                 Incident runbooks keyed to alerts in 27.3
│
├── backend/
│   ├── app/
│   │   ├── main.py               ASGI app, router registration, middleware chain
│   │   ├── platform/             db, cache, storage, config, security, errors, logging, tracing
│   │   ├── identity/             auth, users, sessions, roles
│   │   ├── workspace/            spaces, projects, dashboards
│   │   ├── materials/            upload, document lifecycle, status
│   │   ├── knowledge/            chunks, concepts, retrieval, fusion, rerank, sufficiency
│   │   ├── tutor/                conversations, context composer, grounded answering, citations
│   │   ├── assessment/           quizzes, generation, adaptive policy, grading
│   │   ├── mastery/              mastery state + events + update math
│   │   ├── growth/               trends, weakness detection, recommendations
│   │   ├── analytics/            event ingestion, rollups, queries
│   │   ├── admin/                read models, user inspection, system health
│   │   ├── ai/
│   │   │   ├── gateway.py        The single egress point
│   │   │   ├── providers/        Provider adapters (the ONLY place SDKs are imported)
│   │   │   ├── prompts/          Versioned prompt files + registry
│   │   │   ├── schemas/          Pydantic models for every structured output
│   │   │   ├── evaluation/       Suites, metrics, golden sets, runners
│   │   │   └── cost.py           Price table, estimation
│   │   ├── tools/                Tool registry, schemas, authorization, executor, audit
│   │   └── jobs/                 Celery app, tasks, outbox relay, beat schedule
│   ├── alembic/                  Migrations
│   ├── tests/
│   │   ├── unit/ integration/ isolation/ ai/ e2e-support/ fixtures/
│   ├── pyproject.toml            deps, ruff, mypy, pytest, importlinter contracts
│   └── Dockerfile
│
├── frontend/
│   ├── app/                      Next.js routes (Section 9.2)
│   ├── components/               UI incl. citation panel, mastery bars, job status chips
│   ├── lib/                      Generated API client, SSE client, query hooks
│   ├── tests/                    Component + Playwright E2E
│   └── Dockerfile
│
├── infrastructure/
│   ├── terraform/                VPC, subnets, security groups, DB, cache, bucket, secrets
│   └── modules/
├── deployment/
│   ├── docker-compose.yml        Local: api, worker, beat, postgres+pgvector, redis, minio
│   ├── docker-compose.test.yml
│   └── manifests/                Platform/K8s deployment descriptors
├── scripts/                      seed_data, run_eval, backfill_embeddings, restore_drill
└── .github/workflows/            ci.yml, cd.yml, eval-nightly.yml, contract-tests.yml
```

**Directories that carry weight:**

| Path | Why it exists |
|---|---|
| `app/platform/` | The only place infrastructure concerns live; keeps domain modules free of connection and telemetry plumbing |
| `app/ai/providers/` | The vendor boundary. If this directory is the only place an SDK appears, the provider is swappable |
| `app/ai/prompts/` | Prompts are versioned artifacts, reviewed like code, referenced by id+version in `ai_requests` |
| `app/ai/evaluation/` | Evaluation ships with the product, not as a side project (PRD §14) |
| `app/tools/` | The capability boundary from PRD §8, in one auditable place |
| `tests/isolation/` | A separate suite because the isolation invariant deserves its own gate |
| `docs/` | The PRD's submission requirements (§20) map one-to-one onto these files |

---

## 33. Data Flow

### 33.1 End-to-end request lifecycle (Tutor question, the full path)

```text
User types a question in the Tutor
  ↓
Next.js client — optimistic user bubble, opens SSE POST
  ↓
DNS → CDN (static assets already cached; API call passes through)
  ↓
WAF (OWASP rules, bot checks) → Load balancer → API replica
  ↓
Middleware: request_id + trace context → structured log context → CORS →
security headers → body size cap → rate limit (Redis token bucket) →
JWT verification (RS256, jti denylist check) → Principal
  ↓
SET LOCAL app.current_user_id  (RLS context on this DB session)
  ↓
require_project(project_id) — ownership check → ProjectScope  (404 if not owned)
  ↓
Pydantic validation of the request body
  ↓
Tutor Service → Context Composer
   ├── Conversation window + rolling summary        (Postgres)
   ├── Learning context items by salience           (Postgres)
   ├── Learner state: goal, mastery, recent mistakes(Postgres, cached 120 s)
   └── Retrieval
        ├── query rewrite (small model, ~200 ms)
        ├── embed query                              (cache → provider)
        ├── vector search  WHERE project_id          (pgvector HNSW)   ─┐ parallel
        ├── lexical search WHERE project_id          (tsvector GIN)    ─┘
        ├── RRF fusion → diversity cap → rerank top-6 (rerank provider)
        └── sufficiency decision (top score vs tau, supporting count)
  ↓
        ├── insufficient → insufficiency response path (no generation)
        └── sufficient   → prompt assembly under token budget,
                           evidence in delimited numbered blocks
  ↓
AI Gateway: budget check → prompt version resolve → model route →
circuit breaker → provider call (streamed) with 30 s timeout
  ↓
Tokens stream back → SSE `token` events → client renders progressively
  ↓
Citation validation: every [n] resolves to a retrieved chunk → `citation` events
  ↓
Finalizer (runs even if the client disconnected):
   persist message + message_citations + ai_request  ┐
   + outbox_events row                                ┘ one transaction
  ↓
Outbox relay → `analytics` + `evaluation` queues
  ↓ (async)
Workers: activity event, learning-context extraction, eval sampling, cache invalidation
  ↓
Client shows the answer with a Sources panel (Document — Page N), deep-linkable
```

Failure branches at each hop are defined in Section 35; the user-visible result is always either an answer, a clearly-labelled insufficiency, or a clear error with a retry affordance and a request id.

### 33.2 Material ingestion data flow

```text
Client requests presigned URL → API validates project ownership, size, content type
  ↓  (file bytes never touch the API process)
Client PUTs PDF directly to object storage
  ↓
Client confirms upload → API verifies object, magic bytes, checksum
  ↓
materials row (status=queued) + outbox event  [one transaction]
  ↓
Outbox relay → `documents` queue → worker claims job (dedup_key prevents duplicates)
  ↓
advisory lock(material_id) → status=processing
  ↓
Parse (native) → per page: sufficient text? → OCR → still insufficient? → vision model
  ↓
Structure assembly (sections, tables, figure captions, page anchors)
  ↓
Chunking (≈500 tokens, 15% overlap, page range preserved)
  ↓
Concept extraction (structured output, upserted by normalized name)
  ↓
Batched embeddings → chunks + chunk_embeddings + chunk_concepts written
  ↓
status=ready + page_count + pipeline_version → `material.processed` event
  ↓
Downstream: project state refresh, analytics, recommendation refresh, cache purge
  ↓
UI status chip flips to Ready (poll) — browser need not have stayed open
```

---

## 34. Critical Business Workflows

### 34.1 Material upload and asynchronous processing

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as API
    participant S3 as Object Storage
    participant DB as Postgres
    participant Q as Broker
    participant W as Document Worker
    participant AI as AI Gateway

    U->>FE: Select PDF
    FE->>API: POST /materials/upload-url
    API->>API: authz + size/type policy
    API-->>FE: presigned PUT + material_id
    FE->>S3: PUT file (direct)
    S3-->>FE: 200
    FE->>API: POST /materials (confirm, Idempotency-Key)
    API->>S3: HEAD object, verify size + magic bytes
    API->>DB: INSERT material(status=queued) + outbox event [tx]
    API-->>FE: 202 {material_id, job_id}
    FE-->>U: "Queued" chip

    Note over API,Q: Outbox relay dispatches
    API->>Q: material.uploaded
    Q->>W: consume (dedup check)
    W->>DB: status=processing, advisory lock
    W->>S3: GET object
    W->>W: parse pages; OCR where needed
    alt page still unreadable
        W->>AI: vision understanding
        AI-->>W: structured page content
    end
    W->>W: chunk with page anchors
    W->>AI: extract concepts (structured)
    AI-->>W: concepts[]
    W->>AI: embed chunks (batched)
    AI-->>W: vectors
    W->>DB: INSERT chunks, embeddings, concepts [tx]
    W->>DB: status=ready + outbox material.processed
    FE->>API: GET /jobs/{job_id} (polled, backoff)
    API-->>FE: ready
    FE-->>U: "Ready" chip; Tutor now grounded on this document

    alt processing fails
        W->>DB: attempt++, status stays processing
        W->>Q: retry with backoff
        Note over W,Q: after max attempts
        W->>DB: status=failed + failure_reason; job_runs=dead_lettered
        FE-->>U: "Failed: <reason>" + Retry action
    end
```

### 34.2 Grounded Tutor answer with citation

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as API
    participant CC as Context Composer
    participant R as Retrieval
    participant AI as AI Gateway
    participant DB as Postgres

    U->>FE: "How does gradient descent pick the step size?"
    FE->>API: POST /conversations/{id}/messages (SSE)
    API->>API: auth, ProjectScope, validation, rate limit
    API->>CC: compose(scope, question)
    CC->>DB: conversation window + rolling summary
    CC->>DB: learning context (salience-ranked)
    CC->>R: retrieve(question, project_id)
    R->>AI: embed(query)   [cache checked first]
    R->>DB: vector search (HNSW, project-filtered)
    R->>DB: lexical search (tsvector, project-filtered)
    R->>R: RRF fusion + diversity cap
    R->>AI: rerank(top 30 -> 6)
    R->>R: sufficiency check vs tau
    R-->>CC: evidence[6] + scores + sufficiency=true
    CC-->>API: prompt (budgeted, evidence delimited as DATA)
    API->>AI: stream generate
    AI-->>API: tokens...
    API-->>FE: SSE token events
    API->>API: validate citations against retrieved chunk ids
    API-->>FE: SSE citation events (material, page, marker)
    API->>DB: message + citations + ai_request + outbox [tx]
    API-->>FE: SSE message_end
    FE-->>U: Answer + "Source: ML Notes — Page 14"
```

### 34.3 Unsupported question (the refusal path)

```mermaid
sequenceDiagram
    participant U as User
    participant API as API
    participant R as Retrieval
    participant AI as AI Gateway
    participant DB as Postgres

    U->>API: "What did the 2026 conference say about this?"
    API->>R: retrieve(question, project_id)
    R->>R: hybrid search + rerank
    R->>R: top_score < tau OR supporting_chunks < 2
    R-->>API: sufficiency = false (no generation attempted)
    API->>DB: message(answer_status='insufficient_evidence') + ai_request(status='success', retrieval_meta)
    API-->>U: "Your materials don't cover this. They do cover X and Y.<br/>Upload material on this topic, or ask me to answer from general knowledge (uncited)."
    opt User opts into general knowledge
        U->>API: "Answer from general knowledge"
        API->>AI: generate (explicitly ungrounded mode)
        AI-->>API: answer
        API->>DB: message(answer_status='general_knowledge')
        API-->>U: Answer visually marked "Not from your materials"
    end
```

The key property: **the refusal is decided before generation**, so there is no "model chose to be honest" dependency. The model is never handed thin evidence and asked to resist filling the gap.

### 34.4 Adaptive quiz turn

```mermaid
sequenceDiagram
    participant U as User
    participant API as API
    participant SEL as Selection Policy (deterministic)
    participant AI as AI Gateway
    participant M as Mastery Service
    participant DB as Postgres

    U->>API: POST /projects/{id}/quizzes
    API->>DB: load concept_mastery, question history, recent mistakes
    API->>SEL: score all concepts (weakness, uncertainty, decay, importance, penalties)
    SEL-->>API: concept C, difficulty target d
    API->>DB: retrieve chunks for concept C
    API->>AI: generate question (structured, grounded in chunks, difficulty d)
    AI-->>API: {prompt, options|rubric, source_chunk_ids}
    API->>API: validate schema + grounding
    API->>DB: INSERT question
    API-->>U: question

    U->>API: POST .../answer (Idempotency-Key)
    alt MCQ
        API->>API: deterministic scoring
    else Open-ended
        API->>AI: grade vs rubric (structured: understanding, accuracy,<br/>relevance, concepts covered/missing, reasoning)
        AI-->>API: evaluation + feedback
        API->>API: validate; low confidence -> pending_review
    end
    API->>DB: INSERT answer [tx]
    API->>M: apply evidence (BKT-style + difficulty weighting)
    M->>DB: mastery_events (unique key) + concept_mastery upsert [tx]
    API->>DB: outbox: answer.submitted, mastery.updated
    API-->>U: explanatory feedback + updated mastery
    API->>SEL: next concept/difficulty (loop)
```

### 34.5 Post-quiz learning workflow (event chain)

```mermaid
sequenceDiagram
    participant API as API
    participant OB as Outbox Relay
    participant Q as learning queue
    participant EV as Evaluation Task
    participant MA as Mastery Task
    participant WK as Weakness Detector
    participant RC as Recommendation Task
    participant AI as AI Gateway
    participant DB as Postgres

    API->>DB: quiz.completed + outbox [tx]
    OB->>Q: dispatch quiz.completed
    Q->>EV: consume (processed_events dedup)
    EV->>DB: aggregate answers, re-check low-confidence grading
    EV->>DB: outbox: assessment.evaluated
    Q->>MA: consume assessment.evaluated
    MA->>DB: recompute mastery from mastery_events (pure function)
    MA->>DB: outbox: mastery.updated
    Q->>WK: consume mastery.updated
    WK->>DB: classify trends (improving / stable / needs attention)
    WK->>DB: growth_snapshots; detect repeated mistakes
    WK->>DB: outbox: weakness.detected / mistake.repeated
    Q->>RC: consume weakness.detected
    RC->>DB: gather goal, weak concepts, materials, prior recommendations
    RC->>AI: phrase recommendation (structured; deterministic logic chose the target)
    AI-->>RC: {title, rationale}
    RC->>DB: INSERT recommendation (dedup_key unique WHERE active)
    RC->>DB: outbox: recommendation.created
    Note over DB: Project dashboard + Home now show the next action
```

Every consumer checks `processed_events` first, so a redelivered event is a no-op — the PRD's idempotency requirement (§12) satisfied at the consumer, where at-least-once delivery actually lands.

### 34.6 Admin inspection of a user's learning journey

```mermaid
sequenceDiagram
    participant A as Admin
    participant API as API
    participant AUD as Audit
    participant DB as Postgres

    A->>API: GET /admin/users/{user_id}/journey
    API->>API: require role=admin
    API->>AUD: audit_log(action='admin.user.inspect', target_user_id, request_id)
    API->>DB: spaces/projects counts, activity timeline (partition-pruned)
    API->>DB: assessment summaries, mastery distribution
    API->>DB: ai_requests rollup (usage, cost, error rate)
    DB-->>API: aggregates (metadata only — no document content, no raw answers)
    API-->>A: Journey view with filters (space, project, type, period)
```

---

## 35. Failure Scenarios

Only components actually used appear here. Each row is also a runbook entry (`docs/runbooks/`).

| Failure | Impact | Detection | Recovery / degraded behaviour |
|---|---|---|---|
| **Postgres unavailable** | Total outage — it is the system of record | `/readyz` fails; connection error rate; managed-service alarm | Managed failover to standby (multi-AZ); app retries with backoff; LB stops routing to unready replicas; workers stop acking and requeue. *No application-level workaround — this is the one hard dependency, which is why it is the most redundant component* |
| **Postgres primary degraded (slow queries, pool exhaustion)** | Latency spike, timeouts | Pool saturation + query p95 alerts | `statement_timeout` sheds long queries; circuit on non-essential reads (analytics) ; scale up; kill offending queries per runbook |
| **Redis unavailable** | Cache misses, rate limiting and idempotency unavailable, **Celery broker down** | Redis connection errors; queue depth flatlines; worker heartbeat lost | Cache reads fall through to Postgres (wrapped, never fatal); rate limiting fails **closed** on AI endpoints (protects budget) and **open** on ordinary reads (protects availability); idempotency falls back to DB unique constraints; new background jobs remain in `outbox_events` (unpublished) and are dispatched when Redis returns — **no event loss**, only delay |
| **Object storage unavailable** | New uploads fail; source previews unavailable | 5xx from storage client; upload error rate | Uploads fail fast with a clear message and a retry; **Tutor keeps working** because chunk text lives in Postgres; citation page-image links degrade to text-only citations |
| **Primary LLM provider down / rate-limiting** | Tutor, grading, generation affected | Provider error rate, circuit breaker state, latency | Circuit opens → fallback model → fallback provider; async grading retried later; user sees a clear "AI temporarily degraded" state; non-AI features unaffected (browsing, history, mastery, analytics) |
| **All LLM providers down** | No new AI generation | All circuits open | Tutor returns retrieval results as an evidence list ("here are the relevant passages") instead of a synthesized answer — genuinely useful degradation; quiz falls back to previously generated unseen questions; recommendations fall back to deterministic templates from weakness data |
| **Embedding provider down** | Ingestion stalls; dense retrieval unavailable | Error rate on `embed` | Ingestion tasks retry with backoff (documents stay `processing`, never lost); retrieval degrades to **lexical-only** with a raised sufficiency threshold; answers flagged reduced-confidence |
| **Reranker down** | Lower retrieval precision | Error rate on `rerank` | Skip rerank, use fused order, raise `tau`; metric recorded so quality impact is visible in the eval dashboard |
| **OCR/vision failure** | Scanned pages unusable | Per-page extraction failures | Document still processes with readable pages; affected pages flagged; material marked partial-quality; user told which pages could not be read |
| **Worker fleet down** | Uploads never process; post-quiz chain stalls | Queue depth + oldest-message age; heartbeat loss | Restart/scale workers; `acks_late` means in-flight tasks are redelivered; outbox retains undispatched events; nothing is lost, only delayed |
| **Poison-pill task (always fails)** | One document or workflow stuck | Retry exhaustion → DLQ | DLQ + `job_runs.dead_lettered` + admin visibility + manual replay after fix; other work unaffected (queue bulkheads) |
| **Invalid AI structured output** | A question/grade/recommendation cannot be produced | `structured_output_validity_rate` drop; `AIInvalidOutput` count | One repair attempt → documented per-feature fallback (skip question, `pending_review` grading, template recommendation). **Never persist unvalidated model output** |
| **Prompt-injected document** | Attempted unauthorized tool use or leakage | Injection classifier hits; `tool_invocations` denials; cross-project assertion failures | Structural controls hold (server-injected scope, allow-list); event logged and alerted; material can be quarantined |
| **Traffic spike / abuse** | Latency, cost | Rate-limit trips, cost anomaly alert | Edge + per-user limits; budgets; autoscale API; shed evaluation sampling first, then analytics |
| **Bad deploy** | Errors or latency regression | Post-deploy verification; error-rate alert | Automatic rollback to previous image digest; expand-only migrations guarantee the old version still runs |
| **Certificate expiry / DNS failure** | Total inaccessibility | External uptime check; expiry alert | Managed certificates with auto-renewal; expiry alert at 14 days; DNS provider redundancy |

---

## 36. Disaster Recovery

> **[ASSUMPTION A-14]** The PRD sets no RTO/RPO. The following are proposed targets, split by phase so the prototype is not held to a production promise. They would be confirmed with business input before being treated as commitments.

### 36.1 Targets

| Environment | RPO | RTO | Basis |
|---|---|---|---|
| Phase 0 (prototype) | 24 h | 4 h | Daily automated snapshots; loss of one day of demo data is tolerable; restore is a manual, rehearsed procedure |
| Phase 1 (production) | **15 min** | **1 h** | Point-in-time recovery via continuous WAL archiving; standby promotion for instance failure |
| Regional failure (Phase 2) | 1 h | 4 h | Cross-region snapshot replication + IaC rebuild; only justified once a business case exists |

### 36.2 Backup strategy

| Asset | Method | Frequency | Retention | Restore test |
|---|---|---|---|---|
| Postgres | Managed automated snapshots + continuous WAL archiving (PITR) | Snapshot daily; WAL continuous | 7 daily, 4 weekly, 3 monthly | **Quarterly restore drill into a scratch environment**, timed, result recorded |
| Object storage | Versioning + cross-region replication *(Phase 1)* | Continuous | 30-day version history | Quarterly object-restore spot check |
| Redis | **Not backed up by design** | — | — | Contents are rebuildable: cache regenerates, rate-limit counters are transient, queued work is recoverable from `outbox_events` |
| Secrets | Secrets-manager versioning | On change | Prior versions retained | Rotation drill |
| Infrastructure | Terraform state (remote, locked, versioned) | On change | Full history | `terraform plan` against a clean environment |
| Derived data (chunks/embeddings) | Not separately backed up | — | — | Regenerable from source PDFs + pipeline version; a reprocess script exists (`scripts/backfill_embeddings.py`) |

Backups are **encrypted, access-controlled with separate credentials, and stored in a different account/project** from production where the platform allows — so a compromise of production credentials does not compromise the ability to recover.

### 36.3 Recovery procedures

| Scenario | Procedure |
|---|---|
| Accidental data deletion (single user/project) | PITR restore into a scratch instance → export the affected rows → reimport. Avoids a full-system rollback for a localized problem |
| Database corruption | Promote standby; if corruption replicated, PITR to a timestamp before the corrupting event; replay from application logs where possible |
| Instance/AZ failure | Automatic managed failover to standby; application reconnects via retry and connection-pool recycling |
| Region failure *(Phase 2)* | Rebuild from IaC in the secondary region → restore latest cross-region snapshot → repoint DNS |
| Complete environment loss | `terraform apply` → restore database → restore object storage → deploy last known good image digest → run smoke suite. This path is only credible because infrastructure is code and images are immutable |
| Corrupted derived data (bad chunking/embedding release) | No restore needed: bump `pipeline_version`, run the reprocess job, swap on completion |

**Drill discipline:** an untested backup is a hypothesis. The quarterly restore drill measures actual RTO and is recorded; if measured RTO exceeds target, the target or the procedure changes — the gap is never left implicit.

---

## 37. Technology Stack

| Layer | Technology | Purpose | Reason chosen | Main alternative rejected |
|---|---|---|---|---|
| Frontend framework | **Next.js 15 + TypeScript** | UI, SSR, routing, thin BFF | Server components suit dashboard-heavy reads; one framework for routing/SSR/API proxying; strong streaming support | Plain React SPA — more client-side data plumbing, worse first paint on dashboards |
| Frontend state | **TanStack Query** | Server-state cache, polling | Async job polling with backoff is a first-class use case here | Redux — state here is server state, not client state |
| Styling/UI | **Tailwind + shadcn/ui** | Consistent accessible UI fast | Accessible Radix primitives, no design-system build cost | Component library with heavy theming — slower to adapt |
| Realtime | **SSE** | Token streaming | Unidirectional, works through standard HTTP infra, auto-reconnect | WebSockets — bidirectional complexity not needed (ADR-008) |
| Backend language | **Python 3.12** | Application + AI work | The document/AI ecosystem is Python-native; one language across API and workers | Node/Go — would split the stack and duplicate domain models |
| Backend framework | **FastAPI** | HTTP API | Async (streaming + provider fan-out), Pydantic validation, OpenAPI, DI that maps to auth guards | Django — heavier, less natural for async streaming; DRF adds little here |
| Validation | **Pydantic v2** | Requests, tool args, **LLM structured output** | One schema language for all three; the same validator guards the API and model output | Hand-rolled validation — inconsistent and error-prone |
| ORM / migrations | **SQLAlchemy 2.0 async + Alembic** | Data access, schema evolution | Typed, explicit, raw-SQL escape hatch for analytics; reviewable reversible migrations | Raw asyncpg — faster but loses model/migration ergonomics |
| Primary database | **PostgreSQL 16** | System of record | Transactions across learning state; RLS for isolation; mature ops; JSONB for flexible payloads | MySQL — weaker JSON/extension story, no pgvector |
| Vector search | **pgvector (HNSW)** | Embedding retrieval | Same transaction and same `project_id` filter as the chunks themselves — isolation and consistency for free at this scale | Qdrant/Pinecone — better at scale, adds dual-write + a second security boundary (ADR-003) |
| Lexical search | **Postgres FTS (`tsvector` + GIN)** | Exact-term half of hybrid retrieval | Essential for acronyms/formulas; free with the existing DB | Elasticsearch — a whole cluster for a need Postgres already meets |
| Cache / limits / broker | **Redis 7** | Cache, rate limit, idempotency, Celery broker, SSE pub/sub | One well-understood component covering several needs; nothing stored is a system of record | Memcached (no pub/sub, no persistence); RabbitMQ (stronger routing, another service to run) |
| Background processing | **Celery 5** | Async pipelines | Mature retry/backoff, queue routing, scheduling, visibility | arq/Dramatiq (lighter, smaller ecosystem); cloud queues (more vendor coupling) |
| Reliable eventing | **Transactional Outbox in Postgres** | Atomic state + event publication | Eliminates dual-write inconsistency without adding Kafka | Direct publish (dual-write bugs); Kafka (operationally disproportionate) |
| Object storage | **S3-compatible (R2/S3; MinIO locally)** | PDFs, page images | Cheap, durable, presigned direct transfer keeps files off the app | Database BLOBs — bloats backups and connections |
| Document parsing | **PyMuPDF** | Text, layout, tables, page images | Fast, accurate page/coordinate data — the basis of page-accurate citations | pdfplumber (slower), pypdf (weaker layout) |
| OCR | **Tesseract**, escalating to a vision model | Scanned pages | Cheap first pass; model only where it is needed | Vision model for every page — unnecessary cost |
| AI abstraction | **In-house AI Gateway** | Single egress, metering, fallback | The PRD asks for provider abstraction and AI observability; a thin purpose-built layer beats a heavy framework | LangChain-style framework — indirection that obscures exactly what must be observable (ADR-007) |
| LLM / embeddings / rerank | **Role-based provider config** | Generation, embeddings, reranking | Roles decouple domain code from vendors; per-role fallback (A-07) | Hard-coded single vendor — lock-in and no failover |
| Observability | **OpenTelemetry + Prometheus + Grafana/Tempo/Loki (or Grafana Cloud) + Sentry** | Traces, metrics, logs, errors | Vendor-neutral instrumentation; async work joins the same trace | Vendor-SDK instrumentation — re-instrumenting on a vendor change |
| AI telemetry store | **Postgres `ai_requests`/`ai_evaluations`** | Admin AI usage + quality views | The admin dashboard must query this relationally alongside users/projects | A separate LLM-ops SaaS — useful, but the PRD wants it visible inside the product |
| Containers | **Docker (multi-stage)** | Packaging | Identical artifact across environments; the portability that makes A-13 safe | VM images — slower, less portable |
| IaC | **Terraform** | Infrastructure | Reproducible, reviewable, cloud-portable; enables the rebuild path in DR | Console clicks — unrecoverable and unreviewable |
| CI/CD | **GitHub Actions** | Pipeline | Co-located with the repo, good ecosystem, low setup cost | Jenkins — infrastructure to maintain for no gain here |
| Testing | **pytest, Playwright, k6 (Phase 1)** | Backend, E2E, load | Standard, fast, good fixtures/parallelism | — |

---

## 38. Architecture Decision Records

Each ADR states the decision, the reason, alternatives with their advantages and disadvantages, and the trade-off accepted. Full text lives in `docs/adr/`.

### ADR-001: Modular monolith with a separate worker plane

**Decision.** One FastAPI application with enforced internal module boundaries, plus independently deployed Celery workers. Not microservices.

**Reason.** One small team; a 3–4 day first delivery; domain boundaries still unproven; the only genuinely independent scaling axis (background AI/document work) is already separated as workers. A monolith gives atomic transactions across learning state — mastery, events, and the outbox commit together — which in a microservice split would become sagas.

**Alternatives.**
- *Microservices per domain.* **Advantages:** independent scaling and deployment, technology freedom, team autonomy at scale. **Disadvantages:** distributed transactions, network failure modes, N deployment pipelines, tracing complexity, and — decisively — premature boundaries that ossify wrong guesses.
- *Serverless functions.* **Advantages:** no server management, scale-to-zero. **Disadvantages:** cold starts hurt streaming; long document processing fights execution limits; persistent connection pooling is awkward; local development degrades.

**Trade-off accepted.** One deployment unit for API concerns, so an API deploy touches all modules and a runaway module can affect its neighbours. Mitigated by import-linter boundaries, per-module metrics, separate worker deployment, and rollback by image digest.

**Revisit when.** A module needs independent scaling the worker split does not provide; more than ~2 teams contend on the same deploy cadence; or one module's resource profile (e.g. GPU inference) diverges sharply.

### ADR-002: Python for both API and workers

**Decision.** Python 3.12 across the backend.

**Reason.** PDF parsing, OCR, embedding/eval tooling, and provider SDKs are Python-first. A split stack would duplicate domain models and validation across two languages.

**Alternatives.** *Node API + Python workers:* shares language with the frontend but duplicates the domain layer and doubles the schema surface. *Go:* better raw throughput, far weaker document/AI ecosystem.

**Trade-off.** Lower CPU-bound throughput than Go/Node. Irrelevant here: the workload is IO-bound on provider calls, and the CPU-heavy part (parsing/OCR) is isolated in scalable workers.

### ADR-003: PostgreSQL + pgvector instead of a dedicated vector database

**Decision.** Store embeddings in Postgres with an HNSW index.

**Reason.** Chunks and their embeddings stay in one transaction and one backup; the `project_id` isolation filter is applied **inside** the ANN query rather than as post-filtering; one datastore to secure and operate. Prototype corpus size is well within pgvector's comfortable range.

**Alternatives.** *Qdrant/Pinecone/Weaviate:* **Advantages:** higher recall at scale, quantization, richer payload filtering, horizontal sharding. **Disadvantages:** dual-write consistency between chunks and vectors, a second authorization boundary to get right, extra infrastructure and cost.

**Trade-off.** A ceiling on scale and on ANN tuning sophistication.

**Revisit when.** >5M chunks, p95 vector search >150 ms at target recall, or a requirement pgvector cannot express. Migration is contained: the retrieval interface in `knowledge/` is the only code that would change, and embeddings are regenerable.

### ADR-004: REST + SSE rather than GraphQL

**Decision.** Versioned REST with SSE streaming.

**Reason.** A small, known client surface; simple per-endpoint authorization (critical for a strict-isolation product); trivial HTTP caching; automatic OpenAPI and a generated typed client.

**Alternatives.** *GraphQL:* **Advantages:** flexible querying, fewer round trips, single endpoint. **Disadvantages:** per-field authorization is easy to get subtly wrong when isolation is the top invariant, query-cost control is extra work, caching is harder, and streaming needs additional machinery. *gRPC:* wrong tool for a browser-first product with one backend.

**Trade-off.** Occasional over-fetching and a few extra round trips, mitigated by purpose-built dashboard endpoints.

### ADR-005: Self-hosted JWT authentication

**Decision.** Email/password with RS256 access tokens and rotating opaque refresh tokens.

**Reason.** No external dependency in the login path; direct control over the `role` claim and the RLS user binding; no vendor cost or data-sharing question for a prototype.

**Alternatives.** *Managed IdP (Auth0/Clerk/Supabase Auth):* **Advantages:** faster to ship, MFA/social login/compliance included, fewer credential-handling mistakes. **Disadvantages:** external dependency in the critical path, vendor cost, more work to bind an external identity to RLS context.

**Trade-off.** We own password storage, reset flows, and MFA implementation — real security responsibility, accepted because the surface is small and the controls are standard. RS256 and a single `Principal` resolution point make a later migration to OIDC a localized change.

### ADR-006: Transactional Outbox for event publication

**Decision.** Business writes and event rows commit together; a relay publishes to Celery.

**Reason.** Eliminates the dual-write failure mode where state and events disagree — the class of bug that only appears under production load.

**Alternatives.** *Publish inline after commit:* simplest, but silently loses events on crash between commit and publish. *Kafka with transactions:* strong guarantees, but a substantial operational commitment unjustified at this volume.

**Trade-off.** Small publication latency (polling interval, mitigated by a post-commit nudge) and one extra table. Cheap insurance for the reliability the PRD explicitly asks for (§12).

### ADR-007: Purpose-built AI Gateway instead of an orchestration framework

**Decision.** A small in-house abstraction over providers rather than LangChain/LlamaIndex-style frameworks.

**Reason.** The PRD's AI requirements are observability, cost tracking, structured-output validation, fallback, and evaluation — all of which need *visibility into exactly what is sent and returned*. A heavy framework hides that behind abstractions that must then be instrumented anyway, and drags in opinionated retrieval that would have to be overridden regardless.

**Alternatives.** *LangChain/LlamaIndex:* **Advantages:** fast start, many integrations, prebuilt RAG/agent patterns. **Disadvantages:** abstraction leakage, version churn, harder to attribute latency and cost precisely, and prompt construction becomes indirect — the opposite of "observable AI".

**Trade-off.** We write and maintain the adapters, retries, and streaming plumbing. This is a few hundred lines that are fully understood and fully instrumented — a good trade for a system whose evaluation criteria include AI observability.

### ADR-008: SSE for streaming

**Decision.** Server-Sent Events, not WebSockets.

**Reason.** Streaming here is strictly server→client; SSE traverses ordinary HTTP infrastructure, reconnects natively, and needs no separate protocol handling at the load balancer.

**Alternatives.** *WebSockets:* bidirectional and lower per-message overhead, but stateful connections, sticky-session concerns, and more moving parts than a one-way token stream requires. *Polling:* trivially simple, but defeats the purpose of streaming.

**Trade-off.** Client→server messages use ordinary POSTs. That is exactly the shape of this product's interaction anyway.

### ADR-009: Deterministic mastery and adaptive selection

**Decision.** Mastery updates and question selection are ordinary code (BKT-style update, weighted scoring function); LLMs only generate and grade language.

**Reason.** The PRD explicitly rejects naive adaptivity (§9) and requires mastery to evolve with evidence (§10). Deterministic logic is testable, explainable to the user ("asked because your mastery of X is 42% and you missed it twice"), reproducible across model changes, and free to run.

**Alternatives.** *LLM-chosen next question:* **Advantages:** flexible, less code. **Disadvantages:** nondeterministic, unexplainable, costly per question, impossible to unit test, and prone to drifting with model updates — a regression that would be nearly invisible.

**Trade-off.** Less "intelligent-seeming" selection than a model might produce, in exchange for a system whose adaptivity can actually be demonstrated and evaluated. Selection weights are configuration and tunable against the evaluation suite.

### ADR-010: Redis as cache and broker; Postgres as the durable queue of record

**Decision.** Celery on Redis, with `outbox_events` in Postgres as the durable source.

**Reason.** One fewer service to operate, and durability is provided where it belongs — in the transactional store. A Redis loss delays work; it does not lose it.

**Alternatives.** *RabbitMQ/SQS:* stronger delivery semantics and routing; more infrastructure or more vendor coupling, and largely redundant given the outbox.

**Trade-off.** Redis persistence is not relied upon, so in-flight tasks may be redelivered after a Redis failure — which is precisely why every consumer is idempotent.

### ADR-011: Single repository

**Decision.** Monorepo for backend, frontend, infrastructure, and docs.

**Reason.** Atomic cross-cutting changes (API schema + generated client + tests in one PR), one CI configuration, one source of truth for the submission artifacts the PRD requires (§20).

**Alternatives.** *Polyrepo:* independent versioning and tighter access control, at the cost of cross-repo coordination for every contract change.

**Trade-off.** A larger repository and coarser access control — immaterial at this team size.

### ADR-012: Rolling deployment with expand/contract migrations

**Decision.** Rolling deploys gated on health checks; migrations always backward-compatible with the previous release.

**Reason.** Zero-downtime without a duplicate environment; rollback is a redeploy of the previous digest, which only works if the old code still runs against the new schema.

**Alternatives.** *Blue-green:* instant cutover and rollback, but a full duplicate environment and the same database-compatibility problem anyway. *Recreate:* simple, with downtime — unacceptable given the PRD's deployed-and-working requirement.

**Trade-off.** Two versions run briefly against one schema, which forces migration discipline. That discipline is a feature, not a cost.

---

## 39. Architectural Assumptions

Consolidated. Every one is a gap in the PRD, filled deliberately and reversibly.

| ID | Assumption | Why necessary | Alternative / revisit |
|---|---|---|---|
| A-01 | Admin is read-only over learner content | PRD says "inspect" and calls the panel lightweight (§16); removes a class of risk | Mutating admin with approvals + reason codes, when moderation is required |
| A-02 | Admin role assigned out-of-band | No promotion flow specified; self-service admin would be a vulnerability | Invitation flow (Phase 1) |
| A-03 | Self-hosted email/password auth | Auth required (§18) but no provider named; avoids external dependency in a 4-day build | Managed IdP; localized change thanks to `Principal` + RS256 (ADR-005) |
| A-04 | Email verification stubbed in Phase 0 | No email provider specified; blocking a demo on mail delivery is poor judgment | Enforced in Phase 1 with a transactional email provider |
| A-05 | Admin sees metadata/analytics, not raw documents or free-text answers | Satisfies §16 with minimum privilege | Break-glass content access with mandatory audit reason |
| A-06 | Retention: events 12 months hot, AI detail 90 days, conversations compacted at 180 days, audit 12 months | No retention requirements given; balances "persistent context" (§2) against cost and privacy | Configuration values; set from legal input in production |
| A-07 | Providers/models chosen by *role* in configuration, not named in code | §14 explicitly leaves models open; avoids lock-in | Any provider mix; a thin interface may not expose vendor-unique features |
| A-08 | Context budget split ≈55/20/15/10 (evidence/conversation/learning context/learner state) | A budget must exist; a magic ratio in code would be an invisible assumption | Tuned against the Tutor eval suite |
| A-09 | No regulated data category (health/financial/minors) | PRD describes general skill learning | If minors or EU-regulated data are in scope: DPA review, consent management, residency (Risk R-06) |
| A-10 | Latency targets are engineering targets with stated basis, not measured SLOs | No performance requirements in the PRD; regressions still need a baseline | Replaced by measurements once load testing exists |
| A-11 | Sized for low hundreds of concurrent users in Phase 0 | No user numbers given; sizing justifies the monolith/single-DB choices | Section 24 scaling path; revisit at each phase gate |
| A-12 | Availability: ~99% Phase 0, 99.9% Phase 1 for the core loop (AI features excluded) | No target in the PRD; promising uptime on a third-party dependency would be dishonest | Confirm with business; add provider SLAs if AI features need a target |
| A-13 | Phase 0 on a managed container platform, not Kubernetes | Deployment is required within the build window (§18); K8s cost is unjustified | EKS/GKE when multi-region or multi-team isolation is needed; manifest change only |
| A-14 | RPO/RTO: 24 h/4 h (Phase 0), 15 min/1 h (Phase 1) | No DR requirements given; targets are needed to choose a backup method | Confirm with business; quarterly drills validate or correct them |
| A-15 | English-language material and `english` FTS configuration in Phase 0 | PRD gives no language requirement; the text-search configuration must be chosen | Multi-language: per-material language detection + per-language FTS config, or a multilingual embedding model |
| A-16 | One learner per project; no sharing or collaboration | Nothing in the PRD suggests multi-user projects; assuming it would complicate every isolation control | Collaboration would require a membership table and a rework of RLS predicates — noted in Section 42 |
| A-17 | Cost figures are *estimates* from a configured price table | Providers change prices; "estimated cost" is exactly what §14 asks for | Reconcile against provider billing exports (Phase 1) |

---

## 40. Risks & Mitigations

| ID | Risk | Likelihood | Impact | Mitigation | Residual |
|---|---|---|---|---|---|
| R-01 | **Retrieval quality is poor on real documents** (bad chunking, scanned pages, tables), undermining grounding — the product's core claim | Medium | High | Structure-aware chunking with page anchors; hybrid retrieval + rerank; OCR/vision escalation; retrieval eval suite with labelled pairs; sufficiency gate prevents confident nonsense when retrieval fails | Some documents retrieve poorly; the system says so rather than inventing |
| R-02 | **Model changes silently regress quality** | High | High | Prompt/model versioning recorded per request; CI regression gate on golden sets; online sampling; feature flags to revert a prompt without a deploy | Detection lags by the eval cadence |
| R-03 | **AI cost runs away** (long contexts, retries, abuse) | Medium | Medium | Context budgets, max tokens, per-user daily budgets, small-model routing, caching, cost anomaly alert | Estimation error vs real billing (A-17) |
| R-04 | **Prompt injection via uploaded material** attempts unauthorized action | Medium | High | Structural controls: server-injected scope, per-feature tool allow-lists, data/instruction separation, bounded loop, output validation, full audit | A successful injection can still produce a misleading *answer*, which is a quality issue, not a breach |
| R-05 | **Cross-project leakage through a missed filter** | Low | **Critical** | Four enforcement layers (guard, repository, RLS, retrieval filter) + a dedicated isolation test suite + post-retrieval assertion with alerting | Low, and detectable |
| R-06 | Regulatory scope changes (minors, EU data) | Low | High | A-09 flagged; data minimization and deletion already implemented; residency is a deployment choice | Requires legal review before such a launch |
| R-07 | Provider outage during evaluation/demo | Medium | Medium | Fallback provider, circuit breakers, degraded modes (Section 35), retrieval-only Tutor fallback | Degraded experience during a full multi-provider outage |
| R-08 | Ingestion backlog under a burst of uploads | Medium | Medium | Dedicated queue + independent worker scaling; visible queue position; per-user concurrent-processing cap | Longer waits during bursts |
| R-09 | Modular monolith erodes into a big ball of mud | Medium | Medium | Import-linter contracts in CI, facade-only access, per-module ownership of tables, review discipline | Requires sustained discipline |
| R-10 | Mastery estimates mislead the learner | Medium | Medium | Mastery presented as an estimate with a confidence signal (PRD §10 framing); evidence trail viewable; adaptivity evaluated | Estimation error is inherent; honesty about it is the mitigation |
| R-11 | Open-ended grading is unfair or inconsistent | Medium | Medium | Rubric-based structured grading at temperature 0; agreement measured against human labels; low-confidence grades flagged `pending_review`; feedback explains rather than just scores | Occasional disputed grades |
| R-12 | Scope pressure in a 3–4 day build produces skipped tests or hardcoded secrets | Medium | High | CI gates that cannot be skipped (secret scan, isolation suite, lint/type); Must-Have list mapped to FR ids so cuts are conscious | Some Should-Haves deferred; documented in `limitations.md` |

---

## 41. Scalability Roadmap

### Phase 0 — Prototype (the 3–4 day build)

**Goal:** the complete PRD §19 loop working, deployed, observable, tested, isolated.

- Single API container, 1–2 replicas; one worker container running all queues (routing configured so splitting later is config-only); Beat.
- Managed Postgres (pgvector + FTS), managed Redis, object storage.
- Everything in this document that is *structural*: outbox, tool layer, AI gateway, RLS, citation validation, sufficiency gate, `ai_requests` metering, isolation tests, eval golden sets, CI with security scans, rolling deploys.
- Deferred and documented: email verification (A-04), multi-region, read replicas, PgBouncer, AV scanning, load testing, blue-green.

**Why this is the right Phase 0:** every deferred item is *operational*, and every non-deferred item is *architectural*. Operational gaps are filled with configuration and money later; architectural gaps (no outbox, no tool boundary, no isolation at the DB, no AI metering) are rewrites. The prototype therefore carries the expensive decisions and skips the cheap ones.

### Phase 1 — Early production

**Trigger:** real users, continuous traffic, uptime expectations.

- Split workers per queue; autoscale `documents` on queue depth.
- API autoscaling on CPU + request concurrency; 3+ replicas across AZs.
- Postgres: multi-AZ standby, PITR, **read replica for analytics and admin**, PgBouncer if pool pressure appears.
- Email provider; verification and password reset enforced; MFA optional.
- AV scanning on uploads; WAF tuning; DAST in CI.
- Nightly full evaluation runs with trended dashboards; online sampling raised.
- Load testing to replace assumed targets (A-10, A-11) with measurements.
- Blue-green for high-risk releases; documented runbooks per alert.

### Phase 2 — Scale, only where measurement demands it

Each item has an explicit trigger; none is adopted on principle.

| Change | Trigger |
|---|---|
| Dedicated vector database | >5M chunks or p95 vector search >150 ms at target recall (ADR-003) |
| Extract the document-ingestion service | Ingestion needs a different runtime/hardware (GPU OCR) or a separate release cadence |
| Extract the AI gateway as a service | Multiple products need shared metering/budgeting |
| Durable broker (Kafka/SQS) | Event volume exceeds Redis comfort, or fan-out to external consumers is needed |
| Columnar analytics store | `activity_events` past ~100M rows, or analytics p95 >2 s after partitioning and rollups |
| Multi-region | Availability target above 99.9%, or data-residency requirements (A-09) |
| Kubernetes | Multi-team deployment isolation, complex autoscaling, or multi-region orchestration (A-13) |
| CDN caching of API reads | Measured read-heavy public content — not applicable while all content is private |

**Anti-goals, stated so they are not drifted into:** microservices without a boundary that hurts; Kafka for a workload Redis handles; a second database for a query Postgres answers; GPU inference hosting when provider APIs suffice; a service mesh for one service.

---

## 42. Future Enhancements

Grouped by the PRD's own "Should Have / Nice to Have" framing (§18) plus product extensions the architecture already accommodates.

**Should-Have items with a clear insertion point:**
- Richer document understanding (layout-aware table extraction, diagram description as searchable text) — a new stage in the ingestion pipeline, versioned via `pipeline_version`.
- Background learning insights — another consumer on the `learning` queue.
- Automated regression evaluation on a schedule with trend dashboards — the harness already exists; this is a workflow addition.
- Persistent Tutor continuity improvements (better summarization cadence, salience decay tuning) — inside the Context Composer.

**Product extensions the data model already supports:**
- **Flashcards and spaced repetition** — `concept_mastery.last_evidence_at` plus the decay function is already an SM-2-shaped substrate; needs a card entity and a scheduler task.
- **Concept maps** — `concept_links` exists with `prerequisite_of`/`related_to`; needs visualization and prerequisite-aware recommendation ordering.
- **Learning plans / personalized schedules** — a plan entity over existing recommendations and mastery.
- **Multi-modal learning (audio/video material)** — a transcription stage feeding the same chunk/citation model, with timecodes replacing page numbers as anchors.
- **Voice tutoring** — STT/TTS at the edge of the existing Tutor pipeline; no change to grounding.
- **Notifications and digests** — a consumer on existing events plus an email/push provider.

**Larger changes with real architectural cost (so, deliberately deferred):**
- **Collaboration/shared projects** — invalidates A-16 and requires replacing ownership predicates with membership-based RLS across every table and every tool. Not a feature, a redesign of the isolation model; worth doing once, carefully.
- **Multi-tenancy for institutions** — organization entity, org-scoped admin, per-org data residency and billing.
- **Fine-tuned or self-hosted models** — justified only if provider cost or latency becomes the binding constraint; the AI Gateway's role-based routing is the seam where a self-hosted endpoint would plug in.
- **Richer agentic planning** — justified only if tasks emerge that genuinely need multi-step autonomous planning (e.g. "build me a four-week study plan and execute it"), which today's requirements do not.

---

## 43. Final Architecture Summary

### Architecture Summary

**System architecture.** A modular monolith (FastAPI) serving a Next.js frontend, paired with an independently deployed Celery worker plane. Twelve internal modules with machine-enforced boundaries keep the codebase extractable into services later without paying distributed-systems costs now. The only components that exist are ones a requirement demanded: Postgres, Redis, object storage, and external model providers.

**Major components.** An **AI Gateway** that is the single egress to every model and the single source of AI telemetry; an **Application Capability Layer** that gives the model narrow, validated, authorized, audited tools instead of database access; a **retrieval pipeline** (hybrid vector + lexical, RRF fusion, reranking, sufficiency gating) that makes citations trustworthy and refusals structural; a **deterministic learning engine** (mastery updating and adaptive selection as testable code, not prompts); and a **transactional outbox** that makes the event-driven learning workflows reliable under retry.

**Data flow.** Requests enter through the edge, are authenticated, scoped to a project, and validated before touching a service. Reads are served from indexed queries and precomputed rollups. Writes commit domain rows and their events in a single transaction; the outbox relay hands events to queue-partitioned workers, which are idempotent by construction. Uploaded files bypass the API entirely via presigned URLs and are processed asynchronously into chunks, concepts, and embeddings that carry page anchors — which is what lets every Tutor claim point back to a page the learner can open.

**Security.** Defence in depth on the one invariant that cannot fail: project and user isolation is enforced in the route guard, the repository, Postgres RLS, and the retrieval filter, and is covered by a dedicated test suite. Authentication uses Argon2id with rotating refresh tokens and reuse detection. AI-specific threats are handled structurally rather than by prompt instruction — retrieved content can never become an instruction, tool scope is server-injected, tool access is allow-listed per feature, and every model output that changes state is schema-validated first.

**Scalability.** Compute scales horizontally (stateless API, queue-partitioned workers); data scales vertically first, with explicit, measured triggers for each architectural step — a dedicated vector store, a read replica, a columnar analytics store, a durable broker. The honest bottleneck order (provider limits → ingestion CPU → event write throughput → vector latency → API CPU) is stated so effort goes where it will matter.

**Reliability.** Every external dependency has a timeout, a bounded retry, a circuit breaker, and a defined degraded mode. A full AI provider outage leaves a working product with reduced capability — the Tutor returns evidence passages instead of prose, recommendations fall back to deterministic templates, and everything non-AI is untouched. Retries cannot corrupt state because idempotency is designed into the keys, not bolted on.

**Deployment.** Containerized, configuration- and secret-externalized, deployed by rolling releases gated on health checks, with expand/contract migrations that keep rollback to the previous image digest always available. CI enforces lint, types, module boundaries, tests, isolation tests, AI regression evaluation, and four classes of security scan before an image is ever built.

### Architecture Principles

1. **Isolation is the invariant.** Enforced four times; tested on its own; a breach is treated as a different category of failure from a bug.
2. **Grounding is structural, not aspirational.** Evidence gating happens before generation and citation validation after it, so honesty does not depend on the model's disposition.
3. **The model has no privileges.** It reasons; the application authorizes, executes, and audits.
4. **Model output is untrusted input** until a schema and a validator say otherwise.
5. **Deterministic where determinism is possible.** Mastery, adaptivity, analytics, and scoring are code — testable, explainable, and stable across model changes.
6. **Nothing slow on the user's path.** Async by default, with reliability guaranteed by the outbox and consumer idempotency rather than by hope.
7. **Every component earns its place.** Each technology in Section 37 has a reason and a rejected alternative; each deferral has a trigger.
8. **Observable by construction.** One trace id links a click to the provider call, the retrieved chunk ids, the cost, and the background job that followed.
9. **Fail partially, never totally.** Every dependency has a named degraded mode.
10. **Assumptions are visible.** Seventeen of them, in one table, each reversible.
11. **Build for the next order of magnitude, not the next three.** Architectural decisions are made now; operational ones are made when measurement demands them.

---

## Architecture Review Checklist

- [x] Requirements mapped — every FR/NFR in Section 3 traces to a PRD section and to the components that satisfy it
- [x] Components defined — Section 8 assigns each component a responsibility and an explicit non-responsibility
- [x] Data architecture defined — Sections 13–14, including ownership, indexing, lifecycle, and migration strategy
- [x] API architecture defined — Section 11, conventions plus an endpoint surface derived only from stated requirements
- [x] Security architecture defined — Sections 12, 21, 22; isolation enforced at four layers; AI-specific threats covered structurally
- [x] AI/ML architecture defined where applicable — Sections 17–19: gateway, prompts, structured output, RAG, tool boundary, evaluation, cost control
- [x] Scalability considered — Section 24 with axes, scaling types, statelessness audit, and honest bottleneck ordering
- [x] Reliability considered — Section 25 patterns with placement and rationale; composed timeout budget
- [x] Observability defined — Sections 26–27: three pillars, correlation model, AI-specific metrics, actionable alerts
- [x] Deployment architecture defined — Sections 28–29: cloud-neutral with cloud mapping, rolling deploys, zero-downtime strategy
- [x] CI/CD defined — Section 30 with security scanning, module-boundary enforcement, and AI regression gating
- [x] Disaster recovery considered — Section 36 with phase-split RTO/RPO, backup matrix, and restore drills
- [x] Failure scenarios documented — Section 35 covering only components actually used, each with a degraded behaviour
- [x] Architectural assumptions documented — Section 39, seventeen assumptions with justification and revisit path
- [x] Trade-offs documented — Section 38 ADRs, each with alternatives (advantages/disadvantages) and the accepted trade-off
- [x] Mermaid diagrams validated — eight diagrams consistent with the written architecture: system, request flow, components, ERD, outbox/event flow, AI gateway, RAG, agent/tool loop, security zones, deployment, and six workflow sequences
- [x] No credentials or secrets present — Section 31 uses placeholders only
