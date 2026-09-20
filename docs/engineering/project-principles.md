# Project Engineering Principles — AI Study Companion

**Status:** Binding for all future implementation on this project.
**Purpose:** Every module, endpoint, job, and prompt added to this codebase must be able to answer "which principle does this honour?" Principles are stated with their **enforcement mechanism** — a principle without enforcement is a preference, and preferences drift.

**Source alignment:** Derived from PRD §2 (product principles), §8, §9, §14, §15 (security/quality requirements), §17–§19 (engineering-reasoning evaluation criteria), and the ADR set in `docs/architecture/architecture-decisions.md`. Requirement IDs (FR-xx/NFR-xx) trace to `docs/requirements/requirements-analysis.md`.

---

## 1. Security by design

- Authorization is **explicit at every entry point**: every route resolves a principal and an ownership/scope guard before touching a service; every tool invocation is authorized per-tool; every background task carries and re-checks ownership context. There is no implicit "current user" reaching into business logic.
- Non-owned resources return **404, not 403** — existence itself is information (FR-02, NFR-03).
- Input is validated at the boundary with strict schemas; server-controlled fields (`owner_id`, `role`, `status`) are never bindable from request bodies.
- File uploads: server-generated keys, policy-constrained size/type, magic-byte verification, worker-side parsing with resource caps — the API never parses untrusted bytes.
- *Enforcement:* authorization dependency on every scoped route (code review gate); security unit tests; IDOR-fuzzing in CI; the isolation suite (§3).

## 2. Project-level data isolation is an invariant, not a feature

- Isolation is enforced at **four layers**: route guard → repository scoping (tenant filter mandatory in every tenant query) → database row-level security keyed on a session-scoped variable → tenant filter **inside** retrieval queries (never post-filtering ANN results).
- Background jobs run under the owning user's context; a task without a resolvable ownership context **fails closed**.
- Cross-project leakage is categorized as a **security incident**, not a relevance bug.
- *Enforcement:* dedicated `tests/isolation/` suite (two users, two projects, denial asserted across every endpoint, tool, retrieval path, and job) as its own CI gate; post-retrieval assertion that every chunk's project matches the scope, alerting on mismatch.

## 3. Evidence-grounded AI; no hallucinated citations

- Answers cite only chunks that were **actually retrieved** in that turn; every citation marker is validated against the retrieved set after generation and before display.
- The insufficiency decision is made **before generation**: below the configured sufficiency threshold, the Tutor takes the explicit insufficiency path — the model is never handed thin evidence and asked to resist filling the gap.
- The insufficiency response is a first-class, visually distinct outcome — never a subtle variant of an answer.
- Questions grounded in material, and rubrics, carry source-chunk provenance too.
- *Enforcement:* citation validator in the answer pipeline; sufficiency gate in retrieval; "unanswerable questions produce refusal, not invention" is a golden-set CI gate (FR-35, FR-84).

## 4. AI output is untrusted input

- Every AI-generated structured artifact (quiz question, grade, extracted concept, recommendation draft, insufficiency decision) is parsed against a schema **before it touches persistence or state**. One bounded repair attempt on failure, then a documented per-feature fallback; the fallback is never "persist anyway".
- Model output is rendered in the UI as sanitized content — never raw HTML, never executable.
- *Enforcement:* schema validation as the only write path for model output; `structured_output_validity_rate` tracked per feature with alerting (FR-42).

## 5. Structured AI interaction; the AI never touches the database

- The model has **no** database connection, no internal service handles, no raw SQL, no generic execution tool. It sees a fixed, per-feature allow-list of narrow typed tools.
- Scope (`user_id`, `project_id`) is **injected by the server** from the authenticated context; a model-supplied tenant identifier is rejected outright. Authorization cannot be widened by prompt content.
- Tool calls are honoured only from the model's own tool-call channel; retrieved content and tool results are inserted as delimited, labelled **data** — they can never originate instructions or tool calls.
- The tool loop is bounded (step cap + wall-clock budget); every invocation — authorized or denied — is audited with arguments and outcome.
- *Enforcement:* tool registry as the only execution path; import rules; audit records; loop caps (FR-40, FR-41).

