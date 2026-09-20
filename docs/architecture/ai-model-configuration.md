# AI Model Configuration — Role-Based, Provider-Neutral

**Status:** Configuration concept (ADR-0015/0017 companion). Domain modules reference **roles**, never providers; swapping a provider or model is a **config change**, never a code change. **No real API keys ever enter the repository** — placeholders only (security-baseline §3).

---

## 1. Conceptual configuration keys

Domain code and prompts address capabilities by these role keys:

| Conceptual key | Role (ADR-0015) | Used by | Notes |
|---|---|---|---|
| `generation_model` | `generation.reasoning` | Tutor grounded answers (streaming) | Strong reasoning + streaming required |
| `structured_generation_model` | `generation.grading` / `generation.mid` | Open-ended grading, question generation, concept extraction, recommendation phrasing | Temperature 0 for grading; may resolve to two separate configured models per sub-role |
| `embedding_model` | `embedding` | Chunk + query embeddings | Dimension pinned per schema; model stamped per row |
| `reranker_model` | `rerank` | Evidence rerank top-k → top-6 | Score-only API |
| `evaluation_model` | `evaluate` (judge) | Model-judged eval metrics | Temperature 0; agreement-validated before gating |
| `vision_model` | `vision.document` | OCR-escalation pages (scans, diagrams) | Optional — only if the corpus demands it |

Resolution: role key → (provider, model, api-key-ref, params) via environment config. A role maps to **one primary and one fallback** entry; domain code is unaware of both.

## 2. Environment configuration shape (conceptual)

```text
AI_GENERATION_PROVIDER=<provider-id>            # opaque id, resolved by the adapter registry
AI_GENERATION_MODEL=<model-id>
AI_GENERATION_API_KEY_REF=<secret-ref>          # reference into the secrets facility — never the key itself
AI_GENERATION_TIMEOUT_SECONDS=30
AI_GENERATION_MAX_TOKENS=<per-feature caps>

AI_STRUCTURED_PROVIDER=<provider-id>
AI_STRUCTURED_MODEL=<model-id>
AI_STRUCTURED_API_KEY_REF=<secret-ref>
AI_STRUCTURED_TIMEOUT_SECONDS=60
AI_STRUCTURED_TEMPERATURE=0

AI_GENERATION_FALLBACK_PROVIDER=<provider-id>
AI_GENERATION_FALLBACK_MODEL=<model-id>
AI_GENERATION_FALLBACK_API_KEY_REF=<secret-ref>

AI_EMBEDDING_PROVIDER=<provider-id>
AI_EMBEDDING_MODEL=<model-id>
AI_EMBEDDING_DIMENSIONS=1536
AI_EMBEDDING_BATCH_SIZE=128

AI_RERANKER_PROVIDER=<provider-id>
AI_RERANKER_MODEL=<model-id>

AI_EVALUATION_PROVIDER=<provider-id>
AI_EVALUATION_MODEL=<model-id>

AI_VISION_PROVIDER=<provider-id>            # optional role
AI_VISION_MODEL=<model-id>

AI_PRICE_TABLE_REF=<config-ref>              # per-model price bands; snapshot-dated
AI_USER_DAILY_TOKEN_BUDGET=<tokens>
```

**Rules:** every model entry is (provider, model, key-ref, params); the app **refuses to boot** if a role's primary entry is missing/malformed (ADR-0012 startup validation); the price table carries its snapshot date so cost estimates are auditable; API keys are referenced, fetched from the secrets facility at startup, held in memory only.

## 3. Per-environment posture

| Environment | Configuration posture |
|---|---|
| **Development** | Real roles with throwaway keys and hard-capped budgets; or local stub adapters (scripted responses) when offline; feature parity with prod config shape so nothing is env-conditional in code |
| **Test / CI** | **Stub adapters always** — deterministic fixture responses per the test strategy (no live provider calls in gates); config asserts the stub registry; malformed-config boot-failure has its own test |
| **Staging** | Real providers, **low budgets**, same role mapping as production; trial candidates (ADR-0015 addendum / provider-trial protocol) run here |
| **Production** | Trial-selected primaries + fallbacks; budget enforcement on; prompt logging `redacted` (never `full`); price-table snapshot dated |

Changing providers in any environment = edit env/secret values + restart. No module, prompt, or test changes.

## 4. Fallback configuration

- Each role declares optional `*_FALLBACK_*` entries; the Gateway's fallback chain (ADR-0015) uses them before role-specific degraded modes.
- Fallbacks may cross vendors (preferred: uncorrelated outages); `fallback_from` is recorded on every AI request + `AIRequestCompleted` event.
- Degraded modes per role are fixed by the Gateway contract (lexical-only retrieval, fused-order rerank skip, `pending_review` grading, template recommendations, evidence-list tutor response) — they are behaviour, not config.
- Budget exhaustion: graceful degrade first (smaller configured model for the role where a `*_SMALL_*` entry exists, shorter context budget), typed `AIBudgetExhausted` for hard caps.

## 5. Verification hooks

- Startup: config validation logs each role's resolved (provider, model, dimension) **without** secrets.
- Health: `/readyz` does not depend on providers (AI is a degraded-mode dependency); the Gateway exposes circuit/fallback state as metrics (ADR-0020).
- Drift: scheduled live contract checks verify the configured models still satisfy the interface envelopes (schema mode, streaming, batch) — catches silent provider-side changes.
