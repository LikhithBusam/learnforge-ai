"""Phase 3 RAG Specific Test: Deterministic Citation Lineage Fixture (Prompt §41).

Invariants verified:
- Hierarchical lineage: Space → Project → Material → Document → Page → Chunk → Embedding
- An embedding lookup directly recovers:
  chunk text + page number + document id + material id + project id
  WITHOUT opening or reconstructing the PDF.
"""

import io

import fitz
import pytest
from app.knowledge import service as knowledge_service
from app.knowledge.models import ChunkEmbedding
from app.materials import service as materials_service
from app.platform import db as database
from app.platform.storage import get_storage, init_storage
from sqlalchemy import select


def make_pdf(pages: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages:
        p = doc.new_page()
        p.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.mark.asyncio
async def test_rag_citation_lineage_fixture(cloud_settings, engines, seed_user, seed_project):
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("rag-trace")
    space, project = await seed_project(user.id, "Citation Lineage Project")

    # Fixture: 3 distinct pages with distinct domain content
    p1_content = (
        "Backpropagation calculates the gradient of the error function with respect to weights."
    )
    p2_content = "Stochastic gradient descent updates parameters using a single or batch sample at each step."
    p3_content = (
        "Dropout randomly zeroes units during training to prevent co-adaptation of features."
    )

    pdf_bytes = make_pdf([p1_content, p2_content, p3_content])

    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="Deep Learning Principles",
        filename="dl_principles.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf_bytes),
    )
    storage.upload_bytes(intent.storage_key, pdf_bytes, content_type="application/pdf")

    # Ingest document
    res = await knowledge_service.ingest_document(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent.material_id,
        pdf_bytes=pdf_bytes,
    )
    assert res.page_count == 3
    assert res.chunk_count >= 3

    await materials_service.mark_completed(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent.material_id,
        page_count=3,
    )

    # Now verify from the database:
    # 1. Take any ChunkEmbedding row
    async with database.session_scope(user_id=str(user.id), project_id=str(project.id)) as session:
        emb_query = await session.execute(
            select(ChunkEmbedding).where(ChunkEmbedding.project_id == project.id).limit(1)
        )
        embedding_row = emb_query.scalar_one_or_none()
        assert embedding_row is not None
        chunk_id = embedding_row.chunk_id

    # 2. Recover full lineage using knowledge service
    lineage = await knowledge_service.get_chunk_lineage(
        owner_id=user.id,
        project_id=project.id,
        chunk_id=chunk_id,
    )

    # Lineage must strictly identify:
    # - project_id
    # - material_id
    # - document_id
    # - page_number
    # - chunk_index
    # - chunk content text
    assert lineage.project_id == project.id
    assert lineage.material_id == intent.material_id
    assert lineage.document_id == res.document_id
    assert lineage.page_number in (1, 2, 3)
    assert lineage.chunk_index >= 0
    assert len(lineage.content) > 0
    assert lineage.token_count > 0

    # Verify that the text matches what was originally on that page
    if lineage.page_number == 1:
        assert "Backpropagation" in lineage.content
    elif lineage.page_number == 2:
        assert "Stochastic gradient descent" in lineage.content
    elif lineage.page_number == 3:
        assert "Dropout" in lineage.content
