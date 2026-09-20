"""JWT access-token issuing and verification (ADR-0018 / ADR-0023).

Access tokens are short-lived RS256 JWTs identifying the caller. They carry
NO authorization state beyond the role string needed for coarse routing —
all authorization (ownership, project scope, row access) is enforced
server-side, with PostgreSQL RLS as the final boundary. A JWT never grants
database privileges; the DB role + RLS context do.

Claims: ``sub`` (user id), ``role``, ``sid`` (refresh-session id), ``jti``,
``iat``, ``exp``, ``iss``, ``aud``. No PII, no secrets.

Verification is strict: pinned algorithm (algorithm-confusion attacks that
swap RS256→HS256 fail because the HMAC secret would be the public key
material and the signature check fails; ``algorithms=[config]`` excludes
``none``), issuer/audience/exp/iat validated by PyJWT, and all required
claims present and well-formed — anything else raises a generic
AuthenticationError (no fingerprinting of failure causes).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt as pyjwt
from app.platform.config import Settings, get_settings
from app.platform.errors import AuthenticationError
from app.platform.security import Principal

_CLAIMS_KEYS = ("sub", "role", "sid", "jti")
_ROLE_VALUES = ("learner", "admin")


def issue_access_token(
    *,
    user_id: str,
    role: str,
    session_id: str,
    settings: Settings | None = None,
) -> tuple[str, datetime]:
    """Sign an RS256 access token. Returns (token, expires_at)."""
    s = settings or get_settings()
    if not s.JWT_PRIVATE_KEY:
        raise RuntimeError("JWT_PRIVATE_KEY is not configured")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=s.JWT_ACCESS_TTL_SECONDS)
    claims: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "sid": session_id,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expires_at,
        "iss": s.JWT_ISSUER,
        "aud": s.JWT_AUDIENCE,
    }
    token = pyjwt.encode(claims, s.JWT_PRIVATE_KEY, algorithm=s.JWT_ALGORITHM)
    return token, expires_at


def verify_access_token_claims(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Strict verification returning the validated claims dict.

    Every failure path raises the SAME generic 401 (no cause leaking).
    """
    s = settings or get_settings()
    if not s.JWT_PUBLIC_KEY:
        raise AuthenticationError("Unauthorized")
    try:
        claims: dict[str, Any] = pyjwt.decode(
            token,
            s.JWT_PUBLIC_KEY,
            algorithms=[s.JWT_ALGORITHM],  # pinned — rejects none/HS confusion
            issuer=s.JWT_ISSUER,
            audience=s.JWT_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            leeway=5,
        )
    except pyjwt.PyJWTError:
        raise AuthenticationError("Unauthorized") from None

    # Required custom claims, well-formed only.
    for key in _CLAIMS_KEYS:
        value = claims.get(key)
        if not isinstance(value, str) or not value:
            raise AuthenticationError("Unauthorized")
    if claims["role"] not in _ROLE_VALUES:
        raise AuthenticationError("Unauthorized")
    try:
        uuid.UUID(claims["sub"])
        uuid.UUID(claims["sid"])
    except ValueError:
        raise AuthenticationError("Unauthorized") from None
    return claims


def verify_access_token(token: str, settings: Settings | None = None) -> Principal:
    """Verify signature + all claims and construct the Principal."""
    claims = verify_access_token_claims(token, settings)
    return Principal(
        user_id=claims["sub"],
        role=claims["role"],
        session_id=claims["sid"],
    )
