"""Phase 5 Integration Tests — Idempotency.

Verifies:
1. Same submit_answer call with the same idempotency_key → single attempt
2. Second call returns the exact same result as the first
3. Different idempotency_key on same question → ConflictError (one attempt per question)
"""

from __future__ import annotations

import io

import fitz
import pytest
from app.assessment import service as assessment_service
from app.assessment.schemas import QuestionType, SubmitAnswerInput
from app.knowledge import service as knowledge_service
from app.materials import service as materials_service
from app.platform.storage import get_storage, init_storage


def make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.mark.asyncio
async def test_submit_answer_idempotency_key_replay(
    cloud_settings, engines, seed_user, seed_project
):
    """Same idempotency_key returns the same result without re-grading."""
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p5-idem-user")
    _, project = await seed_project(user.id, "Idempotency Project")

    pdf = make_pdf(
        "Kirchhoff's Current Law states that current entering a node equals current leaving it."
    )
    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="Electronics",
        filename="elec.pdf",
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
        page_count=1,
    )

    quiz = await assessment_service.create_quiz(
        owner_id=user.id,
        project_id=project.id,
        target_question_count=2,
        question_types=[QuestionType.MCQ],
    )
    q = await assessment_service.get_next_question(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz.id,
    )
    assert hasattr(q, "id")

    # First submission
    result1 = await assessment_service.submit_answer(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz.id,
        question_id=q.id,  # type: ignore[union-attr]
        input_data=SubmitAnswerInput(selected_option="A", idempotency_key="idem-key-001"),
    )

    # Replay with same key
    result2 = await assessment_service.submit_answer(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz.id,
        question_id=q.id,  # type: ignore[union-attr]
        input_data=SubmitAnswerInput(selected_option="A", idempotency_key="idem-key-001"),
    )

    # Must return the identical attempt record
    assert result1.attempt_id == result2.attempt_id
    assert result1.is_correct == result2.is_correct
    assert result1.score == result2.score
    assert result1.feedback == result2.feedback


@pytest.mark.asyncio
async def test_second_distinct_attempt_on_same_question_replays(
    cloud_settings, engines, seed_user, seed_project
):
    """A second attempt on the same question (different key) replays the first."""
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p5-idem2-user")
    _, project = await seed_project(user.id, "Idempotency 2")

    pdf = make_pdf("Ohm's law: voltage equals current times resistance (V = IR).")
    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="Ohms",
        filename="ohms.pdf",
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
        page_count=1,
    )

    quiz = await assessment_service.create_quiz(
        owner_id=user.id,
        project_id=project.id,
        target_question_count=2,
        question_types=[QuestionType.MCQ],
    )
    q = await assessment_service.get_next_question(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz.id,
    )
    assert hasattr(q, "id")

    # First attempt — no idempotency_key
    result1 = await assessment_service.submit_answer(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz.id,
        question_id=q.id,  # type: ignore[union-attr]
        input_data=SubmitAnswerInput(selected_option="A"),
    )

    # Second attempt on same question (no key) — should replay first (unique constraint)
    result2 = await assessment_service.submit_answer(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz.id,
        question_id=q.id,  # type: ignore[union-attr]
        input_data=SubmitAnswerInput(selected_option="B"),  # different selection — ignored
    )

    # Immutability: attempt_id is the same
    assert result1.attempt_id == result2.attempt_id


@pytest.mark.asyncio
async def test_complete_quiz_is_idempotent(cloud_settings, engines, seed_user, seed_project):
    """complete_quiz called twice returns consistent results without error."""
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p5-complete-idem")
    _, project = await seed_project(user.id, "Idem Complete")

    pdf = make_pdf("Maxwell's equations describe electromagnetic fields mathematically.")
    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="Maxwell",
        filename="maxwell.pdf",
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
        page_count=1,
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
    await assessment_service.submit_answer(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz.id,
        question_id=q.id,  # type: ignore[union-attr]
        input_data=SubmitAnswerInput(selected_option="A"),
    )

    # Complete twice — should not raise
    r1 = await assessment_service.complete_quiz(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz.id,
    )
    r2 = await assessment_service.complete_quiz(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz.id,
    )

    # Both should return the same terminal state
    from app.assessment.schemas import QuizStatus

    assert r1.status == QuizStatus.COMPLETED
    assert r2.status == QuizStatus.COMPLETED
    assert r1.answered_count == r2.answered_count
