# Phase 4 Test Matrix

| Test Suite | Test Function | Purpose | Result |
|---|---|---|---|
| `unit/test_phase4_query.py` | `test_preprocess_query_normalizes_whitespace` | Whitespace normalization | **PASS** |
| `unit/test_phase4_query.py` | `test_preprocess_query_preserves_arabic_multilingual` | Unicode / Arabic preservation | **PASS** |
| `unit/test_phase4_query.py` | `test_preprocess_query_truncates_at_max_chars` | Length capping | **PASS** |
| `unit/test_phase4_query.py` | `test_preprocess_query_empty_raises_validation_error` | Empty query rejection | **PASS** |
| `unit/test_phase4_fusion.py` | `test_rrf_combines_and_ranks_candidates` | RRF formula correctness | **PASS** |
| `unit/test_phase4_fusion.py` | `test_rrf_truncates_to_top_n` | Top-N candidate cap | **PASS** |
| `unit/test_phase4_sufficiency.py` | `test_sufficiency_empty_candidates` | Zero-candidate refusal | **PASS** |
| `unit/test_phase4_sufficiency.py` | `test_sufficiency_below_threshold` | Low-score refusal | **PASS** |
| `unit/test_phase4_sufficiency.py` | `test_sufficiency_above_threshold_supported` | High-score supported | **PASS** |
| `unit/test_phase4_sufficiency.py` | `test_sufficiency_requires_min_supporting_chunks` | Min chunk threshold | **PASS** |
| `unit/test_phase4_citations.py` | `test_validate_citations_accepts_valid` | Valid citation acceptance | **PASS** |
| `unit/test_phase4_citations.py` | `test_validate_citations_strips_hallucinated_chunk` | Hallucinated citation rejection | **PASS** |
| `unit/test_phase4_citations.py` | `test_validate_citations_repairs_out_of_bounds_page` | Page boundary clamping | **PASS** |
| `unit/test_phase4_citations.py` | `test_context_composer_encapsulates_untrusted_evidence` | Prompt injection isolation | **PASS** |
| `integration/test_phase4_retrieval.py` | `test_hybrid_retrieval_and_reranking` | Independent hybrid retrieval | **PASS** |
| `integration/test_phase4_isolation.py` | `test_cross_project_retrieval_blocked` | Cross-project isolation | **PASS** |
| `integration/test_phase4_isolation.py` | `test_rls_isolation_on_conversations_and_messages` | PostgreSQL RLS on conversations | **PASS** |
| `integration/test_phase4_tutor.py` | `test_tutor_grounded_answer_and_refusal` | Grounded answer, refusal, SSE | **PASS** |
| `integration/test_phase4_prompt_injection.py` | `test_prompt_injection_treated_as_inert_data` | Prompt injection defense | **PASS** |
| `evaluation/test_phase4_rag_eval.py` | `test_rag_evaluation_harness` | Golden dataset Recall@K & MRR | **PASS** |
