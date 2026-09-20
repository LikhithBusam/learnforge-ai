"""RAG retrieval logic — query preprocessing, reciprocal rank fusion (RRF), and sufficiency evaluation.

Rules (Prompt §10, §11, §13, §17):
1. Preserve Unicode completely: Arabic, Latin, accents, scripts. Never strip non-ASCII or force English-only lowercase.
2. Lightweight preprocessing: whitespace normalization and length boundaries without aggressive LLM rewriting.
3. Deterministic Reciprocal Rank Fusion: RRF(d) = sum(1 / (k + rank_i(d))) with documented k=60.
4. Explicit sufficiency decision: SUPPORTED vs INSUFFICIENT with reason code and score.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from app.knowledge.schemas import SufficiencyDecisionDto
from app.platform.errors import ValidationError


def preprocess_query(raw_query: str, max_chars: int = 1000) -> str:
    """Preprocess query safely while strictly preserving Unicode scripts (e.g. Arabic)."""
    if not raw_query or not raw_query.strip():
        raise ValidationError("Query cannot be empty or whitespace only")

    # Safe normalization: collapse consecutive whitespace, strip outer
    # Preserves unicode characters intact (no lowercasing or ascii normalization)
    cleaned = re.sub(r"\s+", " ", raw_query.strip())

    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].strip()

    if not cleaned:
        raise ValidationError("Query cannot be empty after normalization")

    return cleaned


@dataclass
class RetrievedCandidate:
    chunk_id: uuid.UUID
    material_id: uuid.UUID
    document_id: uuid.UUID
    page_start: int
    page_end: int
    text: str
    section_path: str | None = None
    content_type: str = "text"
    vector_score: float | None = None
    lexical_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None


def reciprocal_rank_fusion(
    vector_candidates: list[RetrievedCandidate],
    lexical_candidates: list[RetrievedCandidate],
    k: int = 60,
    top_n: int = 20,
) -> list[RetrievedCandidate]:
    """Combine vector and lexical candidate lists using Reciprocal Rank Fusion (RRF).

    Formula: RRF(d) = sum(1 / (k + rank)) for each rank list where d appears.
    Rank is 1-indexed (1, 2, 3, ...).
    """
    scores: dict[uuid.UUID, float] = {}
    candidate_map: dict[uuid.UUID, RetrievedCandidate] = {}

    for rank, cand in enumerate(vector_candidates, start=1):
        cid = cand.chunk_id
        scores[cid] = scores.get(cid, 0.0) + (1.0 / (k + rank))
        if cid not in candidate_map:
            candidate_map[cid] = cand
        else:
            candidate_map[cid].vector_score = cand.vector_score

    for rank, cand in enumerate(lexical_candidates, start=1):
        cid = cand.chunk_id
        scores[cid] = scores.get(cid, 0.0) + (1.0 / (k + rank))
        if cid not in candidate_map:
            candidate_map[cid] = cand
        else:
            candidate_map[cid].lexical_score = cand.lexical_score

    # Assign fusion_score and sort descending
    fused: list[RetrievedCandidate] = []
    for cid, rrf_score in scores.items():
        cand = candidate_map[cid]
        cand.fusion_score = round(rrf_score, 6)
        fused.append(cand)

    fused.sort(key=lambda c: c.fusion_score or 0.0, reverse=True)
    return fused[:top_n]


def evaluate_evidence_sufficiency(
    candidates: list[RetrievedCandidate],
    tau: float = 0.50,
    min_supporting_chunks: int = 1,
) -> SufficiencyDecisionDto:
    """Explicitly decide if retrieved evidence is sufficient to ground an answer."""
    if not candidates:
        return SufficiencyDecisionDto(
            sufficient=False,
            top_score=0.0,
            supporting_chunk_count=0,
            reason_code="no_candidates",
            threshold_ref=f"tau={tau},min={min_supporting_chunks}",
        )

    # Score precedence: rerank_score -> fusion_score -> vector_score -> 0.0
    top = candidates[0]
    effective_score = (
        top.rerank_score
        if top.rerank_score is not None
        else (top.fusion_score if top.fusion_score is not None else (top.vector_score or 0.0))
    )

    # Count how many candidates meet supporting threshold
    supporting = [
        c
        for c in candidates
        if (
            c.rerank_score
            if c.rerank_score is not None
            else (c.fusion_score if c.fusion_score is not None else (c.vector_score or 0.0))
        )
        >= tau
    ]

    count = len(supporting)
    if effective_score < tau:
        return SufficiencyDecisionDto(
            sufficient=False,
            top_score=round(effective_score, 4),
            supporting_chunk_count=count,
            reason_code="score_below_threshold",
            threshold_ref=f"tau={tau},min={min_supporting_chunks}",
        )

    if count < min_supporting_chunks:
        return SufficiencyDecisionDto(
            sufficient=False,
            top_score=round(effective_score, 4),
            supporting_chunk_count=count,
            reason_code="insufficient_supporting_chunks",
            threshold_ref=f"tau={tau},min={min_supporting_chunks}",
        )

    return SufficiencyDecisionDto(
        sufficient=True,
        top_score=round(effective_score, 4),
        supporting_chunk_count=count,
        reason_code="supported",
        threshold_ref=f"tau={tau},min={min_supporting_chunks}",
    )
