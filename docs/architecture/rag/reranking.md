# Reranking Engine (Phase 4)

## 1. Reranker Role in AI Gateway

Reranking sharpens precision after candidate fusion:

```text
50 candidates (vector + lexical)
      ↓
Reciprocal Rank Fusion
      ↓
Top 20 candidates
      ↓
AI Gateway Reranker (role: "rerank")
      ↓
Top 5 final evidence chunks
```

---

## 2. Safety & Fallback Behavior

1. **Safety:** Reranking receives ONLY candidates that have already been authorized by project scope and filtered by PostgreSQL RLS. It never evaluates or scans the broader database.
2. **Degraded Mode:** If the reranker provider experiences a network timeout or outage:
   - System logs a warning with `rerank_degraded=True`.
   - Pipeline gracefully falls back to the fused RRF ordering.
   - Grounded generation continues without failing the user turn.
