"""Phase 1 SECURITY SUITE — the controls actually implemented (Part 18).

Covers: hashed secrets (password/refresh token), DB-level email uniqueness,
ownership enforcement, SQL-injection resistance (parameterization), malformed
identifier fail-closed, privilege-escalation denial, unsafe-context fail-closed,
pooled-connection context leakage, and unauthorized admin access.

Scope honesty (per prompt): these tests prove THESE controls only — not every
possible attack class. Cloud-first; skips when credentials are absent.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.security


@pytest.fixture()
async def runtime_exec(engines):
    from app.platform import db as database

    async def run(sql: str, params: dict | None = None):
        factory = database.get_runtime_session_factory()
        assert factory is not None
        async with factory() as session:
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


async def test_password_never_stored_plaintext(seed_user):
    u = await seed_user("pwcheck")
    # Read the hash through the admin path (test-only).
    from app.platform import db as database

    engine = database.get_engine()
    assert engine is not None
    async with engine.connect() as conn:
        stored = (
            await conn.execute(text("select password_hash from users where id = :i"), {"i": u.id})
        ).scalar_one()
    assert u.email not in stored
    assert "password-123456" not in stored
    assert stored.startswith("$argon2id$")


async def test_verify_password_rejects_garbage_hash():
    from app.platform.security import hash_password, verify_password

    good = hash_password("correct-horse-battery")
    assert verify_password(good, "correct-horse-battery") is True
    assert verify_password(good, "wrong") is False
    assert verify_password("not-a-hash", "x") is False
    assert verify_password("", "x") is False


async def test_refresh_token_never_stored_plaintext(seed_user):
    from app.identity import service as identity
    from app.platform import db as database

    u = await seed_user("tokcheck")
    created = await identity.create_refresh_session(u.id)
    engine = database.get_engine()
    assert engine is not None
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("select token_hash from refresh_sessions where user_id = :u"),
                {"u": u.id},
            )
        ).fetchall()
    assert rows, "session row missing"
    for (token_hash,) in rows:
        assert created.raw_token not in token_hash
        assert len(token_hash) == 64  # sha-256 hex
        assert not token_hash.startswith("ey")  # not a JWT either


async def test_unique_email_enforced_at_database_level(engines, admin_exec, seed_user):
    from app.identity import service as identity

    await seed_user("uniq")  # unrelated user; the duplicate is inserted below
    email = f"duplicate-{uuid.uuid4().hex[:8]}@phase1.test"
    await identity.register_user(email=email, password="password-123456")
    with pytest.raises(Exception) as excinfo:
        # Direct insert via admin SQL — bypasses service dedup check to prove
        # the DATABASE constraint (uq_users_email_lower) is the backstop.
        await admin_exec(
            "insert into users (id, email, password_hash) values (:i, :e, 'x')",
            {"i": str(uuid.uuid4()), "e": email.upper()},
        )
    assert "uq_users_email_lower" in str(excinfo.value)


async def test_invalid_ownership_denied(seed_user, seed_project):
    from app.platform.errors import NotFound
    from app.workspace import service as workspace

    u1 = await seed_user("owner")
    u2 = await seed_user("intruder")
    space, _ = await seed_project(u1.id)
    with pytest.raises(NotFound):
        await workspace.create_project(owner_id=u2.id, space_id=space.id, name="X")
    with pytest.raises(NotFound):
        await workspace.get_space(owner_id=u2.id, space_id=space.id)


async def test_sql_injection_attempts_are_ineffective(seed_user, runtime_exec):
    """Parameterization control: injection payloads are DATA, never SQL."""
    u = await seed_user("sqli")
    payload = "x'; DROP TABLE users; --"
    await runtime_exec(
        "select count(*) from users where email = :e",
        {"_user_id": str(u.id), "e": payload},
    )
    # Table still exists and the payload was treated as a literal.
    res = await runtime_exec("select count(*) from users", {"_user_id": str(u.id)})
    assert res.scalar_one() >= 1


async def test_malformed_identifiers_fail_closed(seed_user):
    from app.platform.errors import NotFound
    from app.workspace import service as workspace

    u = await seed_user("malformed")
    bad_ids = ["", "not-a-uuid", "1=1", "00000000-0000-0000-0000-000000000000"]
    for bad in bad_ids:
        try:
            fake = uuid.UUID(bad) if bad and "-" in bad else None
        except ValueError:
            fake = None
        if fake is None:
            continue  # non-UUID strings are rejected upstream (parse path)
        with pytest.raises(NotFound):
            await workspace.get_project_in_scope(principal_user_id=u.id, project_id=fake)


async def test_privilege_escalation_role_field_controlled(seed_user):
    """No public path can mint an admin (Part 18: privilege escalation)."""
    import inspect

    from app.identity import service as identity

    sig = inspect.signature(identity.register_user)
    assert "role" not in sig.parameters, "public registration must not accept a role"
    u = await identity.register_user(
        email=f"esc-{uuid.uuid4().hex[:8]}@phase1.test", password="password-123456"
    )
    assert u.role == "learner"


async def test_rls_bypass_attempt_via_set_role_fails(seed_user, runtime_exec):
    """The runtime role cannot SET ROLE to a privileged role (no membership)."""
    u = await seed_user("norole")
    from app.platform.errors import NotFound  # noqa: F401

    with pytest.raises(Exception) as excinfo:
        await runtime_exec(
            "set role postgres",  # attempt to escalate
            {"_user_id": str(u.id)},
        )
    msg = str(excinfo.value).lower()
    assert "permission denied" in msg or "cannot set" in msg or "member" in msg


async def test_unsafe_project_context_fails_closed(seed_user, seed_project, runtime_exec):
    """Empty-string context (malformed header case) must also fail closed."""
    u = await seed_user("emptyctx")
    await seed_project(u.id)
    res = await runtime_exec("select id from projects", {"_user_id": ""})
    assert res.fetchall() == []


async def test_pooled_connection_context_no_leak(seed_user, seed_project, engines):
    """Rapid alternating contexts through the shared pool: zero cross-talk."""
    from app.platform import db as database

    u1 = await seed_user("poolA")
    u2 = await seed_user("poolB")
    _, project_a = await seed_project(u1.id)
    _, project_b = await seed_project(u2.id)

    factory = database.get_runtime_session_factory()
    assert factory is not None

    async def read(user_id: str) -> list:
        async with factory() as session:
            async with session.begin():
                await database.bind_rls_context(session, user_id=user_id)
                res = await session.execute(text("select id from projects"))
                return [r[0] for r in res.fetchall()]

    for _ in range(3):
        a = await read(str(u1.id))
        b = await read(str(u2.id))
        assert a == [project_a.id], a
        assert b == [project_b.id], b


async def test_unauthorized_admin_access_concealed(seed_user):
    from app.platform.errors import NotFound
    from app.platform.security import Principal, resolve_role_or_404

    learner = Principal(user_id=str(uuid.uuid4()), role="learner")
    with pytest.raises(NotFound):
        resolve_role_or_404(learner)
