"""Knowledge service — the public facade of the knowledge domain (module-contracts §M.4).

Phase 3 implements:
- Durable document ingestion & parsing (PyMuPDF)
- Page preservation (page_number 1-indexed)
- Deterministic RAG chunking
- AI Gateway vector embedding persistence
- RAG lineage query for future Tutor citation grounding
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import fitz  # PyMuPDF
from app.ai.gateway import get_gateway
from app.ai.schemas import EmbeddingRequest
from app.knowledge import chunking
from app.knowledge.models import Chunk, ChunkEmbedding, DocumentPage
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import ChunkRefDto, EvidenceSetDto, QueryInput
from app.platform import db as database
from app.platform.config import get_settings
from app.platform.errors import NotFound, ValidationError
from app.platform.ids import uuid7
from app.platform.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    document_id: uuid.UUID
    page_count: int
    chunk_count: int
    embedding_count: int


@dataclass(frozen=True)
class ChunkLineageDto:
    chunk_id: uuid.UUID
    project_id: uuid.UUID
    material_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    chunk_index: int
    content: str
    token_count: int


async def ingest_document(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    material_id: uuid.UUID,
    pdf_bytes: bytes,
    pipeline_version: str = "v1",
) -> IngestionResult:
    """Parse PDF, preserve pages, generate chunks, embed vectors, and persist."""
    settings = get_settings()

    # Validate PDF structure and page count limits
    try:
        doc_pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ValidationError(f"Unreadable PDF document: {exc}") from exc

    try:
        if doc_pdf.is_encrypted:
            raise ValidationError("Encrypted PDFs are not supported")

        page_count = len(doc_pdf)
        if page_count == 0:
            raise ValidationError("PDF has zero pages")
        if page_count > settings.MAX_PDF_PAGES:
            raise ValidationError(
                f"PDF exceeds maximum page limit ({page_count} > {settings.MAX_PDF_PAGES})"
            )

        document_id = uuid7()

        # 1. Page extraction
        page_inputs: list[chunking.PageInput] = []
        page_models: list[DocumentPage] = []

        for pno in range(page_count):
            page_num = pno + 1
            page = doc_pdf.load_page(pno)
            text = page.get_text("text") or ""
            text = text.strip()
            page_id = uuid7()

            page_inputs.append(
                chunking.PageInput(
                    page_id=page_id,
                    page_number=page_num,
                    text=text,
                )
            )
            page_models.append(
                DocumentPage(
                    id=page_id,
                    document_id=document_id,
                    material_id=material_id,
                    project_id=project_id,
                    owner_id=owner_id,
                    page_number=page_num,
                    text_content=text,
                    char_count=len(text),
                    token_count=chunking.estimate_tokens(text),
                )
            )
    finally:
        doc_pdf.close()

    # 2. Deterministic chunking
    chunk_drafts = chunking.create_chunks_for_pages(
        page_inputs,
        target_tokens=settings.CHUNK_TARGET_TOKENS,
        overlap_ratio=settings.CHUNK_OVERLAP_RATIO,
    )

    # 3. Embedding generation via AI Gateway
    gateway = get_gateway()
    vectors: list[list[float]] = []
    if chunk_drafts:
        chunk_texts = [c.content for c in chunk_drafts]
        emb_res = await gateway.embed(
            EmbeddingRequest(
                feature="documents.ingestion",
                texts=chunk_texts,
                model_role="embedding",
            )
        )
        vectors = emb_res.vectors

    # 4. Atomic database persistence
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = KnowledgeRepository(session)

        # Idempotent re-ingestion cleanup of prior runs
        await repo.delete_material_artifacts(material_id)

        # Create Document record
        await repo.create_document(
            document_id=document_id,
            material_id=material_id,
            project_id=project_id,
            owner_id=owner_id,
            page_count=page_count,
            parser_name="pymupdf",
            parser_version=fitz.__version__,
            status="ready",
        )

        # Save pages
        await repo.save_pages(page_models)

        # Save chunks & embeddings
        chunk_models: list[Chunk] = []
        embedding_models: list[ChunkEmbedding] = []

        for idx, draft in enumerate(chunk_drafts):
            chunk_models.append(
                Chunk(
                    id=draft.id,
                    project_id=project_id,
                    material_id=material_id,
                    document_id=document_id,
                    page_id=draft.page_id,
                    owner_id=owner_id,
                    page_start=draft.page_start,
                    page_end=draft.page_end,
                    chunk_index=draft.chunk_index,
                    content=draft.content,
                    token_count=draft.token_count,
                    char_count=draft.char_count,
                    section_path=None,
                    content_type="text",
                    pipeline_version=pipeline_version,
                )
            )
            if idx < len(vectors):
                embedding_models.append(
                    ChunkEmbedding(
                        id=uuid7(),
                        chunk_id=draft.id,
                        project_id=project_id,
                        owner_id=owner_id,
                        model=settings.AI_EMBEDDING_MODEL,
                        model_version="v1",
                        dimension=len(vectors[idx]),
                        embedding=vectors[idx],
                    )
                )

        await repo.save_chunks(chunk_models)
        await repo.save_embeddings(embedding_models)

    logger.info(
        "knowledge_ingestion_completed",
        extra={
            "details": {
                "material_id": str(material_id),
                "document_id": str(document_id),
                "pages": page_count,
                "chunks": len(chunk_models),
                "embeddings": len(embedding_models),
            }
        },
    )

    return IngestionResult(
        document_id=document_id,
        page_count=page_count,
        chunk_count=len(chunk_models),
        embedding_count=len(embedding_models),
    )


async def get_chunk_lineage(
    *, owner_id: uuid.UUID, project_id: uuid.UUID, chunk_id: uuid.UUID
) -> ChunkLineageDto:
    """Retrieve full traceable lineage for a chunk (citation-readiness)."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = KnowledgeRepository(session)
        row = await repo.get_chunk_with_lineage(chunk_id)
        if row is None or row["project_id"] != project_id:
            raise NotFound("Chunk not found")
        return ChunkLineageDto(
            chunk_id=row["chunk_id"],
            project_id=row["project_id"],
            material_id=row["material_id"],
            document_id=row["document_id"],
            page_number=row["page_number"],
            chunk_index=row["chunk_index"],
            content=row["content"],
            token_count=row["token_count"],
        )


