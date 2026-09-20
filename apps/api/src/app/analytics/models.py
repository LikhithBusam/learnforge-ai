"""Analytics SQLAlchemy ORM models (Phase 9).

Persists immutable analytics events and daily project-level metric rollups.
Row-Level Security (RLS) is enforced on all tables.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from app.platform.models import Base
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


class AnalyticsEvent(Base):
    """Immutable, timestamped learning event for analytics and auditing."""

    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_analytics_events_project_occurred", "project_id", "occurred_at"),
        Index("ix_analytics_events_project_type", "project_id", "event_type"),
        Index("ix_analytics_events_user_occurred", "user_id", "occurred_at"),
    )


class ProjectDailyMetric(Base):
    """Aggregated daily metric rollup for read-optimized dashboard queries."""

    __tablename__ = "project_daily_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    metric_category: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "date",
            "metric_category",
            name="uq_project_daily_metrics_proj_date_cat",
        ),
        Index("ix_project_daily_metrics_proj_date", "project_id", "date"),
    )
