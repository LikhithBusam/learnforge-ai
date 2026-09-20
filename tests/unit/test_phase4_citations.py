"""Phase 4 Unit Tests — Citation Validation & Context Composition (Prompt §20, §22, §23, §26).

Verifies:
1. Citation validation strictly enforces chunk membership in retrieved evidence.
2. Citations to non-retrieved chunks are stripped.
3. Page numbers outside chunk bounds are clamped to valid range.
4. Context composer isolates untrusted document evidence inside <retrieved_evidence> blocks.
"""

from __future__ import annotations

import uuid

from app.knowledge.schemas import (
    ChunkRefDto,
    EvidenceHitDto,
    EvidenceSetDto,
    RetrievalMetaDto,
    SufficiencyDecisionDto,
)
from app.tutor.citations import validate_citations
from app.tutor.context import compose_tutor_context
from app.tutor.schemas import CitationPayload


def _make_evidence_set(
    project_id: uuid.UUID, chunks: list[tuple[uuid.UUID, int, int]]
) -> EvidenceSetDto:
    hits = [
        EvidenceHitDto(
            chunk_ref=ChunkRefDto(
                chunk_id=cid,
                project_id=project_id,
                material_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                page_start=p_start,
                page_end=p_end,
                text="Evidence text content for citation validation.",
            ),
            score=0.90,
            rank=idx + 1,
        )
        for idx, (cid, p_start, p_end) in enumerate(chunks)
    ]
    return EvidenceSetDto(
        query_used="Test query",
        project_id=project_id,
        hits=hits,
        sufficiency=SufficiencyDecisionDto(
            sufficient=True,
            top_score=0.90,
            supporting_chunk_count=len(hits),
            reason_code="supported",
        ),
        retrieval_meta=RetrievalMetaDto(),
    )


def test_validate_citations_accepts_valid():
    project_id = uuid.uuid4()
    cid1 = uuid.uuid4()
    evidence = _make_evidence_set(project_id, [(cid1, 10, 12)])

    claimed = [CitationPayload(chunk_id=cid1, page=11, quote="Evidence text")]
    valid, warnings = validate_citations(
        claimed_citations=claimed, evidence_set=evidence, project_id=project_id
    )

    assert len(valid) == 1
    assert valid[0].chunk_id == cid1
    assert valid[0].page_number == 11
    assert len(warnings) == 0


def test_validate_citations_strips_hallucinated_chunk():
    project_id = uuid.uuid4()
    cid_real = uuid.uuid4()
    cid_fake = uuid.uuid4()
    evidence = _make_evidence_set(project_id, [(cid_real, 5, 6)])

    claimed = [
        CitationPayload(chunk_id=cid_fake, page=99, quote="Hallucinated"),
        CitationPayload(chunk_id=cid_real, page=5, quote="Real text"),
    ]
    valid, warnings = validate_citations(
        claimed_citations=claimed, evidence_set=evidence, project_id=project_id
    )

    assert len(valid) == 1
    assert valid[0].chunk_id == cid_real
    assert any("Rejected citation to non-retrieved chunk_id" in w for w in warnings)


def test_validate_citations_repairs_out_of_bounds_page():
    project_id = uuid.uuid4()
    cid = uuid.uuid4()
    evidence = _make_evidence_set(project_id, [(cid, 10, 12)])

    # Claimed page 99 for chunk that only covers pages 10-12
    claimed = [CitationPayload(chunk_id=cid, page=99, quote="Out of bounds")]
    valid, warnings = validate_citations(
        claimed_citations=claimed, evidence_set=evidence, project_id=project_id
    )

    assert len(valid) == 1
    assert valid[0].page_number == 10  # clamped to page_start
    assert any("Page 99 outside chunk" in w for w in warnings)


def test_context_composer_encapsulates_untrusted_evidence():
    project_id = uuid.uuid4()
    cid = uuid.uuid4()
    evidence = _make_evidence_set(project_id, [(cid, 1, 2)])

    system_prompt, user_prompt = compose_tutor_context(
        question="What is congestion control?",
        evidence_set=evidence,
        history=[],
    )

    assert "CRITICAL GROUNDING RULES" in system_prompt
    assert "PROMPT INJECTION DEFENSE" in system_prompt
    assert "<retrieved_evidence>" in user_prompt
    assert "</retrieved_evidence>" in user_prompt
    assert f'<chunk id="{cid}"' in user_prompt
    assert "STUDENT QUESTION:\nWhat is congestion control?" in user_prompt
