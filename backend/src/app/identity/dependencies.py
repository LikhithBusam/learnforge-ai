"""FastAPI authentication dependencies (Phase 2).

* ``CurrentPrincipal`` — Authorization: Bearer <JWT> → verified ``Principal``.
  Identity comes ONLY from the verified token; client-supplied identity
  headers are never consulted (Part 12).
* ``denylist`` — logout denylists the access token's ``jti`` in Redis until
  natural expiry (ADR-0018). Availability posture: if Redis is unavailable we
  FAIL OPEN with a logged warning — the denylist accelerates revocation but
  the hard control is refresh-session revocation in the DB, which always
  applies (documented in docs/security/authentication.md).
* ``refresh_token_from`` — extracts the opaque refresh token from the
  HttpOnly cookie with the non-ambient X-Request-With header check
  (ADR-0018 belt-and-braces CSRF guard).
* ``require_admin`` — coarse RBAC gate for admin capabilities.
"""

from __future__ import annotations

import time
from typing import Annotated

from app.identity import tokens
from app.platform import cache
from app.platform.config import get_settings
from app.platform.errors import AuthenticationError
from app.platform.logging import get_logger
from app.platform.security import Principal
from fastapi import Depends, Request, Response

logger = get_logger(__name__)

REFRESH_COOKIE = "studycompanion_refresh"
CSRF_HEADER = "X-Request-With"
_CSRF_EXPECTED = "studycompanion"

_DENYLIST_PREFIX = "auth:denylist:jti:"


def decode_verified(token: str) -> tuple[str, str, int]:
    """(jti, sid, exp) from a strictly verified token (401 on anything else)."""
    claims = tokens.verify_access_token_claims(token)
    return str(claims["jti"]), str(claims["sid"]), int(claims["exp"])


async def denylist_jti(jti: str, exp: int) -> bool:
    """Denylist until the token's natural expiry (+margin). Returns success."""
    ttl = max(1, exp - int(time.time()) + 60)
    try:
        await cache.set_json(f"{_DENYLIST_PREFIX}{jti}", {"d": True}, ttl_seconds=ttl)
        return True
    except Exception:  # noqa: BLE001 - denylist is acceleration, not control
        logger.warning("auth_denylist_unavailable", extra={"details": {}})
        return False


async def is_jti_denylisted(jti: str) -> bool:
    try:
        entry = await cache.get_json(f"{_DENYLIST_PREFIX}{jti}")
        return bool(entry)
    except Exception:  # noqa: BLE001
        return False


async def get_current_principal(request: Request) -> Principal:
    """Bearer-token authentication dependency (identity from verified JWT only)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AuthenticationError("Unauthorized")
    token = auth[len("Bearer ") :].strip()
    if not token:
        raise AuthenticationError("Unauthorized")
    principal = tokens.verify_access_token(token)  # generic 401 on any failure
    jti, _sid, _exp = decode_verified(token)
    if await is_jti_denylisted(jti):
        logger.info(
            "auth_token_rejected",
            extra={"details": {"event": "denylist_hit", "user_id": principal.user_id}},
        )
        raise AuthenticationError("Unauthorized")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def set_refresh_cookie(response: Response, raw_token: str, expires_at) -> None:  # type: ignore[no-untyped-def]
    from datetime import datetime

    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw_token,
        httponly=True,
        secure=get_settings().REFRESH_COOKIE_SECURE,
        samesite="strict",
        path="/api/v1/auth",
        expires=expires_at if isinstance(expires_at, datetime) else None,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/v1/auth")


async def refresh_token_from(request: Request) -> str:
    """Opaque refresh token from the HttpOnly cookie + non-ambient header check.

    The refresh token is NOT accepted from headers/body (ADR-0018: the only
    cookie-authenticated flow; the API is otherwise Bearer-based).
    """
    if request.headers.get(CSRF_HEADER) != _CSRF_EXPECTED:
        raise AuthenticationError("Unauthorized")
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise AuthenticationError("Unauthorized")
    return raw


async def require_admin(principal: CurrentPrincipal) -> Principal:
    """Coarse RBAC gate; fine-grained posture (404 concealment) is applied by
    the routes/services via resolve_role_or_404."""
    from app.platform.errors import AuthorizationError

    if not principal.is_admin:
        raise AuthorizationError("Forbidden")
    return principal


AdminPrincipal = Annotated[Principal, Depends(require_admin)]
