"""Assessment service — the only public surface of this module (module-contracts §M.6).

Architecture:
    API Router → AssessmentService (this file) → Repository, Generation, Grading
    AssessmentService → KnowledgeService (via retrieve_evidence facade)
    AssessmentService → AIGateway (via generation.py and grading.py only)

BOUNDARY RULES (enforced by check_boundaries.py):
- This module imports knowledge.service and knowledge.schemas (facade, allowed)
- This module imports ai.gateway via generation.py and grading.py (allowed)
- This module does NOT import tutor, mastery, growth, analytics, or admin modules
- This module does NOT access knowledge, tutor, or materials tables directly

Assessment State Machine:
    CREATED → ACTIVE (on first get_next_question)
    ACTIVE  → COMPLETED (on complete_quiz)
    ACTIVE  → ABANDONED (future: timeout)
    COMPLETED → (terminal — no further answers accepted)

Learning Evidence:
    Every non-pending_review attempt produces a QuizEvidence row.
    This is NOT mastery. It feeds Phase 6 Mastery.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.assessment import generation, grading
from app.assessment.models import Question, Quiz
from app.assessment.repository import AssessmentRepository
from app.assessment.schemas import (
    AnswerResultDto,
    AssessmentHistoryEntryDto,
    ConceptResultDto,
    CriterionResultDto,
    Difficulty,
    EvaluationDetailDto,
    GradingMethod,
    LearningEvidenceDto,
    QuestionDto,
    QuestionInternal,
    QuestionType,
    QuizCompleteDto,
    QuizDto,
    QuizOptionDto,
    QuizResultDto,
    QuizStatus,
    SubmitAnswerInput,
)
from app.knowledge import service as knowledge_service
from app.knowledge.schemas import QueryInput
from app.platform import db as database
from app.platform.config import get_settings
from app.platform.errors import ConflictError, NotFound, ValidationError
from app.platform.ids import uuid7
from app.platform.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _quiz_to_dto(quiz: Quiz) -> QuizDto:
    return QuizDto(
        id=quiz.id,
        project_id=quiz.project_id,
        status=QuizStatus(quiz.status),
        mode=quiz.mode,
        target_question_count=quiz.target_question_count,
        answered_count=quiz.answered_count,
        correct_count=quiz.correct_count,
        total_score=quiz.total_score,
        concept_ids=([uuid.UUID(c) for c in quiz.concept_ids] if quiz.concept_ids else None),
        started_at=quiz.started_at,
        completed_at=quiz.completed_at,
        created_at=quiz.created_at,
    )


def _question_to_internal(q: Question) -> QuestionInternal:
    options = None
    if q.options:
        options = [QuizOptionDto(id=o.option_id, text=o.option_text) for o in q.options]
    rubric = None
    if q.rubric:
        from app.assessment.schemas import RubricCriterion

        rubric = [RubricCriterion(**r) for r in q.rubric]
    return QuestionInternal(
        id=q.id,
        quiz_id=q.quiz_id,
        project_id=q.project_id,
        owner_id=q.owner_id,
        concept_id=q.concept_id,
        question_type=QuestionType(q.question_type),
        difficulty=Difficulty(q.difficulty),
        question_text=q.question_text,
        options=options,
        correct_option=q.correct_option,
        reference_answer=q.reference_answer,
        rubric=rubric,
        source_chunk_ids=q.source_chunk_ids or [],
        generation_model=q.generation_model,
        ai_request_id=q.ai_request_id,
        ordinal=q.ordinal,
        created_at=q.created_at,
    )


async def _generate_and_save_question(
    *,
    repo: AssessmentRepository,
    quiz_id: uuid.UUID,
    project_id: uuid.UUID,
    owner_id: uuid.UUID,
    difficulty: str,
    question_type: str,
    ordinal: int,
) -> Question:
    """Retrieve evidence → generate question → validate → persist.

    Uses KnowledgeService.retrieve_evidence (no duplicate retrieval code here).
    """
    query = QueryInput(
        raw_query=(
            f"Generate a {difficulty} level question to test understanding " f"of key concepts"
        )
    )
    evidence = await knowledge_service.retrieve_evidence(
        project_id=project_id,
        owner_id=owner_id,
        query_input=query,
    )

    if not evidence.hits:
        raise ValidationError(
            "No evidence available to generate questions. "
            "Ensure project materials are processed and ready."
        )

    if question_type == "mcq":
        data = await generation.generate_mcq_question(
            evidence=evidence,
            project_id=project_id,
            owner_id=owner_id,
            difficulty=difficulty,
            ordinal=ordinal,
        )
    else:
        data = await generation.generate_open_ended_question(
            evidence=evidence,
            project_id=project_id,
            owner_id=owner_id,
            difficulty=difficulty,
            ordinal=ordinal,
        )

    question = await repo.save_question(
        question_id=uuid7(),
        quiz_id=quiz_id,
        project_id=project_id,
        owner_id=owner_id,
        concept_id=None,  # Phase 5: no concept graph yet
        question_type=data["question_type"],
        difficulty=data["difficulty"],
        question_text=data["question_text"],
        correct_option=data.get("correct_option"),
        reference_answer=data.get("reference_answer"),
        rubric=data.get("rubric"),
        source_chunk_ids=data["source_chunk_ids"],
        generation_model=data.get("generation_model"),
        ai_request_id=data.get("ai_request_id"),
        ordinal=ordinal,
        options=data.get("options"),
    )
    return question


def _pick_difficulty(settings, difficulty_hint: Difficulty | None) -> str:
    """Pick a difficulty for the next question (simple round-robin when no hint)."""
    if difficulty_hint:
        return difficulty_hint.value
    return "medium"


def _pick_question_type(question_types: list[QuestionType], ordinal: int) -> str:
    """Alternate question types so both MCQ and open-ended appear."""
    if not question_types:
        return "mcq"
    return question_types[(ordinal - 1) % len(question_types)].value


# ---------------------------------------------------------------------------
# Public service interface
# ---------------------------------------------------------------------------


async def create_quiz(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    target_question_count: int = 5,
    mode: str = "adaptive",
    concept_ids: list[uuid.UUID] | None = None,
    difficulty: Difficulty | None = None,
    question_types: list[QuestionType] | None = None,
) -> QuizDto:
    """Create a new quiz session in CREATED state.

    Does NOT generate questions eagerly — questions are generated lazily
    on each get_next_question call (adaptive, fresh evidence per question).
    """
    settings = get_settings()
    max_q = settings.ASSESSMENT_MAX_QUESTION_COUNT
    if target_question_count > max_q:
        raise ValidationError(f"target_question_count exceeds maximum of {max_q}")

    quiz_id = uuid7()
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = AssessmentRepository(session)
        quiz = await repo.create_quiz(
            quiz_id=quiz_id,
            project_id=project_id,
            owner_id=owner_id,
            mode=mode,
            target_question_count=target_question_count,
            concept_ids=concept_ids,
        )
        return _quiz_to_dto(quiz)


async def get_quiz(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    quiz_id: uuid.UUID,
) -> QuizDto:
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = AssessmentRepository(session)
        quiz = await repo.get_quiz(quiz_id=quiz_id, project_id=project_id, owner_id=owner_id)
        if quiz is None:
            raise NotFound("Quiz not found")
        return _quiz_to_dto(quiz)


async def get_next_question(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    quiz_id: uuid.UUID,
    target_difficulty: Difficulty | None = None,
    question_types: list[QuestionType] | None = None,
) -> QuestionDto | QuizCompleteDto:
    """Return the next unanswered question, generating one if needed.

    State transition: CREATED → ACTIVE on first call.
    Returns QuizCompleteDto when all target questions are answered.
    """
    settings = get_settings()
    question_types = question_types or [QuestionType.MCQ, QuestionType.OPEN_ENDED]

    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = AssessmentRepository(session)
        quiz = await repo.get_quiz(quiz_id=quiz_id, project_id=project_id, owner_id=owner_id)
        if quiz is None:
            raise NotFound("Quiz not found")

        if quiz.status == "completed":
            return QuizCompleteDto(
                quiz_id=quiz_id,
                status=QuizStatus.COMPLETED,
                message="Quiz is already complete.",
            )
        if quiz.status == "abandoned":
            return QuizCompleteDto(
                quiz_id=quiz_id,
                status=QuizStatus.ABANDONED,
                message="Quiz was abandoned.",
            )

        # Check if target question count reached
        questions = await repo.get_questions_for_quiz(
            quiz_id=quiz_id, project_id=project_id, owner_id=owner_id
        )
        answered = [q for q in questions if q.attempt is not None]

        if len(answered) >= quiz.target_question_count:
            return QuizCompleteDto(
                quiz_id=quiz_id,
                status=QuizStatus.ACTIVE,
                message="All questions answered. Call complete_quiz to finalize.",
            )

        # Find next unanswered question
        unanswered = await repo.get_unanswered_question(
            quiz_id=quiz_id, project_id=project_id, owner_id=owner_id
        )

        if unanswered is None:
            # Generate the next question
            ordinal = len(questions) + 1
            difficulty_str = _pick_difficulty(settings, target_difficulty)
            qtype_str = _pick_question_type(question_types, ordinal)

            unanswered = await _generate_and_save_question(
                repo=repo,
                quiz_id=quiz_id,
                project_id=project_id,
                owner_id=owner_id,
                difficulty=difficulty_str,
                question_type=qtype_str,
                ordinal=ordinal,
            )

        # Activate quiz on first question presentation
        if quiz.status == "created":
            await repo.update_quiz_status(
                quiz,
                status="active",
                started_at=datetime.now(timezone.utc),
            )

        internal = _question_to_internal(unanswered)
        return internal.to_dto()  # strips answer keys


async def submit_answer(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    quiz_id: uuid.UUID,
    question_id: uuid.UUID,
    input_data: SubmitAnswerInput,
) -> AnswerResultDto:
    """Submit an answer for a question.

    Idempotency: if idempotency_key already seen → replay result, no re-grade.
    MCQ grading: deterministic (no AI).
    Open-ended grading: AI Gateway → pending_review fallback.
    Learning evidence: emitted on non-pending_review results.
    """
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = AssessmentRepository(session)

        quiz = await repo.get_quiz(quiz_id=quiz_id, project_id=project_id, owner_id=owner_id)
        if quiz is None:
            raise NotFound("Quiz not found")
        if quiz.status == "completed":
            raise ConflictError("Quiz is already completed. Cannot submit more answers.")
        if quiz.status == "created":
            raise ConflictError("Quiz not yet active. Call get_next_question first.")

        # Idempotency check
        if input_data.idempotency_key:
            existing = await repo.get_attempt_by_idempotency_key(
                quiz_id=quiz_id, idempotency_key=input_data.idempotency_key
            )
            if existing is not None:
                logger.info(
                    "submit_answer_idempotent_replay",
                    extra={"details": {"attempt_id": str(existing.id)}},
                )
                return _attempt_to_dto(existing)

        # Validate question belongs to this quiz
        question = await repo.get_question(
            question_id=question_id, project_id=project_id, owner_id=owner_id
        )
        if question is None or question.quiz_id != quiz_id:
            raise NotFound("Question not found in this quiz")

        # Check for existing attempt (prevent duplicate — unique constraint backup)
        existing_attempt = await repo.get_attempt_for_question(
            quiz_id=quiz_id, question_id=question_id
        )
        if existing_attempt is not None:
            return _attempt_to_dto(existing_attempt)

        internal = _question_to_internal(question)

        # Grade the answer
        if internal.question_type == QuestionType.MCQ:
            if input_data.selected_option is None:
                raise ValidationError("MCQ answer requires selected_option")
            grade = grading.grade_mcq(
                selected_option=input_data.selected_option,
                correct_option=internal.correct_option or "",
                explanation=None,
            )
            learner_answer = input_data.selected_option
        else:
            # Open-ended
            if not input_data.response_text or not input_data.response_text.strip():
                raise ValidationError("Open-ended answer requires response_text")
            # Retrieve evidence for grading context (not strictly required but improves grade quality)
            evidence = None
            try:
                evidence = await knowledge_service.retrieve_evidence(
                    project_id=project_id,
                    owner_id=owner_id,
                    query_input=QueryInput(raw_query=internal.question_text),
                )
            except Exception:  # noqa: BLE001
                pass  # Evidence fetch failure → grade without it (degraded path)

            grade = await grading.grade_open_ended(
                question_text=internal.question_text,
                reference_answer=internal.reference_answer or "",
                rubric=([r.model_dump() for r in internal.rubric] if internal.rubric else []),
                learner_answer=input_data.response_text,
                evidence=evidence,
            )
            learner_answer = input_data.response_text

        attempt_id = uuid7()
        attempt = await repo.save_attempt(
            attempt_id=attempt_id,
            quiz_id=quiz_id,
            question_id=question_id,
            project_id=project_id,
            owner_id=owner_id,
            learner_answer=learner_answer,
            is_correct=grade.is_correct,
            score=grade.score,
            grading_method=grade.grading_method,
            grading_model=grade.grading_model,
            ai_request_id=grade.ai_request_id,
            feedback=grade.feedback,
            grading_detail=grade.grading_detail,
            idempotency_key=input_data.idempotency_key,
        )

        # Update quiz counters
        await repo.increment_quiz_answered(quiz, correct=bool(grade.is_correct))

        # Emit learning evidence (non-pending_review only)
        if not grade.pending_review:
            result_str = "correct" if grade.is_correct else "incorrect"
            await repo.save_evidence(
                evidence_id=uuid7(),
                attempt_id=attempt_id,
                quiz_id=quiz_id,
                question_id=question_id,
                project_id=project_id,
                owner_id=owner_id,
                concept_id=question.concept_id,
                result=result_str,
                score=grade.score or 0.0,
                difficulty=question.difficulty,
                question_type=question.question_type,
                grading_method=grade.grading_method,
                attempted_at=datetime.now(timezone.utc),
            )

        return _attempt_to_dto(attempt)


async def complete_quiz(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    quiz_id: uuid.UUID,
) -> QuizResultDto:
    """Finalize a quiz session. Moves status ACTIVE → COMPLETED."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = AssessmentRepository(session)
        quiz = await repo.get_quiz(quiz_id=quiz_id, project_id=project_id, owner_id=owner_id)
        if quiz is None:
            raise NotFound("Quiz not found")
        if quiz.status == "completed":
            # Idempotent — return current result
            return await _build_result(repo, quiz, project_id, owner_id)
        if quiz.status not in ("active", "created"):
            raise ConflictError(f"Cannot complete quiz in status '{quiz.status}'")

        attempts = await repo.get_attempts_for_quiz(
            quiz_id=quiz_id, project_id=project_id, owner_id=owner_id
        )
        total_score = (
            sum(a.score for a in attempts if a.score is not None) / max(len(attempts), 1)
            if attempts
            else None
        )
        await repo.update_quiz_status(
            quiz,
            status="completed",
            completed_at=datetime.now(timezone.utc),
            total_score=total_score,
        )

        return await _build_result(repo, quiz, project_id, owner_id)


