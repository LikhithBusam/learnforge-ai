"""Integration tests for Phase 10 Admin API RBAC and HTTP endpoint contracts.

Tests:
1. Anonymous requests -> 401 Unauthorized
2. Learner role requests -> 403 Forbidden
3. Admin role requests -> 200 OK with valid response schema and data minimization
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from app.identity.tokens import issue_access_token
from app.main import create_app


@pytest.fixture()
async def admin_api(engines, cloud_settings):
    """ASGI client for Admin API testing."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture()
def admin_headers():
    def _make(role: str = "admin", user_id: str | None = None):
        uid = user_id or str(uuid.uuid4())
        token, _ = issue_access_token(
            user_id=uid,
            role=role,
            session_id=str(uuid.uuid4()),
        )
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.mark.asyncio
async def test_admin_endpoints_anonymous_rejected(admin_api):
    """Anonymous requests must be rejected with 401 Unauthorized."""
    endpoints = [
        "/api/v1/admin/overview",
        "/api/v1/admin/users",
        f"/api/v1/admin/users/{uuid.uuid4()}",
        "/api/v1/admin/projects",
        f"/api/v1/admin/projects/{uuid.uuid4()}",
        "/api/v1/admin/materials/processing",
        "/api/v1/admin/ai/usage",
        "/api/v1/admin/jobs",
        "/api/v1/admin/health",
        "/api/v1/admin/audit",
    ]
    for endpoint in endpoints:
        resp = await admin_api.get(endpoint)
        assert (
            resp.status_code == 401
        ), f"Expected 401 for {endpoint}, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_admin_endpoints_learner_forbidden(admin_api, admin_headers):
    """Learner requests must be rejected with 403 Forbidden."""
    headers = admin_headers(role="learner")
    endpoints = [
        "/api/v1/admin/overview",
        "/api/v1/admin/users",
        f"/api/v1/admin/users/{uuid.uuid4()}",
        "/api/v1/admin/projects",
        f"/api/v1/admin/projects/{uuid.uuid4()}",
        "/api/v1/admin/materials/processing",
        "/api/v1/admin/ai/usage",
        "/api/v1/admin/jobs",
        "/api/v1/admin/health",
        "/api/v1/admin/audit",
    ]
    for endpoint in endpoints:
        resp = await admin_api.get(endpoint, headers=headers)
        assert (
            resp.status_code == 403
        ), f"Expected 403 for {endpoint}, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_admin_endpoints_admin_authorized(admin_api, admin_headers, seed_user, seed_project):
    """Admin requests must succeed with 200 OK and valid schemas."""
    admin_user = await seed_user("p10-admin-user")
    learner_user = await seed_user("p10-learner-for-api")
    space, project = await seed_project(learner_user.id, "P10 Admin API Project")

    headers = admin_headers(role="admin", user_id=str(admin_user.id))

    # Overview
    r = await admin_api.get("/api/v1/admin/overview", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "users" in data
    assert "projects" in data
    assert "materials" in data

    # Users list
    r = await admin_api.get("/api/v1/admin/users?page=1&page_size=10", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data
    # Verify data minimization: no password hashes
    for u in data["items"]:
        assert "password" not in u
        assert "password_hash" not in u

    # User detail
    r = await admin_api.get(f"/api/v1/admin/users/{learner_user.id}", headers=headers)
    assert r.status_code == 200
    u_detail = r.json()
    assert u_detail["id"] == str(learner_user.id)
    assert "password" not in u_detail
    assert "password_hash" not in u_detail

    # Projects list
    r = await admin_api.get("/api/v1/admin/projects?page=1&page_size=10", headers=headers)
    assert r.status_code == 200
    p_data = r.json()
    assert "items" in p_data

    # Project detail
    r = await admin_api.get(f"/api/v1/admin/projects/{project.id}", headers=headers)
    assert r.status_code == 200
    p_detail = r.json()
    assert p_detail["id"] == str(project.id)

    # Materials Processing
    r = await admin_api.get("/api/v1/admin/materials/processing", headers=headers)
    assert r.status_code == 200
    assert "total" in r.json()

    # AI Usage
    r = await admin_api.get("/api/v1/admin/ai/usage", headers=headers)
    assert r.status_code == 200
    assert "total_requests" in r.json()

    # Jobs
    r = await admin_api.get("/api/v1/admin/jobs", headers=headers)
    assert r.status_code == 200
    assert "total_executions" in r.json()

    # Health
    r = await admin_api.get("/api/v1/admin/health", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] in ("healthy", "degraded")

    # Audit logs
    r = await admin_api.get("/api/v1/admin/audit?page=1&page_size=10", headers=headers)
    assert r.status_code == 200
    assert "items" in r.json()
