# Google Gemini Integration Architecture

This document describes how Google Gemini is integrated into the AI Study Companion platform via the unified **AI Gateway**.

---

## 1. Architectural Principles

1. **Server-Side Exclusivity**: The Gemini API key (`GEMINI_API_KEY`) resides exclusively in the FastAPI backend environment. React frontend code has zero references to the Gemini SDK or API key.
2. **Provider Adapter Abstraction**: All application capabilities (Tutor, Assessment, Evaluation) interact solely with `AIGateway`. The Gateway delegates to `GeminiProvider`, which implements `ProviderAdapter`.
3. **Structured Schema Enforcement**: All structured generation calls pass a target Pydantic schema model. Gemini outputs are parsed, sanitized, and validated against Pydantic models before being accepted by downstream domains.
4. **Vector Dimension Compatibility**: The database uses native PostgreSQL `VECTOR(1536)` columns with HNSW indices. Embedding representations conform to this 1536-dimensional space to guarantee zero breaking changes to existing migrations and database indices.

---

## 2. Configuration Parameters

Backend `.env.development`:
```env
AI_PROVIDER=gemini
AI_GENERATION_PROVIDER=gemini
AI_STRUCTURED_PROVIDER=gemini
GEMINI_API_KEY=<your-server-side-gemini-api-key>
GEMINI_MODEL=gemini-2.5-flash
AI_EMBEDDING_DIMENSIONS=1536
AI_GATEWAY_TIMEOUT_SECONDS=60
```

---

## 3. Supported Capabilities

* **Unstructured Text Generation**: Generates conversational tutor responses and explanations.
* **Structured Output Generation**: Generates MCQ quiz questions (`MCQGenerationPayload`) and evaluates open-ended learner responses (`OpenEndedGradingPayload`).
* **Error Handling & Rate Limiting**: Translates Gemini transient rate-limits (HTTP 429) and quota exhaustion into internal domain exceptions (`AIRateLimited`, `AIProviderDown`) with exponential backoff and jitter.
* **Telemetry & Cost Tracking**: Records input tokens, output tokens, latency (ms), and feature tag into the `telemetry_spine` on every request.
