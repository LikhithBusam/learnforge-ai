# Architecture Decision Records — AI Study Companion

**Status:** Planning artifacts for review — no implementation has begun.
**Format:** Each record states Decision, Context, Options considered, Decision rationale, Consequences, Open questions.
**Important:** At this stage, only decisions that are **forced by the requirements themselves** or are **prerequisites for any correct implementation** are made. Technology selections (exact DB engine, cache, broker, framework versions, model vendors) are deliberately **not finalized** here — those get their own ADRs during Phase 0 once the requirements analysis is approved. This keeps an unnecessary-technology-checkpoint from contaminating the plan.

**Consistency note:** The repository already contains `architecture.md` (a full architecture baseline for this PRD). These records are the initial ADR set for the engineering process and align with that baseline; where a baseline choice exists, it is cited as prior art rather than re-argued, and the ADRs below are the ones that must be settled **before any code**. If reviewers amend a decision here, `architecture.md` should be updated to match so the two never diverge.

---

## ADR-0001: Modular monolith with an asynchronous worker plane (no microservices)

- **Decision:** Build one backend application, internally partitioned into strictly-bounded domain modules that communicate only through typed service facades, plus an **independently deployed worker plane** for long-running and scheduled work. Do not build microservices.
- **Context:** PRD §1/§18 set a 3–4 day prototype window; §19 demands production-grade reasoning. The workload has exactly one independent scaling axis — background AI/document work (§2 "Asynchronous by Design", §5, §13). Team size is small; domain boundaries are hypotheses, not proven seams. One team, one repo, one public deployment.
- **Options considered:**
  1. **Modular monolith + separate worker plane** ✅ — one deployable app (API + business logic), one worker deployable, shared codebase.
  2. Microservices per domain — independent scaling/deployment at the cost of distributed transactions (mastery + events + answer commit would become a saga), network failure modes, N pipelines, tracing complexity, and premature boundaries that ossify wrong guesses.
  3. Serverless functions — cold starts hurt Tutor streaming; long document processing fights execution limits; connection pooling is awkward; local dev degrades.
  4. Pure single-process app without workers — would block the request path on minutes-long OCR, violating "Asynchronous by Design" (§2) and FR-23/§13 (browser may close).
- **Decision rationale:** A monolith gives **atomic transactions across learning state** (answer + mastery event + workflow trigger commit together — FR-55, FR-73), which microservices would turn into distributed sagas. The worker split captures the *real* scaling boundary at near-zero cost: same codebase, different entrypoint. Boundaries are enforced in code review + tooling rather than the network.
- **Consequences:**
  - (+) Fastest correct build for the window; atomic cross-module consistency; module seams double as future extraction points.
  - (−) One API deploy touches all modules; a runaway module can affect neighbours — mitigated by facade-only access, per-module metrics, import-linting (future), and rollback by image digest.
  - Requires machine-enforced module rules (facade-only imports; only the AI module imports provider SDKs) or the monolith erodes into a ball of mud (risk in requirements-analysis §15).
- **Open questions:** none blocking; the module list in `requirements-analysis.md` §11 is ready for review.

---

## ADR-0002: Project-level data isolation is a multi-layer invariant enforced down to the database

- **Decision:** Isolation (user + project) is treated as an **architectural invariant with defence in depth**: (1) explicit authorization guard on every scoped route, (2) scoping parameters required in every tenant-data repository query, (3) **row-level enforcement in the database itself** keyed on a session-scoped tenant/user variable, (4) tenant filter **inside** every retrieval query (never post-filtering), plus (5) a dedicated isolation test suite as its own CI gate. Non-owned resources return **404, never 403**, to avoid existence disclosure.
- **Context:** PRD §15 (and §3) make per-user/per-project isolation a core requirement; §2 makes "Context First" a product principle; §8 requires tool execution to be scope-checked. A single application-layer miss (one forgotten `WHERE project_id`) is a breach, not a bug. Background jobs must preserve ownership context (§15).
- **Options considered:**
  1. Application-layer checks only — one missed query = breach; no safety net.
  2. Application checks + DB-level RLS + in-query filters + isolation test suite ✅ — defence in depth; the DB rejects what the app forgets.
  3. Separate database/schema per tenant — operationally heavy for a 4-day window; unnecessary at single-DB scale; complicates cross-project admin aggregates (FR-90).
