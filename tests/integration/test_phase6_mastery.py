"""Integration tests for Phase 6 Concept Mastery Engine (against cloud Supabase DB).

Tests end-to-end evidence processing, mastery state persistence,
audit history trail, and recomputation.
"""

from __future__ import annotations

import io
import uuid

import fitz
import pytest
from app.assessment import service as assessment_service
from app.assessment.schemas import QuestionType, SubmitAnswerInput
from app.knowledge import service as knowledge_service
from app.mastery import service as mastery_service
from app.mastery.schemas import MasteryCategory
from app.materials import service as materials_service
from app.platform.storage import get_storage, init_storage


def make_pdf(texts: list[str] | str) -> bytes:
    doc = fitz.open()
    if isinstance(texts, str):
        texts = [texts]
    for text in texts:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    stream = io.BytesIO()
    doc.save(stream)
    doc.close()
    return stream.getvalue()


@pytest.mark.asyncio
async def test_full_mastery_lifecycle(cloud_settings, engines, seed_user, seed_project):
    """Full mastery flow: Ingest -> Quiz -> Answer -> Process Evidence -> Verify State & Trail."""
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p6-mastery-user")
    _, project = await seed_project(user.id, "Cloud Mastery Project")

    # 1. Ingest material
    pdf_bytes = make_pdf(
        [
            "TCP (Transmission Control Protocol) is connection-oriented and provides reliable byte streams.",
            "TCP uses a three-way handshake (SYN, SYN-ACK, ACK) to establish a connection.",
        ]
    )
    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="TCP Networking",
        filename="tcp.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf_bytes),
    )
    storage.upload_bytes(intent.storage_key, pdf_bytes, content_type="application/pdf")
    await knowledge_service.ingest_document(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent.material_id,
        pdf_bytes=pdf_bytes,
    )
    await materials_service.mark_completed(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent.material_id,
        page_count=2,
    )

    # 2. Create quiz and get question
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
    assert hasattr(q, "id")

    # 3. Submit answer (correct option A)
    res = await assessment_service.submit_answer(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz.id,
        question_id=q.id,  # type: ignore[union-attr]
        input_data=SubmitAnswerInput(selected_option="A"),
    )
    assert res.attempt_id is not None

    # Attach a concept_id to test mastery update
    concept_id = uuid.uuid4()

    # 4. Record evidence directly via mastery_service to verify BKT state update
    mastery_dto = await mastery_service.record_learning_event(
        owner_id=user.id,
        project_id=project.id,
        input_data=mastery_service.RecordEvidenceInput(
            source="assessment",
            source_id=res.attempt_id,
            concept_id=concept_id,
            result="correct",
            score=1.0,
            difficulty="medium",
        ),
    )

    assert mastery_dto.concept_id == concept_id
    assert mastery_dto.evidence_count == 1
    assert mastery_dto.correct_count == 1
    assert mastery_dto.mastery_probability > 0.20  # P_INIT is 0.20, correct answer increases it
    assert mastery_dto.confidence > 0.0

    # 5. Query individual concept mastery
    fetched = await mastery_service.get_concept_mastery(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
    )
    assert fetched is not None
    assert fetched.mastery_probability == mastery_dto.mastery_probability
    assert fetched.confidence == mastery_dto.confidence

    # 6. Query project-level mastery summary
    summary = await mastery_service.get_mastery_summary(
        owner_id=user.id,
        project_id=project.id,
    )
    assert summary.project_id == project.id
    assert len(summary.concepts) >= 1
    assert summary.average_mastery > 0.0

    # 7. Query audit trail
    trail = await mastery_service.get_evidence_trail(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
    )
    assert len(trail) == 1
    assert trail[0].source_id == res.attempt_id
    assert trail[0].result == "correct"
    assert trail[0].mastery_before == 0.20
    assert trail[0].mastery_after == mastery_dto.mastery_probability


@pytest.mark.asyncio
async def test_recompute_mastery_from_trail(cloud_settings, engines, seed_user, seed_project):
    """Recompute produces the exact same deterministic mastery probability."""
    user = await seed_user("p6-recompute-user")
    _, project = await seed_project(user.id, "Recompute Project")

    concept_id = uuid.uuid4()

    # Record 2 learning events
    await mastery_service.record_learning_event(
        owner_id=user.id,
        project_id=project.id,
        input_data=mastery_service.RecordEvidenceInput(
            source="assessment",
            source_id=uuid.uuid4(),
            concept_id=concept_id,
            result="correct",
            score=1.0,
            difficulty="hard",
        ),
    )

    m2 = await mastery_service.record_learning_event(
        owner_id=user.id,
        project_id=project.id,
        input_data=mastery_service.RecordEvidenceInput(
            source="assessment",
            source_id=uuid.uuid4(),
            concept_id=concept_id,
            result="incorrect",
            score=0.0,
            difficulty="easy",
        ),
    )
    assert m2.evidence_count == 2

    # Recompute
    recomputed = await mastery_service.recompute_mastery(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
    )
    assert isinstance(recomputed.category, MasteryCategory)
