# PHASE 12.2 — GEMINI INTEGRATION & PRODUCTION AI GATEWAY REPORT

## Final Status
```text
GEMINI INTEGRATION VERIFIED
```

```text
GEMINI_API_KEY configured: YES
Gemini authentication: PASS
Model: gemini-2.5-flash
```

---

## 1. Gemini Provider Architecture

The Google Gemini API integration follows the strict modular monolith AI Gateway specification (ADR-0007 / ADR-0015):

```text
React Frontend (packages/web)
       ↓  HTTP / REST + SSE
FastAPI Application Services (apps/api)
       ↓  domain facade (never imports Gemini)
AI Gateway (app.ai.gateway)
       ↓  role routing & policy enforcement
Provider Registry (_Registry)
       ↓  resolves "gemini"
GeminiProvider (app.ai.gemini)
       ↓  official google-genai SDK
Google Gemini API (gemini-2.5-flash)
```

Domain modules (`tutor`, `assessment`, `knowledge`, `mastery`, `growth`) depend strictly on `AIGateway`, never on provider SDKs. This is enforced mechanically in CI via AST boundary checks (`scripts/check_boundaries.py`, 126 files checked, 0 violations).

---

## 2. Configuration & Environment Variables

The backend configuration supports generic AI provider switching and model specification:

```env
# AI Provider Selection (development/test defaults to stub; production/integration uses gemini)
AI_PROVIDER=gemini
GEMINI_API_KEY=<server-side-only>
GEMINI_MODEL=gemini-2.5-flash
```

In `apps/api/src/app/platform/config.py`:
- `AI_PROVIDER`: Selects the active provider (e.g. `stub` or `gemini`).
- `GEMINI_API_KEY`: Server-side API key, never serialized into logs, `/readyz`, or `safe_summary()`.
- `GEMINI_MODEL`: Model identifier (defaults to `gemini-2.5-flash`).
- Post-validation hooks automatically route `AI_GENERATION_PROVIDER` and `AI_STRUCTURED_PROVIDER` to `gemini` with the configured model when `AI_PROVIDER=gemini`.
- In test and CI environments, `AI_PROVIDER=stub` preserves complete deterministic execution without network egress or API keys.

---

## 3. Model Selected & Verified

- **Model**: `gemini-2.5-flash`
- **Supported Capabilities**: `generateContent` with free-form unstructured text and native structured JSON schema enforcement (`response_mime_type="application/json"` and `response_schema`).
- **Official SDK**: Google's official `google-genai` SDK (`google.genai`, version `2.24.0`).
- **Async Client**: Utilizes `client.aio.models.generate_content` for non-blocking asynchronous concurrency.

---

## 4. AI Gateway Integration

`GeminiProvider` implements `ProviderAdapter` (from `app.ai.adapter`), providing:
1. `generate(req, settings)`: Generates unstructured responses, maps finish reasons, latency, and token metrics.
2. `generate_structured(req, settings)`: Employs schema-constrained generation via Pydantic schemas, cleans optional markdown wrappers, performs local authoritative Pydantic validation, and returns structured dictionaries.
3. `embed(req, settings)`: Preserves existing 1536-dimensional pgvector / HNSW embeddings (Requirement §13).
4. `rerank(req, settings)`: Reranking adapter delegate.
5. `evaluate(req, settings)`: Structured evaluation delegate.

All calls pass through gateway lifecycle telemetry, budget enforcement, and typed exception normalization (`app.platform.errors`).

---

## 5. Tutor Integration & Groundedness

- **Feature**: `tutor_answer`
- **Grounded Pipeline**:
  ```text
  User Question
        ↓
  Hybrid Retrieval (Dense + BM25)
        ↓
  Reciprocal Rank Fusion (RRF) & Reranking
        ↓
  Sufficiency Check (τ = 0.5, min 1 chunk)
        ↓
  Context Composer (<retrieved_evidence> isolation)
        ↓
  GeminiProvider (Structured schema: TutorGenerationPayload)
        ↓
  Local Authoritative Citation Validation
        ↓
  Stream / Response to Learner
  ```
- **Injection Defense**: Document chunks are isolated in `<retrieved_evidence>` blocks with explicit XML boundary tags. Untrusted text cannot override system directives.
- **Honest Refusal**: If evidence is insufficient, retrieval refuses early without contacting the model. When passed insufficient evidence, Gemini adheres to the prompt contract: `refusal=true`, `grounded=false`.

---

## 6. Assessment Integration

- **Question Generation (`assessment_question_generation`)**:
  - `MCQGenerationPayload`: Generates 4 distinct options (A, B, C, D), a valid `correct_option`, explanation, and traceable `source_chunk_ids`.
  - `OpenEndedGenerationPayload`: Generates question, reference answer, rubric with criterion weights summing to 1.0, and traceable chunk IDs.
  - Full local Pydantic validation before database persistence. Malformed outputs are rejected with `AIInvalidOutput` and never persisted.
