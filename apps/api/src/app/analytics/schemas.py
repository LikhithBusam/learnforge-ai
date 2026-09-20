"""Pydantic schemas and DTOs for Phase 9 Analytics & Progress Dashboard.

All responses returned to clients or callers must use typed DTOs.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsEventInput(BaseModel):
    """Input payload to record an analytics event."""

    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(..., min_length=2, max_length=100)
    entity_type: str = Field(..., min_length=2, max_length=100)
    entity_id: uuid.UUID | None = None
    occurred_at: datetime.datetime | None = None
    schema_version: int = Field(default=1, ge=1)
    metadata_payload: dict[str, Any] = Field(default_factory=dict)


class AnalyticsEventDto(BaseModel):
    """DTO representing an ingested immutable analytics event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    user_id: uuid.UUID
    project_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None
    occurred_at: datetime.datetime
    ingested_at: datetime.datetime
    schema_version: int
    metadata_payload: dict[str, Any]


class ActivityAnalyticsDto(BaseModel):
    """Learner activity and engagement metrics."""

    project_id: uuid.UUID
    range: str
    active_days: int
    study_events: int
    last_activity_at: datetime.datetime | None = None


class TutorAnalyticsDto(BaseModel):
    """Tutor usage and evidence grounding metrics."""

    project_id: uuid.UUID
    range: str
    conversations: int
    messages: int
    grounded_responses: int
    insufficient_evidence: int
    citations_used: int
    grounded_response_rate: float


class AssessmentAnalyticsDto(BaseModel):
    """Assessment and quiz performance analytics."""

    project_id: uuid.UUID
    range: str
    quizzes_started: int
    quizzes_completed: int
    completion_rate: float
    question_attempts: int
    correct_attempts: int
    incorrect_attempts: int
    pending_review_attempts: int
    accuracy: float


class MasteryAnalyticsDto(BaseModel):
    """Concept mastery distribution and progress counts."""

    project_id: uuid.UUID
    range: str
    developing: int
    progressing: int
    mastered: int
    total_concepts: int


class GrowthAnalyticsDto(BaseModel):
    """Concept growth trends and attention levels."""

    project_id: uuid.UUID
    range: str
    improving: int
    stable: int
    declining: int
    attention_required: int
    total_evaluated: int


class RecommendationsAnalyticsDto(BaseModel):
    """Recommendation lifecycle statistics."""

    project_id: uuid.UUID
    range: str
    generated: int
    pending: int
    viewed: int
    started: int
    completed: int
    dismissed: int
    completion_rate: float


class MaterialsAnalyticsDto(BaseModel):
    """Materials and knowledge base volume metrics."""

    project_id: uuid.UUID
    range: str
    materials_uploaded: int
    documents_processed: int
    ready_documents: int
    failed_documents: int
    total_pages: int
    total_chunks: int


class ProjectAnalyticsOverviewDto(BaseModel):
    """Unified comprehensive learner progress dashboard overview."""

    project_id: uuid.UUID
    range: str
    activity: ActivityAnalyticsDto
    tutor: TutorAnalyticsDto
    assessment: AssessmentAnalyticsDto
    mastery: MasteryAnalyticsDto
    growth: GrowthAnalyticsDto
    recommendations: RecommendationsAnalyticsDto
    materials: MaterialsAnalyticsDto
