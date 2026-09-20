"""Unit tests for Phase 10 Admin schemas and data minimization."""

from __future__ import annotations

import datetime
import uuid

import pytest
from app.admin.schemas import (
    AdminAIUsageDto,
    AdminAuditLogDto,
    AdminAuditLogListDto,
    AdminJobExecutionDto,
    AdminJobObservabilityDto,
    AdminMaterialProcessingDto,
    AdminMaterialProcessingItemDto,
    AdminPlatformOverviewDto,
    AdminProjectDetailDto,
    AdminProjectListDto,
    AdminProjectSummaryDto,
    AdminSystemHealthDto,
    AdminUserDetailDto,
    AdminUserDto,
    AdminUserListDto,
)
from pydantic import ValidationError


def test_admin_schemas_serialization():
    """Verify serialization of all typed admin DTOs."""
    now = datetime.datetime.now(datetime.timezone.utc)
    user_id = uuid.uuid4()
    space_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    mat_id = uuid.uuid4()
    audit_id = uuid.uuid4()
    job_id = uuid.uuid4()

    # User DTOs
    u_dto = AdminUserDto(
        id=user_id,
        email="learner@example.com",
        display_name="Learner One",
        role="learner",
        status="active",
        created_at=now,
    )
    assert u_dto.email == "learner@example.com"
    # Ensure no secrets leak in fields
    assert "password" not in u_dto.model_dump()
    assert "password_hash" not in u_dto.model_dump()

    u_detail = AdminUserDetailDto(
        id=user_id,
        email="admin@example.com",
        display_name="Admin One",
        role="admin",
        status="active",
        created_at=now,
        spaces_count=3,
        projects_count=5,
        study_events_count=42,
        last_activity_at=now,
    )
    assert u_detail.projects_count == 5

    u_list = AdminUserListDto(
        items=[u_dto],
        total=1,
        page=1,
        page_size=50,
    )
    assert len(u_list.items) == 1

    # Project DTOs
    p_summary = AdminProjectSummaryDto(
        id=proj_id,
        space_id=space_id,
        owner_id=user_id,
        name="Biology 101",
        created_at=now,
        materials_count=4,
        activity_count=20,
    )
    p_detail = AdminProjectDetailDto(
        id=proj_id,
        space_id=space_id,
        owner_id=user_id,
        name="Biology 101",
        created_at=now,
        materials_count=4,
        conversations_count=2,
        quizzes_count=3,
        mastered_concepts=5,
        recommendations_count=1,
    )
    assert p_detail.materials_count == 4

    p_list = AdminProjectListDto(
        items=[p_summary],
        total=1,
        page=1,
        page_size=50,
    )
    assert p_list.total == 1

    # Material Processing DTOs
    mat_item = AdminMaterialProcessingItemDto(
        material_id=mat_id,
        project_id=proj_id,
        title="Lecture 1.pdf",
        status="READY",
        size_bytes=1048576,
        failure_reason=None,
        created_at=now,
    )
    mat_proc = AdminMaterialProcessingDto(
        total=10,
        ready=8,
        processing=1,
        upload_pending=0,
        failed=1,
        recent_failures=[mat_item],
    )
    assert mat_proc.failed == 1
    assert len(mat_proc.recent_failures) == 1

    # AI Usage DTOs
    ai_dto = AdminAIUsageDto(
        range="24h",
        total_requests=150,
        successful_requests=145,
        failed_requests=5,
        total_input_tokens=30000,
        total_output_tokens=15000,
        avg_latency_ms=450.5,
        by_feature={"rag_generation": 100, "assessment": 50},
        by_model={"gemini-2.5-pro": 150},
        estimated_cost_usd=0.045,
    )
    assert ai_dto.total_requests == 150
    assert ai_dto.avg_latency_ms == 450.5

    # Job Observability DTOs
    job_exec = AdminJobExecutionDto(
        id=job_id,
        task_name="app.materials.tasks.ingest_material",
        queue="materials",
        status="SUCCESS",
        duration_ms=850,
        attempt=1,
        correlation_id="corr-123",
        error_message=None,
        created_at=now,
    )
    job_obs = AdminJobObservabilityDto(
        total_executions=50,
        succeeded_count=48,
        failed_count=2,
        retrying_count=0,
        recent_executions=[job_exec],
    )
    assert job_obs.total_executions == 50

    # Platform Overview
    overview = AdminPlatformOverviewDto(
        users={"total": 25, "active": 20, "admins": 2},
        spaces={"total": 30},
        projects={"total": 45},
        materials={"total": 120, "ready": 115, "processing": 3, "failed": 2},
        learning={"total_events": 500, "active_projects": 15},
        ai={"total_requests": 150, "failed_requests": 5},
        jobs={"total_executions": 50, "failed_executions": 2},
        timestamp=now,
    )
    assert overview.users["total"] == 25

    # Health
    health = AdminSystemHealthDto(
        status="healthy",
        checked_at=now,
        components={"database": {"status": "healthy"}},
    )
    assert health.status == "healthy"

    # Audit Logs
    audit = AdminAuditLogDto(
        id=audit_id,
        actor_user_id=user_id,
        actor_role="admin",
        action="view_overview",
        target_type="platform",
        target_id=None,
        occurred_at=now,
        correlation_id=None,
        metadata_payload={"ip": "127.0.0.1"},
    )
    audit_list = AdminAuditLogListDto(
        items=[audit],
        total=1,
        page=1,
        page_size=50,
    )
    assert audit_list.total == 1


def test_admin_schemas_validation_bounds():
    """Verify validation boundaries and requirements."""
    with pytest.raises(ValidationError):
        # Missing required fields
        AdminPlatformOverviewDto(users={"total": 10})
