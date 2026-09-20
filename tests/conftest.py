"""Root test configuration — put the backend src on sys.path and provide shared fixtures."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent / "apps" / "api" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="session")
def cloud_settings():
    from app.platform.config import get_settings, reset_settings_cache

    reset_settings_cache()
    s = get_settings()
    if not (s.DATABASE_URL and s.DATABASE_RUNTIME_URL):
        pytest.skip("Cloud database credentials unavailable — verification UNVERIFIED")
    return s


@pytest.fixture(scope="session")
def engines(cloud_settings):
    from app.platform import db

    db.init_engine(cloud_settings)
    db.init_runtime_engine(cloud_settings)
    yield db


@pytest.fixture()
async def admin_exec(engines):
    from sqlalchemy import text

    async def run(sql: str, params: dict | None = None):
        from app.platform import db as database

        engine = database.get_engine()
        assert engine is not None
        async with engine.begin() as conn:
            return await conn.execute(text(sql), params or {})

    return run


@pytest.fixture()
async def seed_user(engines, admin_exec):
    from app.identity import service as identity

    async def _make(label: str):
        email = f"{label}-{uuid.uuid4().hex[:10]}@phase1.test"
        return await identity.register_user(email=email, password="password-123456")

    return _make


@pytest.fixture()
async def seed_project(engines, admin_exec):
    from app.workspace import service as workspace

    async def _make(user_id, name="Project"):
        space = await workspace.create_space(owner_id=user_id, name=f"Space {uuid.uuid4().hex[:6]}")
        project = await workspace.create_project(owner_id=user_id, space_id=space.id, name=name)
        return space, project

    return _make
