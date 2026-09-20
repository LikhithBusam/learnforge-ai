"""Assessment HTTP router (Phase 5).

All routes are project-scoped via /api/v1/projects/{project_id}/...

SECURITY: Answer keys (correct_option, reference_answer, rubric) are NEVER
serialized in any response. QuestionDto (the learner-facing schema) explicitly
excludes these fields. The service layer uses QuestionInternal privately.

Authorization: owner-only via RLS (session_scope binds user_id → policies
enforce owner_id = app_user_id()). Non-owned resources → 404 (ADR-0002).
"""

from __future__ import annotations

import uuid

from app.assessment import service as assessment_service
from app.assessment.schemas import (
    AnswerResultDto,
    AssessmentHistoryEntryDto,
    CreateQuizInput,
    Difficulty,
    QuestionDto,
    QuizCompleteDto,
    QuizDto,
    QuizResultDto,
    SubmitAnswerInput,
)
from app.identity.dependencies import CurrentPrincipal
from app.platform.errors import ValidationError
from fastapi import APIRouter, status

router = APIRouter(
    prefix="/api/v1/projects/{project_id}",
    tags=["assessment"],
)


# ---------------------------------------------------------------------------
# Quiz session lifecycle
# ---------------------------------------------------------------------------


@router.post(
    "/quizzes",
    response_model=QuizDto,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new quiz session",
    description=(
        "Creates a quiz session in CREATED state. Questions are generated "
        "lazily on the first get_next_question call. "
        "Answer keys are never returned."
    ),
)
async def create_quiz(
    project_id: uuid.UUID,
    body: CreateQuizInput,
    principal: CurrentPrincipal,
) -> QuizDto:
    owner_id = uuid.UUID(principal.user_id)
    return await assessment_service.create_quiz(
        owner_id=owner_id,
        project_id=project_id,
        target_question_count=body.target_question_count,
        mode=body.mode,
        concept_ids=body.concept_ids,
        difficulty=body.difficulty,
        question_types=body.question_types,
    )


@router.get(
    "/quizzes/{quiz_id}",
    response_model=QuizDto,
    summary="Get quiz session status",
)
async def get_quiz(
    project_id: uuid.UUID,
    quiz_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> QuizDto:
    owner_id = uuid.UUID(principal.user_id)
    return await assessment_service.get_quiz(
        owner_id=owner_id,
        project_id=project_id,
        quiz_id=quiz_id,
    )


@router.get(
    "/quizzes/{quiz_id}/next",
    response_model=QuestionDto | QuizCompleteDto,
    summary="Get the next adaptive question",
    description=(
        "Returns the next unanswered question, generating one via RAG if needed. "
        "Activates the quiz on first call. "
        "Returns QuizCompleteDto when all target questions are answered. "
        "NEVER includes the correct answer or grading rubric."
    ),
)
async def get_next_question(
    project_id: uuid.UUID,
    quiz_id: uuid.UUID,
    principal: CurrentPrincipal,
    difficulty: Difficulty | None = None,
) -> QuestionDto | QuizCompleteDto:
    owner_id = uuid.UUID(principal.user_id)
    return await assessment_service.get_next_question(
        owner_id=owner_id,
        project_id=project_id,
        quiz_id=quiz_id,
        target_difficulty=difficulty,
    )


@router.post(
    "/quizzes/{quiz_id}/answers",
    response_model=AnswerResultDto,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an answer",
    description=(
        "Submit a learner's answer to a question. "
        "MCQ grading is deterministic (no AI). "
        "Open-ended grading uses the AI Gateway. "
        "Idempotent when idempotency_key is supplied."
    ),
)
async def submit_answer(
    project_id: uuid.UUID,
    quiz_id: uuid.UUID,
    body: SubmitAnswerInput,
    principal: CurrentPrincipal,
    question_id: uuid.UUID | None = None,
) -> AnswerResultDto:
    owner_id = uuid.UUID(principal.user_id)
    target_qid = question_id or body.question_id
    if target_qid is None:
        raise ValidationError("question_id must be provided in query parameters or request body")
    return await assessment_service.submit_answer(
        owner_id=owner_id,
        project_id=project_id,
        quiz_id=quiz_id,
        question_id=target_qid,
        input_data=body,
    )


@router.post(
    "/quizzes/{quiz_id}/complete",
    response_model=QuizResultDto,
    summary="Complete the quiz session",
    description="Finalizes the quiz (ACTIVE → COMPLETED) and returns summary results.",
)
async def complete_quiz(
    project_id: uuid.UUID,
    quiz_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> QuizResultDto:
    owner_id = uuid.UUID(principal.user_id)
    return await assessment_service.complete_quiz(
        owner_id=owner_id,
        project_id=project_id,
        quiz_id=quiz_id,
    )


@router.get(
    "/quizzes/{quiz_id}/results",
    response_model=QuizResultDto,
    summary="Get quiz results",
)
async def get_results(
    project_id: uuid.UUID,
    quiz_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> QuizResultDto:
    owner_id = uuid.UUID(principal.user_id)
    return await assessment_service.get_results(
        owner_id=owner_id,
        project_id=project_id,
        quiz_id=quiz_id,
    )


@router.get(
    "/assessment/history",
    response_model=list[AssessmentHistoryEntryDto],
    summary="Get assessment history for this project",
)
async def get_assessment_history(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    limit: int = 100,
) -> list[AssessmentHistoryEntryDto]:
    owner_id = uuid.UUID(principal.user_id)
    return await assessment_service.get_assessment_history(
        owner_id=owner_id,
        project_id=project_id,
        limit=min(limit, 200),
    )
