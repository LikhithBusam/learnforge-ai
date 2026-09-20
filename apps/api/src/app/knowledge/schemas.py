"""Knowledge DTOs — public contracts for the Knowledge domain (module-contracts §M.4).

Phase 4 implements:
- QueryInput
- ChunkRefDto
- EvidenceHitDto
- SufficiencyDecisionDto
- RetrievalMetaDto
- EvidenceSetDto
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class QueryInput(BaseModel):
    raw_query: str = Field(..., min_length=1, max_length=1000)
    conversation_context_ref: str | None = None
    rewritten_query: str | None = None


class ChunkRefDto(BaseModel):
    chunk_id: uuid.UUID
    project_id: uuid.UUID
    material_id: uuid.UUID
    material_title: str | None = None
    document_id: uuid.UUID
    page_start: int
    page_end: int
    section_path: str | None = None
    content_type: str = "text"
    text: str


class EvidenceHitDto(BaseModel):
    chunk_ref: ChunkRefDto
    vector_score: float | None = None
    lexical_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    score: float
    rank: int


class SufficiencyDecisionDto(BaseModel):
    sufficient: bool
    top_score: float
    supporting_chunk_count: int
    reason_code: str
    threshold_ref: str | None = None


class RetrievalMetaDto(BaseModel):
    vector_candidates_count: int = 0
    lexical_candidates_count: int = 0
    fusion_candidates_count: int = 0
    reranked: bool = False
    rerank_degraded: bool = False
    latency_ms: int = 0


class EvidenceSetDto(BaseModel):
    query_used: str
    project_id: uuid.UUID
    hits: list[EvidenceHitDto] = Field(default_factory=list)
    sufficiency: SufficiencyDecisionDto
    retrieval_meta: RetrievalMetaDto
