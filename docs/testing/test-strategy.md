# Test Strategy — AI Study Companion

**Status:** Strategy for review. Aligned with NFR-08 ("meaningful tests rather than exhaustive coverage, in named areas") and project-principles §10 (coverage deliberately unequal: near-exhaustive on isolation, learning math, grounding, idempotency; E2E-covered on glue/UI).

**The master determinism rule:** anything that is **pure logic** (mastery math, adaptive selection, MCQ scoring, RRF fusion, sufficiency comparison, citation validation, context budgeting, event schema, tool authorization) is tested **deterministically** — exact assertions, no AI in the loop, no flakiness tolerance. Anything that involves a **model** (answer quality, grading nuance, question quality) is tested through the **evaluation suite** (golden sets + rules + validated model-judges), never through ad-hoc "does the output look right" assertions. This document says which is which, per layer.

---

## 1. Test pyramid

```text
                        ┌─────────────────────┐
                        │  E2E (few, whole    │  Playwright-class, staging-like env
                        │  PRD §19 loop)      │
                   ┌────┴─────────────────────┴────┐
                   │  AI evaluation tests          │  golden sets, rule metrics + validated
                   │  (behavioural, gated)         │  model-judges; merge gate
              ┌────┴───────────────────────────────┴────┐
              │  Isolation / authorization tests        │  two users × two projects; every
              │  (RLS, routes, tools, jobs)             │  endpoint, tool, retrieval path, job
         ┌────┴──────────────────────────────────────────┴────┐
         │  Background job + idempotency tests                │  outbox → relay → consumer; retries,
         │                                                    │  dedup, DLQ; real broker + store
    ┌────┴─────────────────────────────────────────────────────┴────┐
    │  API tests (contract level)        Repository tests           │  schema/error contract, real DB,
    │                                    (queries, constraints)     │  RLS session vars, constraints
 ┌──┴────────────────────────────────────────────────────────────────┴──┐
 │  Module/service tests (facade contracts, orchestration, boundaries)  │
 ├───────────────────────────────────────────────────────────────────────┤
 │  Unit tests (pure logic — the deterministic core)                     │
 └───────────────────────────────────────────────────────────────────────┘
```

**Environment classes:** `E0` pure in-process (unit); `E1` containerized infrastructure (DB with RLS, cache, broker, object storage) — no external AI providers; `E2` staging-like, includes recorded-provider AI eval + E2E. **No live provider calls inside any merge gate** (contract-drift checks run on a separate schedule).

---

## 2. Layers in detail

### 2.1 Unit tests — *deterministic*
| Aspect | Definition |
|---|---|
| Scope | Pure functions, no IO: mastery math (BKT-style + decay, difficulty weighting, **order independence**), adaptive selection scoring + difficulty targeting, RRF fusion, diversity cap, sufficiency threshold comparison, citation parsing/validation, context budget allocation, token/price estimation math, event envelope schema, tool argument JSON-schema validation, scope-injection guard, dedup-key derivation, retention/decay/salience math |
| Environment | E0 |
| Determinism | **Fully deterministic** — property-based tests where valuable (permutation invariance of mastery evidence; monotonicity of selection weights) |
| Gate | Every push |
| Traceability | Mastery FR-60; adaptivity FR-52; grounding FR-34/35; citations FR-25/34; context FR-63/64; idempotency NFR-02 |

### 2.2 Module/service tests — *deterministic orchestration, AI stubbed*
| Aspect | Definition |
|---|---|
| Scope | Each module's facade contract (module-contracts.md): inputs/DTOs, typed errors, transaction boundaries, **events emitted with correct payloads**, authorization rejections at the service level. AI-dependent paths use stub gateways with scripted responses (success / timeout / invalid output / rate-limit) — orchestrations must handle all AI failure modes per contract |
| Environment | E0/E1 |
| Determinism | Deterministic given scripted AI responses |
| Gate | Every push |
| Key cases | Tutor finalization commits message+citations+events atomically even on disconnect; Assessment falls back per contract on `AIInvalidOutput` (skip question / `pending_review`); Growth dedups recommendations; Materials rejects unverified uploads; Tools enforces allow-list + scope-injection + audit on every outcome |
| Traceability | Module contracts §1–14; FR-26, FR-40–42, NFR-01/02 |

