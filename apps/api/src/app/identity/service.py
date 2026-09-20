"""Identity service — registration, login, rotation, logout (Phase 2).

Transaction ownership: every public method opens exactly one
`db.session_scope` transaction (Part 11) — the unit of work is the service
operation, which is what the future outbox requires (state + event rows
committed atomically in the same scope).

RLS context: the service binds `app.current_user_id` for every operation on
the runtime engine. Registration/login bootstrap: the id is generated
application-side (UUIDv7) and the context is bound to it BEFORE the insert so
the row-level WITH CHECK (`id = app_user_id()`) passes for the actor's own
row — no privileged role involved.

Rotation (Part 7/8): revoke-old + insert-new happen in ONE transaction with
a `FOR UPDATE` lock on the presented session — concurrent refreshes of the
same session serialize; the loser sees the row revoked and fails. Reuse of a
revoked token revokes the WHOLE family (token-theft detection, ADR-0018).

Email canonicalization (ADR-0018): trim + casefold before persist/lookup;
DB-level case-insensitive uniqueness is the enforcement backstop.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.identity import repository as repo
from app.platform import db as database
from app.platform import security
from app.platform.config import get_settings
from app.platform.errors import AuthenticationError, ConflictError, ValidationError
from app.platform.ids import uuid7
from app.platform.logging import get_logger
from sqlalchemy.exc import IntegrityError

logger = get_logger(__name__)


@dataclass(frozen=True)
class RegisteredUser:
    id: uuid.UUID
    email: str
    display_name: str | None
    role: str
    status: str


def _canonical_email(email: str) -> str:
    return email.strip().casefold()


PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 1024  # DoS guard: Argon2 cost applies to long inputs too


async def register_user(
    *, email: str, password: str, display_name: str | None = None
) -> RegisteredUser:
    """Public registration path: ALWAYS creates a learner.

    There is intentionally no role parameter — self-service admin creation
    would be a privilege-escalation seam. Admin accounts are provisioned by
    the bootstrap script only (Part 16)."""
    canonical = _canonical_email(email)
    if not canonical or "@" not in canonical or len(canonical) > 320:
        raise ValidationError("Invalid email")
    _validate_password(password)
    password_hash = security.hash_password(password)
    user_id = uuid7()
    role = "learner"
    async with database.session_scope(user_id=str(user_id)) as session:
        users = repo.UserRepository(session)
        # Dedup enforcement IS the database constraint (uq_users_email_lower):
        # a plain SELECT cannot see other users' rows under the new user's RLS
        # context, so the unique index is the authoritative backstop. The
        # IntegrityError is translated to the domain ConflictError (409).
        try:
            record = await users.create(
                id=user_id,
                email=canonical,
                password_hash=password_hash,
                role=role,
                display_name=(display_name or "").strip() or None,
            )
        except IntegrityError as exc:
            raise ConflictError("Email already registered") from exc
        return RegisteredUser(
            id=record.id,
            email=record.email,
            display_name=record.display_name,
            role=record.role,
            status=record.status,
        )


def _validate_password(password: str) -> None:
    """Reasonable policy per Part 11 — length bounds only; no complexity theater."""
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LENGTH:
        raise ValidationError("Password too short")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValidationError("Password too long")


async def get_user(user_id: uuid.UUID) -> RegisteredUser | None:
    async with database.session_scope(user_id=str(user_id)) as session:
        record = await repo.UserRepository(session).get_by_id(user_id)
        if record is None:
            return None
        return RegisteredUser(
            id=record.id,
            email=record.email,
            display_name=record.display_name,
            role=record.role,
            status=record.status,
        )


@dataclass(frozen=True)
class CreatedSession:
    session_id: uuid.UUID
    raw_token: str  # returned ONCE to the caller; only the hash is stored
    expires_at: datetime


async def create_refresh_session(
    user_id: uuid.UUID, *, ttl: timedelta | None = None
) -> CreatedSession:
    """Create a fresh rotation family (used by login and tests)."""
    if ttl is None:
        ttl = timedelta(days=get_settings().REFRESH_TTL_DAYS)
    raw = security.new_refresh_token()
    token_hash = security.hash_refresh_token(raw)
    expires_at = datetime.now(timezone.utc) + ttl
    async with database.session_scope(user_id=str(user_id)) as session:
        record = await repo.RefreshSessionRepository(session).create(
            user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
        return CreatedSession(session_id=record.id, raw_token=raw, expires_at=expires_at)


# --- Login --------------------------------------------------------------


async def login(*, email: str, password: str) -> tuple[RegisteredUser, CreatedSession]:
    """Credential verification + session creation. Generic 401 on ANY failure
    (unknown email, wrong password, disabled account) — no fingerprinting.

    The pre-auth credential read goes through ``auth_user_credentials``
    (SECURITY DEFINER, migration 0002): before authentication there is no RLS
    context, and the ``users`` policy is fail-closed by design. A dummy Argon2
    verify equalizes timing when the account is absent/missing so latency does
    not reveal account existence."""
    canonical = _canonical_email(email)
    if not canonical or "@" not in canonical:
        raise AuthenticationError("Unauthorized")
    found = await repo.auth_user_credentials(canonical)
    if found is None:
        security.verify_password(
            "$argon2id$v=19$m=65536,t=3,p=4"
            "$c29tZXNhbHRzb21lc2FsdA$qvEPWwAPeQBT52LzDKhiYImWj3qnjPI6xAaVU9kLDxc",
            password,
        )
        raise AuthenticationError("Unauthorized")
    user_id, user_email, display_name, password_hash, role = found
    if not security.verify_password(password_hash, password):
        raise AuthenticationError("Unauthorized")
    async with database.session_scope(user_id=str(user_id)) as session:
        created = await _persist_session(session, user_id=user_id)
    logger.info(
        "auth_login",
        extra={"details": {"event": "login", "user_id": str(user_id), "outcome": "success"}},
    )
    return (
        RegisteredUser(
            id=user_id, email=user_email, display_name=display_name, role=role, status="active"
        ),
        created,
    )


async def _persist_session(session, user_id: uuid.UUID) -> CreatedSession:  # type: ignore[no-untyped-def]
    raw = security.new_refresh_token()
    token_hash = security.hash_refresh_token(raw)
    expires_at = datetime.now(timezone.utc) + timedelta(days=get_settings().REFRESH_TTL_DAYS)
    record = await repo.RefreshSessionRepository(session).create(
        user_id=user_id, token_hash=token_hash, expires_at=expires_at
    )
    return CreatedSession(session_id=record.id, raw_token=raw, expires_at=expires_at)


# --- Rotation / reuse detection -----------------------------------------


@dataclass(frozen=True)
class RotatedSession:
    user_id: uuid.UUID
    old_session_id: uuid.UUID
    new_session_id: uuid.UUID
    raw_token: str
    expires_at: datetime
    role: str


async def refresh_session(raw_token: str) -> RotatedSession:
    """Rotate a refresh token: revoke old, issue new, atomically.

    Pre-auth lookup uses the SECURITY DEFINER function (runtime role) because
    no user context exists yet; the rotation itself runs bound to the resolved
    user so RLS still governs every write. The lookup returns revoked rows too
    so reuse of a rotated token is DETECTABLE (not merely 'unknown').

    Reuse of a revoked token revokes the WHOLE family (token-theft response);
    the client receives the same generic 401 as an unknown token (Part 8/18).
    """
    if not raw_token:
        raise AuthenticationError("Unauthorized")
    token_hash = security.hash_refresh_token(raw_token)
    now = datetime.now(timezone.utc)

    found = await repo.auth_session_lookup(token_hash, now=now)
    if found is None:
        raise AuthenticationError("Unauthorized")  # unknown/expired: generic
    user_id, session_id, family_id, revoked_at = found

    if revoked_at is not None:
        # REUSE of a rotated/revoked token: revoke the whole family.
        async with database.session_scope(user_id=str(user_id)) as session:
            sessions = repo.RefreshSessionRepository(session)
            n = await sessions.revoke_family(family_id, reason="reuse_detected", now=now)
            logger.warning(
                "auth_refresh_reuse",
                extra={
                    "details": {
                        "event": "refresh_reuse",
                        "user_id": str(user_id),
                        "family_id": str(family_id),
                        "sessions_revoked": n,
                    }
                },
            )
        raise AuthenticationError("Unauthorized")

    async with database.session_scope(user_id=str(user_id)) as session:
        sessions = repo.RefreshSessionRepository(session)
        current = await sessions.lock_by_id(session_id)  # FOR UPDATE
        if current is None or current.revoked_at is not None or current.expires_at <= now:
            # Lost the race (concurrent rotation committed first) — treat as
            # reuse: kill the family so the loser cannot be replayed either.
            if current is not None and current.family_id:
                n = await sessions.revoke_family(
                    current.family_id, reason="reuse_detected", now=now
                )
                logger.warning(
                    "auth_refresh_race",
                    extra={
                        "details": {
                            "event": "refresh_race",
                            "user_id": str(user_id),
                            "family_id": str(current.family_id),
                            "sessions_revoked": n,
                        }
                    },
                )
            raise AuthenticationError("Unauthorized")

        # Healthy rotation: revoke old (reason=rotated), mint child in family.
        await sessions.revoke(session_id, reason="rotated", now=now)
        raw = security.new_refresh_token()
        new_hash = security.hash_refresh_token(raw)
        expires_at = now + timedelta(days=get_settings().REFRESH_TTL_DAYS)
        new_record = await sessions.create(
            user_id=user_id,
            token_hash=new_hash,
            expires_at=expires_at,
            parent_session_id=session_id,
            family_id=current.family_id,
        )
        user = await repo.UserRepository(session).get_by_id(user_id)
        if user is None or user.status != "active":
            raise AuthenticationError("Unauthorized")
        logger.info(
            "auth_refresh",
            extra={
                "details": {
                    "event": "refresh",
                    "user_id": str(user_id),
                    "family_id": str(current.family_id),
                    "outcome": "rotated",
                }
            },
        )
        return RotatedSession(
            user_id=user_id,
            old_session_id=session_id,
            new_session_id=new_record.id,
            raw_token=raw,
            expires_at=expires_at,
            role=user.role,
        )


# --- Logout ---------------------------------------------------------------


async def logout(raw_token: str | None, *, user_id: uuid.UUID) -> bool:
    """Revoke the presented session (idempotent). The access token's `jti` is
    denylisted by the API layer; here we guarantee the refresh token cannot be
    reused. Returns True when a live session was revoked by this call."""
    now = datetime.now(timezone.utc)
    if raw_token:
        token_hash = security.hash_refresh_token(raw_token)
        found = await repo.auth_session_lookup(token_hash, now=now)
        if found is not None:
            user_id_found, session_id, _family, _revoked = found
            if user_id_found != user_id:
                return False  # never touch another user's session
            async with database.session_scope(user_id=str(user_id)) as session:
                sessions = repo.RefreshSessionRepository(session)
                current = await sessions.lock_by_id(session_id)
                if current is not None and current.user_id == user_id:
                    n = await sessions.revoke(session_id, reason="logout", now=now)
                    return n > 0
    return False


async def revoke_sessions_for_user(user_id: uuid.UUID, *, reason: str) -> int:
    now = datetime.now(timezone.utc)
    async with database.session_scope(user_id=str(user_id)) as session:
        return await repo.RefreshSessionRepository(session).revoke_all_for_user(
            user_id, reason=reason, now=now
        )


__all__ = [
    "ConflictError",
    "CreatedSession",
    "RegisteredUser",
    "RotatedSession",
    "create_refresh_session",
    "get_user",
    "login",
    "logout",
    "refresh_session",
    "register_user",
    "revoke_sessions_for_user",
]
