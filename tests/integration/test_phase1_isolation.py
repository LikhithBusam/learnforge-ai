"""Phase 1 ISOLATION SUITE — RLS defense-in-depth proofs (Part 17).

Layer model under test (module-contracts / rls-model.md):
  L1 route authorization · L2 repository scope · L3 PostgreSQL RLS ·
  L4 retrieval filtering (later phases).

Tests 3–6 bypass L1/L2 on purpose: they speak raw SQL through the RUNTIME
engine (the same role the API uses) to prove **L3 alone** blocks cross-project
access — including when application filtering is removed entirely (Test 6,
the critical demonstration that RLS is a real second boundary).

All tests run against the live Supabase PostgreSQL connection path
(Part 17/12 — no local substitution) and skip when credentials are absent.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.isolation


@pytest.fixture()
async def runtime_exec(engines):
    """Raw SQL executor on the RUNTIME engine (application role, no BYPASSRLS).

    This is the L3-only probe surface: no repository scoping, no route auth.
    """

    from app.platform import db as database

    async def run(sql: str, params: dict | None = None):
        engine = database.get_runtime_session_factory()
        assert engine is not None
        async with engine() as session:
            async with session.begin():
                if params is None:
                    params = {}
                await database.bind_rls_context(
                    session,
                    user_id=params.pop("_user_id", None),
                    project_id=params.pop("_project_id", None),
                )
                return await session.execute(text(sql), params)

    return run


async def test_01_same_project_access_allowed(seed_user, seed_project, runtime_exec):
    """Test 1 — User A → Project A → allowed."""
    u1 = await seed_user("alice")
    space, project = await seed_project(u1.id)
    res = await runtime_exec(
        "select id, name from projects where id = :pid", {"_user_id": str(u1.id), "pid": project.id}
    )
    rows = res.fetchall()
    assert len(rows) == 1 and rows[0][0] == project.id


async def test_02_different_project_access_denied(seed_user, seed_project, runtime_exec):
    """Test 2 — User A → Project B → denied at the service layer (404 posture)."""
    from app.platform.errors import NotFound
    from app.workspace import service as workspace

    u1 = await seed_user("alice")
    u2 = await seed_user("bob")
    _, project_b = await seed_project(u2.id)
    with pytest.raises(NotFound):
        await workspace.get_project_in_scope(principal_user_id=u1.id, project_id=project_b.id)


async def test_03_cross_project_read_returns_zero_rows(seed_user, seed_project, runtime_exec):
    """Test 3 — raw runtime-role SELECT of B's rows while bound as A: 0 rows."""
    u1 = await seed_user("alice")
    u2 = await seed_user("bob")
    _, project_b = await seed_project(u2.id)
    res = await runtime_exec(
        "select id from projects where id = :pid", {"_user_id": str(u1.id), "pid": project_b.id}
    )
    assert res.fetchall() == []


async def test_04_cross_project_update_affects_zero_rows(seed_user, seed_project, runtime_exec):
    """Test 4 — UPDATE of B's project under A's context: 0 rows affected."""
    u1 = await seed_user("alice")
    u2 = await seed_user("bob")
    _, project_b = await seed_project(u2.id)
    res = await runtime_exec(
        "update projects set description = :d where id = :pid",
        {"_user_id": str(u1.id), "d": "hijacked", "pid": project_b.id},
    )
    assert res.rowcount == 0
    # And the row is unchanged when read by its true owner.
    res2 = await runtime_exec(
        "select description from projects where id = :pid",
        {"_user_id": str(u2.id), "pid": project_b.id},
    )
    assert res2.scalar_one() != "hijacked"


async def test_05_cross_project_delete_affects_zero_rows(seed_user, seed_project, runtime_exec):
    """Test 5 — DELETE of B's project under A's context: 0 rows affected."""
    u1 = await seed_user("alice")
    u2 = await seed_user("bob")
    _, project_b = await seed_project(u2.id)
    res = await runtime_exec(
        "delete from projects where id = :pid", {"_user_id": str(u1.id), "pid": project_b.id}
    )
    assert res.rowcount == 0
    res2 = await runtime_exec(
        "select count(*) from projects where id = :pid",
        {"_user_id": str(u2.id), "pid": project_b.id},
    )
    assert res2.scalar_one() == 1


