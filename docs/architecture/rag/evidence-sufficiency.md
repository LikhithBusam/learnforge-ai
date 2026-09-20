# Evidence Sufficiency & Honest Refusal (Phase 4)

## 1. Sufficiency Decision States

Rather than blindly sending whatever candidates are retrieved to the LLM, the system explicitly evaluates evidence sufficiency:

1. **`SUPPORTED`:** Top reranker/fusion score $\ge \tau$ (default $\tau = 0.50$) and supporting chunk count $\ge \text{min\_chunks}$ (default 1).
2. **`INSUFFICIENT` (`no_candidates`):** Zero chunks retrieved matching the project.
3. **`INSUFFICIENT` (`score_below_threshold`):** Retrieved candidates exist but their relevance score is below $\tau$.
4. **`INSUFFICIENT` (`insufficient_supporting_chunks`):** Candidate count below minimum required supporting evidence.

---

## 2. Honest Refusal Mandate

When evidence sufficiency is `INSUFFICIENT`:
- The AI Tutor does NOT attempt to answer from general knowledge.
- The AI Tutor emits an honest, explicit refusal:
  > *"I could not find enough supporting information in the project materials to answer that reliably."*
- `answer_status` is set to `"insufficient_evidence"`.
- Zero citations are generated (`citations: []`).