## 6. Deterministic business logic where determinism is possible

- Mastery updates, adaptive question selection, MCQ scoring, and trend classification are **pure, testable code over stored evidence** — never model decisions. LLMs handle language (writing questions at a requested concept/difficulty, grading against a rubric, phrasing recommendations), never arithmetic or learning-state decisions.
- Mastery is recomputable as a pure function of an append-only evidence trail — replayable, auditable, idempotent under event redelivery.
- *Enforcement:* unit tests on the scoring/update math (e.g. "weak concepts are favoured"; "mastery converges regardless of event order"); adaptivity eval metric (selected concepts correlate with low mastery — FR-83).

## 7. Asynchronous by design; idempotent background jobs

- Anything the user does not need to wait for is off the request path: ingestion, grading analysis, the post-quiz chain, rollups, eval sampling. Synchronous = only what the user is waiting for.
- State changes and their workflow events commit **atomically** (transactional outbox semantics); delivery is at-least-once, so **every consumer is idempotent** (dedup table + natural unique constraints). Retried work never duplicates state (NFR-02).
- Jobs carry ownership context; retries use backoff with jitter; exhausted work dead-letters with visibility and replay; queues are partitioned as bulkheads so one workload cannot starve another.
- The browser may close: job state lives server-side; the UI only reflects it.
- *Enforcement:* unique constraints as the idempotency backstop; consumer dedup tests; outbox→consumer integration tests; queue-depth and DLQ dashboards.

## 8. Observable AI calls

- Every model call passes through the single AI Gateway and is recorded: feature, operation, provider, model, **prompt id + version**, latency, time-to-first-token, tokens, estimated cost, outcome/status, retrieval metadata, and correlation ids linking request → background job → AI call.
- Any user-visible AI interaction can be reconstructed from its ids: inputs (per logging policy), retrieved chunk ids, model, cost, outcome (FR-81, FR-82).
- *Enforcement:* import rule — only the AI module imports provider SDKs; a missing metering record for a model call is a defect.

## 9. Versioned prompts, models, and embeddings

- Prompts are versioned artifacts in version control, referenced by id+version in every AI request; model and embedding-model names are stamped on every derived row; derived knowledge carries a pipeline version.
- Changing prompt, model, retrieval strategy, or chunking **requires the evaluation suite to pass** before merge (FR-84). Changing embedding model or pipeline is a **reprocessing job**, not an in-place mutation.
- *Enforcement:* eval gate in CI on AI-affecting changes; `pipeline_version` on derived rows; regeneration scripts over migrations for derived data.

## 10. Testable modules; meaningful coverage over exhaustive coverage

- Domain logic is pure and unit-tested without IO; integration tests use real infrastructure containers; the isolation suite is its own gate; AI-behavioural golden sets gate regressions; one E2E covers the PRD's full loop.
- Coverage is **deliberately unequal**: near-exhaustive on isolation, mastery/selection math, grounding, and idempotency; E2E-covered on glue and UI (NFR-08).
- *Enforcement:* CI stages per layer; merge requires the gates, not an aggregate percentage.

## 11. Clean separation of concerns; modules over services

- Domain modules interact **only through service facades** — never each other's models/repositories; `platform` is the only home for infrastructure concerns; the dependency direction is one-way.
- Module seams are future extraction points: pulling a module into a service means replacing its facade, not rewriting it.
- *Enforcement:* import-linter contracts in CI (facade-only; AI-SDK isolation); per-module table ownership (§13-style ownership map).

## 12. Explicit authorization; least privilege everywhere

- Roles are resolved from the token; admin is read-only by default `[A-01]`; admin access to user data is audited with target ids; the DB application role is non-superuser (RLS cannot be bypassed by the app role); audit logging is append-only and separate from product analytics. Error posture (ADR-0021/Q5): **role/existence failures → 404; capability/policy denials → 403** — every admin-route denial is audit-logged.
- *Enforcement:* admin router guard + audit writes; DB role grants; audit-log immutability at the application level.

