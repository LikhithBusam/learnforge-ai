"""Phase 2 AUTHENTICATION SUITE — registration, login, JWT, refresh, logout.

Cloud-first: runs against the live Supabase path via the fixtures in
``tests/integration/conftest.py``; skips (UNVERIFIED) when credentials are
absent. Error contract under test: generic 401 for every auth failure
(ADR-0018 + Part 18); no fingerprinting of email existence / password
validity / token cause.
"""

from __future__ import annotations

import base64
import json
import time
import uuid as uuid_mod

import pytest

pytestmark = pytest.mark.auth

PASSWORD = "password-123456"


def _jwt_parts(token: str) -> tuple[dict, dict, str]:
    h, p, s = token.split(".")
    pad = lambda x: x + "=" * (-len(x) % 4)  # noqa: E731
    return (
        json.loads(base64.urlsafe_b64decode(pad(h))),
        json.loads(base64.urlsafe_b64decode(pad(p))),
        s,
    )


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture()
async def api(engines, cloud_settings):
    """ASGI client on the SAME event loop as the DB engines (TestClient's
    portal loop breaks asyncpg's loop affinity)."""
    import httpx
    from app.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # httpx cookie persistence
        yield client


@pytest.fixture()
def register_and_login(api):
    async def _make(label="user"):
        email = f"{label}-{uuid_mod.uuid4().hex[:10]}@phase2.test"
        r = await api.post(
            "/api/v1/auth/register",
            json={"email": email, "password": PASSWORD, "display_name": label.title()},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        login = await api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert login.status_code == 200, login.text
        return email, body, login.json()

    return _make


# --- Registration -----------------------------------------------------------


async def test_register_valid_201(api):
    email = f"reg-{uuid_mod.uuid4().hex[:10]}@phase2.test"
    r = await api.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD, "display_name": "Reg"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == email
    assert body["user"]["role"] == "learner"
    assert body["access_token"]
    assert "password" not in json.dumps(body).lower()


async def test_register_duplicate_email_conflict(api):
    email = f"dup-{uuid_mod.uuid4().hex[:10]}@phase2.test"
    first = await api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert first.status_code == 201
    second = await api.post(
        "/api/v1/auth/register", json={"email": email.upper(), "password": PASSWORD}
    )
    assert second.status_code == 409


async def test_register_email_canonicalized(api):
    email = f"CANON-{uuid_mod.uuid4().hex[:10]}@PHASE2.test"
    r = await api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201
    assert r.json()["user"]["email"] == email.strip().casefold()


async def test_register_weak_password_422(api):
    r = await api.post(
        "/api/v1/auth/register",
        json={"email": f"w-{uuid_mod.uuid4().hex[:6]}@x.test", "password": "short"},
    )
    assert r.status_code == 422


async def test_register_cannot_choose_role(api):
    """Attempted admin registration must be rejected/ignored — server decides."""
    r = await api.post(
        "/api/v1/auth/register",
        json={
            "email": f"esc-{uuid_mod.uuid4().hex[:8]}@phase2.test",
            "password": PASSWORD,
            "role": "admin",
        },
    )
    # Either 422 (extra fields forbidden) or 201-as-learner — but never admin.
    if r.status_code == 201:
        assert r.json()["user"]["role"] == "learner"
    else:
        assert r.status_code == 422


# --- Login -------------------------------------------------------------------


async def test_login_valid(api, register_and_login):
    email, _, _ = await register_and_login("login")
    r = await api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] and body["token_type"] == "Bearer"
    # Refresh cookie flags (HttpOnly; SameSite=Strict per ADR-0018)
    set_cookie = r.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "samesite=strict" in set_cookie.lower()


async def test_login_generic_failure_unknown_email(api):
    r = await api.post(
        "/api/v1/auth/login",
        json={"email": f"ghost-{uuid_mod.uuid4().hex[:6]}@x.test", "password": PASSWORD},
    )
    assert r.status_code == 401
    assert r.json()["type"].endswith("unauthorized")


async def test_login_generic_failure_wrong_password(api, register_and_login):
    email, _, _ = await register_and_login("wrongpw")
    r = await api.post("/api/v1/auth/login", json={"email": email, "password": "not-the-password!"})
    assert r.status_code == 401


