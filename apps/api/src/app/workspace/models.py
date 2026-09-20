"""Workspace ORM models — spaces, projects, project_memberships (Phase 1).

RLS model (docs/security/rls-model.md):
- spaces/projects: owner-keyed policies on ``owner_id`` — the exact layout the
  contracts use (module-contracts §M.2: SpaceDto/ProjectDto carry owner_id;
  owner-only CRUD with 404-equivalent denials).
- project_memberships: row-keyed on ``user_id`` (a member sees their own
  membership rows; joins ship in the collaboration phase, never here — A-16
  keeps one learner per project for now).

No speculative fields; every column has a data-model justification.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.platform.models import Base
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class Space(Base):
    __tablename__ = "spaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Display name; uniqueness is per-owner (natural constraint from the PRD
    # journey: a learner's spaces are a small personal list).
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("uq_spaces_owner_name_lower", "owner_id", text("lower(name)"), unique=True),
        {
            "comment": "Top-level learner workspace (FR-05). RLS: owner-keyed via app.current_user_id.",
        },
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalized owner for (a) owner-scoped queries without joins, (b) RLS
    # predicates without subqueries, (c) consistency with Space ownership.
    # Kept consistent by the service layer (create derives it from the space)
    # and by FK cascade semantics (space delete cascades project).
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # The learner's goal for this project (PRD §4 project creation).
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    learning_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Lifecycle: active | archived (module-contracts ProjectDto.status).
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        # Part 6: Space → Project consistency — a project's owner must equal
        # its space's owner. Plain FKs cannot express this; the trigger below
        # (added in the migration) enforces it.
        Index("uq_projects_space_name_lower", "space_id", text("lower(name)"), unique=True),
        Index("ix_projects_owner_id", "owner_id"),
        {
            "comment": "Learning project within a space (FR-12). RLS: owner-keyed via app.current_user_id.",
        },
    )


class ProjectMembership(Base):
    __tablename__ = "project_memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Future collaboration capability; TODAY only 'owner' is ever written
    # (A-16: one learner per project — enforced by the partial unique index
    # below until collaboration is a real, reviewed decision).
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="owner")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        # Current behavior: exactly one membership per project (the owner).
        # Future capability: add roles; relax via a new migration (additive).
        Index(
            "uq_project_memberships_owner_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
        Index("uq_project_memberships_user_project", "user_id", "project_id", unique=True),
        CheckConstraint("role IN ('owner')", name="ck_project_memberships_role"),
        {
            "comment": "Project access rows (A-16: owner-only today; collaboration deferred).",
        },
    )
