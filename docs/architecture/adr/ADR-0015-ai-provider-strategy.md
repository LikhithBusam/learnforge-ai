# ADR-0015: AI Provider Strategy — Capability Roles Behind the AI Gateway

**Status:** DECIDED (architecture); specific vendor/model choices DEFERRED to build start (selection is a budget/quality exercise, not an architecture one) · **Criteria basis:** C4, C6, C7 · **Resolves:** deferred "provider roles" row · **Contracts affected:** §M.11 (AIGateway), ADR-0007

## Decision

Domain code calls **only the AI Gateway** (`AIGateway` contract, §M.11). The Gateway routes each call by **capability role**, mapped to concrete provider/model in **configuration** (env-injected, never hard-coded). Import rules permit provider SDKs **only** inside `app/ai/providers/` adapters. Credentials come exclusively from runtime secrets (security-baseline.md); none are committed, logged, or exposed in errors.

## Model roles (capability-based, not vendor-based)

| Role | Used by | Required capabilities | Temperature/params posture | Fallback role |
|---|---|---|---|---|
| `generation.reasoning` (primary) | Tutor grounded answers, streaming | Strong instruction following, long-context, **streaming**, low-refusal-compliance under grounding prompt | Default; pinned per prompt version | `generation.reasoning.fallback` |
| `generation.grading` | Open-ended answer grading, quiz-level analysis | Structured output reliability, rubric faithfulness | **Temperature 0**, deterministic params (grading consistency metric depends on it) | same-role fallback model |
| `generation.mid` | Question generation, recommendation phrasing | Structured output, cost efficiency | Default/low | `generation.mid.fallback` or template |
| `generation.small` | Query rewriting, intent/routing classification | Sub-second latency, trivial tasks | Default | skip (deterministic path) |
| `embedding` | Chunk + query embeddings | Fixed dimensions (config, e.g. 1536 — dimension pinned per ADR-0006 schema plan), batch API | n/a | **degrade to lexical-only retrieval** (documented degraded mode) |
| `rerank` | Evidence rerank top-k→top-6 | Cross-encoder-style relevance scoring | n/a | skip rerank + raise sufficiency threshold (flagged) |
| `evaluate` (judge) | Model-judged eval metrics | Rubric adherence, structured scoring | Temperature 0 | none — judged metrics then don't gate (judge must be human-validated) |
| `vision.document` | Scanned/diagram pages OCR escalation | Page-image understanding, structured output | Default | page marked unreadable; document still processes (per-page flag) |

Roles map to providers via config like `LLM_PRIMARY_PROVIDER`, `LLM_PRIMARY_REASONING_MODEL`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `RERANK_PROVIDER`, `VISION_MODEL` (full catalogue in security-baseline §2). The PRD deliberately leaves vendors open (A-07); selection among them is made at build start against measured cost/latency budgets (A-17 price table), not popularity.

## Provider abstraction — provider-neutral interface contracts

The Gateway exposes five operations (streaming is a mode of `generate`; `understand_document` is the vision specialization of `structured`). Every operation shares a **common envelope** so callers and telemetry are provider-independent:

**Common envelope (all operations):**
- **Correlation:** `correlation_id` (request/trace chain) + `ai_request_id` (gateway-assigned, returned in every result and event).
- **Version metadata:** `prompt_id` + `prompt_version` (resolved from the prompt registry), `model_role`, resolved `provider` + `model` (recorded, never asserted by callers), `fallback_from` when a fallback engaged.
- **Usage metadata:** `input_tokens`, `output_tokens` (or item counts for embed/rerank), `time_to_first_token_ms` for streaming, `latency_ms`.
- **Cost metadata:** `estimated_cost_usd` from the configured price table (estimate, labelled — A-17).
- **Error classification:** every failure normalized to the typed taxonomy — `AITimeout` · `AIRateLimited` · `AIProviderDown` · `AIInvalidOutput` · `AIBudgetExhausted` — with `retryable` flag; raw provider errors never escape the Gateway.

### `generate`
- **Input:** `prompt_ref{id, version}`, `variables` (strict renderer; untrusted content escaped/delimited), `model_role`, `max_tokens?`, `temperature?`, `stream: bool`.
- **Output:** non-streaming → `GenerationResult{text, usage, finish_reason, ai_request_id}`; streaming → typed chunk sequence (`token` deltas) + a finalizer delivering the same result metadata even on client disconnect.
- **Timeout:** per role (30 s generation / streaming within the turn budget; deadline propagation — inner retries only if the remaining budget allows a full attempt).
- **Retry:** none after first token; pre-first-token transient errors may retry once if budget allows.

