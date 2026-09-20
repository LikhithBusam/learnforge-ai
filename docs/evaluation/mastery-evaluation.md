# Phase 6 — Mastery Engine Evaluation Strategy

## 1. Overview

The evaluation suite for the Concept Mastery Engine ensures that:
1. The mathematical BKT model behaves deterministically and obeys strict probability and confidence bounds.
2. The partial-credit interpolation and symmetric difficulty weighting behave according to specification.
3. The database layer guarantees multi-tenant isolation, immutable audit trails, and atomic idempotency.

---

## 2. Mandatory Evaluation Scenarios

| Scenario | Objective | Expected Outcome |
|---|---|---|
| **Scenario 1** | Repeated Correct | Monotonic mastery increase from $P_{init} = 0.20$ to $> 0.85$ |
| **Scenario 2** | Repeated Incorrect | Monotonic mastery decrease from $0.80$ to $< 0.15$ |
| **Scenario 3** | Mixed Evidence | Deterministic final state for fixed mixed sequence |
| **Scenario 4** | Partial Credit | Strict inequality: $p(\text{incorrect}) < p(0.25) < p(0.50) < p(0.75) < p(\text{correct})$ |
| **Scenario 5** | Difficulty Sensitivity | Hard correct $>$ Easy correct; Easy incorrect drop $>$ Hard incorrect drop |
| **Scenario 6** | Confidence Saturation | Monotonic saturation: $N=0 \implies 0.0$, $N=5 \implies \approx 0.63$, $N=20 \implies \approx 0.98$ |
| **Scenario 7** | Duplicate Suppression | Duplicate evidence submission yields identical state and 0 extra events |
| **Scenario 8** | Cross-Project Rejection | Attempting to process cross-project evidence raises `NotFound` |
| **Scenario 9** | Pending Review Exclusion | Evidence in `pending_review` state is not applied to mastery |
| **Scenario 10** | Determinism | Repeated simulation of any arbitrary evidence sequence yields exact floating-point equality |

---

## 3. Calibration & Empirical Limitations

- **Parameter Calibration**: Baseline parameters ($P_{init}=0.20, P_{learn}=0.10, P_{guess}=0.20, P_{slip}=0.10$) are initial defaults designed for stable progression. Future phases should incorporate calibration against empirical student interaction data using Expectation-Maximization or Markov Chain Monte Carlo methods.
- **Concept Independence**: Current Phase 6 models concepts as independent knowledge components. Prerequisite dependency graphs and slip decay over long idle times are reserved for Phase 7+.