- **Open-Ended Grading (`assessment_open_ended_grading`)**:
  - `OpenEndedGradingPayload`: Grades learner responses against reference answers and rubric criteria.
  - Deterministic fallback to `pending_review` if model output fails validation or times out.

---

## 7. Error Handling & Normalization

The provider normalizes Google SDK errors into typed application exceptions:
- **Authentication Failure (401, 403, API_KEY_INVALID)**: Normalized to `AIProviderDown`. Fails immediately without retry.
- **Rate Limit (429, RESOURCE_EXHAUSTED)**: Normalized to `AIRateLimited`.
- **Transient Service Unavailability (500, 502, 503, 504)**: Normalized to `AIProviderDown`.
- **Invalid Request (400, INVALID_ARGUMENT)**: Normalized to `AIInvalidOutput`.
- **Timeouts**: Wrapped with `asyncio.wait_for(..., timeout=timeout)` and normalized to `AITimeout`.
- **Malformed JSON**: Parsed safely; returns `invalid_output` error category and triggers controlled fallback.

---

## 8. Retry & Backoff Policy

- **Bounded Retries**: Maximum of 3 attempts with exponential backoff (`backoff = 1.5s`, then `3.0s`).
- **Dynamic Quota Parsing**: Detects Google's `"Please retry in Xs"` response on 429 quota responses to adapt backoff timing.
- **Strict Non-Retry**: Authentication failures (401/403) and invalid request schemas (400) are never retried.

---

## 9. Token Telemetry & Cost Tracking

Telemetry records are emitted to `app.ai.telemetry` on every call:
- `provider`: `"gemini"`
- `model`: `"gemini-2.5-flash"`
- `feature`: `req.feature` (e.g., `tutor_answer`, `assessment_question_generation`)
- `latency_ms`: Total execution time in milliseconds
- `input_tokens`: Mapped from `response.usage_metadata.prompt_token_count`
- `output_tokens`: Mapped from `response.usage_metadata.candidates_token_count`
- `status`: `"success"` or error category (`"timeout"`, `"rate_limited"`, `"invalid_output"`, `"provider_error"`)
- `cost`: Price table reference remains unverified/null unless explicit pricing table is configured, avoiding fabricated costs (Requirement §15).

---

## 10. Security Compliance

1. **Server-Side Only**: `GEMINI_API_KEY` is loaded solely in the backend.
2. **Frontend Isolation**: Zero occurrences of `GEMINI`, `VITE_GEMINI_API_KEY`, or `google-genai` exist in `packages/web`.
3. **Redaction**:
   - `safe_summary()` in `apps/api/src/app/platform/config.py` omits `GEMINI_API_KEY`.
   - Result text and telemetry metadata do not leak the key.
   - `.env.development` is excluded in `.gitignore` (`.env*` with `!.env.example`).
   - `.env.example` contains only `GEMINI_API_KEY=` with no value.

---

## 11. Verification Results

### Real Gemini Provider Integration Tests (`tests/integration/test_gemini_provider.py`)
```text
======================= test session starts =======================
collected 7 items

tests/integration/test_gemini_provider.py::test_gemini_unstructured_generation PASSED
tests/integration/test_gemini_provider.py::test_gemini_structured_generation_with_schema PASSED
tests/integration/test_gemini_provider.py::test_gemini_grounded_tutor_schema PASSED
tests/integration/test_gemini_provider.py::test_gemini_honest_refusal_when_insufficient_evidence PASSED
tests/integration/test_gemini_provider.py::test_gemini_assessment_mcq_generation PASSED
tests/integration/test_gemini_provider.py::test_gemini_assessment_open_ended_grading PASSED
tests/integration/test_gemini_provider.py::test_gemini_auth_failure_handling PASSED

======================= 7 passed in 79.97s =======================
```

### Full Quality Gates
- **Deterministic Unit Tests**: 165 passed in 4.72s (`AI_PROVIDER=stub`).
- **AI Evaluation Suite**: 58 passed in 214.16s (`AI_PROVIDER=stub`).
- **Architecture Boundary Check**: 126 files scanned, 0 violations (`python scripts/check_boundaries.py`).
- **Linter (Ruff)**: Clean, 0 errors (`ruff check apps/api/src/app/ai/`).
- **Formatter (Black)**: Clean (`black --check apps/api/src/app/ai/`).
- **Type Checker (Mypy)**: `Success: no issues found in 7 source files` (`mypy -p app.ai`).
- **Frontend Production Build**: `tsc && vite build` passed cleanly in 6.87s (`packages/web/dist`).

---

## 12. Known Limitations & Operating Notes

1. **Free Tier Quotas**: Free-tier Gemini accounts enforce strict rate limits (RPM) and requests-per-day (RPD) ceilings. The provider implements exponential backoff and parses `retry in Xs`, but high-volume automated test runs should use `AI_PROVIDER=stub` to preserve quota.
2. **Embeddings**: Kept as 1536d / pgvector embeddings per Requirement §13. To migrate embeddings to Gemini (`text-embedding-004`), an explicit database migration and vector re-indexing phase would be required.