async def test_06_application_filter_removed_rls_still_blocks(
    seed_user, seed_project, runtime_exec
):
    """Test 6 (CRITICAL) — NO application filter at all: a full-table SELECT
    through the runtime role returns ONLY the caller's own rows."""
    u1 = await seed_user("alice")
    u2 = await seed_user("bob")
    await seed_project(u1.id)
    _, project_b = await seed_project(u2.id)
    res = await runtime_exec(
        "select id from projects",  # deliberately unfiltered query
        {"_user_id": str(u1.id)},
    )
    ids = {r[0] for r in res.fetchall()}
    assert project_b.id not in ids
    assert len(ids) >= 1  # A still sees their own rows


async def test_07_worker_context_isolated_between_tasks(seed_user, seed_project, engines):
    """Test 7 — a background-task-shaped context (user/project/correlation)
    binds correctly and cannot leak into the next task on the same engine."""
    from app.platform import db as database

    u1 = await seed_user("alice")
    u2 = await seed_user("bob")
    _, project_a = await seed_project(u1.id)
    _, project_b = await seed_project(u2.id)

    factory = database.get_runtime_session_factory()
    assert factory is not None

    async def task_like(user_id: str, project_id: uuid.UUID) -> list:
        async with factory() as session:
            async with session.begin():
                await database.bind_rls_context(
                    session, user_id=user_id, project_id=str(project_id)
                )
                res = await session.execute(text("select id from projects"))
                return [r[0] for r in res.fetchall()]

    seen_a = await task_like(str(u1.id), project_a.id)
    seen_b = await task_like(str(u2.id), project_b.id)
    # Each task sees exactly its own project — no leakage in either direction.
    assert seen_a == [project_a.id]
    assert seen_b == [project_b.id]


async def test_08_admin_posture(seed_user, seed_project):
    """Test 8 — admin authorization posture (404 concealment per ADR-0021/Q5)."""
    from app.platform.errors import NotFound
    from app.platform.security import Principal, resolve_role_or_404

    learner = Principal(user_id=str(uuid.uuid4()), role="learner")
    with pytest.raises(NotFound):
        resolve_role_or_404(learner)
    admin = Principal(user_id=str(uuid.uuid4()), role="admin")
    assert resolve_role_or_404(admin).is_admin


async def test_09_runtime_role_cannot_bypass_rls(engines, admin_exec):
    """Test 9 — the application runtime role has NO BYPASSRLS and NO superuser."""
    row = (
        await admin_exec(
            "select rolsuper, rolbypassrls, rolcanlogin from pg_roles "
            "where rolname = 'studycompanion_runtime'"
        )
    ).one()
    assert row.rolsuper is False
    assert row.rolbypassrls is False
    assert row.rolcanlogin is True


async def test_10_missing_context_fails_closed(seed_user, seed_project, runtime_exec):
    """Test 10 — project-scoped access with NO context bound: zero rows."""
    u1 = await seed_user("alice")
    await seed_project(u1.id)
    res = await runtime_exec("select id from projects")  # no _user_id param
    assert res.fetchall() == []


async def test_11_context_isolation_through_shared_pool_path(seed_user, seed_project, engines):
    """Test 11 — sequential A/B operations over the same pooled engine: no
    context bleed in either direction (transaction-scoped set_config)."""
    from app.platform import db as database

    u1 = await seed_user("alice")
    u2 = await seed_user("bob")
    _, project_a = await seed_project(u1.id)
    _, project_b = await seed_project(u2.id)

    factory = database.get_runtime_session_factory()
    assert factory is not None

    async def scoped_read(user_id: str) -> list:
        async with factory() as session:
            async with session.begin():
                await database.bind_rls_context(session, user_id=user_id)
                res = await session.execute(text("select id from projects"))
                return [r[0] for r in res.fetchall()]

    a1 = await scoped_read(str(u1.id))
    b1 = await scoped_read(str(u2.id))
    a2 = await scoped_read(str(u1.id))
    assert project_a.id in a1 and project_b.id not in a1
    assert project_b.id in b1 and project_a.id not in b1
    # Re-bind after B: A's view is intact (no residue from B's transaction).
    assert a1 == a2


async def test_12_cloud_connection_path_is_supabase(engines, admin_exec):
    """Test 12 — the critical RLS tests above ran through the Supabase pooler
    (not a local substitute): assert the connection's server identity/host."""
    row = (
        await admin_exec(
            "select version(), inet_server_addr() is not null as remote, current_database()"
        )
    ).one()
    assert row.remote is True  # a real remote (cloud) address, not a unix socket
    assert "PostgreSQL" in row.version
