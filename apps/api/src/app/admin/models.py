"""Admin & System Observability SQLAlchemy ORM models (Phase 10).

Persists immutable administrative audit records and background job execution telemetry.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.platform.models import Base
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


class AdminAuditLog(Base):
    """Immutable audit trail of administrative access and operations."""

    __tablename__ = "admin_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False, default="admin")
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_admin_audit_actor_occurred", "actor_user_id", "occurred_at"),
        Index("ix_admin_audit_action_occurred", "action", "occurred_at"),
    )


class JobExecutionRecord(Base):
    """Execution telemetry record for Celery background tasks."""

    __tablename__ = "job_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    queue: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUCCEEDED", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_job_executions_task_created", "task_name", "created_at"),
        Index("ix_job_executions_status_created", "status", "created_at"),
    )
