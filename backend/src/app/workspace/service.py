"""Workspace service — spaces/projects/memberships use-cases.

Authorization layer (Part 16) + transaction boundary (Part 11):
* `create_project` derives the project owner from the space server-side —
  the client never supplies ownership, so the Space→Project ownership
  invariant holds by construction (the DB trigger backstops it).
* Project creation is atomic: project row + owner membership row commit
  together in one `session_scope` transaction.
* Owner mismatch on any read/write → `NotFoundError` (404 posture: a
  non-owner must not learn the resource exists — ADR-0021/Q5). 403 is
  reserved for known-resource capability denials (none in this phase).
* Project context returned to callers is RLS-ready: the workspace service
  itself never sets DB context — request/worker entrypoints do that via
  `db.session_scope` contextvars (fail-closed default).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.platform import db as database
from app.platform.errors import ConflictError, NotFound
from app.workspace import repository as repo


@dataclass(frozen=True)
class SpaceDto:
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None


@dataclass(frozen=True)
class ProjectDto:
    id: uuid.UUID
    space_id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    learning_goal: str | None
    status: str


async def create_space(
    *, owner_id: uuid.UUID, name: str, description: str | None = None
) -> SpaceDto:
    name = name.strip()
    if not name:
        raise ValueError("Space name required")
    async with database.session_scope(user_id=str(owner_id)) as session:
        spaces = repo.SpaceRepository(session)
        duplicate = any(
            s.name.casefold() == name.casefold() for s in await spaces.list_for_owner(owner_id)
        )
        if duplicate:
            raise ConflictError("Space name already used")
        record = await spaces.create(owner_id=owner_id, name=name, description=description)
        return SpaceDto(
            id=record.id, owner_id=record.owner_id, name=record.name, description=record.description
        )


async def get_space(*, owner_id: uuid.UUID, space_id: uuid.UUID) -> SpaceDto:
    async with database.session_scope(user_id=str(owner_id)) as session:
        record = await repo.SpaceRepository(session).get_for_owner(space_id, owner_id)
        if record is None:
            raise NotFound("Space not found")
        return SpaceDto(
            id=record.id, owner_id=record.owner_id, name=record.name, description=record.description
        )


async def list_spaces(*, owner_id: uuid.UUID) -> list[SpaceDto]:
    async with database.session_scope(user_id=str(owner_id)) as session:
        records = await repo.SpaceRepository(session).list_for_owner(owner_id)
        return [
            SpaceDto(id=r.id, owner_id=r.owner_id, name=r.name, description=r.description)
            for r in records
        ]


@dataclass(frozen=True)
class ProjectContext:
    """Fully-resolved project scope handed to callers (module-contracts rule:
    project context is passed explicitly, never discovered lazily)."""

    project: ProjectDto
    space: SpaceDto


async def create_project(
    *,
    owner_id: uuid.UUID,
    space_id: uuid.UUID,
    name: str,
    description: str | None = None,
    learning_goal: str | None = None,
) -> ProjectDto:
    name = name.strip()
    if not name:
        raise ValueError("Project name required")
    async with database.session_scope(user_id=str(owner_id)) as session:
        spaces = repo.SpaceRepository(session)
        projects = repo.ProjectRepository(session)
        memberships = repo.ProjectMembershipRepository(session)

        space = await spaces.get_for_owner(space_id, owner_id)
        if space is None:
            raise NotFound("Space not found")

        duplicate = any(
            p.name.casefold() == name.casefold()
            for p in await projects.list_for_owner(owner_id)
            if p.space_id == space_id
        )
        if duplicate:
            raise ConflictError("Project name already used in this space")

        record = await projects.create(
            space_id=space_id,
            owner_id=owner_id,
            name=name,
            description=description,
            learning_goal=learning_goal,
        )
        # Atomic co-commit: project + its owner membership (Part 7/A-16).
        await memberships.create(project_id=record.id, user_id=owner_id, role="owner")
        return ProjectDto(
            id=record.id,
            space_id=record.space_id,
            owner_id=record.owner_id,
            name=record.name,
            description=record.description,
            learning_goal=record.learning_goal,
            status=record.status,
        )


async def get_project_in_scope(
    *, principal_user_id: uuid.UUID, project_id: uuid.UUID
) -> ProjectContext:
    """Owner-scoped read; 404-equivalent on mismatch (Part 16)."""
    async with database.session_scope(user_id=str(principal_user_id)) as session:
        projects = repo.ProjectRepository(session)
        record = await projects.get_for_owner(project_id, principal_user_id)
        if record is None:
            raise NotFound("Project not found")
        space = await repo.SpaceRepository(session).get_for_owner(
            record.space_id, principal_user_id
        )
        if space is None:  # inconsistent state; fail closed
            raise NotFound("Project not found")
        return ProjectContext(
            project=ProjectDto(
                id=record.id,
                space_id=record.space_id,
                owner_id=record.owner_id,
                name=record.name,
                description=record.description,
                learning_goal=record.learning_goal,
                status=record.status,
            ),
            space=SpaceDto(
                id=space.id, owner_id=space.owner_id, name=space.name, description=space.description
            ),
        )


async def list_projects_for_user(
    *, owner_id: uuid.UUID, status: str | None = None
) -> list[ProjectDto]:
    async with database.session_scope(user_id=str(owner_id)) as session:
        records = await repo.ProjectRepository(session).list_for_owner(owner_id, status=status)
        return [
            ProjectDto(
                id=r.id,
                space_id=r.space_id,
                owner_id=r.owner_id,
                name=r.name,
                description=r.description,
                learning_goal=r.learning_goal,
                status=r.status,
            )
            for r in records
        ]


async def set_project_status(
    *, owner_id: uuid.UUID, project_id: uuid.UUID, status: str
) -> ProjectDto:
    if status not in ("active", "archived"):
        raise ValueError("Invalid status")
    async with database.session_scope(user_id=str(owner_id)) as session:
        record = await repo.ProjectRepository(session).set_status(
            project_id, owner_id, status=status
        )
        if record is None:
            raise NotFound("Project not found")
        return ProjectDto(
            id=record.id,
            space_id=record.space_id,
            owner_id=record.owner_id,
            name=record.name,
            description=record.description,
            learning_goal=record.learning_goal,
            status=record.status,
        )


async def get_project_membership(*, project_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID | None:
    """Scoped membership probe for downstream modules (never a list-all)."""
    async with database.session_scope(user_id=str(user_id)) as session:
        record = await repo.ProjectMembershipRepository(session).get(project_id, user_id)
        return record.id if record else None


async def list_projects_for_space(*, owner_id: uuid.UUID, space_id: uuid.UUID) -> list[ProjectDto]:
    async with database.session_scope(user_id=str(owner_id)) as session:
        space = await repo.SpaceRepository(session).get_for_owner(space_id, owner_id)
        if space is None:
            raise NotFound("Space not found")
        records = [
            p
            for p in await repo.ProjectRepository(session).list_for_owner(owner_id)
            if p.space_id == space_id
        ]
        return [
            ProjectDto(
                id=r.id,
                space_id=r.space_id,
                owner_id=r.owner_id,
                name=r.name,
                description=r.description,
                learning_goal=r.learning_goal,
                status=r.status,
            )
            for r in records
        ]


__all__ = [
    "ProjectContext",
    "ProjectDto",
    "SpaceDto",
    "create_project",
    "create_space",
    "get_project_in_scope",
    "get_project_membership",
    "get_space",
    "list_projects_for_space",
    "list_projects_for_user",
    "list_spaces",
    "set_project_status",
]