- **Decision rationale:** The one invariant the product cannot violate deserves redundant enforcement. DB-level enforcement makes isolation hold even under a buggy query or a compromised code path, and applies identically to workers if session variables are set per task (§15 requirement).
- **Consequences:**
  - (+) Isolation survives application bugs; admin aggregates still possible via an explicit bypass role used only by migrations/aggregation jobs.
  - (−) Every DB session must set the tenant context (request path and worker tasks); connection pooling interacts with `SET LOCAL` semantics — pooling strategy must be chosen with this in mind (open question below); slightly more ceremony in repositories and tests.
- **Open questions:**
  1. Confirm 4-layer posture (reviewers flagged in requirements-analysis §17.2).
  2. Connection-pooling mode must be compatible with transaction-scoped session variables — to be settled in the DB ADR.
  3. Worker tasks must refuse to run without an ownership context (fail closed) — to be encoded in the jobs module design.

---

## ADR-0003: Grounding is structural — sufficiency gate before generation, citation validation after

- **Decision:** Honest, grounded Tutor behaviour is enforced **structurally**, not by prompt instruction alone:
  1. **Pre-generation gate:** retrieval produces an evidence set with a sufficiency decision (threshold + minimum supporting chunks, configurable and eval-tuned). Below it, the Tutor answers via the explicit insufficiency path — generation for a grounded answer never happens.
  2. **Prompt contract:** system prompt requires every claim to map to numbered evidence blocks; output carries a machine-readable answer status.
  3. **Post-generation validation:** every citation marker is checked against the retrieved set; unsupported claims downgrades the answer to the insufficiency response. Hallucinated citations cannot reach the user.
  The insufficiency response is useful (what materials cover, suggested actions, opt-in clearly-labelled general-knowledge answer).
- **Context:** PRD §7 makes grounded answers + citations and explicit insufficiency handling "a core evaluation requirement"; §5 requires traceability to source (FR-25); §15 requires AI-specific security. Prompt-only honesty is not a control — models fill evidence gaps under pressure.
- **Options considered:**
  1. Prompt instructions only ("cite your sources, say when unsure") — not enforceable, unmeasurable, exactly the failure PRD §7 targets.
  2. Structural gate + validation ✅ — refusal decided before generation; citation validity machine-checkable, evaluable, and alertable.
  3. Post-hoc claim verification against a second model pass — adds cost/latency on every turn and still admits the answer to the model with thin evidence.
- **Decision rationale:** The refusal property becomes independent of model disposition, testable in CI (unanswerable questions → refusal, not invention), and observable via sufficiency/citation-validity metrics (FR-81–83). This is the direct implementation of the "no hallucinated citations" principle.
- **Consequences:**
  - (+) Grounding is evaluable and gated; false-confidence answers become structurally impossible when evidence is thin; general-knowledge answers are clearly labelled and never mixed with cited content.
  - (−) Thresholds (τ, min chunks, k values) are tunable policy that must live in configuration and be tuned against an evaluation set — never magic numbers in code; over-conservative thresholds may refuse answerable questions (tuned via eval).
- **Open questions:** threshold starting values and the labelled eval set construction (answerable + unanswerable) — needed before retrieval tuning, tracked as pre-implementation decision D-2.

---

## ADR-0004: The AI has zero privileges — capability layer, server-injected scope, untrusted output

