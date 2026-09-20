"""Assessment repository — project-scoped data access (module-contracts §M.6).

All queries carry both owner_id and project_id for RLS alignment.
The repository never performs grading logic or policy decisions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.assessment.models import (
    Question,
    QuestionAttempt,
    QuestionOption,
    Quiz,
    QuizEvidence,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class AssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Quiz
    # ------------------------------------------------------------------

    async def create_quiz(
        self,
        *,
        quiz_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        mode: str,
        target_question_count: int,
        concept_ids: list[uuid.UUID] | None,
    ) -> Quiz:
        quiz = Quiz(
            id=quiz_id,
            project_id=project_id,
            owner_id=owner_id,
            status="created",
            mode=mode,
            target_question_count=target_question_count,
            answered_count=0,
            correct_count=0,
            concept_ids=[str(c) for c in concept_ids] if concept_ids else None,
        )
        self._session.add(quiz)
        await self._session.flush()
        return quiz

    async def get_quiz(
        self,
        *,
        quiz_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Quiz | None:
        stmt = select(Quiz).where(
            Quiz.id == quiz_id,
            Quiz.project_id == project_id,
            Quiz.owner_id == owner_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_quizzes(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        limit: int = 20,
    ) -> list[Quiz]:
        stmt = (
            select(Quiz)
            .where(Quiz.project_id == project_id, Quiz.owner_id == owner_id)
            .order_by(Quiz.created_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def update_quiz_status(
        self,
        quiz: Quiz,
        *,
        status: str,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        total_score: float | None = None,
    ) -> Quiz:
        quiz.status = status
        if started_at is not None:
            quiz.started_at = started_at
        if completed_at is not None:
            quiz.completed_at = completed_at
        if total_score is not None:
            quiz.total_score = total_score
        quiz.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return quiz

    async def increment_quiz_answered(
        self,
        quiz: Quiz,
        *,
        correct: bool,
    ) -> Quiz:
        quiz.answered_count += 1
        if correct:
            quiz.correct_count += 1
        quiz.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return quiz

    # ------------------------------------------------------------------
    # Question
    # ------------------------------------------------------------------

    async def save_question(
        self,
        *,
        question_id: uuid.UUID,
        quiz_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        concept_id: uuid.UUID | None,
        question_type: str,
        difficulty: str,
        question_text: str,
        correct_option: str | None,
        reference_answer: str | None,
        rubric: list | None,
        source_chunk_ids: list[str],
        generation_model: str | None,
        ai_request_id: str | None,
        ordinal: int,
        options: list[dict] | None,
    ) -> Question:
        """Persist question + options atomically. answer keys stored, never API-exposed."""
        question = Question(
            id=question_id,
            quiz_id=quiz_id,
            project_id=project_id,
            owner_id=owner_id,
            concept_id=concept_id,
            question_type=question_type,
            difficulty=difficulty,
            question_text=question_text,
            correct_option=correct_option,
            reference_answer=reference_answer,
            rubric=rubric,
            source_chunk_ids=source_chunk_ids,
            generation_model=generation_model,
            ai_request_id=ai_request_id,
            ordinal=ordinal,
        )
        self._session.add(question)
        await self._session.flush()

        if options:
            from app.platform.ids import uuid7

            for opt in options:
                qo = QuestionOption(
                    id=uuid7(),
                    question_id=question_id,
                    owner_id=owner_id,
                    option_id=opt["id"],
                    option_text=opt["text"],
                )
                self._session.add(qo)
            await self._session.flush()

        loaded = await self.get_question(
            question_id=question_id,
            project_id=project_id,
            owner_id=owner_id,
        )
        return loaded or question

    async def get_question(
        self,
        *,
        question_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Question | None:
        stmt = (
            select(Question)
            .options(selectinload(Question.options))
            .where(
                Question.id == question_id,
                Question.project_id == project_id,
                Question.owner_id == owner_id,
            )
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_questions_for_quiz(
        self,
        *,
        quiz_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[Question]:
        stmt = (
            select(Question)
            .options(selectinload(Question.options), selectinload(Question.attempt))
            .where(
                Question.quiz_id == quiz_id,
                Question.project_id == project_id,
                Question.owner_id == owner_id,
            )
            .order_by(Question.ordinal.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def get_unanswered_question(
        self,
        *,
        quiz_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Question | None:
        """Return first question that has no attempt yet."""
        stmt = (
            select(Question)
            .options(selectinload(Question.options))
            .outerjoin(
                QuestionAttempt,
                (QuestionAttempt.question_id == Question.id)
                & (QuestionAttempt.quiz_id == Question.quiz_id),
            )
            .where(
                Question.quiz_id == quiz_id,
                Question.project_id == project_id,
                Question.owner_id == owner_id,
                QuestionAttempt.id.is_(None),
            )
            .order_by(Question.ordinal.asc())
            .limit(1)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Attempts
    # ------------------------------------------------------------------

    async def get_attempt_by_idempotency_key(
        self,
        *,
        quiz_id: uuid.UUID,
        idempotency_key: str,
    ) -> QuestionAttempt | None:
        stmt = select(QuestionAttempt).where(
            QuestionAttempt.quiz_id == quiz_id,
            QuestionAttempt.idempotency_key == idempotency_key,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_attempt_for_question(
        self,
        *,
        quiz_id: uuid.UUID,
        question_id: uuid.UUID,
    ) -> QuestionAttempt | None:
        stmt = select(QuestionAttempt).where(
            QuestionAttempt.quiz_id == quiz_id,
            QuestionAttempt.question_id == question_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def save_attempt(
        self,
        *,
        attempt_id: uuid.UUID,
        quiz_id: uuid.UUID,
        question_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        learner_answer: str,
        is_correct: bool | None,
        score: float | None,
        grading_method: str,
        grading_model: str | None,
        ai_request_id: str | None,
        feedback: str | None,
        grading_detail: dict | None,
        idempotency_key: str | None,
    ) -> QuestionAttempt:
        attempt = QuestionAttempt(
            id=attempt_id,
            quiz_id=quiz_id,
            question_id=question_id,
            project_id=project_id,
            owner_id=owner_id,
            learner_answer=learner_answer,
            is_correct=is_correct,
            score=score,
            grading_method=grading_method,
            grading_model=grading_model,
            ai_request_id=ai_request_id,
            feedback=feedback,
            grading_detail=grading_detail,
            idempotency_key=idempotency_key,
        )
        self._session.add(attempt)
        await self._session.flush()
        return attempt

    async def get_attempts_for_quiz(
        self,
        *,
        quiz_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[QuestionAttempt]:
        stmt = (
            select(QuestionAttempt)
            .where(
                QuestionAttempt.quiz_id == quiz_id,
                QuestionAttempt.project_id == project_id,
                QuestionAttempt.owner_id == owner_id,
            )
            .order_by(QuestionAttempt.created_at.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def get_assessment_history(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        limit: int = 100,
    ) -> list[tuple[QuestionAttempt, Question]]:
        """Return (attempt, question) pairs for the project's history."""
        stmt = (
            select(QuestionAttempt, Question)
            .join(Question, QuestionAttempt.question_id == Question.id)
            .where(
                QuestionAttempt.project_id == project_id,
                QuestionAttempt.owner_id == owner_id,
            )
            .order_by(QuestionAttempt.created_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in res.all()]

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    async def save_evidence(
        self,
        *,
        evidence_id: uuid.UUID,
        attempt_id: uuid.UUID,
        quiz_id: uuid.UUID,
        question_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        concept_id: uuid.UUID | None,
        result: str,
        score: float,
        difficulty: str,
        question_type: str,
        grading_method: str,
        attempted_at: datetime,
    ) -> QuizEvidence:
        ev = QuizEvidence(
            id=evidence_id,
            attempt_id=attempt_id,
            quiz_id=quiz_id,
            question_id=question_id,
            project_id=project_id,
            owner_id=owner_id,
            concept_id=concept_id,
            result=result,
            score=score,
            difficulty=difficulty,
            question_type=question_type,
            grading_method=grading_method,
            source="assessment",
            attempted_at=attempted_at,
        )
        self._session.add(ev)
        await self._session.flush()
        return ev

    async def get_evidence_for_project(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        limit: int = 200,
    ) -> list[QuizEvidence]:
        stmt = (
            select(QuizEvidence)
            .where(
                QuizEvidence.project_id == project_id,
                QuizEvidence.owner_id == owner_id,
            )
            .order_by(QuizEvidence.attempted_at.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def get_evidence(
        self,
        *,
        evidence_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> QuizEvidence | None:
        """Fetch a specific QuizEvidence row under RLS."""
        stmt = select(QuizEvidence).where(
            QuizEvidence.id == evidence_id,
            QuizEvidence.project_id == project_id,
            QuizEvidence.owner_id == owner_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_evidence_for_concept(
        self,
        *,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[QuizEvidence]:
        """Fetch all evidence rows for a concept in chronological order."""
        stmt = (
            select(QuizEvidence)
            .where(
                QuizEvidence.project_id == project_id,
                QuizEvidence.concept_id == concept_id,
                QuizEvidence.owner_id == owner_id,
            )
            .order_by(QuizEvidence.attempted_at.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
