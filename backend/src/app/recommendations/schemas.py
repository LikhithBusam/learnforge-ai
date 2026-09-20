"""Recommendation DTOs and API schemas (Phase 8).

Defines public data contracts for Recommendations, feedback, and listings.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.recommendations.calculator import (
    ReasonCode,
    RecommendationPriorityLevel,
    RecommendationStatus,
    RecommendationType,
)
from pydantic import BaseModel, ConfigDict, Field


class RecommendationDto(BaseModel):
    """A personalized, evidence-grounded study recommendation."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    project_id: uuid.UUID
    concept_id: uuid.UUID | None = None
    type: RecommendationType
    title: str
    description: str
    priority_score: float = Field(ge=0.0, le=1.0)
    priority_level: RecommendationPriorityLevel
    reason_codes: list[ReasonCode]
    evidence_refs: dict[str, Any]
    action_type: str
    action_target: str | None = None
    status: RecommendationStatus
    algorithm_version: str
    source_growth_event_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RecommendationListDto(BaseModel):
    """Paginated or bounded list of active recommendations for a project."""

    model_config = ConfigDict(frozen=True)

    project_id: uuid.UUID
    count: int = Field(ge=0)
    recommendations: list[RecommendationDto]
    generated_at: datetime


class RecommendationFeedbackInput(BaseModel):
    """Learner feedback on a recommendation."""

    action: str = Field(pattern="^(viewed|started|completed|dismissed)$")
    feedback_text: str | None = Field(default=None, max_length=1000)


class GenerateRecommendationsInput(BaseModel):
    """Payload for on-demand recommendation generation."""

    source_growth_event_id: uuid.UUID | None = None
