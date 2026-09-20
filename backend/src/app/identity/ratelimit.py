"""Login rate limiting — fixed-window Redis counter (Phase 2 completion fix).

Wires the pre-existing ``RATE_LIMIT_LOGIN_PER_MINUTE`` setting to
``POST /api/v1/auth/login`` (it was configured but unwired — caught by the
Phase 2 honesty check). Deliberately NOT a rate-limiting framework: one
function, one Redis key family.

Design:
* Key: ``auth:login:rl:{sha256(canonical_email)}:{unix_minute}`` — the raw
  email is never stored in Redis (SHA-256 only: bounded key length, no PII,
  no credentials), and buckets expire on their own (bounded cardinality).
* Window: fixed 60-second bucket; the TTL is set on the first increment so
  idle buckets disappear without a sweeper.
* Identity: the normalized login identifier submitted in the request body —
  never a client-provided header (``X-User-ID``/``X-Admin``/``X-Role`` are
  ignored everywhere).
* Enforcement runs BEFORE credential verification: exhausted clients never
  trigger Argon2 work, and the 429 is identical whether or not the email
  exists (no account-existence leak).
* Availability: Redis is loss-tolerant infrastructure (ADR-0014) and the
  limiter is abuse mitigation, not a correctness control — when Redis is
  unavailable the limiter FAILS OPEN with a logged warning (same posture as
  the logout denylist in ``identity/dependencies.py``).
"""

from __future__ import annotations

import hashlib
import time

from app.platform.logging import get_logger

logger = get_logger(__name__)

_WINDOW_SECONDS = 60
_KEY_PREFIX = "auth:login:rl:"


def _key(identifier: str) -> str:
    from app.platform import cache

    canonical = identifier.strip().casefold()
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    window = int(time.time()) // _WINDOW_SECONDS
    return cache.namespaced(f"{_KEY_PREFIX}{digest}:{window}")


async def enforce_login_limit(identifier: str) -> None:
    """Raise ``RateLimitedError`` when the configured per-minute limit is exceeded.

    ``RATE_LIMIT_LOGIN_PER_MINUTE`` is read at call time (config-driven; a
    value of 0 disables limiting). Fail-open when Redis is unavailable
    (documented ADR-0014 posture).
    """
    from app.platform import cache
    from app.platform.config import get_settings
    from app.platform.errors import RateLimitedError

    limit = get_settings().RATE_LIMIT_LOGIN_PER_MINUTE
    if limit <= 0:
        return  # disabled by configuration
    client = cache.get_client()
    if client is None:
        logger.warning(
            "auth_login_ratelimit_unavailable",
            extra={"details": {"event": "ratelimit_unavailable"}},
        )
        return
    key = _key(identifier)
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, _WINDOW_SECONDS)
    except Exception:  # noqa: BLE001 - fail open, same as the denylist
        logger.warning(
            "auth_login_ratelimit_error", extra={"details": {"event": "ratelimit_unavailable"}}
        )
        return
    if count > limit:
        logger.info(
            "auth_login_ratelimited",
            extra={"details": {"event": "ratelimit_hit", "outcome": "limited"}},
        )
        raise RateLimitedError("Too many requests")
