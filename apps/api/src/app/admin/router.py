"""Admin HTTP router (Phase 10).

Exposes administrative, read-oriented observability endpoints:
- Platform Overview
- User directory and user inspection (with strict data minimization)
- Project directory and project inspection
- Material processing health and failure diagnostics
- AI Gateway token usage, latency, and provider distribution
- Background job telemetry and execution history
- Immutable administrative audit logs
- Infrastructure dependency health checks

All endpoints are protected by the ``AdminPrincipal`` RBAC dependency.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from app.admin import service
from app.admin.schemas import (
    AdminAIUsageDto,
    AdminAuditLogListDto,
    AdminJobObservabilityDto,
    AdminMaterialProcessingDto,
    AdminPlatformOverviewDto,
    AdminProjectDetailDto,
    AdminProjectListDto,
    AdminSystemHealthDto,
    AdminUserDetailDto,
    AdminUserListDto,
)
from app.identity.dependencies import AdminPrincipal
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/overview", response_model=AdminPlatformOverviewDto)
async def get_overview(
    admin: AdminPrincipal,
) -> AdminPlatformOverviewDto:
    """Aggregate high-level platform status and activity across all domains."""
    actor_id = uuid.UUID(admin.user_id)
    return await service.get_platform_overview(actor_id=actor_id)


@router.get("/users", response_model=AdminUserListDto)
async def list_users(
    admin: AdminPrincipal,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size")] = 50,
    query: Annotated[str | None, Query(description="Search email or handle prefix")] = None,
) -> AdminUserListDto:
    """Safe, paginated list of platform users with data minimization."""
    actor_id = uuid.UUID(admin.user_id)
    return await service.list_users(
        actor_id=actor_id,
        page=page,
        page_size=page_size,
        query=query,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetailDto)
async def get_user_detail(
    user_id: uuid.UUID,
    admin: AdminPrincipal,
) -> AdminUserDetailDto:
    """Detailed view of a single user without exposing secrets or credentials."""
    actor_id = uuid.UUID(admin.user_id)
    return await service.get_user_detail(
        actor_id=actor_id,
        target_user_id=user_id,
    )


@router.get("/projects", response_model=AdminProjectListDto)
async def list_projects(
    admin: AdminPrincipal,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size")] = 50,
    search: Annotated[str | None, Query(description="Search project name prefix")] = None,
) -> AdminProjectListDto:
    """Paginated list of all projects across workspaces."""
    actor_id = uuid.UUID(admin.user_id)
    return await service.list_projects(
        actor_id=actor_id,
        page=page,
        page_size=page_size,
        search=search,
    )


@router.get("/projects/{project_id}", response_model=AdminProjectDetailDto)
async def get_project_detail(
    project_id: uuid.UUID,
    admin: AdminPrincipal,
) -> AdminProjectDetailDto:
    """Operational summary of a specific project."""
    actor_id = uuid.UUID(admin.user_id)
    return await service.get_project_detail(
        actor_id=actor_id,
        project_id=project_id,
    )


@router.get("/materials/processing", response_model=AdminMaterialProcessingDto)
async def get_material_processing_health(
    admin: AdminPrincipal,
) -> AdminMaterialProcessingDto:
    """Processing health and failure diagnostics for materials and ingestion pipelines."""
    actor_id = uuid.UUID(admin.user_id)
    return await service.get_material_processing_health(actor_id=actor_id)


@router.get("/ai/usage", response_model=AdminAIUsageDto)
async def get_ai_usage_analytics(
    admin: AdminPrincipal,
) -> AdminAIUsageDto:
    """AI Gateway usage metrics, token volume, latency, and error breakdown."""
    actor_id = uuid.UUID(admin.user_id)
    return await service.get_ai_usage_analytics(actor_id=actor_id)


@router.get("/jobs", response_model=AdminJobObservabilityDto)
async def get_job_observability(
    admin: AdminPrincipal,
    limit: Annotated[int, Query(ge=1, le=100, description="Recent execution limit")] = 50,
) -> AdminJobObservabilityDto:
    """Celery background task execution telemetry and queue status."""
    actor_id = uuid.UUID(admin.user_id)
    return await service.get_job_observability(actor_id=actor_id, limit=limit)


@router.get("/health", response_model=AdminSystemHealthDto)
async def get_system_health(
    admin: AdminPrincipal,
) -> AdminSystemHealthDto:
    """Detailed health and readiness status of platform dependencies."""
    actor_id = uuid.UUID(admin.user_id)
    return await service.get_system_health(actor_id=actor_id)


@router.get("/audit", response_model=AdminAuditLogListDto)
async def list_audit_logs(
    admin: AdminPrincipal,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size")] = 50,
    action: Annotated[str | None, Query(description="Filter by action name")] = None,
) -> AdminAuditLogListDto:
    """Paginated list of immutable administrative audit logs."""
    actor_id = uuid.UUID(admin.user_id)
    return await service.list_audit_logs(
        actor_id=actor_id,
        page=page,
        page_size=page_size,
        filter_action=action,
    )
