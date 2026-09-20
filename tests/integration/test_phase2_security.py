"""Phase 2 SECURITY SUITE — controls actually implemented (Part 21).

Complements the auth matrix: secret persistence, header-identity rejection,
key exposure, and log hygiene. Cloud-first; skips without credentials.
"""

from __future__ import annotations

import uuid as uuid_mod

import pytest

pytestmark = pytest.mark.security

PASSWORD = "password-123456"


@pytest.fixture()
async def api(engines, cloud_settings):
    import httpx
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _register(api, label="sec"):
    email = f"{label}-{uuid_mod.uuid4().hex[:10]}@phase2.test"
    r = await api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return email, r.json()


async def _login(api, email):
    r = await api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200
    return r.json()


async def test_password_hash_is_argon2id_and_plaintext_absent(engines, admin_exec):

    email = f"hash-{uuid_mod.uuid4().hex[:8]}@phase2.test"
    from app.identity import service as identity

    await identity.register_user(email=email, password=PASSWORD)
    row = (await admin_exec("select password_hash from users where email = :e", {"e": email})).one()
    assert row.password_hash.startswith("$argon2id$")
    assert PASSWORD not in row.password_hash


async def test_refresh_token_never_persisted_raw(engines, admin_exec, api):
    email, _ = await _register(api, "rawtok")
    row = (
        await admin_exec(
            "select token_hash from refresh_sessions s join users u on u.id = s.user_id "
            "where u.email = :e",
            {"e": email},
        )
    ).one()
    cookie = api.cookies.get("studycompanion_refresh")
    assert cookie and cookie not in row.token_hash
    assert len(row.token_hash) == 64


async def test_refresh_token_hash_cannot_authenticate_directly(api):
    """A hash leaked from the DB cannot be used as a refresh token."""
    email, reg = await _register(api, "hashauth")

    from app.platform import db as database

    engine = database.get_engine()
    assert engine is not None
    # fetch the hash through the admin engine (test-only path)
    from sqlalchemy import text as t

    async with engine.connect() as conn:
        token_hash = (
            await conn.execute(
                t(
                    "select s.token_hash from refresh_sessions s join users u on u.id=s.user_id "
                    "where u.email = :e"
                ),
                {"e": email},
            )
        ).scalar_one()
    # Using the HASH as a token must fail (hash ≠ preimage).
    from app.identity import service
    from app.platform.errors import AuthenticationError

    with pytest.raises(AuthenticationError):
        await service.refresh_session(token_hash)


async def test_client_identity_headers_never_authenticate(api):
    """X-User-ID / X-Admin / X-Role must never act as authentication."""
    headers_variants = [
        {"X-User-ID": str(uuid_mod.uuid4()), "X-Role": "admin"},
        {"X-Admin": "true"},
        {"X-Role": "admin"},
    ]
    for headers in headers_variants:
        r = await api.get("/api/v1/auth/me", headers=headers)
        assert r.status_code == 401, headers
        r = await api.get("/api/v1/workspaces/me", headers=headers)
        assert r.status_code == 401, headers


async def test_user_supplied_id_cannot_override_principal(api):
    """A valid token for user A cannot be re-targeted at user B by headers."""
    email_a, reg_a = await _register(api, "victimA")
    email_b, reg_b = await _register(api, "attackerB")
    login_b = await _login(api, email_b)
    headers = {
        "Authorization": f"Bearer {login_b['access_token']}",
        "X-User-ID": reg_a["user"]["id"],  # impostor override attempt
        "X-Role": "admin",
    }
    r = await api.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == reg_b["user"]["id"]  # Principal B, not A
    assert r.json()["id"] != reg_a["user"]["id"]


async def test_jwt_private_key_never_in_responses(api):
    from app.platform.config import get_settings

    s = get_settings()
    email, reg = await _register(api, "keyleak")
    await _login(api, email)
    for path in ("/api/v1/auth/me", "/readyz", "/healthz", "/openapi.json"):
        r = await api.get(path)
        body = r.text
        assert "BEGIN PRIVATE KEY" not in body
        # The private key body (a distinctive PEM fragment) must not appear:
        priv_fragment = s.JWT_PRIVATE_KEY.split("\n")[1][:24] if s.JWT_PRIVATE_KEY else ""
        if priv_fragment:
            assert priv_fragment not in body


async def test_auth_error_bodies_leak_no_internals(api):
    r = await api.post(
        "/api/v1/auth/login",
        json={"email": f"ghost-{uuid_mod.uuid4().hex[:6]}@x.test", "password": "x" * 12},
    )
    assert r.status_code == 401
    flat = r.text.lower()
    for forbidden in ("argon", "sql", "postgres", "asyncpg", "traceback", "password_hash"):
        assert forbidden not in flat


async def test_register_rejects_role_escalation(api):
    r = await api.post(
        "/api/v1/auth/register",
        json={
            "email": f"esc-{uuid_mod.uuid4().hex[:8]}@phase2.test",
            "password": PASSWORD,
            "role": "admin",
        },
    )
    assert r.status_code == 422  # extra fields are forbidden by the schema
    login = await api.post(
        "/api/v1/auth/login",
        json={"email": f"esc-{uuid_mod.uuid4().hex[:8]}@phase2.test", "password": PASSWORD},
    )
    assert login.status_code == 401


async def test_sql_injection_in_login_is_data(api):
    r = await api.post(
        "/api/v1/auth/login",
        json={"email": "x'; DROP TABLE users; --", "password": "y'; DROP TABLE sessions; --"},
    )
    assert r.status_code == 401
    # Table still exists:
    from app.platform import db as database
    from sqlalchemy import text

    engine = database.get_engine()
    assert engine is not None
    async with engine.connect() as conn:
        n = (await conn.execute(text("select count(*) from users"))).scalar_one()
    assert n >= 0
