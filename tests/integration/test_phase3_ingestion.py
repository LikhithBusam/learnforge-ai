"""Phase 3 Integration test: End-to-end Material creation & Document ingestion."""

import io

import fitz
import pytest
from app.knowledge import service as knowledge_service
from app.knowledge.repository import KnowledgeRepository
from app.materials import service as materials_service
from app.materials.repository import MaterialRepository
from app.platform import db as database
from app.platform.storage import get_storage, init_storage


def make_pdf(page_texts: list[str]) -> bytes:
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.mark.asyncio
async def test_full_document_ingestion_pipeline(cloud_settings, engines, seed_user, seed_project):
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p3-ingest")
    space, project = await seed_project(user.id, "Machine Learning 101")

    # Generate test PDF with 3 distinct pages
    pdf_bytes = make_pdf(
        [
            "Chapter 1: Supervised Learning Fundamentals and Loss Functions.",
            "Chapter 2: Optimization with Gradient Descent and Learning Rates.",
            "Chapter 3: Regularization, Overfitting, and Cross Validation.",
        ]
    )

    # 1. Create upload intent
    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="ML Lecture Notes",
        filename="lecture_notes.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf_bytes),
    )
    assert intent.material_id is not None
    assert intent.upload_url is not None
    assert intent.storage_key.endswith("document.pdf")

    # 2. Simulate client upload to private storage
    storage.upload_bytes(intent.storage_key, pdf_bytes, content_type="application/pdf")

    # 3. Complete upload & run ingestion
    # Execute knowledge ingestion directly with verified context
    ingest_res = await knowledge_service.ingest_document(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent.material_id,
        pdf_bytes=pdf_bytes,
    )
    assert ingest_res.page_count == 3
    assert ingest_res.chunk_count >= 3
    assert ingest_res.embedding_count == ingest_res.chunk_count

    # Mark material completed
    completed = await materials_service.mark_completed(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent.material_id,
        page_count=ingest_res.page_count,
    )
    assert completed.status == "ready"
    assert completed.page_count == 3

    # 4. Verify durable persistence in database
    async with database.session_scope(user_id=str(user.id), project_id=str(project.id)) as session:
        mat_repo = MaterialRepository(session)
        k_repo = KnowledgeRepository(session)

        # Material is ready
        mat = await mat_repo.get_by_id_and_project(intent.material_id, project.id)
        assert mat is not None
        assert mat.status == "ready"
        assert mat.page_count == 3

        # Document is ready
        doc = await k_repo.get_document_by_material(intent.material_id)
        assert doc is not None
        assert doc.status == "ready"
        assert doc.page_count == 3
        assert doc.parser_name == "pymupdf"

        # DocumentPages are preserved
        pages = await k_repo.get_pages_for_material(intent.material_id)
        assert len(pages) == 3
        assert [p.page_number for p in pages] == [1, 2, 3]
        assert "Supervised Learning" in pages[0].text_content
        assert "Gradient Descent" in pages[1].text_content
        assert "Regularization" in pages[2].text_content

        # Chunks are created and traceable
        chunks = await k_repo.get_chunks_for_material(intent.material_id)
        assert len(chunks) >= 3
        for idx, chunk in enumerate(chunks):
            assert chunk.chunk_index == idx
            assert chunk.page_start in (1, 2, 3)
            assert chunk.token_count > 0

            # Verify chunk embedding exists with dimension 1536
            emb = await k_repo.get_embedding_by_chunk_id(chunk.id)
            assert emb is not None
            assert emb.dimension == 1536
            assert len(emb.embedding) == 1536
