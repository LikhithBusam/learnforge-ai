# Recommendation Engine Evaluation Suite (Phase 8)

## 1. Overview
The Recommendation Evaluation Suite benchmarks the deterministic scoring, eligibility, deduplication, cooldown, and ranking logic across 12 canonical pedagogical scenarios.

---

## 2. Canonical Test Scenarios

| Scenario | Conditions | Expected Candidate / Outcome |
| :--- | :--- | :--- |
| **1. Weak + Declining** | Mastery: 0.35, Trend: Declining ($\Delta = -0.20$), Failures: 80%, Material: Available | `REVISIT_MATERIAL` or `REVIEW_MISTAKES` with `HIGH` priority ($\ge 0.70$). |
| **2. Weak but Improving** | Mastery: 0.40, Trend: Improving ($\Delta = +0.20$), Failures: 0%, Material: Available | `PRACTICE_CONCEPT` / `REVISIT_MATERIAL` with `MEDIUM` priority (not inflated like declining). |
| **3. Strong but Declining** | Mastery: 0.82, Trend: Declining ($\Delta = -0.15$), Failures: 40% | Decline signal triggers remediation despite high base mastery. |
| **4. Strong and Stable** | Mastery: 0.90, Trend: Stable ($\Delta = 0.0$), Failures: 0%, Attention: False | 0 remediation candidates generated (no artificial study tasks). |
| **5. Low Confidence** | Mastery: 0.40, Confidence: 0.10 | Low confidence dampens weakness panic; triggers `PRACTICE_CONCEPT` with `LOW_CONFIDENCE` reason. |
| **6. Material Available** | Relevant material exists for concept | `REVISIT_MATERIAL` generated referencing concrete `material_id`. |
| **7. Material Missing** | No material exists for concept | `REVIEW_CONCEPT` / `PRACTICE_CONCEPT` generated; never hallucinating material IDs. |
| **8. Recent Duplicate** | Concept recommended within last 24h | Cooldown penalty (-0.40) applied; rank drops. |
| **9. Completed State** | Recommendation marked completed | Excluded from active recommendations unless regenerated with new evidence. |
| **10. Multiple Weak Concepts** | 10 weak concepts competing | Top-K constraint enforces maximum 5, stably sorted by priority score. |
| **11. Cold Start** | 0 prior mastery/growth evidence | Initial onboarding recommendation generated if materials exist, else empty. |
| **12. Determinism** | 10 identical runs | Bitwise identical scores, reason codes, evidence references, and ordering. |
