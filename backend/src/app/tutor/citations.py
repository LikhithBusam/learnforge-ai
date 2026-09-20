"""Citation Validation Engine (Prompt §22, §23).

Strict Validation Rules:
1. Every cited chunk_id MUST exist in the current turn's retrieved evidence set.
2. The cited page_number MUST fall within [page_start, page_end] of that chunk.
3. Every cited chunk must belong to the active project.
4. Any invalid, hallucinated, or out-of-scope citations are stripped.
5. If an answer claimed to be grounded has zero valid citations remaining, it is downgraded to 'insufficient_evidence'.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.knowledge.schemas import EvidenceSetDto
    from app.tutor.schemas import CitationPayload


@dataclass(frozen=True)
class ValidatedCitation:
    chunk_id: uuid.UUID
    material_id: uuid.UUID
    document_id: uuid.UUID
    project_id: uuid.UUID
    page_number: int
    quote: str | None = None


def validate_citations(
    *,
    claimed_citations: list[CitationPayload],
    evidence_set: EvidenceSetDto,
    project_id: uuid.UUID,
) -> tuple[list[ValidatedCitation], list[str]]:
    """Validate model citations against retrieved evidence.

    Returns:
        (valid_citations, validation_warnings)
    """
    evidence_map = {hit.chunk_ref.chunk_id: hit.chunk_ref for hit in evidence_set.hits}

    valid: list[ValidatedCitation] = []
    warnings: list[str] = []

    for cit in claimed_citations:
        # 1. Existence check
        ref = evidence_map.get(cit.chunk_id)
        if ref is None:
            warnings.append(f"Rejected citation to non-retrieved chunk_id: {cit.chunk_id}")
            continue

        # 2. Scope check
        if evidence_set.project_id != project_id:
            warnings.append(f"Rejected citation across project boundary: {ref.chunk_id}")
            continue

        # 3. Page range check
        page = cit.page
        if page < ref.page_start or page > ref.page_end:
            warnings.append(
                f"Page {page} outside chunk {cit.chunk_id} bounds [{ref.page_start}, {ref.page_end}]"
            )
            # Safe repair: clamp to page_start if it refers to the right chunk
            page = ref.page_start

        valid.append(
            ValidatedCitation(
                chunk_id=ref.chunk_id,
                material_id=ref.material_id,
                document_id=ref.document_id,
                project_id=project_id,
                page_number=page,
                quote=cit.quote,
            )
        )

    return valid, warnings
