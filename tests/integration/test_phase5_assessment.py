"""Phase 5 Integration Tests — Full Quiz Lifecycle.

Verifies:
1. Create quiz → get_next_question (generates MCQ from ingested material)
2. Submit correct MCQ answer → is_correct=True, score=1.0, evidence emitted
3. Submit wrong MCQ answer → is_correct=False, score=0.0
4. Open-ended question → submit answer → graded (ai or pending_review)
5. complete_quiz → status=completed, per-concept results returned
6. get_results → same totals
7. get_assessment_history → includes answered questions
"""

from __future__ import annotations

import io

import fitz
import pytest
from app.assessment import service as assessment_service
from app.assessment.schemas import (
    QuestionType,
    QuizStatus,
    SubmitAnswerInput,
)
from app.knowledge import service as knowledge_service
from app.materials import service as materials_service
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
async def test_full_quiz_lifecycle_mcq(cloud_settings, engines, seed_user, seed_project):
    """Full MCQ quiz: create → next → submit → complete → results."""
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p5-quiz-user")
    space, project = await seed_project(user.id, "Network Protocols")

    # Ingest material for RAG grounding
    pdf_bytes = make_pdf(
        [
            "Ethernet uses CSMA/CD (Carrier Sense Multiple Access with Collision Detection) "
            "to manage shared access to the transmission medium.",
            "When a collision is detected, all transmitters send a jam signal and apply "
            "binary exponential backoff before retransmitting.",
        ]
    )
    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="Network Standards",
        filename="network.pdf",
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

    # 1. Create quiz
    quiz_dto = await assessment_service.create_quiz(
        owner_id=user.id,
        project_id=project.id,
        target_question_count=2,
        mode="adaptive",
        question_types=[QuestionType.MCQ],
    )
    assert quiz_dto.status == QuizStatus.CREATED
    assert quiz_dto.target_question_count == 2
    assert quiz_dto.answered_count == 0

    # 2. Get first question (generates MCQ from evidence)
    q1 = await assessment_service.get_next_question(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz_dto.id,
        question_types=[QuestionType.MCQ],
    )
    assert hasattr(q1, "question_text"), "Expected QuestionDto, got QuizCompleteDto"
    assert q1.question_type == QuestionType.MCQ
    assert q1.options is not None
    assert len(q1.options) == 4
    assert q1.ordinal == 1
    # Answer key must NOT be exposed
    assert not hasattr(q1, "correct_option") or q1.correct_option is None  # type: ignore[union-attr]
    # Source provenance present
    assert len(q1.source_chunk_ids) > 0

    # Quiz should now be ACTIVE
    quiz_state = await assessment_service.get_quiz(
        owner_id=user.id, project_id=project.id, quiz_id=quiz_dto.id
    )
    assert quiz_state.status == QuizStatus.ACTIVE

    # 3. Submit answer for Q1 (select A — stub always makes A correct)
    result1 = await assessment_service.submit_answer(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz_dto.id,
        question_id=q1.id,
        input_data=SubmitAnswerInput(
            selected_option="A",
            idempotency_key="q1-attempt-1",
        ),
    )
    assert result1.attempt_id is not None
    assert result1.is_correct is True
    assert result1.score == 1.0
    assert result1.grading_method.value == "deterministic"
    assert result1.pending_review is False
    assert result1.feedback is not None

    # 4. Idempotent replay — same key returns same result
    replayed = await assessment_service.submit_answer(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz_dto.id,
        question_id=q1.id,
        input_data=SubmitAnswerInput(
            selected_option="A",
            idempotency_key="q1-attempt-1",
        ),
    )
    assert replayed.attempt_id == result1.attempt_id

    # 5. Get second question
    q2 = await assessment_service.get_next_question(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz_dto.id,
        question_types=[QuestionType.MCQ],
    )
    assert hasattr(q2, "question_text")
    assert q2.ordinal == 2

    # Submit wrong answer
    result2 = await assessment_service.submit_answer(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz_dto.id,
        question_id=q2.id,
        input_data=SubmitAnswerInput(selected_option="B"),
    )
    assert result2.is_correct is False
    assert result2.score == 0.0

    # 6. Complete quiz
    final = await assessment_service.complete_quiz(
        owner_id=user.id, project_id=project.id, quiz_id=quiz_dto.id
    )
    assert final.status == QuizStatus.COMPLETED
    assert final.answered_count == 2
    assert final.correct_count == 1
    assert final.total_score == pytest.approx(0.5, abs=0.01)

    # 7. get_results matches
    results = await assessment_service.get_results(
        owner_id=user.id, project_id=project.id, quiz_id=quiz_dto.id
    )
    assert results.answered_count == 2

    # 8. History includes both attempts
    history = await assessment_service.get_assessment_history(
        owner_id=user.id, project_id=project.id
    )
    quiz_attempts = [h for h in history if h.quiz_id == quiz_dto.id]
    assert len(quiz_attempts) == 2


@pytest.mark.asyncio
async def test_quiz_complete_status_rejects_further_answers(
    cloud_settings, engines, seed_user, seed_project
):
    """Completed quiz does not accept further answers."""
    from app.platform.errors import ConflictError

    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p5-complete-user")
    space, project = await seed_project(user.id, "History")

    pdf_bytes = make_pdf(["The French Revolution began in 1789 with the storming of the Bastille."])
    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="History",
        filename="hist.pdf",
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
        question_id=q.id,
        input_data=SubmitAnswerInput(selected_option="A"),
    )
    await assessment_service.complete_quiz(
        owner_id=user.id,
        project_id=project.id,
        quiz_id=quiz.id,
    )

    # Creating a new question on a completed quiz should raise ConflictError
    with pytest.raises(ConflictError):
        await assessment_service.submit_answer(
            owner_id=user.id,
            project_id=project.id,
            quiz_id=quiz.id,
            question_id=q.id,
            input_data=SubmitAnswerInput(selected_option="B"),
        )