async def retrieve_evidence(
    *,
    project_id: uuid.UUID,
    owner_id: uuid.UUID,
    query_input: QueryInput,
    top_k: int | None = None,
    tau: float | None = None,
) -> EvidenceSetDto:
    """Independently testable hybrid RAG retrieval pipeline (Prompt §4, §13, §15, §17).

    Pipeline:
    1. Unicode-preserving query preprocessing
    2. Vector similarity search (pgvector cosine via HNSW)
    3. PostgreSQL full-text search (tsvector + GIN via plainto_tsquery)
    4. Deterministic Reciprocal Rank Fusion (RRF k=60)
    5. AI Gateway reranking (role: rerank)
    6. Evidence sufficiency evaluation
    """
    import time

    from app.ai.schemas import RerankRequest
    from app.knowledge import retrieval
    from app.knowledge.schemas import (
        ChunkRefDto,
        EvidenceHitDto,
        EvidenceSetDto,
        RetrievalMetaDto,
    )

    started = time.perf_counter()
    settings = get_settings()

    cleaned_query = retrieval.preprocess_query(query_input.raw_query)

    vec_k = settings.RETRIEVAL_VECTOR_TOP_K
    lex_k = settings.RETRIEVAL_LEXICAL_TOP_K
    fusion_k = settings.RETRIEVAL_FUSION_TOP_K
    rerank_k = settings.RETRIEVAL_RERANK_TO
    final_k = top_k or settings.RETRIEVAL_FINAL_CONTEXT_TOP_K
    threshold = tau if tau is not None else (settings.RETRIEVAL_SUFFICIENCY_TAU or 0.50)
    rrf_k = settings.RETRIEVAL_RRF_K
    min_supporting = settings.RETRIEVAL_MIN_SUPPORTING_CHUNKS

    # 1. Query vector embedding via AI Gateway
    gateway = get_gateway()
    emb_res = await gateway.embed(EmbeddingRequest(feature="retrieval", texts=[cleaned_query]))
    query_vector = emb_res.vectors[0]

    # 2. Database candidate retrieval under project scope & RLS
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = KnowledgeRepository(session)
        vec_rows = await repo.search_vectors(
            project_id=project_id,
            owner_id=owner_id,
            query_embedding=query_vector,
            limit=vec_k,
        )
        lex_rows = await repo.search_lexical(
            project_id=project_id,
            owner_id=owner_id,
            query_text=cleaned_query,
            limit=lex_k,
        )

    vec_cands = [
        retrieval.RetrievedCandidate(
            chunk_id=r["chunk_id"],
            material_id=r["material_id"],
            document_id=r["document_id"],
            page_start=r["page_start"],
            page_end=r["page_end"],
            text=r["content"],
            section_path=r["section_path"],
            content_type=r["content_type"],
            vector_score=r["vector_score"],
        )
        for r in vec_rows
    ]

    lex_cands = [
        retrieval.RetrievedCandidate(
            chunk_id=r["chunk_id"],
            material_id=r["material_id"],
            document_id=r["document_id"],
            page_start=r["page_start"],
            page_end=r["page_end"],
            text=r["content"],
            section_path=r["section_path"],
            content_type=r["content_type"],
            lexical_score=r["lexical_score"],
        )
        for r in lex_rows
    ]

    # 3. Reciprocal Rank Fusion
    fused = retrieval.reciprocal_rank_fusion(vec_cands, lex_cands, k=rrf_k, top_n=fusion_k)

    # 4. Reranking via AI Gateway
    reranked = False
    rerank_degraded = False
    candidates_to_rerank = fused[:rerank_k]

    final_candidates: list[retrieval.RetrievedCandidate] = []
    if candidates_to_rerank:
        candidate_texts = [c.text for c in candidates_to_rerank]
        try:
            rerank_res = await gateway.rerank(
                RerankRequest(
                    feature="retrieval",
                    query=cleaned_query,
                    candidates=candidate_texts,
                    top_n=final_k,
                )
            )
            for hit in rerank_res.ranked:
                if hit.index < len(candidates_to_rerank):
                    cand = candidates_to_rerank[hit.index]
                    cand.rerank_score = hit.score
                    final_candidates.append(cand)
            reranked = True
        except Exception as e:
            logger.warning(
                "Reranker degraded or unavailable, using fused order",
                extra={"error": str(e)},
            )
            rerank_degraded = True
            final_candidates = candidates_to_rerank[:final_k]
    else:
        final_candidates = []

    # 5. Evidence sufficiency decision
    sufficiency = retrieval.evaluate_evidence_sufficiency(
        final_candidates, tau=threshold, min_supporting_chunks=min_supporting
    )

    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))

    hits = [
        EvidenceHitDto(
            chunk_ref=ChunkRefDto(
                chunk_id=c.chunk_id,
                project_id=project_id,
                material_id=c.material_id,
                document_id=c.document_id,
                page_start=c.page_start,
                page_end=c.page_end,
                section_path=c.section_path,
                content_type=c.content_type,
                text=c.text,
            ),
            vector_score=c.vector_score,
            lexical_score=c.lexical_score,
            fusion_score=c.fusion_score,
            rerank_score=c.rerank_score,
            score=(
                c.rerank_score
                if c.rerank_score is not None
                else (c.fusion_score if c.fusion_score is not None else (c.vector_score or 0.0))
            ),
            rank=idx + 1,
        )
        for idx, c in enumerate(final_candidates)
    ]

    return EvidenceSetDto(
        query_used=cleaned_query,
        project_id=project_id,
        hits=hits,
        sufficiency=sufficiency,
        retrieval_meta=RetrievalMetaDto(
            vector_candidates_count=len(vec_cands),
            lexical_candidates_count=len(lex_cands),
            fusion_candidates_count=len(fused),
            reranked=reranked,
            rerank_degraded=rerank_degraded,
            latency_ms=elapsed_ms,
        ),
    )


async def get_chunk_refs(
    *,
    project_id: uuid.UUID,
    owner_id: uuid.UUID,
    chunk_ids: list[uuid.UUID],
) -> list[ChunkRefDto]:
    """Retrieve chunk references for citation resolution and verification."""
    from app.knowledge.schemas import ChunkRefDto

    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = KnowledgeRepository(session)
        chunks = await repo.get_chunks_by_ids(
            project_id=project_id, owner_id=owner_id, chunk_ids=chunk_ids
        )
        return [
            ChunkRefDto(
                chunk_id=c.id,
                project_id=c.project_id,
                material_id=c.material_id,
                document_id=c.document_id,
                page_start=c.page_start,
                page_end=c.page_end,
                section_path=c.section_path,
                content_type=c.content_type,
                text=c.content,
            )
            for c in chunks
        ]
