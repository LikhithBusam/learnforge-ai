"""Identity repositories — scoped operations only (module-contracts §M.1).

No unrestricted queries: every method is keyed by an explicit, caller-supplied
identifier. Password hashes are never returned by any read method except the
explicit auth-lookup path (`get_by_email_with_hash`) that the future login
endpoint uses — general reads return the dataclass without the hash.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.identity.models import RefreshSession, User
from sqlalchemy import delete, select, update


@dataclass(frozen=True)
class UserRecord:
    id: uuid.UUID
    email: str
    display_name: str | None
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SessionRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None
    revoked_reason: str | None
    parent_session_id: uuid.UUID | None
    family_id: uuid.UUID
    created_at: datetime


def _user_record(u: User) -> UserRecord:
    return UserRecord(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=u.role,
        status=u.status,
        created_at=u.created_at,
        updated_at=u.updated_at,
    )


class UserRepository:
    """Reads are scoped by explicit id/email; no list-all surfaces."""

    def __init__(self, session) -> None:
        self._s = session

    async def get_by_id(self, user_id: uuid.UUID) -> UserRecord | None:
        row = await self._s.get(User, user_id)
        return _user_record(row) if row else None

    async def get_by_email(self, email: str) -> UserRecord | None:
        from sqlalchemy import func

        row = (
            await self._s.execute(select(User).where(func.lower(User.email) == email.lower()))
        ).scalar_one_or_none()
        return _user_record(row) if row else None

    async def email_exists(self, email: str) -> bool:
        from sqlalchemy import func

        return (
            await self._s.execute(
                select(func.lower(User.email)).where(func.lower(User.email) == email.lower())
            )
        ).scalar_one_or_none() is not None

    async def create(
        self,
        *,
        id: uuid.UUID,
        email: str,
        password_hash: str,
        role: str,
        display_name: str | None = None,
    ) -> UserRecord:
        u = User(
            id=id,
            email=email,
            password_hash=password_hash,
            role=role,
            display_name=display_name,
        )
        self._s.add(u)
        await self._s.flush()
        return _user_record(u)

    async def get_by_email_with_hash(self, email: str) -> tuple[UserRecord, str] | None:
        """The ONLY hash-revealing lookup; reserved for the auth (login) path."""
        from sqlalchemy import func

        row = (
            await self._s.execute(select(User).where(func.lower(User.email) == email.lower()))
        ).scalar_one_or_none()
        if row is None:
            return None
        return _user_record(row), row.password_hash


class RefreshSessionRepository:
    """Lookup is by token hash only; raw tokens never enter this layer."""

    def __init__(self, session) -> None:
        self._s = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        parent_session_id: uuid.UUID | None = None,
        family_id: uuid.UUID | None = None,
    ) -> SessionRecord:
        from app.platform.ids import uuid7

        s = RefreshSession(
            id=uuid7(),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            parent_session_id=parent_session_id,
            family_id=family_id or uuid7(),  # new family unless rotating into one
        )
        self._s.add(s)
        await self._s.flush()
        return self._to_record(s)

    async def lock_by_id(self, session_id: uuid.UUID) -> SessionRecord | None:
        """SELECT ... FOR UPDATE — serializes concurrent rotations of the same
        session: the second request blocks until the first commits, then sees
        revoked_at set and fails (Part 7 anti-double-rotation)."""
        row = (
            await self._s.execute(
                select(RefreshSession).where(RefreshSession.id == session_id).with_for_update()
            )
        ).scalar_one_or_none()
        return self._to_record(row) if row else None

    async def revoke_family(self, family_id: uuid.UUID, *, reason: str, now: datetime) -> int:
        """Token-theft response: revoke every member of the family."""
        result = await self._s.execute(
            update(RefreshSession)
            .where(
                RefreshSession.family_id == family_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoked_reason=reason)
        )
        return int(result.rowcount or 0)

    async def get_by_token_hash(self, token_hash: str) -> SessionRecord | None:
        row = (
            await self._s.execute(
                select(RefreshSession).where(RefreshSession.token_hash == token_hash)
            )
        ).scalar_one_or_none()
        return self._to_record(row) if row else None

    async def revoke(self, session_id: uuid.UUID, *, reason: str, now: datetime) -> int:
        result = await self._s.execute(
            update(RefreshSession)
            .where(RefreshSession.id == session_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason=reason)
        )
        return int(result.rowcount or 0)

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, reason: str, now: datetime) -> int:
        result = await self._s.execute(
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason=reason)
        )
        return int(result.rowcount or 0)

    async def purge_expired(self, *, now: datetime) -> int:
        """Housekeeping hook (future Beat task); deletes only expired rows."""
        result = await self._s.execute(
            delete(RefreshSession).where(RefreshSession.expires_at < now)
        )
        return int(result.rowcount or 0)

    @staticmethod
    def _to_record(s: RefreshSession) -> SessionRecord:
        return SessionRecord(
            id=s.id,
            user_id=s.user_id,
            token_hash=s.token_hash,
            expires_at=s.expires_at,
            revoked_at=s.revoked_at,
            revoked_reason=s.revoked_reason,
            parent_session_id=s.parent_session_id,
            family_id=s.family_id,
            created_at=s.created_at,
        )


async def auth_user_credentials(
    email: str,
) -> tuple[uuid.UUID, str, str | None, str, str] | None:
    """Pre-authentication credential lookup via auth_user_credentials()
    (SECURITY DEFINER, migration 0002) through the RUNTIME engine.
    Returns (user_id, email, display_name, password_hash, role) for an ACTIVE
    account, else None. Missing/disabled are indistinguishable here — the
    service layer raises one generic 401 for both."""
    from app.platform import db as database
    from sqlalchemy import text as sa_text

    factory = database.get_runtime_session_factory()
    if factory is None:
        raise RuntimeError("Runtime database engine not initialized")
    async with factory() as session:
        row = (
            await session.execute(
                sa_text("SELECT * FROM auth_user_credentials(:e)"),
                {"e": email},
            )
        ).first()
    if row is None:
        return None
    return row.user_id, row.email_out, row.display_name_out, row.password_hash_out, row.role_out


async def auth_session_lookup(
    token_hash: str, *, now: datetime
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, datetime | None] | None:
    """Pre-authentication lookup via the SECURITY DEFINER function (migration
    0002). Returns (user_id, session_id, family_id, revoked_at) for an
    UNEXPIRED session — including REVOKED ones, so the service layer can
    distinguish reuse-of-rotated-token (family revocation) from a genuinely
    unknown token. Expired tokens return None (nothing left to protect).

    The ONLY path that reads session data without a bound RLS context; the
    surface is the minimal session tuple, nothing else. Called through the
    RUNTIME engine (EXECUTE granted on the definer function); the privileged
    admin engine is never used in request paths.
    """
    from app.platform import db as database
    from sqlalchemy import text as sa_text

    factory = database.get_runtime_session_factory()
    if factory is None:
        raise RuntimeError("Runtime database engine not initialized")
    async with factory() as session:
        row = (
            await session.execute(
                sa_text("SELECT * FROM auth_session_lookup(:h, :now)"),
                {"h": token_hash, "now": now},
            )
        ).first()
    if row is None:
        return None
    return row.out_user_id, row.session_id, row.family_id, row.revoked_at
