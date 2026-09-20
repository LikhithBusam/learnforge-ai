"""Assessment ORM models (Phase 5).

Tables owned by Assessment (module-contracts §M.6):
- quizzes          — quiz session with state machine
- questions        — RAG-grounded questions (answer keys stored but never API-exposed)
- question_options — MCQ options (1:N per question)
- question_attempts — immutable answer records
- quiz_evidence    — structured learning evidence for Phase 6 Mastery

SECURITY: correct_option, reference_answer, and rubric live ONLY in the DB
and service layer. They are NEVER serialized into QuestionDto (the learner-
facing schema). This is enforced by using two separate Pydantic models.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.platform.models import Base
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Quiz(Base):
    """Quiz session — state machine: created → active → completed | abandoned."""

    __tablename__ = "quizzes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="created")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, server_default="adaptive")
    target_question_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    answered_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    concept_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    questions: Mapped[list[Question]] = relationship(
        "Question",
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="Question.ordinal.asc()",
        lazy="selectin",
    )
    attempts: Mapped[list[QuestionAttempt]] = relationship(
        "QuestionAttempt",
        back_populates="quiz",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_quizzes_project_owner", "project_id", "owner_id"),
        Index("ix_quizzes_owner_id", "owner_id"),
        Index("ix_quizzes_status", "status"),
        CheckConstraint(
            "status IN ('created', 'active', 'completed', 'abandoned')",
            name="ck_quizzes_status",
        ),
        CheckConstraint(
            "mode IN ('adaptive', 'concept_focus', 'difficulty_focus')",
            name="ck_quizzes_mode",
        ),
        {
            "comment": "Quiz sessions owned by Assessment. RLS: owner_id = app_user_id()",
        },
    )


class Question(Base):
    """RAG-grounded question.

    SECURITY CONTRACT: correct_option, reference_answer, rubric are NEVER
    serialized into QuestionDto. They stay in the service layer only.
    """

    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # concept_id: nullable in Phase 5; Phase 6 Mastery engine connects it
    concept_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    question_type: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Answer key — NEVER exposed via API
    correct_option: Mapped[str | None] = mapped_column(String(4), nullable=True)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    rubric: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Provenance: chunk ids that grounded this question
    source_chunk_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    generation_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    quiz: Mapped[Quiz] = relationship("Quiz", back_populates="questions")
    options: Mapped[list[QuestionOption]] = relationship(
        "QuestionOption",
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionOption.option_id.asc()",
        lazy="selectin",
    )
    attempt: Mapped[QuestionAttempt | None] = relationship(
        "QuestionAttempt",
        back_populates="question",
        uselist=False,
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_questions_quiz_id", "quiz_id"),
        Index("ix_questions_project_owner", "project_id", "owner_id"),
        Index("ix_questions_concept_id", "concept_id"),
        Index("ix_questions_difficulty", "difficulty"),
        CheckConstraint(
            "question_type IN ('mcq', 'open_ended')",
            name="ck_questions_type",
        ),
        CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')",
            name="ck_questions_difficulty",
        ),
        {
            "comment": "RAG-grounded questions. Answer keys never exposed via API. RLS: owner_id = app_user_id()",
        },
    )


class QuestionOption(Base):
    """MCQ option (A, B, C, D) — 1:N per question."""

    __tablename__ = "question_options"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    option_id: Mapped[str] = mapped_column(String(4), nullable=False)  # A, B, C, D
    option_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    question: Mapped[Question] = relationship("Question", back_populates="options")

    __table_args__ = (
        UniqueConstraint("question_id", "option_id", name="uq_question_options_question_option"),
        Index("ix_question_options_question_id", "question_id"),
        Index("ix_question_options_owner_id", "owner_id"),
        {
            "comment": "MCQ answer options. RLS: owner_id = app_user_id()",
        },
    )


class QuestionAttempt(Base):
    """Immutable learner answer record — never overwritten.

    Idempotency: unique constraint on (quiz_id, question_id) means a second
    attempt on the same question is either rejected or replayed via the
    idempotency_key check in the repository.
    """

    __tablename__ = "question_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    learner_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    grading_method: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="deterministic"
    )
    grading_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    grading_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    quiz: Mapped[Quiz] = relationship("Quiz", back_populates="attempts")
    question: Mapped[Question] = relationship("Question", back_populates="attempt")
    evidence: Mapped[QuizEvidence | None] = relationship(
        "QuizEvidence",
        back_populates="attempt",
        uselist=False,
        lazy="selectin",
    )

    __table_args__ = (
        # One attempt per (quiz, question) — enforces immutability
        Index(
            "uq_question_attempts_quiz_question",
            "quiz_id",
            "question_id",
            unique=True,
        ),
        Index("ix_question_attempts_quiz_id", "quiz_id"),
        Index("ix_question_attempts_question_id", "question_id"),
        Index("ix_question_attempts_project_owner", "project_id", "owner_id"),
        Index(
            "uq_question_attempts_idempotency",
            "quiz_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        CheckConstraint(
            "grading_method IN ('deterministic', 'ai', 'pending_review')",
            name="ck_question_attempts_grading_method",
        ),
        {
            "comment": "Immutable learner answer records. RLS: owner_id = app_user_id()",
        },
    )


class QuizEvidence(Base):
    """Structured learning evidence — Phase 6 Mastery feed.

    One row per completed (non-pending_review) question attempt.
    The Phase 6 Mastery engine reads this table as its evidence input.
    This is NOT mastery — it is raw evidence for the future mastery engine.
    """

    __tablename__ = "quiz_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("question_attempts.id", ondelete="CASCADE"), nullable=False
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # concept_id nullable — Phase 5: follows question.concept_id (also nullable)
    concept_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False)  # correct|incorrect|partial
    score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    question_type: Mapped[str] = mapped_column(String(32), nullable=False)
    grading_method: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="assessment")
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    attempt: Mapped[QuestionAttempt] = relationship("QuestionAttempt", back_populates="evidence")

    __table_args__ = (
        Index("uq_quiz_evidence_attempt", "attempt_id", unique=True),
        Index("ix_quiz_evidence_project_owner", "project_id", "owner_id"),
        Index("ix_quiz_evidence_concept_id", "concept_id"),
        Index("ix_quiz_evidence_quiz_id", "quiz_id"),
        CheckConstraint(
            "result IN ('correct', 'incorrect', 'partial')",
            name="ck_quiz_evidence_result",
        ),
        {
            "comment": "Structured learning evidence for Phase 6 Mastery. RLS: owner_id = app_user_id()",
        },
    )
