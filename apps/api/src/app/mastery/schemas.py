"""Mastery DTOs and API schemas (Phase 6).

Strictly defines the public DTOs and validation contracts for Concept Mastery,
following module-contracts §M.7 and domain-events §2.5.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.mastery.calculator import MasteryCategory
from pydantic import BaseModel, ConfigDict, Field


class MasteryStateDto(BaseModel):
    """Current mastery state for a (project, concept) pair."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    project_id: uuid.UUID
    concept_id: uuid.UUID
    mastery_probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    category: MasteryCategory
    evidence_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    incorrect_count: int = Field(ge=0)
    partial_count: int = Field(ge=0)
    consecutive_correct: int = Field(ge=0)
    last_evidence_at: datetime | None = None
    algorithm_version: str
    updated_at: datetime


class MasteryEventDto(BaseModel):
    """Immutable audit trail entry of a single mastery update step."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    project_id: uuid.UUID
    concept_id: uuid.UUID
    source: str
    source_id: uuid.UUID
    mastery_before: float = Field(ge=0.0, le=1.0)
    mastery_after: float = Field(ge=0.0, le=1.0)
    confidence_before: float = Field(ge=0.0, le=1.0)
    confidence_after: float = Field(ge=0.0, le=1.0)
    result: str
    score: float = Field(ge=0.0, le=1.0)
    difficulty: str
    algorithm_version: str
    occurred_at: datetime


class MasterySummaryDto(BaseModel):
    """Aggregated project-level mastery summary for dashboards and tools."""

    model_config = ConfigDict(frozen=True)

    project_id: uuid.UUID
    concepts: list[MasteryStateDto]
    attention_concepts: list[uuid.UUID]
    average_mastery: float = Field(ge=0.0, le=1.0)
    generated_at: datetime


class RecordEvidenceInput(BaseModel):
    """Input payload for recording a learning evidence event directly."""

    model_config = ConfigDict(extra="forbid")

    source: str = "assessment"
    source_id: uuid.UUID
    concept_id: uuid.UUID
    result: str = Field(description="correct | incorrect | partial")
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    difficulty: str = Field(default="medium", description="easy | medium | hard")
    occurred_at: datetime | None = None
