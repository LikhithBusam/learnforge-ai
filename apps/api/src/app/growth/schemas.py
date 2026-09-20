"""Growth DTOs and API schemas (Phase 7).

Defines the public data contracts for Concept Growth trajectories,
attention classifications, and project summaries (module-contracts §M.8).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.growth.calculator import AttentionLevel, GrowthTrend
from pydantic import BaseModel, ConfigDict, Field


class ConceptGrowthDto(BaseModel):
    """Current growth and trajectory state for a (project, concept) pair."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    project_id: uuid.UUID
    concept_id: uuid.UUID
    current_mastery: float = Field(ge=0.0, le=1.0)
    previous_mastery: float | None = Field(default=None, ge=0.0, le=1.0)
    short_term_delta: float
    long_term_delta: float
    trend: GrowthTrend
    short_term_trend: GrowthTrend
    long_term_trend: GrowthTrend
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_count: int = Field(ge=0)
    attention_score: float = Field(ge=0.0, le=1.0)
    attention_level: AttentionLevel
    attention_required: bool
    recent_failure_rate: float = Field(ge=0.0, le=1.0)
    algorithm_version: str
    last_evaluated_at: datetime
    updated_at: datetime


class GrowthEventDto(BaseModel):
    """Immutable audit event recorded when a concept's growth trajectory is evaluated."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    project_id: uuid.UUID
    concept_id: uuid.UUID
    source_mastery_event_id: uuid.UUID | None = None
    previous_trend: GrowthTrend | None = None
    new_trend: GrowthTrend
    previous_attention_score: float | None = None
    new_attention_score: float
    previous_mastery: float | None = None
    new_mastery: float
    short_term_delta: float
    long_term_delta: float
    algorithm_version: str
    occurred_at: datetime


class ProjectGrowthSummaryDto(BaseModel):
    """Aggregate project-level growth summary across all concepts."""

    model_config = ConfigDict(frozen=True)

    project_id: uuid.UUID
    concept_count: int = Field(ge=0)
    improving_count: int = Field(ge=0)
    stable_count: int = Field(ge=0)
    declining_count: int = Field(ge=0)
    insufficient_data_count: int = Field(ge=0)
    attention_count: int = Field(ge=0)
    attention_concepts: list[uuid.UUID]
    average_mastery: float = Field(ge=0.0, le=1.0)
    average_confidence: float = Field(ge=0.0, le=1.0)
    concepts: list[ConceptGrowthDto]
    generated_at: datetime


class EvaluateGrowthInput(BaseModel):
    """Payload for manual or event-driven growth evaluation."""

    source_mastery_event_id: uuid.UUID | None = None
    occurred_at: datetime | None = None