### 2.3 Repository tests — *deterministic*
| Aspect | Definition |
|---|---|
| Scope | Data access against the real store (E1): query correctness, **in-query tenant filters present**, unique constraints fire (duplicate checksum; one answer per question; mastery-event natural key; active-recommendation dedup; queued/running dedup), RLS session-variable mechanism works at the session layer, partition pruning on event ranges, advisory-style per-material processing guard |
| Environment | E1 (real DB with migrations applied) |
| Determinism | Fully deterministic |
| Gate | Every push (integration stage) |
| Traceability | NFR-02, NFR-03, FR-26 |

### 2.4 API tests — *deterministic contract*
| Aspect | Definition |
|---|---|
| Scope | HTTP contract per endpoint: request/response schemas, status codes, problem+json error bodies, `X-Request-Id` presence, pagination contract, idempotency-key replay behavior, SSE event sequence types for Tutor streaming (against scripted gateway), rate-limit responses, request-size caps |
| Environment | E1 |
| Determinism | Deterministic (AI scripted) |
| Gate | Every push |
| Traceability | API contract in module-contracts; FR-36; NFR-01 |

### 2.5 Authorization tests — *deterministic*
| Aspect | Definition |
|---|---|
| Scope | Role matrix from the contracts: learner owner vs non-owner (404-equivalent everywhere, never 403 existence leaks), **admin-route 404 cases for non-admin principals (ADR-0021/Q5) + mandatory audit entry on every admin-route denial**, admin read-only (every admin route denies mutation; every admin read writes audit), unauthenticated denials, tool-layer per-feature allow-list matrix, server-injected scope (tenant id in tool args rejected + audited as security signal) |
| Environment | E1 |
| Determinism | Fully deterministic |
| Gate | Every push |
| Traceability | FR-02, FR-03, A-01/A-05, FR-40/41 |

### 2.6 RLS / isolation tests — *deterministic; dedicated gate*
| Aspect | Definition |
|---|---|
| Scope | The invariant suite: two users × two projects; denial asserted across **every endpoint, every tool, every retrieval path, every background job**; retrieval filters are in-query (post-filter impossible by construction — verified by query inspection + crafted cross-tenant data); post-retrieval scope assertion raises on mismatch; worker tasks without ownership context fail closed; cross-tenant chunk ids in tool args → denial |
| Environment | E1 (real DB with RLS enabled; app role is non-superuser) |
| Determinism | Fully deterministic |
| Gate | **Own CI gate** — red isolation blocks merge regardless of feature completeness (principles §2/§3) |
| Traceability | NFR-03, G1 invariant; PRD §15 |

### 2.7 RAG retrieval tests — *deterministic metrics over labelled data*
| Aspect | Definition |
|---|---|
| Scope | Pipeline behavior (embed → hybrid → fuse → cap → rerank → sufficiency) against the golden corpus with labelled chunks: recall/ndcg/mrr computed by rules; sufficiency agreement; degraded modes (embedder down → lexical-only flag; reranker down → fused order + raised threshold flag) exercised with stub providers |
| Environment | E1 with stub/fixed-fixture embedding + rerank responses; identical corpus via fixtures |
| Determinism | Deterministic with fixture vectors; live-embedding variance handled by the separate scheduled contract check, never in the merge gate |
| Gate | Merge gate (with the AI eval stage) |
| Traceability | FR-24/25, FR-34/35; evaluation-strategy §2.2 |

### 2.8 AI evaluation tests — *the model-behavior layer (this is where AI lives in testing)*
| Aspect | Definition |
|---|---|
| Scope | The suites in evaluation-strategy.md: tutor answer quality/groundedness, citation validity (structural), refusal correctness/fabrication (structural zero-tolerance), quiz generation quality, grading agreement, recommendation targeting/actionability |
| Method | Rule metrics first; validated model-judges for judgment metrics; human labels as ground truth; all results persisted against prompt/model versions |
| Environment | Recorded fixtures in CI; live-provider checks scheduled separately |
| Determinism | **Not fully deterministic by nature** — made trustworthy via: temperature-0 generation where the contract requires it, repeated-run consistency metrics, judge-agreement validation, and structural zero-tolerance rules that *are* deterministic |
| Gate | Merge gate for armed metrics (structural rules + calibrated thresholds); baseline-delta failure blocks |
| Traceability | FR-83, FR-84, FR-35 |

