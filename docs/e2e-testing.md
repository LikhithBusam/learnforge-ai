# End-to-End Testing Guide (Phase 11)

## Overview
The end-to-end integration test suite (`tests/integration/test_phase11_e2e.py`) exercises the complete cross-module lifecycle of a learner from registration to administrative oversight.

---

## E2E Lifecycle Stages

```text
1. User Registration & Token Auth (Phase 1 & 2)
   ↓
2. Space & Project Creation (Phase 1)
   ↓
3. PDF Upload Intent & Storage Ingestion (Phase 3)
   ↓
4. Document Chunking, Embedding & Knowledge Graph (Phase 3)
   ↓
5. Socratic Tutor Conversation & Grounded Citations (Phase 4)
   ↓
6. Safety Check: Unsupported Question Refusal (Phase 4)
   ↓
7. Quiz Generation & Question Submission (Phase 5)
   ↓
8. Bayesian Knowledge Tracing (BKT) Mastery Update (Phase 6)
   ↓
9. Growth Trajectory & Skill Velocity Snapshot (Phase 7)
   ↓
10. Adaptive Next-Best-Action Recommendation (Phase 8)
   ↓
11. Analytics Event Ingestion & Daily Rollup (Phase 9)
   ↓
12. Admin Observability, Health Check & Audit Logging (Phase 10)
```

---

## Running the E2E Suite
```bash
python -m pytest tests/integration/test_phase11_e2e.py
```
