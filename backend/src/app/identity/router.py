"""Auth API — /api/v1/auth (Phase 2, Part 9/10/14/15).

Error contract (Part 18): every authentication failure is a generic 401
`unauthorized` problem document — no fingerprinting of email existence,
password validity, token expiry vs. signature, or session state.

Cookies: the opaque refresh token is set as HttpOnly; SameSite=Strict on the
/auth path (ADR-0018). /refresh additionally requires the non-ambient
X-Request-With header (CSRF belt-and-braces). The API is otherwise
Bearer-header based.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.identity import dependencies as auth_deps
from app.identity import ratelimit, service
from app.identity.tokens import issue_access_token
from app.platform.errors import AuthenticationError
from app.platform.logging import get_logger
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    # extra="forbid": a client sending {"role": "admin"} (or ANY unmodeled
    # field) gets 422 — privilege-escalation attempts are rejected, never
    # silently ignored (Part 10/21).
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class UserBody(BaseModel):
    id: str
    email: str
    display_name: str | None
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserBody


def _user_body(user: service.RegisteredUser) -> UserBody:
    return UserBody(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )


def _expires_in(expires_at: datetime) -> int:
    return max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))


@router.post("/register", status_code=201)
async def register(payload: RegisterRequest, response: Response) -> TokenResponse:
    user = await service.register_user(
        email=payload.email, password=payload.password, display_name=payload.display_name
    )
    created = await service.create_refresh_session(user.id)
    access, _ = issue_access_token(
        user_id=str(user.id), role=user.role, session_id=str(created.session_id)
    )
    auth_deps.set_refresh_cookie(response, created.raw_token, created.expires_at)
    logger.info(
        "auth_register",
        extra={"details": {"event": "register", "user_id": str(user.id)}},
    )
    return TokenResponse(
        access_token=access,
        expires_in=_expires_in(created.expires_at),
        user=_user_body(user),
    )


@router.post("/login")
async def login(payload: LoginRequest, response: Response) -> TokenResponse:
    # Abuse mitigation BEFORE any credential work: Redis fixed-window counter
    # keyed on the normalized login identifier (RATE_LIMIT_LOGIN_PER_MINUTE).
    await ratelimit.enforce_login_limit(payload.email)
    user, created = await service.login(email=payload.email, password=payload.password)
    access, _ = issue_access_token(
        user_id=str(user.id), role=user.role, session_id=str(created.session_id)
    )
    auth_deps.set_refresh_cookie(response, created.raw_token, created.expires_at)
    return TokenResponse(
        access_token=access,
        expires_in=_expires_in(created.expires_at),
        user=_user_body(user),
    )


@router.post("/refresh")
async def refresh(request: Request, response: Response) -> TokenResponse:
    raw = await auth_deps.refresh_token_from(request)  # cookie + CSRF header
    rotated = await service.refresh_session(raw)
    access, _ = issue_access_token(
        user_id=str(rotated.user_id),
        role=rotated.role,
        session_id=str(rotated.new_session_id),
    )
    auth_deps.set_refresh_cookie(response, rotated.raw_token, rotated.expires_at)
    return TokenResponse(
        access_token=access,
        expires_in=_expires_in(rotated.expires_at),
        user=UserBody(
            id=str(rotated.user_id),
            email="",  # minimal response: identity re-provable via /me
            display_name=None,
            role=rotated.role,
        ),
    )


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    principal = await auth_deps.get_current_principal(request)
    raw = request.cookies.get(auth_deps.REFRESH_COOKIE)
    revoked = False
    if raw:
        revoked = await service.logout(raw, user_id=uuid.UUID(principal.user_id))
    # Denylist the presented ACCESS token's jti until natural expiry
    # (best-effort: Redis unavailability must not fail a logout).
    access_header = request.headers.get("Authorization", "")
    if access_header.startswith("Bearer "):
        try:
            jti, _sid, exp = auth_deps.decode_verified(access_header[len("Bearer ") :].strip())
            await auth_deps.denylist_jti(jti, exp)
        except AuthenticationError:
            pass  # expired/invalid access token: nothing to denylist
        except Exception:  # noqa: BLE001 - logout must succeed regardless
            logger.warning("auth_logout_denylist_skipped", extra={"details": {}})
    auth_deps.clear_refresh_cookie(response)
    logger.info(
        "auth_logout",
        extra={
            "details": {
                "event": "logout",
                "user_id": principal.user_id,
                "session_revoked": revoked,
            }
        },
    )
    return {"status": "logged_out", "session_revoked": revoked}


@router.get("/me")
async def me(principal: auth_deps.CurrentPrincipal) -> dict:
    user = await service.get_user(uuid.UUID(principal.user_id))
    if user is None:
        raise AuthenticationError("Unauthorized")
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
    }
