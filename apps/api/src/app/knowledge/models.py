"""Knowledge ORM models — Documents, Pages, Chunks, and Vector Embeddings (Phase 3).

Establishes the durable RAG foundation:
Project → Material → Document → DocumentPage → Chunk → ChunkEmbedding

RLS model:
- All tables enforce owner-keyed isolation via ``owner_id = app_user_id()``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.platform.models import Base
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materials.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    parser_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="pymupdf")
    parser_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="1.26.5")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="processing")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_documents_material_id", "material_id"),
        Index("ix_documents_project_id", "project_id"),
        Index("ix_documents_owner_id", "owner_id"),
        CheckConstraint(
            "status IN ('processing', 'ready', 'failed')",
            name="ck_documents_status",
        ),
        {
            "comment": "Parsed document representation of a material. RLS: owner_id = app_user_id()",
        },
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materials.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("uq_document_pages_doc_page", "document_id", "page_number", unique=True),
        Index("ix_document_pages_material_page", "material_id", "page_number"),
        Index("ix_document_pages_project_id", "project_id"),
        Index("ix_document_pages_owner_id", "owner_id"),
        {
            "comment": "Stable page-level text extraction for citations. RLS: owner_id = app_user_id()",
        },
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materials.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    section_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="text")
    content_tsv = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )
    pipeline_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_chunks_project_material_idx", "project_id", "material_id", "chunk_index"),
        Index("ix_chunks_document_page", "document_id", "page_id"),
        Index("ix_chunks_owner_id", "owner_id"),
        Index("chunks_tsv_idx", "content_tsv", postgresql_using="gin"),
        CheckConstraint(
            "content_type IN ('text', 'table', 'figure_caption', 'code', 'ocr')",
            name="ck_chunks_content_type",
        ),
        {
            "comment": "Retrieval chunks with source lineage and FTS. RLS: owner_id = app_user_id()",
        },
    )


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="v1")
    dimension: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1536")
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("uq_chunk_embeddings_chunk_model", "chunk_id", "model", "model_version", unique=True),
        Index("ix_chunk_embeddings_project_id", "project_id"),
        Index("ix_chunk_embeddings_owner_id", "owner_id"),
        {
            "comment": "Vector embeddings for chunks. RLS: owner_id = app_user_id()",
        },
    )
