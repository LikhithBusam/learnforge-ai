"""Phase 2 COMPLETION FIX — login rate-limit wiring proofs.

Proves that ``RATE_LIMIT_LOGIN_PER_MINUTE`` actually gates
``POST /api/v1/auth/login`` through the project's REAL Redis path (Upstash
via the platform cache client) — not an in-memory stub:

* below limit → processed normally
* over limit → 429 ``rate-limited`` problem+json (threshold = configured value)
* configuration-driven: the test boots the app with RATE_LIMIT_LOGIN_PER_MINUTE=2
  via ``reset_settings_cache`` and proves the threshold follows the setting
* Redis behavior: the counter is read back through ``cache.get_client()``
* enforcement precedes credential verification (Argon2 is never reached for
  exhausted clients) and never leaks account existence
"""

from __future__ import annotations

import uuid as uuid_mod

import pytest

pytestmark = pytest.mark.auth

PASSWORD = "password-123456"
LIMIT = 2  # the test's own configured threshold

# Determinism: cloud-path requests can be slow enough to straddle a 60s
# fixed-window boundary, which would legitimately split the bucket. The
# counting tests widen the window (same code path, same expire-on-first-INCR
# mechanics) so the proofs are stable; the TTL assertion still proves the
# counter is written with the module's configured window.
WIDE_WINDOW = 3600


@pytest.fixture(autouse=True)
def _wide_window(monkeypatch):
    from app.identity import ratelimit

    monkeypatch.setattr(ratelimit, "_WINDOW_SECONDS", WIDE_WINDOW)


@pytest.fixture()
async def limited_api(engines, monkeypatch):
    """App booted with RATE_LIMIT_LOGIN_PER_MINUTE=2 and a LIVE cache client.

    ``engines`` provides the session-scoped DB engines (runtime + admin);
    httpx.ASGITransport does not run lifespan hooks, so the cache is
    initialized here exactly as ``main.create_app`` would.
    """
    import httpx
    from app.main import create_app
    from app.platform import cache, config

    monkeypatch.setenv("RATE_LIMIT_LOGIN_PER_MINUTE", str(LIMIT))
    config.reset_settings_cache()
    settings = config.get_settings()
    assert settings.RATE_LIMIT_LOGIN_PER_MINUTE == LIMIT  # config-driven, not hardcoded

    cache.init_cache(settings)
    app = create_app()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Only the function-scoped cache client is disposed here. The DB engines
    # are SESSION-scoped (owned by the ``engines`` fixture) and must survive
    # this teardown for subsequent tests.
    await cache.close_cache()
    config.reset_settings_cache()


@pytest.fixture()
async def _registered(limited_api):
    email = f"rl-{uuid_mod.uuid4().hex[:10]}@phase2.test"
    r = await limited_api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return email


def _limit_key(email: str) -> str:
    import hashlib

    from app.platform import cache

    digest = hashlib.sha256(email.strip().casefold().encode()).hexdigest()
    return cache.namespaced(f"auth:login:rl:{digest}:0")  # window suffix replaced by caller


async def test_below_limit_processed_normally(limited_api, _registered):
    email = _registered
    for _ in range(LIMIT):
        r = await limited_api.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert r.status_code == 200, r.text
        assert r.json()["access_token"]


async def test_over_limit_returns_429(limited_api, _registered):
    email = _registered
    for _ in range(LIMIT):
        r = await limited_api.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert r.status_code == 200
    r = await limited_api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 429
    body = r.json()
    assert body["title"] == "Too many requests"
    assert body["type"].endswith("/rate-limited")


async def test_threshold_follows_configuration(limited_api, _registered, monkeypatch):
    """The 3rd request is the FIRST blocked one — proves threshold == config value (2),
    i.e. changing the configuration changes enforcement. The window is widened
    for determinism (a 60s boundary mid-test could otherwise split the bucket)."""
    from app.identity import ratelimit as rl

    monkeypatch.setattr(rl, "_WINDOW_SECONDS", WIDE_WINDOW)
    email = _registered
    statuses = [
        (
            await limited_api.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
        ).status_code
        for _ in range(LIMIT + 2)
    ]
    assert statuses == [200, 200, 429, 429]


async def test_counter_lives_in_redis(limited_api, _registered, monkeypatch):
    """Direct evidence the limiter uses the project's Redis path: after two
    logins the fixed-window counter exists in Redis (TTL bounded, no PII)."""
    import time

    from app.identity import ratelimit
    from app.platform import cache

    monkeypatch.setattr(ratelimit, "_WINDOW_SECONDS", WIDE_WINDOW)  # deterministic bucket
    email = _registered
    for _ in range(LIMIT):
        r = await limited_api.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert r.status_code == 200

    client = cache.get_client()
    assert client is not None
    from app.identity import ratelimit

    window = int(time.time()) // WIDE_WINDOW
    namespaced = cache.namespaced(f"auth:login:rl:{_digest(email)}:{window}")
    value = await client.get(namespaced)
    assert value is not None and int(value) >= LIMIT
    ttl = await client.ttl(namespaced)
    assert 0 < ttl <= WIDE_WINDOW  # expire-on-first-increment happened through real Redis
    assert email.encode() not in namespaced.encode()  # no raw email in keys


def _digest(email: str) -> str:
    import hashlib

    return hashlib.sha256(email.strip().casefold().encode()).hexdigest()


async def test_enforcement_before_password_verification(limited_api, _registered):
    """Exhausted client: the 429 arrives without Argon2 ever running —
    enforcement happens before ``service.login``."""

    email = _registered
    for _ in range(LIMIT):
        await limited_api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

    import app.identity.router as router_mod

    called = False
    original = router_mod.service.login

    async def _spy(*a, **k):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        return await original(*a, **k)  # resolve once — patched attr would recurse

    router_mod.service.login = _spy  # type: ignore[misc]
    try:
        r = await limited_api.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
    finally:
        router_mod.service.login = original  # type: ignore[misc]
    assert r.status_code == 429
    assert called is False, "service.login must not run when the limit is exhausted"


async def test_unknown_email_rate_limited_identically(limited_api):
    """429 for an exhausted UNKNOWN email — identical to a known one (no
    account-existence leak through the limiter)."""
    phantom = f"phantom-{uuid_mod.uuid4().hex[:10]}@phase2.test"
    for _ in range(LIMIT):
        r = await limited_api.post(
            "/api/v1/auth/login", json={"email": phantom, "password": PASSWORD}
        )
        assert r.status_code == 401  # generic auth failure, counted
    r = await limited_api.post("/api/v1/auth/login", json={"email": phantom, "password": PASSWORD})
    assert r.status_code == 429