- **Decision:**
  - The model **never** receives a database connection, internal service objects, raw SQL, or generic execution tools. It sees a fixed catalogue of narrow, typed, allow-listed tools (per feature), each with JSON-Schema-validated arguments and per-tool authorization.
  - **Scope is injected by the server** (`user_id`, `project_id` from the authenticated request context); a model-supplied tenant id is rejected outright.
  - Tool results are inserted back as delimited, labelled **data**; retrieved content can never originate a tool call (tool calls are only honoured from the model's own tool-channel).
  - Every tool invocation — authorized or denied — is audited.
  - All AI-generated structured data is **schema-validated before persistence or state change**; one bounded repair attempt on validation failure, then a documented per-feature fallback; structured-output validity is a tracked metric.
- **Context:** PRD §8 (FR-40–42) requires controlled, validated, permission-aware AI interaction; §15 requires that materials/messages are never trusted instructions (NFR-05) and that AI-generated structured data be validated (§8). A prompt-injected PDF must not be able to widen authorization.
- **Options considered:**
  1. Model queries the DB directly (function-calling into SQL) — violates FR-40/41 outright; unbounded blast radius.
  2. Free-form agent with dynamic tools — nondeterministic surface, per-call authorization becomes advisory, audit becomes partial.
  3. Fixed narrow tool catalogue + server-injected scope + validation + full audit ✅.
  4. Multi-agent planner/critic fleets — adds nondeterminism, cost, latency; the PRD asks for controlled interaction, not autonomy (§8).
- **Decision rationale:** Authorization that the model cannot influence cannot be bypassed by injection. Schema validation implements FR-42 literally. Bounded loop (step + wall-clock caps) bounds cost and runaway behaviour (NFR-01).
- **Consequences:**
  - (+) Injection cannot escalate privileges; every AI side-effect is auditable (supports FR-82, admin views); deterministic fallbacks per feature.
  - (−) Every new AI capability requires registry/schema/authz wiring; the model can only do what the catalogue allows (by design).
- **Open questions:** the exact Phase 0 tool list (candidate set from PRD §8: search materials, get progress, get assessment history, identify weak concepts, generate quiz, record learning event, update learning context, generate recommendation) — to be confirmed during tutor/tools design, not before.

---

## ADR-0005: Deterministic business logic for mastery, adaptivity, and scoring — LLMs for language, not arithmetic

- **Decision:** Mastery updating, adaptive question selection, MCQ scoring, and trend classification are **deterministic, unit-testable code** operating on stored evidence (append-only mastery events; mastery recomputable as a pure function of that trail). LLMs are used only for language tasks: writing questions at a requested concept/difficulty, grading open-ended answers against a rubric, phrasing recommendations whose *target* was chosen deterministically, extracting concepts.
- **Context:** PRD §9 explicitly rejects naive adaptivity (wrong→easy/correct→hard) and requires selection to weigh mastery, uncertainty, mistakes, recency, difficulty, and history (FR-52); §10 requires mastery that evolves with evidence (FR-60); §14/§18 require evaluation of adaptivity and grading quality (FR-83). Nondeterministic selection would be untestable, unexplainable, and unstable across model changes.
- **Options considered:**
  1. LLM chooses next question/concept — flexible but nondeterministic, costly per question, impossible to unit-test, unexplainable, regresses invisibly with model updates.
  2. Fully naive heuristic (recent mistakes only) — explicitly rejected by PRD §9.
  3. Deterministic weighted scoring policy + BKT-style mastery update from append-only evidence ✅.
- **Decision rationale:** PRD §19 evaluates engineering reasoning: a scoring function over stored evidence is testable (assert weak concepts are favoured; assert decay drives revisits), explainable to the user ("asked because…"), reproducible across model changes, and free. Append-only evidence + pure recomputation also gives idempotency under retried events (NFR-02) and replayable growth analysis (FR-61).
- **Consequences:**
  - (+) Adaptive selection and mastery can be demonstrated and evaluated (FR-83 "adaptivity check"); no hidden model drift in learning state; evidence trail is user-visible.
  - (−) Selection is less "intelligent-seeming" than a model might be; weights are tunable configuration that must be calibrated against the eval suite, not guessed.
- **Open questions:** exact weight set + mastery update formula parameters — design-time choices within the assessment/mastery modules, tuned against evaluation, recorded in evaluation docs (PRD §20.7).

---

## ADR-0006: Durable asynchronous work via transactional outbox semantics + consumer-side idempotency

- **Decision:** Long-running/derived work (ingestion, post-quiz chain, rollups, eval sampling) is dispatched through a **transactional outbox**: the business transaction writes domain rows **and** the event row atomically; a relay publishes to the task queue; consumers are idempotent (dedup table + natural unique constraints) because delivery is at-least-once. Retries use backoff; exhausted work dead-letters with admin visibility and replay. Background tasks carry the ownership context and fail closed without it (ADR-0002).
- **Context:** PRD §12/§13 require event-driven workflows with retries, duplicate handling, and idempotency (FR-73, FR-74); §2 demands "Asynchronous by Design"; §5 requires retry/failure/duplicate-job handling (FR-26). Publishing to a broker inline after a DB commit is a dual-write: under failure, state and events disagree — the class of bug that appears only under load.
- **Options considered:**
  1. Inline publish to broker after commit — simplest; silently loses events on crash between commit and publish.
  2. Transactional outbox + relay + idempotent consumers ✅ — atomicity by construction; no new infrastructure beyond the task queue.
  3. Kafka / durable log — strong guarantees but operationally disproportionate at this scale (§19 "boring technology").
- **Decision rationale:** Implements FR-73/74 and NFR-02 literally, with the durability living in the transactional store (the system of record) rather than the broker. Queue **partitioning** (documents / learning / analytics / evaluation) provides bulkhead isolation so an ingestion burst cannot delay the learning loop.
- **Consequences:**
  - (+) No lost workflows under crash; duplicate-safe consumers; DLQ makes failures visible work items; broker loss delays but never loses work (events remain pending in the store).
  - (−) Small publication latency (relay cadence; mitigated by a post-commit nudge); one extra table + relay process; every consumer must implement dedup (discipline).
- **Open questions:** concrete broker/task framework choice (Celery-class vs alternatives) — deferred to the Phase 0 infrastructure ADR; the outbox contract above is independent of that choice.

---

## ADR-0007: Single AI Gateway as the only egress to model providers

- **Decision:** One module (`ai` — the AI Gateway) is the **only** code path to any model provider, enforced by import rules. It provides provider-neutral operations (generate, stream, structured, embed, rerank, evaluate, document-understand), per-feature model routing by **role** in configuration, prompt resolution with **versioned prompts**, timeouts, bounded retries, circuit breaking with fallback chains, structured-output validation, and per-call metering (model, feature, latency, tokens, estimated cost, outcome, prompt version, retrieval metadata) persisted for product-visible AI analytics.
- **Context:** PRD §14 (FR-80–84) requires provider-neutral abstraction, per-request tracking, investigation support, evaluation hooks, and regression awareness. Domain code with scattered SDK calls cannot be metered, cost-bounded, or evaluated coherently.
- **Options considered:**
  1. Direct SDK calls in each module — vendor lock-in, unmeasurable, no coherent fallback/cost story.
  2. Heavy orchestration framework (LangChain-class) — abstraction hides exactly what must be observable (latency, cost, prompts, retrieval sets); version churn.
  3. Purpose-built thin gateway ✅ — a few hundred lines, fully understood, fully instrumented.
- **Decision rationale:** The gateway is the enforcement point for FR-81/82 (every call recorded with feature/cost/latency) and the seam where eval sampling, budget enforcement, and provider fallback live. Versioned prompts + per-request prompt ids make regressions attributable (FR-84). Role-based model config avoids lock-in `[A-07]`.
- **Consequences:**
  - (+) One place for cost budgets, circuit breaking, fallback, validation, metering; provider swap = config + adapter; admin AI views read relational telemetry.
  - (−) All provider calls funnel through one module (a code-review-enforced boundary); thin abstraction may not expose vendor-unique features — adopting one is a deliberate interface change, never a smuggled dependency.
- **Open questions:** provider selection per role (decided at Phase 0 with budget constraints); price-table source for cost estimates `[A-17]`.

---

## ADR-0008: Presigned direct-to-storage uploads; documents processed in the worker plane

- **Decision:** File bytes **never pass through the API process**. Uploads use short-lived presigned URLs with server-generated keys and policy-constrained content-type/size; on confirmation the backend verifies existence, size, and **magic bytes** (never trusting declared type/extension), computes a checksum, and records the material + dispatch event atomically. Parsing/OCR/chunking/embedding happen exclusively in workers with resource limits (page/time/memory caps), so a malicious or bomb PDF kills a task, not the API.
- **Context:** PRD §5 (FR-20–26) requires PDF upload with async processing and failure handling; §15 requires secure document handling; §13 requires the browser not to stay open.
- **Options considered:**
  1. Multipart upload through the API — saturates API workers with byte shuffling; couples upload latency to API capacity; complicates streaming.
  2. Presigned direct upload + worker-side verification/processing ✅.
- **Decision rationale:** Keeps large uploads off the request path (NFR-06), isolates parsing risk in the worker plane (§15), and the checksum + unique constraint per project gives duplicate-upload handling (PRD §5).
- **Consequences:**
  - (+) Upload confirmations stay fast; processing risk contained; direct client→storage transfer scales independently.
  - (−) Requires storage endpoint reachability from the browser and presign/verify logic; upload confirmation must verify the object actually landed (client honesty is not assumed).
- **Open questions:** size/page caps as configuration values; object storage provider (deferred to infrastructure ADR).

---

## ADR-0009: Context is composed under a token budget — never "send the whole history"

- **Decision:** Every Tutor turn composes context from four sources under an explicit token budget with configured shares: retrieved evidence, conversation (recent window + rolling summary of the rest), structured learning-context items (salience-ranked), and learner state (goal, relevant mastery, recent mistakes). Budget shares and window sizes are configuration tuned by evaluation, not magic numbers in code.
- **Context:** PRD §6 requires the Tutor to understand goal, materials, concepts, prior conversation, assessment history, and learning context (FR-31) while §11 requires retrieving *only* relevant context (FR-64) and §2 demands "Persistent but Relevant Context". §15/NFR-06 require avoiding unnecessary token spend.
- **Options considered:**
  1. Send full conversation history each turn — violates FR-33/FR-64; costs grow per turn; context dilution.
  2. Vector-memory-only approach — loses structured facts (goals, repeated mistakes) that §11 explicitly requires.
  3. Budgeted multi-source composer with rolling summaries + structured learning-context store ✅.
- **Decision rationale:** Directly implements PRD §11's select-and-compose requirement; keeps latency and cost bounded per turn (NFR-06); the structured learning-context store is what makes durable facts (weaknesses, goals, preferences) retrievable by relevance rather than position in a chat log.
- **Consequences:**
  - (+) Bounded per-turn cost/latency; relevance-first context; durable facts survive across sessions (FR-63).
  - (−) Summarization and salience logic need their own maintenance (async post-turn processing); budget shares need eval tuning.
- **Open questions:** summarization cadence and salience decay parameters — tutor-module design items, tuned against the Tutor eval suite.

---

## ADR-0010: Frontend = Next.js (App Router) + server-state cache library; SSE for Tutor streaming

- **Decision:** The web client is a **Next.js (App Router, TypeScript)** application using a server-state cache/query library with polling for async job status, and **SSE (not WebSockets)** for Tutor token streaming. Dashboards are server-component-heavy; citations and the insufficiency state are first-class UI states (visually distinct, not subtle styling). ADR-0001 keeps it decoupled from the API.
- **Context:** PRD §15/§18 (FR-36) require streaming; §5/§13 require polled document status with the browser free to close; §4/§16 are dashboard-heavy read surfaces; §7 requires citations with document+page and §7/FR-35 require unmistakable insufficiency UX.
- **Options considered:**
  1. Plain React SPA — more client-side data plumbing; worse dashboard first-paint; no SSR.
  2. WebSockets — bidirectional machinery not needed for one-way token streams; stateful connections, sticky sessions, LB complexity.
  3. Polling only — simple but defeats streaming; poor perceived latency for Tutor answers.
  4. Next.js + query library + SSE ✅.
- **Decision rationale:** SSE is unidirectional (matches the interaction), traverses ordinary HTTP infrastructure, and reconnects natively. A query library handles the dominant state shape here — server state with polling/backoff for job status. Server components fit dashboard-heavy reads.
- **Consequences:**
  - (+) Fast dashboard reads; simple streaming ops story; citations/insufficiency are explicit render states supporting FR-34/35 evaluation.
  - (−) Client→server messages remain ordinary POSTs (fine for this interaction shape); SSE fan-out across replicas needs a pub/sub channel (platform concern).
- **Open questions:** exact UI component library (shadcn/Radix-class suggested for speed, final call at Phase 0 start); chart library (lightweight, declarative).

---

## ADR-0011: Monorepo with generated API client

- **Decision:** Single repository containing backend, frontend, infrastructure manifests, and documentation. The frontend consumes a **generated typed client** from the API's OpenAPI schema, keeping client/server contract drift machine-detectable.
- **Context:** PRD §18–20 requires co-located submission artifacts (README, architecture docs, evaluation docs, limitations); one team; API + workers share domain code (ADR-0001).
- **Options considered:**
  1. Polyrepo — independent versioning but coordination cost for every contract change; submission artifacts split across repos.
  2. Monorepo ✅ — atomic cross-cutting changes (schema + generated client + tests in one PR), one CI config, one source of truth for §20 artifacts.
- **Decision rationale:** Matches ADR-0001's shared-code requirement and keeps the PRD §20 submission set in one place; generated-client rule turns API drift into a CI failure rather than a runtime surprise.
- **Consequences:**
  - (+) Atomic contract changes; single CI; docs co-located.
  - (−) Larger repo; coarser access control (immaterial at team size).
- **Open questions:** none blocking.

---

## ADR-0012: Configuration and secrets are externalized and validated at startup

- **Decision:** All configuration flows from environment variables, parsed and **validated at startup** by a typed settings object; the application refuses to boot on missing/malformed config. Secrets exist only in a secrets manager/platform injection at runtime; only `.env.example` (placeholders) is committed; secret scanning runs in CI; logs redact secrets centrally in the log formatter (not per-call-site). No environment-conditional code paths in domain logic — behaviour differences are configuration values.
- **Context:** PRD §18 (NFR-07) prohibits secrets in source; §17/§19 demand justified choices and operational honesty; §14 requires cost/latency parameters (thresholds, budgets, model roles) that must be tunable without code changes.
- **Options considered:**
  1. Config files in repo per environment — leaks secrets; drift.
  2. Env-only + typed startup validation + secrets manager + gitleaks-class CI scan ✅.
- **Decision rationale:** 12-factor alignment; fail-fast boot catches misconfiguration before first request; central redaction means one careless log line cannot leak a credential; configuration-as-values is what makes thresholds/budgets tunable per ADR-0003/0005/0007 without redeploying code semantics.
- **Consequences:**
  - (+) No secrets in VCS; rotation without code change (restart); environment behaviour differences are visible in config, not buried in `if env ==` branches.
  - (−) Startup dependency on complete config (a deliberate fail-fast); local dev needs a documented `.env.example`-based setup.
- **Open questions:** none blocking; the variable catalogue will be drafted with the infrastructure ADR in Phase 0.

---

## Decisions deliberately deferred (with their trigger)

| Decision | Deferred until | Trigger / reason |
|---|---|---|
| ~~Database engine + vector + FTS strategy~~ | **RESOLVED — ADR-0013** (PostgreSQL 16 + pgvector + FTS; external vector DB deferred with measured triggers) | — |
| ~~Cache/broker/rate-limit component~~ | **RESOLVED — ADR-0014** (Redis + Celery; durable record stays in Postgres outbox) | — |
| ~~Application frameworks (backend/frontend)~~ | **RESOLVED — ADR-0017** (FastAPI + Next.js/TypeScript) | — |
| ~~Authentication approach~~ | **RESOLVED — ADR-0018** (self-hosted JWT RS256 + rotating refresh; advanced features deferred explicitly) | — |
| ~~Deployment platform + IaC specifics~~ | **RESOLVED — ADR-0019** (managed container platform + Compose local; AWS/K8s are Phase 1/2 triggers) | — |
| ~~Observability stack~~ | **RESOLVED — ADR-0020** (OTel → hosted free-tier backends; ai_requests + job_runs spine) | — |
| ~~Object storage~~ | **RESOLVED — ADR-0016** (S3-compatible; MinIO dev → managed prod) | — |
| LLM/embedding/rerank/vision vendors per role | Build kickoff — ADR-0015 addendum | A-07 keeps domain code role-based; selection input = golden-set trial + price table, not popularity |
| Exact UI kit + chart library | Phase 0 build start | Speed-oriented default exists (ADR-0010/0017); no requirements force it now |
| Retrieval thresholds + HNSW parameters | Retrieval tuning phase | Calibrated against the eval set (A-20); never magic numbers |
| Microservice extraction of any module | Post-prototype, on measurement | ADR-0001 revisit triggers |

---

## Decision dependency map

```text
ADR-0001 (monolith + workers) ──┬── ADR-0006 (outbox) ── broker choice (deferred)
                                ├── ADR-0002 (isolation layers) ── DB choice (deferred)
                                └── ADR-0011 (monorepo)

ADR-0003 (structural grounding) ──┬── ADR-0007 (gateway: metering, thresholds)
                                  └── eval suite design (FR-83/84)

ADR-0004 (capability layer) ── ADR-0007 (gateway) + tools module design

ADR-0005 (deterministic learning logic) ── assessment/mastery module design

ADR-0012 (config/secrets) ── every module; unblocks all implementation
```

Nothing in the deferred table blocks writing requirements, module contracts, test strategy, or the eval set design — which is the recommended next step.

---

**Series continuation:** the technology decisions deferred above are resolved in `adr/ADR-0012b` (criteria) through `adr/ADR-0020`, summarized in `technology-baseline.md`; the open contract questions were resolved in `adr/ADR-0021-open-contract-resolutions.md` (with a per-document change log); cross-document consistency is audited in `consistency-audit.md`.