async def get_results(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    quiz_id: uuid.UUID,
) -> QuizResultDto:
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = AssessmentRepository(session)
        quiz = await repo.get_quiz(quiz_id=quiz_id, project_id=project_id, owner_id=owner_id)
        if quiz is None:
            raise NotFound("Quiz not found")
        return await _build_result(repo, quiz, project_id, owner_id)


async def _build_result(
    repo: AssessmentRepository,
    quiz: Quiz,
    project_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> QuizResultDto:
    attempts = await repo.get_attempts_for_quiz(
        quiz_id=quiz.id, project_id=project_id, owner_id=owner_id
    )
    questions = await repo.get_questions_for_quiz(
        quiz_id=quiz.id, project_id=project_id, owner_id=owner_id
    )
    q_by_id = {q.id: q for q in questions}

    pending_any = any(a.grading_method == "pending_review" for a in attempts)
    total_score = (
        sum(a.score for a in attempts if a.score is not None) / max(len(attempts), 1)
        if attempts
        else None
    )

    # Build per-concept summary
    concept_map: dict[uuid.UUID | None, dict] = {}
    for attempt in attempts:
        q = q_by_id.get(attempt.question_id)
        cid = q.concept_id if q else None
        if cid not in concept_map:
            concept_map[cid] = {"correct": 0, "total": 0, "scores": []}
        concept_map[cid]["total"] += 1
        if attempt.is_correct:
            concept_map[cid]["correct"] += 1
        if attempt.score is not None:
            concept_map[cid]["scores"].append(attempt.score)

    per_concept = [
        ConceptResultDto(
            concept_id=cid,
            correct_count=v["correct"],
            total_count=v["total"],
            avg_score=(sum(v["scores"]) / len(v["scores"]) if v["scores"] else 0.0),
        )
        for cid, v in concept_map.items()
    ]

    return QuizResultDto(
        quiz_id=quiz.id,
        status=QuizStatus(quiz.status),
        answered_count=quiz.answered_count,
        correct_count=quiz.correct_count,
        total_score=total_score,
        per_concept=per_concept,
        graded_pending_review=pending_any,
    )


async def get_assessment_history(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    limit: int = 100,
) -> list[AssessmentHistoryEntryDto]:
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = AssessmentRepository(session)
        rows = await repo.get_assessment_history(
            project_id=project_id, owner_id=owner_id, limit=limit
        )
        return [
            AssessmentHistoryEntryDto(
                quiz_id=attempt.quiz_id,
                question_id=attempt.question_id,
                question_type=QuestionType(question.question_type),
                difficulty=Difficulty(question.difficulty),
                concept_id=question.concept_id,
                is_correct=attempt.is_correct,
                score=attempt.score,
                grading_method=GradingMethod(attempt.grading_method),
                answered_at=attempt.created_at,
            )
            for attempt, question in rows
        ]


def _attempt_to_dto(attempt) -> AnswerResultDto:
    """Convert a QuestionAttempt ORM to AnswerResultDto."""
    evaluation = None
    if attempt.grading_detail and attempt.grading_method == "ai":
        criteria = [
            CriterionResultDto(
                criterion=c["criterion"],
                score=c["score"],
                feedback=c["feedback"],
            )
            for c in attempt.grading_detail.get("criteria", [])
        ]
        evaluation = EvaluationDetailDto(
            score=attempt.score or 0.0,
            correct=bool(attempt.is_correct),
            confidence=attempt.grading_detail.get("confidence", 0.0),
            criteria=criteria,
        )
    return AnswerResultDto(
        attempt_id=attempt.id,
        question_id=attempt.question_id,
        is_correct=attempt.is_correct,
        score=attempt.score,
        feedback=attempt.feedback,
        grading_method=GradingMethod(attempt.grading_method),
        evaluation=evaluation,
        pending_review=attempt.grading_method == "pending_review",
    )


def _evidence_to_dto(ev) -> LearningEvidenceDto:
    return LearningEvidenceDto(
        evidence_id=ev.id,
        user_id=ev.owner_id,
        project_id=ev.project_id,
        quiz_id=ev.quiz_id,
        question_id=ev.question_id,
        concept_id=ev.concept_id,
        result=ev.result,
        score=ev.score,
        difficulty=Difficulty(ev.difficulty),
        question_type=QuestionType(ev.question_type),
        grading_method=GradingMethod(ev.grading_method),
        source=ev.source,
        attempted_at=ev.attempted_at,
    )


async def get_quiz_evidence(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    evidence_id: uuid.UUID,
) -> LearningEvidenceDto | None:
    """Retrieve structured learning evidence by ID (facade for Phase 6 Mastery)."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = AssessmentRepository(session)
        ev = await repo.get_evidence(
            evidence_id=evidence_id, project_id=project_id, owner_id=owner_id
        )
        if ev is None:
            return None
        return _evidence_to_dto(ev)


async def list_evidence_for_concept(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
) -> list[LearningEvidenceDto]:
    """Retrieve all evidence rows for a concept in chronological order (facade for Phase 6 Mastery recompute)."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = AssessmentRepository(session)
        evidence_list = await repo.list_evidence_for_concept(
            project_id=project_id, concept_id=concept_id, owner_id=owner_id
        )
        return [_evidence_to_dto(e) for e in evidence_list]
