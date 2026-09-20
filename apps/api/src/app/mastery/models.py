"""Mastery ORM models (Phase 6).

Tables owned by Mastery Engine (module-contracts §M.7):
- concept_mastery — current mastery probability, confidence, and statistics per (project, concept)
- mastery_events  — immutable audit trail of learning evidence updates

RLS model:
- All tables enforce owner-keyed isolation via ``owner_id = app_user_id()``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.platform.models import Base
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ConceptMastery(Base):
    """Current mastery state and metrics for a single concept within a project."""

    __tablename__ = "concept_mastery"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mastery_probability: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.20")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    incorrect_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    partial_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    consecutive_correct: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_evidence_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    algorithm_version: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="bkt-1.0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    events: Mapped[list[MasteryEvent]] = relationship(
        "MasteryEvent",
        back_populates="mastery",
        cascade="all, delete-orphan",
        order_by="MasteryEvent.occurred_at.asc()",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("project_id", "concept_id", name="uq_concept_mastery_project_concept"),
        Index("ix_concept_mastery_project_owner", "project_id", "owner_id"),
        Index("ix_concept_mastery_concept_id", "concept_id"),
        Index("ix_concept_mastery_owner_id", "owner_id"),
        CheckConstraint(
            "mastery_probability >= 0.0 AND mastery_probability <= 1.0",
            name="ck_concept_mastery_probability",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_concept_mastery_confidence",
        ),
        {
            "comment": "Current mastery state per (project, concept). RLS: owner_id = app_user_id()",
        },
    )


class MasteryEvent(Base):
    """Immutable audit trail of Bayesian Knowledge Tracing updates."""

    __tablename__ = "mastery_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    mastery_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("concept_mastery.id", ondelete="CASCADE"), nullable=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="assessment")
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mastery_before: Mapped[float] = mapped_column(Float, nullable=False)
    mastery_after: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_before: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_after: Mapped[float] = mapped_column(Float, nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, server_default="medium")
    algorithm_version: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="bkt-1.0"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    mastery: Mapped[ConceptMastery | None] = relationship(
        "ConceptMastery",
        back_populates="events",
    )

    __table_args__ = (
        UniqueConstraint(
            "source", "source_id", "concept_id", name="uq_mastery_events_source_concept"
        ),
        Index("ix_mastery_events_project_owner", "project_id", "owner_id"),
        Index("ix_mastery_events_concept_id", "concept_id"),
        Index("ix_mastery_events_source_source_id", "source", "source_id"),
        Index("ix_mastery_events_occurred_at", "occurred_at"),
        {
            "comment": "Immutable evidence-to-mastery audit trail. RLS: owner_id = app_user_id()",
        },
    )
