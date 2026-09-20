"""Phase 4 Unit Tests — Evidence Sufficiency Decision (Prompt §17).

Verifies:
1. Empty candidate list produces honest refusal with reason_code="no_candidates".
2. Score below threshold tau produces sufficient=False with reason_code="score_below_threshold".
3. High score above threshold produces sufficient=True with reason_code="supported".
"""

from __future__ import annotations

import uuid

from app.knowledge.retrieval import RetrievedCandidate, evaluate_evidence_sufficiency


def _make_candidate(score: float, is_rerank: bool = True) -> RetrievedCandidate:
    return RetrievedCandidate(
        chunk_id=uuid.uuid4(),
        material_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        page_start=1,
        page_end=1,
        text="Sample candidate content",
        rerank_score=score if is_rerank else None,
        fusion_score=score if not is_rerank else None,
    )


def test_sufficiency_empty_candidates():
    decision = evaluate_evidence_sufficiency([], tau=0.50)
    assert not decision.sufficient
    assert decision.top_score == 0.0
    assert decision.supporting_chunk_count == 0
    assert decision.reason_code == "no_candidates"


def test_sufficiency_below_threshold():
    cands = [_make_candidate(0.35), _make_candidate(0.20)]
    decision = evaluate_evidence_sufficiency(cands, tau=0.50)
    assert not decision.sufficient
    assert decision.top_score == 0.35
    assert decision.supporting_chunk_count == 0
    assert decision.reason_code == "score_below_threshold"


def test_sufficiency_above_threshold_supported():
    cands = [_make_candidate(0.85), _make_candidate(0.65)]
    decision = evaluate_evidence_sufficiency(cands, tau=0.50, min_supporting_chunks=1)
    assert decision.sufficient
    assert decision.top_score == 0.85
    assert decision.supporting_chunk_count == 2
    assert decision.reason_code == "supported"


def test_sufficiency_requires_min_supporting_chunks():
    cands = [_make_candidate(0.75), _make_candidate(0.30)]
    # Requires 2 supporting chunks above 0.50, but only 1 candidate exceeds it
    decision = evaluate_evidence_sufficiency(cands, tau=0.50, min_supporting_chunks=2)
    assert not decision.sufficient
    assert decision.reason_code == "insufficient_supporting_chunks"
