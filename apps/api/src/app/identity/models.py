"""Identity ORM models — users, refresh_sessions (Phase 1, data-model doc §1–2).

Column policy: every column maps to a requirement/architecture decision
(see docs/architecture/database/phase-1-data-model.md). No speculative fields.
IDs are UUIDv7 generated application-side (platform.ids); timestamps are
timezone-aware server defaults.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.platform.models import Base
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # Email stored as provided; case-insensitive uniqueness via functional
    # unique index on lower(email) (see migration). Normalization (trim/lower)
    # happens in the service before persist/lookup.
    email: Mapped[str] = mapped_column(Text, nullable=False)
    # Profile display name (Phase 2 registration; nullable — bootstrap/admin
    # accounts may not have one).
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # PHC argon2id string only — never plaintext (security-baseline §3).
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Authorization foundation (Part 16): learner | admin.
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="learner")
    # Account state for future login checks; 'disabled' denies auth (ADR-0018).
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
        {
            "comment": "Identity root (FR-01). RLS: row visible only to its owner via app.current_user_id.",
        },
    )


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # SHA-256 hex of the raw refresh token — raw tokens are NEVER stored
    # (ADR-0018; lookup by hash is the only supported path).
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Why the session ended: rotated | reuse_detected | logout (reuse detection
    # = presenting a token whose session already has a successor).
    revoked_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Rotation chain: the session this one replaced. A stored token whose
    # session has been superseded ⇒ reuse detected (ADR-0018).
    parent_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_sessions.id", ondelete="SET NULL"), nullable=True
    )
    # Rotation family (Phase 2): copied from the parent at rotation; reuse of
    # any family member revokes the whole family (token-theft detection).
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("uq_refresh_sessions_token_hash", "token_hash", unique=True),
        Index("ix_refresh_sessions_user_id", "user_id"),
        Index(
            "ix_refresh_sessions_active_expiry",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_refresh_sessions_family_id", "family_id"),
        {
            "comment": "Rotating refresh-token sessions (ADR-0018). Secret classification: token hashes only.",
        },
    )