### `generate_structured`
- **Input:** `prompt_ref`, `variables`, `output_schema` (schema object — the caller's Pydantic model, never a string), `model_role` (typically `generation.grading`/`generation.mid`), `max_repair_attempts` (default 1).
- **Output:** `StructuredResult{data (validated) | ValidationErrorSet, usage, attempt_count, ai_request_id}` — validation is always re-checked locally; provider schema modes are an optimization, not a guarantee.
- **Timeout:** 60 s class; **retry:** no blind re-ask — one repair attempt with validation errors appended, then typed `AIInvalidOutput` to the caller's documented fallback.

### `embed`
- **Input:** `texts[]` (batched 64–128 by the Gateway), `model_role` (fixed dimension pinned per schema).
- **Output:** `EmbeddingResult{vectors, model, dimensions, usage, ai_request_id}`; cache layer `(text-hash, model)` inside the Gateway.
- **Timeout:** 15 s; **retry:** yes (idempotent, max 2, backoff+jitter); degraded mode: provider down → typed error → Knowledge degrades to lexical-only.

### `rerank`
- **Input:** `query`, `candidates[]` (passage refs + excerpts), `model_role`, `top_n`.
- **Output:** `RerankResult{ranked: [{index, score}], usage, ai_request_id}`.
- **Timeout:** 5 s; **retry:** yes (max 2); degraded mode: skip → fused order + raised sufficiency threshold, flagged.

### `evaluate`
- **Input:** `eval_request{rubric_ref, subject (answer/question/recommendation + evidence refs), output_schema}` — judge runs at temperature 0.
- **Output:** `EvaluationResult{scores (validated against schema), rationale? (truncated), usage, ai_request_id}`.
- **Timeout:** 60 s; **retry:** one; the judge's own agreement with human labels must be demonstrated before its scores gate anything (evaluation-strategy §1).

Adapters implement exactly these envelopes; a provider capability that does not map to an envelope field is out of scope until the interface is deliberately extended (module-contracts §M.11 rule).

- Adapters are thin: auth, request/response mapping, error normalization to the typed `AIError` taxonomy (`AITimeout`, `AIRateLimited`, `AIProviderDown`, `AIInvalidOutput`, `AIBudgetExhausted`).
- Structured generation uses each provider's native schema/JSON mode where available; validation is **always** re-checked locally against the Pydantic schema (provider "guarantees" are not trusted — principle §4).
- No provider-unique feature enters domain code; adopting one is a deliberate Gateway interface extension (module-contracts §M.11 rule).

## Fallback strategy (per role, in order)

1. Same role on the fallback provider (uncorrelated vendor where possible) — `fallback_from` recorded on the AI request.
2. Role-specific degraded mode: embedding → lexical-only retrieval + raised sufficiency threshold + reduced-confidence flag; rerank → fused order + raised τ; grading → `pending_review`; recommendation phrasing → deterministic template; question generation → skip/replace question; tutor generation → evidence-list response (clearly labelled).
3. All-provider failure → typed `AIProviderDown` to the caller, which applies its documented degraded path (module-contracts failure rows).

## Timeout strategy (budgets composed; deadline propagation per ADR-0001 principles)

| Operation | Timeout | Notes |
|---|---|---|
| Tutor generation (stream) | 30 s within the turn budget; TTFT tracked separately | Inner retries only if remaining budget allows a full attempt |
| Grading / structured | 60 s | One repair attempt inside the budget |
| Embeddings | 15 s | Batched (64–128); cache-hit path bypasses |
| Rerank | 5 s | Fast-fail to fused order |
| Vision page | ~120 s/page cap | Bounded by worker task limits |

## Retry strategy

- **Retryable:** embed, rerank, idempotent structured calls on transient errors (`AIRateLimited`, 5xx-class `AIProviderDown`) — max 2 in-request, exponential backoff + jitter.
- **Non-retried:** streaming generation after first token (client-visible stream); anything after budget exhaustion; invalid-structured-output (one local repair attempt, then typed failure — never a silent re-ask loop).
- Async work (worker-plane calls) may retry more per event policy; all retries flow through the same typed taxonomy and metering.

## Token / cost tracking

Every call writes an `ai_requests`-class record + `AIRequestCompleted` event (§E): provider role, model, prompt id+version, latency, TTFT, tokens in/out, `estimated_cost_usd` computed from a **configured price table** (labelled estimate in UI; reconciled against billing later — A-17). Budgets: per-user daily token/cost budget (config) enforced in the Gateway before the call; exceeding → graceful degrade (smaller model/shorter context) or typed `AIBudgetExhausted` for hard caps.

## Model / version tracking

- Every record carries `provider`, `model`, `prompt_id`, `prompt_version`, `fallback_from`, and retrieval meta — a regression is attributable to the exact change (FR-84; evaluation-strategy baseline discipline).
- Embedding rows store the model name; dimension changes are a reprocessing job (pipeline-versioned), never in-place mutation.

## Prompt version tracking

- Prompts are versioned files in the repo (`id + version + model_role + variables + output_schema` front-matter), resolved by the Gateway at call time; the version used is recorded on every AI request.
- Changing a prompt = a reviewed change that must pass the eval gate (evaluation-strategy L1) before merge; feature-flagged rollback without deploy where risky.

## Options considered (abstraction level)

1. **Direct SDK calls per module** — rejected: unmeterable, unbounded fallback story, vendor lock-in in domain code (violates FR-80).
2. **Orchestration framework (LangChain-class)** — rejected (ADR-0007): hides exactly what must be observable; version churn.
3. **Thin in-house Gateway over adapter interfaces + role config** ✅ — a few hundred fully-instrumented lines; vendor swap = config + one adapter.
4. **Self-hosted model serving** — rejected for Phase 0 (no requirement; cost/ops); FUTURE TRIGGER when provider cost/latency becomes the binding constraint; the adapter seam is where a self-hosted endpoint plugs in.

## Consequences

- (+) Domain code is vendor-agnostic by construction; metering/fallback/budget enforcement live in exactly one place; per-role degradation preserves partial functionality under any single-provider outage.
- (−) Team writes/maintains adapters (accepted: small, understood); thin abstraction may lag vendor-unique capabilities (deliberate); provider choice at build start still required (DEFERRED decision with a named owner: build kickoff, driven by budget + eval-set quality trial).

## Open questions

1. Final vendor/model per role at build start (recorded as an addendum here; selection input = golden-set trial + price table, not popularity).
2. Whether the `evaluate` (judge) role shares `generation.reasoning`'s vendor or uses a distinct one (agreement-validation decides).
