"""Knowledge repository — database operations for Documents, Pages, Chunks, Embeddings (Phase 3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.knowledge.models import Chunk, ChunkEmbedding, Document, DocumentPage
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


class KnowledgeRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_document(
        self,
        *,
        document_id: uuid.UUID,
        material_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        page_count: int,
        parser_name: str = "pymupdf",
        parser_version: str = "1.26.5",
        status: str = "processing",
    ) -> Document:
        doc = Document(
            id=document_id,
            material_id=material_id,
            project_id=project_id,
            owner_id=owner_id,
            page_count=page_count,
            parser_name=parser_name,
            parser_version=parser_version,
            status=status,
        )
        self._session.add(doc)
        await self._session.flush()
        return doc

    async def get_document_by_material(self, material_id: uuid.UUID) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.material_id == material_id)
        )
        return result.scalar_one_or_none()

    async def update_document_status(
        self, document_id: uuid.UUID, status: str, page_count: int | None = None
    ) -> Document | None:
        result = await self._session.execute(select(Document).where(Document.id == document_id))
        doc = result.scalar_one_or_none()
        if doc:
            doc.status = status
            doc.updated_at = datetime.now(timezone.utc)
            if page_count is not None:
                doc.page_count = page_count
            await self._session.flush()
        return doc

    async def delete_material_artifacts(self, material_id: uuid.UUID) -> None:
        """Clear previous parsed documents, pages, chunks, and embeddings for a material.

        Guarantees idempotent re-ingestion without duplicate or stale chunks.
        """
        await self._session.execute(delete(Document).where(Document.material_id == material_id))
        await self._session.flush()

    async def save_pages(self, pages: list[DocumentPage]) -> None:
        for page in pages:
            self._session.add(page)
        await self._session.flush()

    async def save_chunks(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            self._session.add(chunk)
        await self._session.flush()

    async def save_embeddings(self, embeddings: list[ChunkEmbedding]) -> None:
        for emb in embeddings:
            self._session.add(emb)
        await self._session.flush()

    async def get_chunks_for_material(self, material_id: uuid.UUID) -> list[Chunk]:
        result = await self._session.execute(
            select(Chunk).where(Chunk.material_id == material_id).order_by(Chunk.chunk_index.asc())
        )
        return list(result.scalars().all())

    async def get_pages_for_material(self, material_id: uuid.UUID) -> list[DocumentPage]:
        result = await self._session.execute(
            select(DocumentPage)
            .where(DocumentPage.material_id == material_id)
            .order_by(DocumentPage.page_number.asc())
        )
        return list(result.scalars().all())

    async def get_chunk_with_lineage(self, chunk_id: uuid.UUID) -> dict | None:
        """Traceable RAG lookup: retrieves chunk text, page number, document, material, project."""
        stmt = (
            select(
                Chunk.id.label("chunk_id"),
                Chunk.content.label("content"),
                Chunk.page_start.label("page_start"),
                Chunk.page_end.label("page_end"),
                Chunk.chunk_index.label("chunk_index"),
                Chunk.token_count.label("token_count"),
                DocumentPage.page_number.label("page_number"),
                Document.id.label("document_id"),
                Chunk.material_id.label("material_id"),
                Chunk.project_id.label("project_id"),
            )
            .join(DocumentPage, Chunk.page_id == DocumentPage.id)
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.id == chunk_id)
        )
        res = await self._session.execute(stmt)
        row = res.one_or_none()
        if row is None:
            return None
        return dict(row._mapping)

    async def get_embedding_by_chunk_id(self, chunk_id: uuid.UUID) -> ChunkEmbedding | None:
        result = await self._session.execute(
            select(ChunkEmbedding).where(ChunkEmbedding.chunk_id == chunk_id)
        )
        return result.scalar_one_or_none()

    async def search_vectors(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        query_embedding: list[float],
        limit: int = 20,
    ) -> list[dict]:
        """Project-scoped vector similarity search using pgvector cosine distance."""
        dist = ChunkEmbedding.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(
                Chunk.id.label("chunk_id"),
                Chunk.material_id.label("material_id"),
                Chunk.document_id.label("document_id"),
                Chunk.page_start.label("page_start"),
                Chunk.page_end.label("page_end"),
                Chunk.content.label("content"),
                Chunk.section_path.label("section_path"),
                Chunk.content_type.label("content_type"),
                dist,
            )
            .join(ChunkEmbedding, Chunk.id == ChunkEmbedding.chunk_id)
            .where(
                Chunk.project_id == project_id,
                Chunk.owner_id == owner_id,
                ChunkEmbedding.project_id == project_id,
                ChunkEmbedding.owner_id == owner_id,
            )
            .order_by(dist.asc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        rows = []
        for r in res.mappings():
            d = dict(r)
            distance = float(d.get("distance", 1.0))
            d["vector_score"] = round(max(0.0, 1.0 - distance), 4)
            rows.append(d)
        return rows

    async def search_lexical(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        query_text: str,
        limit: int = 20,
    ) -> list[dict]:
        import re

        from sqlalchemy import func

        clean_words = [re.sub(r"[^\w]", "", w) for w in query_text.split()]
        filtered = [w for w in clean_words if len(w) > 1]
        if filtered:
            or_expr = " | ".join(filtered)
            ts_q = func.to_tsquery("english", or_expr)
        else:
            ts_q = func.plainto_tsquery("english", query_text)

        rank_score = func.ts_rank_cd(Chunk.content_tsv, ts_q).label("rank_score")

        stmt = (
            select(
                Chunk.id.label("chunk_id"),
                Chunk.material_id.label("material_id"),
                Chunk.document_id.label("document_id"),
                Chunk.page_start.label("page_start"),
                Chunk.page_end.label("page_end"),
                Chunk.content.label("content"),
                Chunk.section_path.label("section_path"),
                Chunk.content_type.label("content_type"),
                rank_score,
            )
            .where(
                Chunk.project_id == project_id,
                Chunk.owner_id == owner_id,
                Chunk.content_tsv.op("@@")(ts_q),
            )
            .order_by(rank_score.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        rows = []
        for r in res.mappings():
            d = dict(r)
            d["lexical_score"] = round(float(d.get("rank_score", 0.0)), 4)
            rows.append(d)
        return rows

    async def get_chunks_by_ids(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        chunk_ids: list[uuid.UUID],
    ) -> list[Chunk]:
        """Fetch multiple chunks within project and owner boundaries."""
        if not chunk_ids:
            return []
        stmt = select(Chunk).where(
            Chunk.project_id == project_id,
            Chunk.owner_id == owner_id,
            Chunk.id.in_(chunk_ids),
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
