"""Pydantic schemas and DTOs for Phase 10 Admin Dashboard & System Observability.

All admin responses use strictly typed DTOs with data minimization (never exposing
password hashes, tokens, API keys, or raw private document bodies).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AdminPlatformOverviewDto(BaseModel):
    """High-level operational overview of platform entities and activity."""

    users: dict[str, int] = Field(
        ..., description="User counts: {'total': int, 'active': int, 'admins': int}"
    )
    spaces: dict[str, int] = Field(..., description="Space counts: {'total': int}")
    projects: dict[str, int] = Field(..., description="Project counts: {'total': int}")
    materials: dict[str, int] = Field(
        ...,
        description="Material counts: {'total': int, 'ready': int, 'processing': int, 'failed': int}",
    )
    learning: dict[str, int] = Field(
        ..., description="Learning activity: {'total_events': int, 'active_projects': int}"
    )
    ai: dict[str, Any] = Field(
        ..., description="AI metrics: {'total_requests': int, 'failed_requests': int}"
    )
    jobs: dict[str, int] = Field(
        ..., description="Job metrics: {'total_executions': int, 'failed_executions': int}"
    )
    timestamp: datetime.datetime


class AdminUserDto(BaseModel):
    """Safe administrative user read-model (data-minimized)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    role: str
    status: str
    created_at: datetime.datetime


class AdminUserListDto(BaseModel):
    """Paginated user listing."""

    items: list[AdminUserDto]
    total: int
    page: int
    page_size: int


class AdminUserDetailDto(BaseModel):
    """Detailed administrative user view."""

    id: uuid.UUID
    email: str
    display_name: str | None
    role: str
    status: str
    created_at: datetime.datetime
    spaces_count: int
    projects_count: int
    study_events_count: int
    last_activity_at: datetime.datetime | None = None


class AdminProjectSummaryDto(BaseModel):
    """Administrative project summary."""

    id: uuid.UUID
    space_id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    created_at: datetime.datetime
    materials_count: int
    activity_count: int


class AdminProjectListDto(BaseModel):
    """Paginated project listing."""

    items: list[AdminProjectSummaryDto]
    total: int
    page: int
    page_size: int


class AdminProjectDetailDto(BaseModel):
    """Detailed administrative project view."""

    id: uuid.UUID
    space_id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    created_at: datetime.datetime
    materials_count: int
    conversations_count: int
    quizzes_count: int
    mastered_concepts: int
    recommendations_count: int


class AdminMaterialProcessingItemDto(BaseModel):
    """Material processing status item."""

    material_id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: str
    size_bytes: int
    failure_reason: str | None
    created_at: datetime.datetime


class AdminMaterialProcessingDto(BaseModel):
    """Material processing health overview."""

    total: int
    ready: int
    processing: int
    upload_pending: int
    failed: int
    recent_failures: list[AdminMaterialProcessingItemDto]


class AdminAIUsageDto(BaseModel):
    """Aggregated AI gateway telemetry."""

    range: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_input_tokens: int
    total_output_tokens: int
    avg_latency_ms: float
    by_feature: dict[str, int]
    by_model: dict[str, int]
    estimated_cost_usd: float | None = None


class AdminJobExecutionDto(BaseModel):
    """Job execution log item."""

    id: uuid.UUID
    task_name: str
    queue: str
    status: str
    duration_ms: int | None
    attempt: int
    correlation_id: str | None
    error_message: str | None
    created_at: datetime.datetime


class AdminJobObservabilityDto(BaseModel):
    """Background job telemetry overview."""

    total_executions: int
    succeeded_count: int
    failed_count: int
    retrying_count: int
    recent_executions: list[AdminJobExecutionDto]


class AdminSystemHealthDto(BaseModel):
    """Structured dependency health check report."""

    status: str  # healthy, degraded, unhealthy
    checked_at: datetime.datetime
    components: dict[str, dict[str, Any]]


class AdminAuditLogDto(BaseModel):
    """Immutable administrative audit record."""

    id: uuid.UUID
    actor_user_id: uuid.UUID
    actor_role: str
    action: str
    target_type: str
    target_id: str | None
    occurred_at: datetime.datetime
    correlation_id: str | None
    metadata_payload: dict[str, Any]


class AdminAuditLogListDto(BaseModel):
    """Paginated administrative audit logs."""

    items: list[AdminAuditLogDto]
    total: int
    page: int
    page_size: int
