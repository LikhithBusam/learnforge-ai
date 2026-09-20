"""Growth SQLAlchemy ORM models (Phase 7).

Persists concept-level growth state and an immutable audit trail of growth evaluations.
Row-Level Security (RLS) is enforced on both tables (owner_id = app_user_id()).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.platform.models import Base
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ConceptGrowth(Base):
    """Current progression, trend, and attention state for a (project, concept) pair."""

    __tablename__ = "concept_growth"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    current_mastery: Mapped[float] = mapped_column(Float, nullable=False, default=0.20)
    previous_mastery: Mapped[float | None] = mapped_column(Float, nullable=True)
    short_term_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    long_term_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trend: Mapped[str] = mapped_column(String(32), nullable=False, default="insufficient_data")
    short_term_trend: Mapped[str] = mapped_column(
        String(32), nullable=False, default="insufficient_data"
    )
    long_term_trend: Mapped[str] = mapped_column(
        String(32), nullable=False, default="insufficient_data"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attention_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attention_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    attention_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recent_failure_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False, default="growth-1.0")
    last_evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    events: Mapped[list[GrowthEvent]] = relationship(
        "GrowthEvent",
        back_populates="growth",
        cascade="all, delete-orphan",
        order_by="GrowthEvent.occurred_at.asc()",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("project_id", "concept_id", name="uq_concept_growth_project_concept"),
        CheckConstraint(
            "current_mastery >= 0.0 AND current_mastery <= 1.0",
            name="chk_concept_growth_current_mastery",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="chk_concept_growth_confidence",
        ),
        CheckConstraint(
            "attention_score >= 0.0 AND attention_score <= 1.0",
            name="chk_concept_growth_attention_score",
        ),
        Index("ix_concept_growth_owner_project", "owner_id", "project_id"),
    )


class GrowthEvent(Base):
    """Immutable audit trail step recording a growth trajectory transition."""

    __tablename__ = "growth_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    growth_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("concept_growth.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_mastery_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    previous_trend: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_trend: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_attention_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_attention_score: Mapped[float] = mapped_column(Float, nullable=False)
    previous_mastery: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_mastery: Mapped[float] = mapped_column(Float, nullable=False)
    short_term_delta: Mapped[float] = mapped_column(Float, nullable=False)
    long_term_delta: Mapped[float] = mapped_column(Float, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False, default="growth-1.0")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    growth: Mapped[ConceptGrowth | None] = relationship(
        "ConceptGrowth", back_populates="events", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "concept_id",
            "source_mastery_event_id",
            name="uq_growth_events_proj_concept_source",
        ),
        Index("ix_growth_events_concept_occurred", "project_id", "concept_id", "occurred_at"),
        Index("ix_growth_events_owner_project", "owner_id", "project_id"),
    )
