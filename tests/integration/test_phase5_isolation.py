"""Phase 5 Integration Tests — User/Project Isolation.

Verifies:
1. User A cannot see User B's quizzes or questions
2. User A + Project A cannot access User A's quiz under Project B
3. User B cannot submit answers to User A's quiz
"""

from __future__ import annotations

import io

import fitz
import pytest
from app.assessment import service as assessment_service
from app.assessment.schemas import QuestionType, SubmitAnswerInput
from app.knowledge import service as knowledge_service
from app.materials import service as materials_service
from app.platform.errors import NotFound
from app.platform.storage import get_storage, init_storage


def make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


async def _seed_project_with_material(user, project, storage):
    """Helper: ingest a small document so questions can be generated."""
    pdf = make_pdf("Isolation test material: circuits use resistance to limit current flow.")
    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="Isolation",
        filename="iso.pdf",
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


@pytest.mark.asyncio
async def test_user_b_cannot_see_user_a_quiz(cloud_settings, engines, seed_user, seed_project):
    """User B cannot read User A's quiz — gets NotFound (ADR-0002)."""
    init_storage(cloud_settings)
    storage = get_storage()

    user_a = await seed_user("p5-iso-user-a")
    user_b = await seed_user("p5-iso-user-b")
    _, project_a = await seed_project(user_a.id, "Project A")
    _, project_b = await seed_project(user_b.id, "Project B")

    await _seed_project_with_material(user_a, project_a, storage)

    # User A creates a quiz
    quiz = await assessment_service.create_quiz(
        owner_id=user_a.id,
        project_id=project_a.id,
        target_question_count=1,
    )

    # User B tries to access User A's quiz — should get NotFound
    with pytest.raises(NotFound):
        await assessment_service.get_quiz(
            owner_id=user_b.id,
            project_id=project_a.id,  # wrong project for user_b
            quiz_id=quiz.id,
        )

    # User B tries using their own project_id — also NotFound
    with pytest.raises(NotFound):
        await assessment_service.get_quiz(
            owner_id=user_b.id,
            project_id=project_b.id,
            quiz_id=quiz.id,
        )


@pytest.mark.asyncio
async def test_user_a_cannot_access_quiz_under_wrong_project(
    cloud_settings, engines, seed_user, seed_project
):
    """User A cannot access their own quiz under a different project_id."""
    init_storage(cloud_settings)
    storage = get_storage()

    user_a = await seed_user("p5-iso-cross-a")
    _, project_a = await seed_project(user_a.id, "Project A")
    _, project_a2 = await seed_project(user_a.id, "Project A2")

    await _seed_project_with_material(user_a, project_a, storage)

    quiz = await assessment_service.create_quiz(
        owner_id=user_a.id,
        project_id=project_a.id,
        target_question_count=1,
    )

    # Same user, different project — should get NotFound
    with pytest.raises(NotFound):
        await assessment_service.get_quiz(
            owner_id=user_a.id,
            project_id=project_a2.id,
            quiz_id=quiz.id,
        )


@pytest.mark.asyncio
async def test_user_b_cannot_submit_answers_to_user_a_quiz(
    cloud_settings, engines, seed_user, seed_project
):
    """User B cannot submit answers to User A's quiz."""
    init_storage(cloud_settings)
    storage = get_storage()

    user_a = await seed_user("p5-iso-submit-a")
    user_b = await seed_user("p5-iso-submit-b")
    _, project_a = await seed_project(user_a.id, "Project A Subnet")
    _, project_b = await seed_project(user_b.id, "Project B Subnet")

    await _seed_project_with_material(user_a, project_a, storage)

    quiz = await assessment_service.create_quiz(
        owner_id=user_a.id,
        project_id=project_a.id,
        target_question_count=1,
        question_types=[QuestionType.MCQ],
    )
    q = await assessment_service.get_next_question(
        owner_id=user_a.id,
        project_id=project_a.id,
        quiz_id=quiz.id,
    )
    assert hasattr(q, "id"), "Expected QuestionDto"

    # User B tries to submit to User A's quiz
    with pytest.raises((NotFound, Exception)):
        await assessment_service.submit_answer(
            owner_id=user_b.id,
            project_id=project_b.id,
            quiz_id=quiz.id,
            question_id=q.id,  # type: ignore[union-attr]
            input_data=SubmitAnswerInput(selected_option="A"),
        )


@pytest.mark.asyncio
async def test_assessment_history_is_user_scoped(cloud_settings, engines, seed_user, seed_project):
    """Assessment history only shows the calling user's quiz attempts."""
    init_storage(cloud_settings)
    storage = get_storage()

    user_a = await seed_user("p5-hist-a")
    user_b = await seed_user("p5-hist-b")
    _, project_a = await seed_project(user_a.id, "History A")
    _, project_b = await seed_project(user_b.id, "History B")

    await _seed_project_with_material(user_a, project_a, storage)
    await _seed_project_with_material(user_b, project_b, storage)

    # Each user completes one quiz
    for user, project in [(user_a, project_a), (user_b, project_b)]:
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
        if hasattr(q, "id"):
            await assessment_service.submit_answer(
                owner_id=user.id,
                project_id=project.id,
                quiz_id=quiz.id,
                question_id=q.id,  # type: ignore[union-attr]
                input_data=SubmitAnswerInput(selected_option="A"),
            )

    # User A history should only contain User A's attempts
    history_a = await assessment_service.get_assessment_history(
        owner_id=user_a.id,
        project_id=project_a.id,
    )
    quiz_ids_a = {h.quiz_id for h in history_a}

    # User B history should only contain User B's attempts
    history_b = await assessment_service.get_assessment_history(
        owner_id=user_b.id,
        project_id=project_b.id,
    )
    quiz_ids_b = {h.quiz_id for h in history_b}

    # No overlap between user histories
    assert quiz_ids_a.isdisjoint(quiz_ids_b)
