"""Database foundation — dual-engine model + RLS context (Phase 1).

Two engines, two privilege classes (rls-model.md):

* **Admin engine** (`init_engine`) — migration/DDL/health role (on Supabase the
  project owner role). Used by Alembic, migrations and readiness probes.
  This role HAS BYPASSRLS on Supabase — it must never serve normal requests.
* **Runtime engine** (`init_runtime_engine`) — the application's normal
  request path. Connects as a dedicated role with NO superuser and NO
  BYPASSRLS, so PostgreSQL RLS is a real second boundary. Every project/user
  scoped query runs inside `session_scope()`, which binds a **transaction-
  scoped** RLS context first (`set_config(..., true)` — survives Supavisor
  pooling, cannot leak between requests; verified in the cloud phase).

Missing context fails CLOSED: policies compare against
`current_setting('app.current_user_id', true)` which is NULL/empty when
unbound → zero rows (see `app.bind_context_from_envelope`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.platform.config import Settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None  # admin/migration engine (Phase 0 name kept)
_session_factory: async_sessionmaker[AsyncSession] | None = None

_runtime_engine: AsyncEngine | None = None  # RLS-enforced application engine
_runtime_session_factory: async_sessionmaker[AsyncSession] | None = None


def _create_engine(database_url: str, settings: Settings) -> AsyncEngine:
    # pool_recycle: managed poolers (Supavisor) and server idle limits recycle
    # connections; combined with pool_pre_ping this keeps checkouts healthy.
    return create_async_engine(
        database_url,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def init_engine(settings: Settings) -> AsyncEngine:
    """Admin/migration engine (Phase 0 behavior preserved)."""
    global _engine, _session_factory
    if _engine is None:
        if not settings.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        _engine = _create_engine(settings.DATABASE_URL, settings)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def init_runtime_engine(settings: Settings) -> AsyncEngine:
    """Runtime engine — MUST use the non-BYPASSRLS application role (Part 8)."""
    global _runtime_engine, _runtime_session_factory
    if _runtime_engine is None:
        if not settings.DATABASE_RUNTIME_URL:
            raise RuntimeError(
                "DATABASE_RUNTIME_URL is not configured: refusing to serve "
                "application traffic on a privileged/owner database role"
            )
        if settings.DATABASE_RUNTIME_URL == settings.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_RUNTIME_URL must differ from DATABASE_URL: the "
                "application runtime must not use the migration/owner role"
            )
        _runtime_engine = _create_engine(settings.DATABASE_RUNTIME_URL, settings)
        _runtime_session_factory = async_sessionmaker(_runtime_engine, expire_on_commit=False)
    return _runtime_engine


def get_engine() -> AsyncEngine | None:
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession] | None:
    return _session_factory


def get_runtime_session_factory() -> async_sessionmaker[AsyncSession] | None:
    return _runtime_session_factory


async def close_engine() -> None:
    global _engine, _session_factory, _runtime_engine, _runtime_session_factory
    if _engine is not None:
        await _engine.dispose()
    if _runtime_engine is not None:
        await _runtime_engine.dispose()
    _engine = None
    _session_factory = None
    _runtime_engine = None
    _runtime_session_factory = None


async def bind_rls_context(
    session: AsyncSession,
    *,
    user_id: str | None,
    project_id: str | None = None,
) -> None:
    """Bind the transaction-scoped RLS context with BIND PARAMETERS (no interpolation).

    ``set_config(..., is_local => true)`` scopes the setting to the current
    transaction: it disappears on commit/rollback, making it safe under
    transaction/connection pooling and impossible to leak between requests.
    Empty values are stored as '' so `current_setting(..., true)` reads ''
    (falsy for every policy) instead of raising.
    """
    await session.execute(
        text("select set_config('app.current_user_id', :user_id, true)"),
        {"user_id": user_id or ""},
    )
    if project_id:
        await session.execute(
            text("select set_config('app.current_project_id', :project_id, true)"),
            {"project_id": project_id},
        )


@asynccontextmanager
async def session_scope(
    *,
    user_id: str | None = None,
    project_id: str | None = None,
) -> AsyncIterator[AsyncSession]:
    """One unit of work on the RLS-enforced runtime engine.

    Transaction ownership: this context manager owns the transaction — commit
    on success, rollback on any exception (module-contracts transaction
    boundaries). Services must not commit; nested "transactions" in callers
    are plain function composition, not new SQL transactions (a future outbox
    insert joins THIS transaction, keeping state+event atomic per ADR-0004).

    The RLS context is bound as the first statement of the same transaction
    that runs the work — fail-closed if omitted (Part 12).
    """
    if _runtime_session_factory is None:
        raise RuntimeError("Runtime database engine not initialized")
    async with _runtime_session_factory() as session:
        try:
            async with session.begin():
                await bind_rls_context(session, user_id=user_id, project_id=project_id)
                yield session
        except Exception:
            # session.begin() rolls back on exception; context vars stay clean.
            raise


@asynccontextmanager
async def admin_session_scope() -> AsyncIterator[AsyncSession]:
    """Explicit, auditable escape hatch for the privileged engine.

    Legitimate uses: migrations, DDL backfills, health probes. NEVER for
    normal request handling (rls-model.md §privileged-operations).
    """
    if _session_factory is None:
        raise RuntimeError("Admin database engine not initialized")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database() -> dict:
    """Readiness probe: SELECT 1 on the admin engine. Never exposes credentials."""
    if _engine is None:
        return {
            "status": "unconfigured",
            "detail": "DATABASE_URL not set; database features disabled",
        }
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 - probe must not raise
        return {"status": "error", "detail": type(exc).__name__}


async def check_runtime_database() -> dict:
    """Readiness probe for the runtime role path (connect + minimal query)."""
    if _runtime_engine is None:
        return {
            "status": "unconfigured",
            "detail": "DATABASE_RUNTIME_URL not set; runtime engine disabled",
        }
    try:
        async with _runtime_engine.connect() as conn:
            role = (await conn.execute(text("select current_user"))).scalar()
            props = (
                await conn.execute(
                    text("select rolsuper, rolbypassrls from pg_roles where rolname = current_user")
                )
            ).one()
        return {
            "status": "ok",
            "role": role,
            "rolsuper": bool(props[0]),
            "rolbypassrls": bool(props[1]),
        }
    except Exception as exc:  # noqa: BLE001 - probe must not raise
        return {"status": "error", "detail": type(exc).__name__}
