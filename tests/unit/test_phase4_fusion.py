"""Phase 4 Unit Tests — Reciprocal Rank Fusion (RRF).

Verifies:
1. Standard RRF score calculation: sum(1 / (k + rank)).
2. Candidates appearing in both vector and lexical sets rise above single-list candidates.
3. Top-N truncation and deterministic sorting.
"""

from __future__ import annotations

import uuid

from app.knowledge.retrieval import RetrievedCandidate, reciprocal_rank_fusion


def _make_candidate(
    cid: uuid.UUID, text: str, v_score: float | None = None, l_score: float | None = None
) -> RetrievedCandidate:
    return RetrievedCandidate(
        chunk_id=cid,
        material_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        page_start=1,
        page_end=1,
        text=text,
        vector_score=v_score,
        lexical_score=l_score,
    )


def test_rrf_combines_and_ranks_candidates():
    cid_both = uuid.uuid4()
    cid_vec_only = uuid.uuid4()
    cid_lex_only = uuid.uuid4()

    # Vector list: cid_both (rank 1), cid_vec_only (rank 2)
    vec_cands = [
        _make_candidate(cid_both, "Networking TCP", v_score=0.92),
        _make_candidate(cid_vec_only, "UDP Transport", v_score=0.88),
    ]

    # Lexical list: cid_lex_only (rank 1), cid_both (rank 2)
    lex_cands = [
        _make_candidate(cid_lex_only, "HTTP Protocol", l_score=0.85),
        _make_candidate(cid_both, "Networking TCP", l_score=0.80),
    ]

    # k=60
    # cid_both score: 1/(60+1) + 1/(60+2) = 1/61 + 1/62 = 0.016393 + 0.016129 = 0.032522
    # cid_lex_only: 1/(60+1) = 0.016393
    # cid_vec_only: 1/(60+2) = 0.016129

    fused = reciprocal_rank_fusion(vec_cands, lex_cands, k=60, top_n=10)

    assert len(fused) == 3
    # cid_both must rank first
    assert fused[0].chunk_id == cid_both
    assert fused[0].fusion_score is not None
    assert round(fused[0].fusion_score, 4) == 0.0325
    assert fused[0].vector_score == 0.92
    assert fused[0].lexical_score == 0.80

    # cid_lex_only must rank second
    assert fused[1].chunk_id == cid_lex_only
    assert fused[1].fusion_score is not None
    assert round(fused[1].fusion_score, 4) == 0.0164

    # cid_vec_only must rank third
    assert fused[2].chunk_id == cid_vec_only
    assert fused[2].fusion_score is not None
    assert round(fused[2].fusion_score, 4) == 0.0161


def test_rrf_truncates_to_top_n():
    cands = [_make_candidate(uuid.uuid4(), f"Chunk {i}", v_score=1.0 - 0.05 * i) for i in range(10)]
    fused = reciprocal_rank_fusion(cands, [], k=60, top_n=5)
    assert len(fused) == 5
