"""Integration tests for Phase 10 Admin Dashboard & System Observability.

Tests against live Supabase PostgreSQL database:
- Platform Overview aggregation
- Paginated user list and user detail inspection
- Paginated project list and project detail inspection
- Material processing health
- Immutable audit log writing and retrieval
- Job execution telemetry persistence and retrieval
"""

from __future__ import annotations

import pytest
from app.admin import service as admin_service
from app.admin.schemas import (
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


@pytest.mark.asyncio
async def test_full_admin_service_lifecycle_e2e(cloud_settings, engines, seed_user, seed_project):
    """Verify all admin service read-models and audit logging against live database."""
    # Seed test users and projects
    admin_user = await seed_user("p10-admin-actor")
    user1 = await seed_user("p10-learner-1")
    user2 = await seed_user("p10-learner-2")
    space1, project1 = await seed_project(user1.id, "P10 Admin Test Project")

    admin_actor_id = admin_user.id

    # 1. Platform Overview
    overview = await admin_service.get_platform_overview(actor_id=admin_actor_id)
    assert isinstance(overview, AdminPlatformOverviewDto)
    assert overview.users["total"] >= 3
    assert overview.projects["total"] >= 1
    assert overview.materials["total"] >= 0
    assert overview.timestamp is not None

    # 2. List Users
    user_list = await admin_service.list_users(
        actor_id=admin_actor_id,
        page=1,
        page_size=50,
    )
    assert isinstance(user_list, AdminUserListDto)
    assert user_list.total >= 3
    user_ids = [u.id for u in user_list.items]
    assert user1.id in user_ids
    assert user2.id in user_ids

    # 3. User Detail
    user_detail = await admin_service.get_user_detail(
        actor_id=admin_actor_id,
        target_user_id=user1.id,
    )
    assert isinstance(user_detail, AdminUserDetailDto)
    assert user_detail.id == user1.id
    assert user_detail.email == user1.email
    assert user_detail.spaces_count >= 1
    assert user_detail.projects_count >= 1

    # 4. List Projects
    proj_list = await admin_service.list_projects(
        actor_id=admin_actor_id,
        page=1,
        page_size=50,
    )
    assert isinstance(proj_list, AdminProjectListDto)
    assert proj_list.total >= 1
    project_ids = [p.id for p in proj_list.items]
    assert project1.id in project_ids

    # 5. Project Detail
    proj_detail = await admin_service.get_project_detail(
        actor_id=admin_actor_id,
        project_id=project1.id,
    )
    assert isinstance(proj_detail, AdminProjectDetailDto)
    assert proj_detail.id == project1.id
    assert proj_detail.name == "P10 Admin Test Project"
    assert proj_detail.owner_id == user1.id

    # 6. Material Processing Health
    mat_proc = await admin_service.get_material_processing_health(actor_id=admin_actor_id)
    assert isinstance(mat_proc, AdminMaterialProcessingDto)
    assert mat_proc.total >= 0

    # 7. Job Telemetry: Record and Observe
    job_rec = await admin_service.record_job_execution(
        task_name="app.materials.tasks.ingest_material",
        queue="materials",
        status="SUCCESS",
        duration_ms=320,
        correlation_id="corr-test-p10",
    )
    assert job_rec.id is not None

    jobs_obs = await admin_service.get_job_observability(actor_id=admin_actor_id, limit=10)
    assert isinstance(jobs_obs, AdminJobObservabilityDto)
    assert jobs_obs.total_executions >= 1
    assert any(j.id == job_rec.id for j in jobs_obs.recent_executions)

    # 8. System Health
    health = await admin_service.get_system_health(actor_id=admin_actor_id)
    assert isinstance(health, AdminSystemHealthDto)
    assert health.status in ("healthy", "degraded")

    # 9. Audit Logs
    audit_logs = await admin_service.list_audit_logs(
        actor_id=admin_actor_id,
        page=1,
        page_size=50,
    )
    assert isinstance(audit_logs, AdminAuditLogListDto)
    assert audit_logs.total >= 5  # Actions from previous calls
    assert any(a.action == "view_overview" for a in audit_logs.items)
