"""Recommendation SQLAlchemy ORM models (Phase 8).

Persists personalized learning recommendations, structured explanations,
and user feedback / action history.
Row-Level Security (RLS) is enforced on all tables (owner_id = app_user_id()).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.platform.models import Base
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Recommendation(Base):
    """Personalized learning action recommendation for a learner in a project."""

    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.50)
    priority_level: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    evidence_refs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False, default="rec-1.0")
    source_growth_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    feedbacks: Mapped[list[RecommendationFeedback]] = relationship(
        "RecommendationFeedback",
        back_populates="recommendation",
        cascade="all, delete-orphan",
        order_by="RecommendationFeedback.created_at.asc()",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "priority_score >= 0.0 AND priority_score <= 1.0",
            name="chk_recommendations_priority_score",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'VIEWED', 'STARTED', 'COMPLETED', 'DISMISSED', 'EXPIRED')",
            name="chk_recommendations_status",
        ),
        Index(
            "ix_recommendations_project_status",
            "project_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_recommendations_project_concept_status",
            "project_id",
            "concept_id",
            "status",
        ),
    )


class RecommendationFeedback(Base):
    """Audit log of learner interaction or feedback on a recommendation."""

    __tablename__ = "recommendation_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    recommendation: Mapped[Recommendation] = relationship(
        "Recommendation", back_populates="feedbacks"
    )

    __table_args__ = (
        CheckConstraint(
            "action IN ('viewed', 'started', 'completed', 'dismissed')",
            name="chk_recommendation_feedback_action",
        ),
    )