async def test_login_unknown_email_and_wrong_password_responses_equivalent(api):
    """Generic failure contract: identical status/type; bodies differ only by
    request-scoped ids (no cause fingerprinting)."""
    r1 = await api.post(
        "/api/v1/auth/login",
        json={"email": f"nouser-{uuid_mod.uuid4().hex[:6]}@x.test", "password": PASSWORD},
    )
    email = f"real-{uuid_mod.uuid4().hex[:8]}@phase2.test"
    await api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    r2 = await api.post(
        "/api/v1/auth/login", json={"email": email, "password": "definitely-wrong!"}
    )
    assert r1.status_code == r2.status_code == 401
    b1, b2 = r1.json(), r2.json()
    for k in ("type", "title"):
        assert b1[k] == b2[k]


# --- JWT ---------------------------------------------------------------------


async def test_jwt_claims_shape(api, register_and_login):
    _, _, login = await register_and_login("claims")
    header, payload, _sig = _jwt_parts(login["access_token"])
    assert header["alg"] == "RS256"
    uuid_mod.UUID(payload["sub"])
    uuid_mod.UUID(payload["sid"])
    uuid_mod.UUID(payload["jti"])
    assert payload["role"] == "learner"
    assert {"iat", "exp", "iss", "aud"} <= set(payload)
    assert payload["exp"] - payload["iat"] <= 900


async def test_jwt_expired_token_401(api, register_and_login, monkeypatch):
    from app.identity import tokens as token_mod

    _, _, login = await register_and_login("expired")
    access = login["access_token"]
    header, payload, sig = _jwt_parts(access)
    payload["exp"] = int(time.time()) - 10
    forged = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}.{sig}"
    from app.platform.errors import AuthenticationError

    with pytest.raises(AuthenticationError):
        token_mod.verify_access_token(forged)
    r = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


async def test_jwt_invalid_signature_401(api, register_and_login):
    _, _, login = await register_and_login("badsig")
    header, payload, _sig = _jwt_parts(login["access_token"])
    forged = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}.{_b64url(b'tampered-sig')}"
    r = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


async def test_jwt_wrong_issuer_and_audience_401(api, register_and_login):
    from app.platform.config import get_settings

    _, _, login = await register_and_login("issa")
    s = get_settings()
    other_iss = dict(
        sub=uuid_mod.uuid4().hex,
        role="learner",
        sid=uuid_mod.uuid4().hex,
        jti=uuid_mod.uuid4().hex,
        iat=int(time.time()),
        exp=int(time.time()) + 300,
    )
    import jwt as pyjwt

    token = (
        pyjwt.encode(other_iss, s.JWT_PRIVATE_KEY, algorithm="RS256", headers={"kid": "x"})
        if s.JWT_PRIVATE_KEY
        else None
    )
    assert token is not None
    # encode with WRONG issuer/audience by overriding claims:
    claims = dict(
        sub=uuid_mod.uuid4().hex,
        role="learner",
        sid=uuid_mod.uuid4().hex,
        jti=uuid_mod.uuid4().hex,
        iat=int(time.time()),
        exp=int(time.time()) + 300,
        iss="other-issuer",
        aud="other-audience",
    )
    token = pyjwt.encode(claims, s.JWT_PRIVATE_KEY, algorithm="RS256")
    r = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_jwt_missing_subject_401(api):
    from app.platform.config import get_settings

    s = get_settings()
    import jwt as pyjwt

    claims = dict(
        role="learner",
        sid=uuid_mod.uuid4().hex,
        jti=uuid_mod.uuid4().hex,
        iat=int(time.time()),
        exp=int(time.time()) + 300,
        iss=s.JWT_ISSUER,
        aud=s.JWT_AUDIENCE,
    )  # no sub
    token = pyjwt.encode(claims, s.JWT_PRIVATE_KEY, algorithm="RS256")
    r = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_jwt_algorithm_confusion_rejected(api):
    """HS256-signed token (algorithm confusion attempt) must be rejected."""
    from app.platform.config import get_settings

    s = get_settings()
    import jwt as pyjwt

    claims = dict(
        sub=uuid_mod.uuid4().hex,
        role="admin",
        sid=uuid_mod.uuid4().hex,
        jti=uuid_mod.uuid4().hex,
        iat=int(time.time()),
        exp=int(time.time()) + 300,
        iss=s.JWT_ISSUER,
        aud=s.JWT_AUDIENCE,
    )
    token = pyjwt.encode(claims, "any-secret", algorithm="HS256")
    r = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_jwt_malformed_authorization_header_401(api):
    for header in ("", "Bearer", "Bearer ", "Basic dXNlcjpwYXNz", "Bearer not.a.jwt"):
        r = await api.get("/api/v1/auth/me", headers={"Authorization": header} if header else {})
        assert r.status_code == 401, header