## 13. No secrets in source; configuration through the environment

- Secrets exist only in a secrets manager and runtime memory; only `.env.example` (placeholders) is committed; CI secret-scanning fails the build on credential-shaped strings; logs redact credentials **centrally in the formatter**.
- All configuration is env-injected and **validated at startup** — the app refuses to boot on missing/malformed config. Behaviour differences between environments are configuration values, never `if env == "production"` branches in domain code.
- *Enforcement:* gitleaks-class scan; typed settings object; `.gitignore` rules; startup validation.

## 14. Production-quality error handling

- Errors follow one contract (problem+json style) with stable machine-readable types; internal errors never leak stack traces or provider payloads — the client gets a request id it can quote, and support can reconstruct the failure from that id.
- Every external dependency has a timeout, bounded retry with jitter, circuit breaker, and a **named degraded mode**; degradation is user-visible and honest ("AI temporarily degraded", reduced-confidence answers), never silent.
- *Enforcement:* exception taxonomy mapped centrally; failure-scenario matrix as runbooks; chaos checklist per dependency.

## 15. Boring technology, deliberately chosen; every component earns its place

- Each dependency carries a written reason and a rejected alternative; novelty is spent only where it buys something the requirements demand. Fewer moving parts is the default.
- Deferred complexity has **explicit triggers** (e.g. dedicated vector store, read replicas, columnar analytics) — none is adopted on principle.
- *Enforcement:* ADRs for every non-trivial choice; the deferred-decisions table in `architecture-decisions.md`.

## 16. Honesty in the interface and in the documentation

- Mastery is presented as an **estimate with confidence**; low-confidence grades are flagged provisional; insufficiency is unmistakable; general-knowledge answers are labelled and never mixed with cited content; cost figures are labelled estimates.
- Documentation states assumptions, not silent choices; no benchmark or spend numbers are fabricated anywhere.
- *Enforcement:* UI states for provisional/degraded/insufficient; assumptions register (`assumptions.md`) maintained per its rules; review checklist.

---

## Principle → enforcement summary

| Principle | Primary enforcement |
|---|---|
| Security by design | Auth guards on all routes; IDOR fuzzing; upload verification |
| Isolation invariant | 4 layers + `tests/isolation/` CI gate + post-retrieval assertion |
| Grounding / no hallucinated citations | Sufficiency gate + citation validator + golden-set gate |
| Untrusted AI output | Schema-validated write path + validity metric |
| No DB access for AI | Tool registry + import rules + audit |
| Deterministic logic | Unit-tested pure functions over append-only evidence |
| Async + idempotency | Outbox semantics + consumer dedup + unique constraints |
| Observable AI | Gateway metering + correlation ids + import rule |
| Versioned AI artifacts | Prompt/model/pipeline versions + eval CI gate |
| Testability | Layered CI stages; unequal-by-design coverage |
| Separation of concerns | Import-linter contracts; facade-only access |
| Explicit authorization | Role guards; read-only admin; RLS-capable DB role |
| Secrets/config | Startup validation; secret scan; central redaction |
| Error handling | problem+json contract; failure matrix + runbooks |
| Boring technology | ADR requirement; deferred-decisions triggers |
| Honesty | UI states for estimate/degraded/insufficient; assumptions register |

---

## How these principles apply in practice

1. **Before writing code:** the change maps to requirements (FR/NFR ids) and to the principles above; anything assumed gets an entry in `assumptions.md` first.
2. **During implementation:** the module boundary rules (principle 11) and the AI boundary rules (principles 4–5, 8) are checked at every diff; no module reaches into another's tables; no provider SDK leaves the AI module.
3. **Before merge:** the gates run — lint/types, unit, integration, **isolation**, AI golden sets, secret scan, import contracts. A red isolation or grounding gate blocks regardless of feature completeness.
4. **When something must slip:** cuts are conscious — the MoSCoW map (requirements-analysis §9) names what moved and why, recorded in limitations (PRD §20.8). Silent scope reduction is the failure mode the cut protocol exists to prevent.
