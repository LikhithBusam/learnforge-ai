"""Workspace repositories — project/user scope preserved by construction
(module-contracts §M.2). No `get_all_projects()` surface exists; admin
aggregation is explicitly deferred to the Admin module with its own
authorization boundary (A-01).

Records are dataclasses (not ORM objects) so repositories never leak ORM
identity/lazy-loading across service boundaries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.platform.ids import uuid7
from app.workspace.models import Project, ProjectMembership, Space
from sqlalchemy import func, select


@dataclass(frozen=True)
class SpaceRecord:
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProjectRecord:
    id: uuid.UUID
    space_id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    learning_goal: str | None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MembershipRecord:
    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    created_at: datetime


def _space(s: Space) -> SpaceRecord:
    return SpaceRecord(
        id=s.id,
        owner_id=s.owner_id,
        name=s.name,
        description=s.description,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _project(p: Project) -> ProjectRecord:
    return ProjectRecord(
        id=p.id,
        space_id=p.space_id,
        owner_id=p.owner_id,
        name=p.name,
        description=p.description,
        learning_goal=p.learning_goal,
        status=p.status,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _membership(m: ProjectMembership) -> MembershipRecord:
    return MembershipRecord(
        id=m.id, project_id=m.project_id, user_id=m.user_id, role=m.role, created_at=m.created_at
    )


class SpaceRepository:
    """Owner-scoped: reads require the owner id; writes stamp it server-side."""

    def __init__(self, session) -> None:
        self._s = session

    async def create(
        self, *, owner_id: uuid.UUID, name: str, description: str | None
    ) -> SpaceRecord:
        s = Space(id=uuid7(), owner_id=owner_id, name=name, description=description)
        self._s.add(s)
        await self._s.flush()
        return _space(s)

    async def get_for_owner(self, space_id: uuid.UUID, owner_id: uuid.UUID) -> SpaceRecord | None:
        row = (
            await self._s.execute(
                select(Space).where(Space.id == space_id, Space.owner_id == owner_id)
            )
        ).scalar_one_or_none()
        return _space(row) if row else None

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[SpaceRecord]:
        rows = (
            (
                await self._s.execute(
                    select(Space).where(Space.owner_id == owner_id).order_by(Space.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [_space(r) for r in rows]

    async def rename(
        self, space_id: uuid.UUID, owner_id: uuid.UUID, *, name: str, description: str | None
    ) -> SpaceRecord | None:
        row = (
            await self._s.execute(
                select(Space).where(Space.id == space_id, Space.owner_id == owner_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        row.name = name
        row.description = description
        await self._s.flush()
        return _space(row)


class ProjectRepository:
    """Every read is owner-scoped or membership-scoped; writes stamp the owner."""

    def __init__(self, session) -> None:
        self._s = session

    async def create(
        self,
        *,
        space_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
        description: str | None,
        learning_goal: str | None,
    ) -> ProjectRecord:
        p = Project(
            id=uuid7(),
            space_id=space_id,
            owner_id=owner_id,
            name=name,
            description=description,
            learning_goal=learning_goal,
        )
        self._s.add(p)
        await self._s.flush()
        return _project(p)

    async def get_for_owner(
        self, project_id: uuid.UUID, owner_id: uuid.UUID
    ) -> ProjectRecord | None:
        row = (
            await self._s.execute(
                select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
            )
        ).scalar_one_or_none()
        return _project(row) if row else None

    async def get_in_space(
        self, project_id: uuid.UUID, space_id: uuid.UUID
    ) -> ProjectRecord | None:
        row = (
            await self._s.execute(
                select(Project).where(Project.id == project_id, Project.space_id == space_id)
            )
        ).scalar_one_or_none()
        return _project(row) if row else None

    async def list_for_owner(
        self, owner_id: uuid.UUID, *, status: str | None = None
    ) -> list[ProjectRecord]:
        stmt = select(Project).where(Project.owner_id == owner_id)
        if status is not None:
            stmt = stmt.where(Project.status == status)
        rows = (await self._s.execute(stmt.order_by(Project.created_at))).scalars().all()
        return [_project(r) for r in rows]

    async def set_status(
        self, project_id: uuid.UUID, owner_id: uuid.UUID, *, status: str
    ) -> ProjectRecord | None:
        row = (
            await self._s.execute(
                select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        row.status = status
        await self._s.flush()
        return _project(row)

    async def count_for_space(self, space_id: uuid.UUID) -> int:
        return int(
            (
                await self._s.execute(
                    select(func.count()).select_from(Project).where(Project.space_id == space_id)
                )
            ).scalar_one()
        )


class ProjectMembershipRepository:
    """Membership is written only as part of project creation (service layer);
    reads are keyed by (project, user) or (user) — never unscoped."""

    def __init__(self, session) -> None:
        self._s = session

    async def create(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, role: str = "owner"
    ) -> MembershipRecord:
        m = ProjectMembership(id=uuid7(), project_id=project_id, user_id=user_id, role=role)
        self._s.add(m)
        await self._s.flush()
        return _membership(m)

    async def get(self, project_id: uuid.UUID, user_id: uuid.UUID) -> MembershipRecord | None:
        row = (
            await self._s.execute(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        return _membership(row) if row else None

    async def list_for_user(self, user_id: uuid.UUID) -> list[MembershipRecord]:
        rows = (
            (
                await self._s.execute(
                    select(ProjectMembership).where(ProjectMembership.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        return [_membership(r) for r in rows]