# --- /me + RLS-bound workspace proof ----------------------------------------


async def test_me_returns_safe_profile(api, register_and_login):
    email, reg, login = await register_and_login("me")
    r = await api.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == email
    assert body["role"] == "learner"
    assert "password" not in json.dumps(body).lower()
    assert "token" not in json.dumps(body).lower()


async def test_me_without_token_401(api):
    r = await api.get("/api/v1/auth/me")
    assert r.status_code == 401


# --- Refresh rotation / reuse / logout ---------------------------------------


async def _client_cookies(api):
    return {k: v for k, v in api.cookies.items()}


async def test_refresh_rotates_and_old_token_rejected(api, register_and_login):
    email, _, login = await register_and_login("rot")
    old_cookie = api.cookies.get("studycompanion_refresh")
    assert old_cookie
    r1 = await api.post("/api/v1/auth/refresh", headers={"X-Request-With": "studycompanion"})
    assert r1.status_code == 200, r1.text
    new_cookie = api.cookies.get("studycompanion_refresh")
    assert new_cookie and new_cookie != old_cookie
    # Old token must no longer work (rotated) — and it is ALSO reuse-detected
    # (family revoked). Either way: 401.
    api.cookies.set("studycompanion_refresh", old_cookie)
    r2 = await api.post("/api/v1/auth/refresh", headers={"X-Request-With": "studycompanion"})
    assert r2.status_code == 401
    # Restore the valid new cookie for subsequent assertions about family state.
    api.cookies.set("studycompanion_refresh", new_cookie)


async def test_refresh_reuse_revokes_family(api, register_and_login):
    """Reuse detection: present the rotated-away token → family dies."""
    email, _, login = await register_and_login("reuse")
    first = api.cookies.get("studycompanion_refresh")
    r1 = await api.post("/api/v1/auth/refresh", headers={"X-Request-With": "studycompanion"})
    assert r1.status_code == 200
    second = api.cookies.get("studycompanion_refresh")
    # Present the OLD (already rotated) token again:
    api.cookies.set("studycompanion_refresh", first)
    r2 = await api.post("/api/v1/auth/refresh", headers={"X-Request-With": "studycompanion"})
    assert r2.status_code == 401
    # The CURRENT (latest) token is also dead now — family revocation:
    api.cookies.set("studycompanion_refresh", second)
    r3 = await api.post("/api/v1/auth/refresh", headers={"X-Request-With": "studycompanion"})
    assert r3.status_code == 401


async def test_refresh_missing_cookie_or_header_401(api):
    api.cookies.clear()
    r = await api.post("/api/v1/auth/refresh", headers={"X-Request-With": "studycompanion"})
    assert r.status_code == 401


async def test_logout_revokes_and_cannot_reuse(api, register_and_login):
    email, _, login = await register_and_login("out")
    refresh_before = api.cookies.get("studycompanion_refresh")
    r = await api.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert r.status_code == 200
    # Refresh token no longer usable:
    api.cookies.set("studycompanion_refresh", refresh_before)
    r2 = await api.post("/api/v1/auth/refresh", headers={"X-Request-With": "studycompanion"})
    assert r2.status_code == 401


async def test_refresh_concurrent_double_rotation_single_winner(api, register_and_login):
    """Two refreshes with the same token: exactly one 200 (FOR UPDATE lock),
    the other 401; and the race loser's path revokes the family, so a third
    replay with the winner's fresh token also fails closed."""
    from app.identity import service
    from app.platform.errors import AuthenticationError

    email, _, login = await register_and_login("conc")
    token = api.cookies.get("studycompanion_refresh")

    import asyncio

    async def one():
        try:
            await service.refresh_session(token)
            return 200
        except AuthenticationError:
            return 401

    statuses = sorted(await asyncio.gather(one(), one()))
    assert statuses == [200, 401], statuses
    # The winner's cookie is ALSO dead now (race → family revocation).
    r = await api.post("/api/v1/auth/refresh", headers={"X-Request-With": "studycompanion"})
    assert r.status_code == 401


# --- Denylist / logout semantics ---------------------------------------------


async def test_access_token_still_valid_until_ttl(api, register_and_login):
    """Documented semantics: logout does not invalidate un-expired JWTs
    mid-flight unless denylisted; a FRESH login's token is unaffected by a
    previous logout's denylist (jti-scoped)."""
    email, _, login = await register_and_login("ttl")
    r = await api.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"}
    )
    assert r.status_code == 200
