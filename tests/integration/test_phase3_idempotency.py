"""Phase 3 Integration test: Ingestion idempotency and re-processing safety."""

import io

import fitz
import pytest
from app.knowledge import service as knowledge_service
from app.knowledge.repository import KnowledgeRepository
from app.materials import service as materials_service
from app.platform import db as database
from app.platform.storage import get_storage, init_storage


def make_pdf(texts: list[str]) -> bytes:
    doc = fitz.open()
    for text in texts:
        p = doc.new_page()
        p.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.mark.asyncio
async def test_reingestion_idempotency_prevents_duplicate_chunks(
    cloud_settings, engines, seed_user, seed_project
):
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p3-idempotent")
    space, project = await seed_project(user.id, "Idempotency Project")

    pdf_v1 = make_pdf(["Page 1 original content", "Page 2 original content"])

    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="Idempotency Spec",
        filename="spec.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf_v1),
    )
    storage.upload_bytes(intent.storage_key, pdf_v1, content_type="application/pdf")

    # Run Ingestion run 1
    res1 = await knowledge_service.ingest_document(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent.material_id,
        pdf_bytes=pdf_v1,
    )
    assert res1.page_count == 2
    initial_chunks = res1.chunk_count

    # Check count in database
    async with database.session_scope(user_id=str(user.id), project_id=str(project.id)) as session:
        k_repo = KnowledgeRepository(session)
        chunks = await k_repo.get_chunks_for_material(intent.material_id)
        pages = await k_repo.get_pages_for_material(intent.material_id)
        assert len(chunks) == initial_chunks
        assert len(pages) == 2

    # Run Ingestion run 2 (Reprocess / retry with updated PDF or same PDF)
    pdf_v2 = make_pdf(["Page 1 revised content", "Page 2 revised content", "Page 3 added content"])
    res2 = await knowledge_service.ingest_document(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent.material_id,
        pdf_bytes=pdf_v2,
    )
    assert res2.page_count == 3

    # Check count in database after run 2
    async with database.session_scope(user_id=str(user.id), project_id=str(project.id)) as session:
        k_repo = KnowledgeRepository(session)
        chunks_after = await k_repo.get_chunks_for_material(intent.material_id)
        pages_after = await k_repo.get_pages_for_material(intent.material_id)

        # There must NOT be duplicate chunks or old chunks lingering!
        assert len(pages_after) == 3
        assert len(chunks_after) == res2.chunk_count
        # Old content must not exist
        assert not any("original content" in c.content for c in chunks_after)
        # New content must exist
        assert any("revised content" in c.content for c in chunks_after)
        assert any("added content" in c.content for c in chunks_after)
