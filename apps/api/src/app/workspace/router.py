"""Workspace HTTP layer — Spaces and Projects management (Phases 1, 2 & 13).

Provides REST endpoints for Spaces, Projects, and the legacy /workspaces/me endpoint.
Enforces owner isolation via CurrentPrincipal and RLS session_scope.
"""

from __future__ import annotations

import uuid

from app.identity.dependencies import CurrentPrincipal
from app.workspace import service
from app.workspace.schemas import (
    CreateProjectRequest,
    CreateSpaceRequest,
    ProjectListResponse,
    ProjectResponse,
    SpaceListResponse,
    SpaceResponse,
)
from fastapi import APIRouter, Response, status

router = APIRouter(prefix="/api/v1", tags=["workspace"])


# ---------------------------------------------------------------------------
# Space endpoints
# ---------------------------------------------------------------------------


@router.post("/spaces", response_model=SpaceResponse, status_code=status.HTTP_201_CREATED)
async def create_space(
    payload: CreateSpaceRequest,
    principal: CurrentPrincipal,
) -> SpaceResponse:
    user_id = uuid.UUID(principal.user_id)
    space = await service.create_space(
        owner_id=user_id,
        name=payload.name,
        description=payload.description,
    )
    return SpaceResponse(
        id=str(space.id),
        owner_id=str(space.owner_id),
        name=space.name,
        description=space.description,
    )


@router.get("/spaces", response_model=SpaceListResponse)
async def list_spaces(
    principal: CurrentPrincipal,
) -> SpaceListResponse:
    user_id = uuid.UUID(principal.user_id)
    spaces = await service.list_spaces(owner_id=user_id)
    items = [
        SpaceResponse(
            id=str(s.id),
            owner_id=str(s.owner_id),
            name=s.name,
            description=s.description,
        )
        for s in spaces
    ]
    return SpaceListResponse(items=items, total=len(items))


@router.get("/spaces/{space_id}", response_model=SpaceResponse)
async def get_space(
    space_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> SpaceResponse:
    user_id = uuid.UUID(principal.user_id)
    space = await service.get_space(owner_id=user_id, space_id=space_id)
    return SpaceResponse(
        id=str(space.id),
        owner_id=str(space.owner_id),
        name=space.name,
        description=space.description,
    )


# ---------------------------------------------------------------------------
# Project endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/spaces/{space_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    space_id: uuid.UUID,
    payload: CreateProjectRequest,
    principal: CurrentPrincipal,
) -> ProjectResponse:
    user_id = uuid.UUID(principal.user_id)
    project = await service.create_project(
        owner_id=user_id,
        space_id=space_id,
        name=payload.name,
        description=payload.description,
        learning_goal=payload.learning_goal,
    )
    return ProjectResponse(
        id=str(project.id),
        space_id=str(project.space_id),
        owner_id=str(project.owner_id),
        name=project.name,
        description=project.description,
        learning_goal=project.learning_goal,
        status=project.status,
    )


@router.get("/spaces/{space_id}/projects", response_model=ProjectListResponse)
async def list_projects_for_space(
    space_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> ProjectListResponse:
    user_id = uuid.UUID(principal.user_id)
    projects = await service.list_projects_for_space(owner_id=user_id, space_id=space_id)
    items = [
        ProjectResponse(
            id=str(p.id),
            space_id=str(p.space_id),
            owner_id=str(p.owner_id),
            name=p.name,
            description=p.description,
            learning_goal=p.learning_goal,
            status=p.status,
        )
        for p in projects
    ]
    return ProjectListResponse(items=items, total=len(items))


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    principal: CurrentPrincipal,
    status: str | None = None,
) -> ProjectListResponse:
    user_id = uuid.UUID(principal.user_id)
    projects = await service.list_projects_for_user(owner_id=user_id, status=status)
    items = [
        ProjectResponse(
            id=str(p.id),
            space_id=str(p.space_id),
            owner_id=str(p.owner_id),
            name=p.name,
            description=p.description,
            learning_goal=p.learning_goal,
            status=p.status,
        )
        for p in projects
    ]
    return ProjectListResponse(items=items, total=len(items))


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> ProjectResponse:
    user_id = uuid.UUID(principal.user_id)
    ctx = await service.get_project_in_scope(principal_user_id=user_id, project_id=project_id)
    p = ctx.project
    return ProjectResponse(
        id=str(p.id),
        space_id=str(p.space_id),
        owner_id=str(p.owner_id),
        name=p.name,
        description=p.description,
        learning_goal=p.learning_goal,
        status=p.status,
    )


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> Response:
    user_id = uuid.UUID(principal.user_id)
    await service.set_project_status(owner_id=user_id, project_id=project_id, status="archived")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Legacy / Workspaces / Me (Phase 2 backward compatibility)
# ---------------------------------------------------------------------------


@router.get("/workspaces/me")
async def my_workspaces(principal: CurrentPrincipal) -> dict:
    user_id = uuid.UUID(principal.user_id)
    spaces = await service.list_spaces(owner_id=user_id)
    projects = await service.list_projects_for_user(owner_id=user_id)
    return {
        "user_id": str(user_id),
        "spaces": [{"id": str(s.id), "name": s.name, "description": s.description} for s in spaces],
        "projects": [
            {
                "id": str(p.id),
                "space_id": str(p.space_id),
                "name": p.name,
                "status": p.status,
                "learning_goal": p.learning_goal,
            }
            for p in projects
        ],
    }