### 2.9 Background job tests — *deterministic*
| Aspect | Definition |
|---|---|
| Scope | Real broker + store (E1): outbox commit → relay → consumer end-to-end; consumer dedup on redelivery (`(consumer, event_id)` + natural keys); retry/backoff behavior per event policy; poison task → DLQ with job-run record + admin visibility; broker-down → events stay pending, no loss; task without ownership context fails closed; queue separation (a blocked documents queue does not delay learning-queue consumption) |
| Environment | E1 |
| Determinism | Deterministic (time-dependent parts use controllable clocks) |
| Gate | Every push (integration stage) |
| Traceability | FR-26, FR-73/74, NFR-01/02, BP-01–05 |

### 2.10 Idempotency tests — *deterministic (cross-cutting)*
| Aspect | Definition |
|---|---|
| Scope | Every NFR-02 surface: idempotency-key replay on mutating POSTs (returns recorded result, no duplicate state); duplicate upload by checksum; double answer submission; redelivered events; duplicate tool invocation (dedup returns existing); re-run ingestion per pipeline version (replace-not-append); recompute idempotent |
| Environment | E1 |
| Determinism | Fully deterministic |
| Gate | Every push |
| Traceability | NFR-02 end-to-end |

### 2.11 End-to-end tests — *few, whole-loop, AI-included but pinned*
| Aspect | Definition |
|---|---|
| Scope | The PRD §19 demonstration loop: register → space → project → upload fixture PDF → wait ready (polled) → tutor grounded answer **with valid citation** → unsupported question → explicit refusal → adaptive quiz (MCQ + open-ended) → feedback → mastery visible → growth/recommendation present → analytics populated → admin view shows the journey |
| Environment | E2 staging-like; AI responses pinned to recorded fixtures for CI stability; a separate nightly E2E runs against live providers (not a merge gate — contract-drift detector) |
| Determinism | Flow deterministic with fixtures; assertion focus on **structural** properties (status fields, citation resolution, refusal occurred) — not prose quality (that's the eval suite's job) |
| Gate | Merge to main / pre-deploy |
| Traceability | §19 journey; FR-09/NFR-09 "working end-to-end"; all FRs' integration |

---

## 3. Deterministic vs AI-evaluated — the explicit split

| Fully deterministic (unit/integration, exact assertions) | Requires AI evaluation (golden sets, judged) |
|---|---|
| Mastery math + order independence | Tutor answer quality/relevance |
| Adaptive selection scoring + difficulty targeting | Groundedness of claims (judged layer) |
| MCQ scoring | Quiz question quality (answerability, distractors) |
| RRF fusion, diversity cap, top-k mechanics | Grading feedback quality (actionability) |
| Sufficiency threshold comparison (given scores) | Recommendation phrasing relevance |
| Citation marker resolution + page attribution (rule) | Refusal near-miss band judgment |
| Context budget allocation | Model-judge calibration itself |
| Tool allow-list/scope/audit rules | — |
| Event schemas, dedup keys, envelope validation | — |
| Idempotency/retry/DLQ behavior | — |
| Isolation/authorization matrices | — |

**Rule of thumb enforced in review:** if the expected output can be written as an exact assertion, it lives in the deterministic layers; if it requires judging *language*, it belongs to the AI evaluation suite with labels and a validated judge — and never as a flaky unit test.

---

## 4. CI gate order (conceptual pipeline)

```text
push / PR
 ├─ static: lint · type check · import-boundary contracts · secret scan
 ├─ unit (E0)                          ← deterministic core
 ├─ integration (E1): repository · API · module · jobs/idempotency
 ├─ isolation + authorization gate     ← dedicated, blocking
 ├─ AI evaluation (fixtures, E1): structural rules always armed;
 │    calibrated-threshold metrics armed once baselines exist
 ├─ build + image scan + SBOM
 └─ E2E (E2, pinned fixtures)          ← merge-to-main / pre-deploy
scheduled: live-provider contract checks · nightly live E2E · (Phase 1) load
```

A red **isolation**, **grounding-structural**, or **idempotency** gate blocks merge regardless of feature completeness — the cut protocol (requirements-analysis §9) governs deliberate scope reductions, never skipped gates.

---

## 5. What we deliberately do **not** test

- Prose quality via string-matching (brittle, meaningless) — judged metrics instead.
- Exact token counts from providers (unstable) — budgets asserted as caps, not exact numbers.
- Third-party availability in merge gates — scheduled contract checks only.
- Pixel-level UI snapshots as primary gates — E2E asserts function + accessibility basics; visual regressions are review concerns.
- Exhaustive CRUD permutations on every module (low-value duplication) — contract tests cover the surface; the unequal-coverage rule spends depth where the risk is (isolation, math, grounding, idempotency).
