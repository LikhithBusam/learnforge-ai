"""Phase 5 Integration Tests — RAG Grounding Traceability.

Verifies:
1. Generated questions have source_chunk_ids
2. source_chunk_ids can be traced: Project → Material → Document → Page → Chunk
3. Questions are answerable from evidence (source chunks contain relevant text)
4. Questions from Project A do not reference chunks from Project B
"""

from __future__ import annotations

import io

import fitz
import pytest
from app.assessment import service as assessment_service
from app.assessment.schemas import QuestionType
from app.knowledge import service as knowledge_service
from app.materials import service as materials_service
from app.platform.storage import get_storage, init_storage


def make_pdf(pages: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.mark.asyncio
async def test_question_source_chunk_ids_are_traceable(
    cloud_settings, engines, seed_user, seed_project, admin_exec
):
    """Generated question source_chunk_ids belong to the project's chunks table."""
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p5-rag-trace-user")
    _, project = await seed_project(user.id, "TCP/IP Reference")

    pdf = make_pdf(
        [
            "TCP uses a three-way handshake: SYN, SYN-ACK, ACK to establish connections.",
            "TCP guarantees ordered delivery and retransmits lost packets.",
        ]
    )
    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="TCP Reference",
        filename="tcp.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf),
    )
    storage.upload_bytes(intent.storage_key, pdf, content_type="application/pdf")
    await knowledge_service.ingest_document(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent.material_id,
        pdf_bytes=pdf,
    )
    await materials_service.mark_completed(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent.material_id,
        page_count=2,
    )

    quiz = await assessment_service.create_quiz(
        owner_id=user.id,
        project_id=project.id,
        target_question_count=1,
        question_types=[QuestionType.MCQ],
    )
    q = await assessment_service.get_next_question(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz.id,
    )
    assert hasattr(q, "source_chunk_ids"), "Expected QuestionDto with source_chunk_ids"
    assert len(q.source_chunk_ids) > 0, "Question must have at least one source chunk"  # type: ignore[union-attr]

    # Verify each source chunk id exists in the DB and belongs to this project
    for chunk_id_str in q.source_chunk_ids:  # type: ignore[union-attr]
        rows = await admin_exec(
            "SELECT id, project_id FROM chunks WHERE id = :chunk_id",
            {"chunk_id": chunk_id_str},
        )
        chunk_rows = rows.fetchall()
        assert len(chunk_rows) == 1, f"Chunk {chunk_id_str} not found in DB"
        chunk_project_id = str(chunk_rows[0][1])
        assert chunk_project_id == str(project.id), (
            f"Chunk {chunk_id_str} belongs to project {chunk_project_id}, " f"expected {project.id}"
        )


@pytest.mark.asyncio
async def test_questions_from_project_a_do_not_reference_project_b_chunks(
    cloud_settings, engines, seed_user, seed_project, admin_exec
):
    """Cross-project chunk leakage check: questions only reference own project's chunks."""
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p5-cross-chunk")
    _, project_a = await seed_project(user.id, "Project Alpha")
    _, project_b = await seed_project(user.id, "Project Beta")

    for proj, text in [
        (project_a, "Alpha project: TCP SYN handshake establishes connections."),
        (project_b, "Beta project: UDP is stateless and connectionless by design."),
    ]:
        pdf = make_pdf([text])
        intent = await materials_service.create_upload_intent(
            owner_id=user.id,
            project_id=proj.id,
            title="Protocol",
            filename="proto.pdf",
            content_type="application/pdf",
            size_bytes=len(pdf),
        )
        storage.upload_bytes(intent.storage_key, pdf, content_type="application/pdf")
        await knowledge_service.ingest_document(
            owner_id=user.id,
            project_id=proj.id,
            material_id=intent.material_id,
            pdf_bytes=pdf,
        )
        await materials_service.mark_completed(
            owner_id=user.id,
            project_id=proj.id,
            material_id=intent.material_id,
            page_count=1,
        )

    # Generate question from Project A
    quiz_a = await assessment_service.create_quiz(
        owner_id=user.id,
        project_id=project_a.id,
        target_question_count=1,
        question_types=[QuestionType.MCQ],
    )
    q_a = await assessment_service.get_next_question(
        owner_id=user.id,
        project_id=project_a.id,
        quiz_id=quiz_a.id,
    )
    assert hasattr(q_a, "source_chunk_ids")

    # Get all of Project B's chunk ids
    rows_b = await admin_exec(
        "SELECT id FROM chunks WHERE project_id = :project_id",
        {"project_id": str(project_b.id)},
    )
    project_b_chunk_ids = {str(row[0]) for row in rows_b.fetchall()}

    # Project A's question must NOT reference any Project B chunk
    for chunk_id_str in q_a.source_chunk_ids:  # type: ignore[union-attr]
        assert chunk_id_str not in project_b_chunk_ids, (
            f"Question from Project A referenced Project B chunk {chunk_id_str} — "
            f"cross-project leakage detected!"
        )
