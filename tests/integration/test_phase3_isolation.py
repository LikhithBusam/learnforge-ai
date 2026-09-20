"""Phase 3 Integration test: PostgreSQL RLS project isolation on Materials and Knowledge tables."""

import io

import fitz
import pytest
from app.knowledge import service as knowledge_service
from app.knowledge.models import Chunk, ChunkEmbedding, Document, DocumentPage
from app.materials import service as materials_service
from app.materials.models import Material
from app.platform import db as database
from app.platform.errors import NotFound
from app.platform.storage import get_storage, init_storage
from sqlalchemy import select


def make_pdf(text: str) -> bytes:
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.mark.asyncio
async def test_rls_blocks_cross_user_knowledge_access(
    cloud_settings, engines, seed_user, seed_project
):
    init_storage(cloud_settings)
    storage = get_storage()

    # Create User A & Project A
    user_a = await seed_user("user-a-iso")
    _space_a, project_a = await seed_project(user_a.id, "Project A")

    # Create User B & Project B
    user_b = await seed_user("user-b-iso")
    _space_b, project_b = await seed_project(user_b.id, "Project B")

    pdf_bytes_a = make_pdf("Confidential Research from User A that User B must never see.")

    intent_a = await materials_service.create_upload_intent(
        owner_id=user_a.id,
        project_id=project_a.id,
        title="Project A Confidential Spec",
        filename="confidential_a.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf_bytes_a),
    )
    storage.upload_bytes(intent_a.storage_key, pdf_bytes_a, content_type="application/pdf")

    # User A ingests material
    res_a = await knowledge_service.ingest_document(
        owner_id=user_a.id,
        project_id=project_a.id,
        material_id=intent_a.material_id,
        pdf_bytes=pdf_bytes_a,
    )
    assert res_a.chunk_count >= 1

    # Test 1: Service level authorization check
    with pytest.raises(NotFound):
        await materials_service.get_material(
            owner_id=user_b.id,
            project_id=project_a.id,
            material_id=intent_a.material_id,
        )

    # Test 2: Database RLS level - User B executing queries under runtime role
    async with database.session_scope(
        user_id=str(user_b.id), project_id=str(project_b.id)
    ) as session:
        # A) Materials: User B cannot see User A's material
        mats_b = await session.execute(select(Material).where(Material.id == intent_a.material_id))
        assert mats_b.scalar_one_or_none() is None

        # B) Documents: User B cannot see User A's document
        docs_b = await session.execute(select(Document).where(Document.id == res_a.document_id))
        assert docs_b.scalar_one_or_none() is None

        # C) Pages: User B cannot see User A's document pages
        pages_b = await session.execute(
            select(DocumentPage).where(DocumentPage.material_id == intent_a.material_id)
        )
        assert len(pages_b.scalars().all()) == 0

        # D) Chunks: Even with NO WHERE filter, User B gets 0 of User A's chunks
        chunks_b = await session.execute(
            select(Chunk).where(Chunk.material_id == intent_a.material_id)
        )
        assert len(chunks_b.scalars().all()) == 0

        # E) ChunkEmbeddings: User B gets 0 of User A's embeddings
        embs_b = await session.execute(
            select(ChunkEmbedding).where(ChunkEmbedding.project_id == project_a.id)
        )
        assert len(embs_b.scalars().all()) == 0

    # Test 3: User A querying User A's chunks succeeds
    async with database.session_scope(
        user_id=str(user_a.id), project_id=str(project_a.id)
    ) as session:
        chunks_a = await session.execute(
            select(Chunk).where(Chunk.material_id == intent_a.material_id)
        )
        assert len(chunks_a.scalars().all()) >= 1
