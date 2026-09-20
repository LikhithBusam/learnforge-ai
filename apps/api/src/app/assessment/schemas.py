"""Assessment DTOs — public contracts for the Assessment domain (module-contracts §M.6).

Phase 5 implements:
- AI generation contracts (MCQ + open-ended question, open-ended grading)
- Learner-facing DTOs (answer keys NEVER included)
- Internal service DTOs (contain answer keys — never serialized to HTTP)
- Learning evidence DTOs for Phase 6 Mastery feed

SECURITY: QuestionDto (learner-facing) intentionally omits correct_option,
reference_answer, and rubric. QuestionInternal (service-layer only) carries
the full data. Never serialize QuestionInternal to an HTTP response.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Domain enums
# ---------------------------------------------------------------------------


class QuizStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class QuestionType(str, Enum):
    MCQ = "mcq"
    OPEN_ENDED = "open_ended"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class GradingMethod(str, Enum):
    DETERMINISTIC = "deterministic"
    AI = "ai"
    PENDING_REVIEW = "pending_review"


# ---------------------------------------------------------------------------
# AI Generation Contracts — Pydantic models for structured LLM output
# Validated by AI Gateway before being accepted by the service.
# ---------------------------------------------------------------------------


class MCQOption(BaseModel):
    """One MCQ option — id must be A, B, C, or D."""

    id: Annotated[str, Field(pattern=r"^[A-D]$")]
    text: Annotated[str, Field(min_length=1, max_length=1000)]


class MCQGenerationPayload(BaseModel):
    """Structured output schema for MCQ question generation.

    Validated by the service before persisting. If validation fails,
    the question is NOT stored and generation is retried or skipped.
    """

    question_type: str = "mcq"
    difficulty: Difficulty
    question: Annotated[str, Field(min_length=10, max_length=2000)]
    options: Annotated[list[MCQOption], Field(min_length=4, max_length=4)]
    correct_option: Annotated[str, Field(pattern=r"^[A-D]$")]
    explanation: Annotated[str, Field(min_length=10, max_length=2000)]
    source_chunk_ids: Annotated[list[str], Field(min_length=1)]

    @field_validator("options")
    @classmethod
    def options_must_be_unique(cls, v: list[MCQOption]) -> list[MCQOption]:
        ids = [o.id for o in v]
        if len(ids) != len(set(ids)):
            raise ValueError("MCQ option ids must be unique")
        texts = [o.text.strip().lower() for o in v]
        if len(texts) != len(set(texts)):
            raise ValueError("MCQ option texts must be unique")
        return v

    @model_validator(mode="after")
    def correct_option_must_exist(self) -> MCQGenerationPayload:
        option_ids = {o.id for o in self.options}
        if self.correct_option not in option_ids:
            raise ValueError(
                f"correct_option '{self.correct_option}' is not in options {option_ids}"
            )
        return self


class RubricCriterion(BaseModel):
    """A single rubric criterion for open-ended grading."""

    criterion: Annotated[str, Field(min_length=3, max_length=500)]
    weight: Annotated[float, Field(ge=0.0, le=1.0)]


class OpenEndedGenerationPayload(BaseModel):
    """Structured output schema for open-ended question generation."""

    question_type: str = "open_ended"
    difficulty: Difficulty
    question: Annotated[str, Field(min_length=10, max_length=2000)]
    reference_answer: Annotated[str, Field(min_length=20, max_length=5000)]
    rubric: Annotated[list[RubricCriterion], Field(min_length=1, max_length=8)]
    source_chunk_ids: Annotated[list[str], Field(min_length=1)]

    @model_validator(mode="after")
    def rubric_weights_must_sum_to_one(self) -> OpenEndedGenerationPayload:
        total = sum(c.weight for c in self.rubric)
        if abs(total - 1.0) > 0.05:
            raise ValueError(f"Rubric criterion weights must sum to 1.0 (got {total:.3f})")
        return self


# ---------------------------------------------------------------------------
# AI Grading Contracts — structured open-ended grading output
# ---------------------------------------------------------------------------


class GradingCriterionScore(BaseModel):
    criterion: str
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    feedback: Annotated[str, Field(min_length=1, max_length=1000)]


class OpenEndedGradingPayload(BaseModel):
    """Structured output schema for AI open-ended grading.

    Validated before persisting. Malformed output → pending_review fallback.
    """

    score: Annotated[float, Field(ge=0.0, le=1.0)]
    criteria: list[GradingCriterionScore]
    correct: bool
    feedback: Annotated[str, Field(min_length=1, max_length=3000)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]

    @model_validator(mode="after")
    def correct_must_align_with_score(self) -> OpenEndedGradingPayload:
        # Soft alignment: correct=True requires score >= 0.5
        if self.correct and self.score < 0.5:
            raise ValueError("correct=True but score < 0.5 — inconsistent grading")
        return self


# ---------------------------------------------------------------------------
# API Input DTOs
# ---------------------------------------------------------------------------


class CreateQuizInput(BaseModel):
    target_question_count: int = Field(default=5, ge=1, le=20)
    mode: str = Field(default="adaptive", pattern=r"^(adaptive|concept_focus|difficulty_focus)$")
    concept_ids: list[uuid.UUID] | None = None
    difficulty: Difficulty | None = None  # None = let adaptive policy decide
    question_types: list[QuestionType] = Field(
        default_factory=lambda: [QuestionType.MCQ, QuestionType.OPEN_ENDED]
    )


class SubmitAnswerInput(BaseModel):
    """Learner answer submission. Idempotency key prevents duplicate processing."""

    selected_option: str | None = Field(default=None, description="MCQ: option id (A/B/C/D)")
    selected_option_id: str | None = Field(default=None, description="Alias for selected_option")
    response_text: str | None = Field(default=None, description="Open-ended: free text answer")
    text_response: str | None = Field(default=None, description="Alias for response_text")
    question_id: uuid.UUID | None = Field(default=None, description="Optional question UUID")
    idempotency_key: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def unify_and_validate(self) -> SubmitAnswerInput:
        if not self.selected_option and self.selected_option_id:
            self.selected_option = self.selected_option_id
        if not self.response_text and self.text_response:
            self.response_text = self.text_response
        has_option = self.selected_option is not None
        has_text = self.response_text is not None and bool(self.response_text.strip())
        if not has_option and not has_text:
            raise ValueError("Either selected_option or response_text must be provided")
        return self


# ---------------------------------------------------------------------------
# API Output DTOs — learner-facing (NEVER include answer keys)
# ---------------------------------------------------------------------------


class QuizOptionDto(BaseModel):
    """MCQ option presented to the learner — no correct flag."""

    id: str  # A, B, C, D
    text: str


class QuestionDto(BaseModel):
    """Question presented to the learner.

    SECURITY: Does NOT include correct_option, reference_answer, or rubric.
    """

    id: uuid.UUID
    question_type: QuestionType
    difficulty: Difficulty
    question_text: str
    options: list[QuizOptionDto] | None = None  # MCQ only
    concept_id: uuid.UUID | None = None
    source_chunk_ids: list[str]  # provenance (chunk ids, not content)
    ordinal: int


class QuizDto(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: QuizStatus
    mode: str
    target_question_count: int
    answered_count: int
    correct_count: int
    total_score: float | None = None
    concept_ids: list[uuid.UUID] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class QuizCompleteDto(BaseModel):
    """Returned by get_next_question when the quiz has no more questions."""

    quiz_id: uuid.UUID
    status: QuizStatus
    message: str = "Quiz is complete. Call complete_quiz to finalize."


class CriterionResultDto(BaseModel):
    criterion: str
    score: float
    feedback: str


class EvaluationDetailDto(BaseModel):
    """Structured open-ended grading detail."""

    score: float
    correct: bool
    confidence: float
    criteria: list[CriterionResultDto]


class AnswerResultDto(BaseModel):
    """Result returned after submitting an answer."""

    attempt_id: uuid.UUID
    question_id: uuid.UUID
    is_correct: bool | None  # None when pending_review
    score: float | None
    feedback: str | None
    grading_method: GradingMethod
    evaluation: EvaluationDetailDto | None = None  # open-ended detail
    pending_review: bool = False


class ConceptResultDto(BaseModel):
    concept_id: uuid.UUID | None
    correct_count: int
    total_count: int
    avg_score: float


class QuizResultDto(BaseModel):
    quiz_id: uuid.UUID
    status: QuizStatus
    answered_count: int
    correct_count: int
    total_score: float | None
    per_concept: list[ConceptResultDto]
    graded_pending_review: bool = False


class AssessmentHistoryEntryDto(BaseModel):
    quiz_id: uuid.UUID
    question_id: uuid.UUID
    question_type: QuestionType
    difficulty: Difficulty
    concept_id: uuid.UUID | None
    is_correct: bool | None
    score: float | None
    grading_method: GradingMethod
    answered_at: datetime


# ---------------------------------------------------------------------------
# Internal service DTOs — contain answer keys (NEVER serialize to HTTP)
# ---------------------------------------------------------------------------


class QuestionInternal(BaseModel):
    """Full question data including answer keys — service layer only.

    NEVER expose this model in a router response. Use QuestionDto instead.
    """

    id: uuid.UUID
    quiz_id: uuid.UUID
    project_id: uuid.UUID
    owner_id: uuid.UUID
    concept_id: uuid.UUID | None
    question_type: QuestionType
    difficulty: Difficulty
    question_text: str
    options: list[QuizOptionDto] | None
    # Answer keys — service layer only:
    correct_option: str | None
    reference_answer: str | None
    rubric: list[RubricCriterion] | None
    source_chunk_ids: list[str]
    generation_model: str | None
    ai_request_id: str | None
    ordinal: int
    created_at: datetime

    def to_dto(self) -> QuestionDto:
        """Produce learner-safe DTO — strips all answer key fields."""
        return QuestionDto(
            id=self.id,
            question_type=self.question_type,
            difficulty=self.difficulty,
            question_text=self.question_text,
            options=self.options,
            concept_id=self.concept_id,
            source_chunk_ids=self.source_chunk_ids,
            ordinal=self.ordinal,
        )


# ---------------------------------------------------------------------------
# Learning evidence DTO — Phase 6 Mastery feed
# ---------------------------------------------------------------------------


class LearningEvidenceDto(BaseModel):
    """One row of structured learning evidence produced per completed attempt.

    This is NOT mastery. It is raw evidence the Phase 6 Mastery engine will
    consume. No mastery math is performed here.
    """

    evidence_id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID
    quiz_id: uuid.UUID
    question_id: uuid.UUID
    concept_id: uuid.UUID | None
    result: str  # correct | incorrect | partial
    score: float
    difficulty: Difficulty
    question_type: QuestionType
    grading_method: GradingMethod
    source: str = "assessment"
    attempted_at: datetime
