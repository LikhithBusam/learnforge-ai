"""Provision the runtime database role's password (operator-run; Part 8).

The Alembic migration creates ``studycompanion_runtime`` with a NULL password
(it cannot authenticate until provisioned). This script:

1. Reads the migration/admin ``DATABASE_URL`` from the existing settings
   abstraction (never hard-coded).
2. Generates a strong random password in memory.
3. Sets it via ALTER ROLE over the admin connection.
4. Derives ``DATABASE_RUNTIME_URL`` from the admin URL by swapping ONLY the
   user:password component — host/port/db stay identical (works for the
   Supabase pooler and local Compose alike).
5. Upserts ``DATABASE_RUNTIME_URL`` into the gitignored ``.env.development``
   (never printed, never committed).

Run:  python scripts/provision_runtime_role.py
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api" / "src"))

from app.platform.config import get_settings  # noqa: E402


def _build_runtime_url(admin_url: str, runtime_user: str, password: str) -> str:
    parts = urlsplit(admin_url)
    if not parts.hostname:
        raise ValueError("DATABASE_URL does not contain a host")
    username = unquote(parts.username or "")
    # Supavisor (pooler.supabase.com) routes by tenant embedded in the
    # username as "<role>.<project-ref>"; the runtime URL must keep that
    # qualifier or the pooler rejects the connection before auth
    # ("no tenant identifier provided"). Local/other hosts: unchanged.
    if "pooler.supabase.com" in (parts.hostname or "") and "." in username:
        tenant = username.split(".", 1)[1]
        runtime_user = f"{runtime_user}.{tenant}"
    netloc = f"{runtime_user}:{password}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def main() -> int:
    from sqlalchemy import text

    settings = get_settings()
    if not settings.DATABASE_URL:
        print("ERROR: DATABASE_URL is not configured", file=sys.stderr)
        return 1

    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    runtime_user = "studycompanion_runtime"
    password = secrets.token_urlsafe(32)
    runtime_url = _build_runtime_url(settings.DATABASE_URL, runtime_user, password)

    async def _alter_role() -> None:
        # hide_parameters: SQLAlchemy must never echo credentials in errors.
        # ALTER ROLE is a utility statement: asyncpg cannot bind parameters in
        # it, so the statement is composed server-side with format('%L')
        # (proper literal escaping) and executed as a second statement.
        engine = create_async_engine(
            settings.DATABASE_URL, pool_pre_ping=True, hide_parameters=True
        )
        try:
            async with engine.begin() as conn:
                stmt = (
                    await conn.execute(
                        text(
                            "SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', "
                            "p.role_name, p.pw_value) FROM "
                            "(SELECT :role AS role_name, :pw AS pw_value) p"
                        ),
                        {"role": runtime_user, "pw": password},
                    )
                ).scalar_one()
                try:
                    await conn.execute(text(stmt))
                except Exception as exc:  # noqa: BLE001
                    # The composed statement embeds the password literal; the
                    # raw exception would echo it. Re-raise WITHOUT any SQL.
                    raise RuntimeError(
                        f"ALTER ROLE failed: {type(exc).__name__} — "
                        "has the Phase 1 migration created the role yet?"
                    ) from None
        finally:
            await engine.dispose()

    asyncio.run(_alter_role())

    env_path = PROJECT_ROOT / ".env.development"
    line = f"DATABASE_RUNTIME_URL={runtime_url}"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    replaced = False
    out: list[str] = []
    for existing in lines:
        if existing.startswith("DATABASE_RUNTIME_URL="):
            out.append(line)
            replaced = True
        else:
            out.append(existing)
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append("# Runtime RLS role (provisioned by scripts/provision_runtime_role.py)")
        out.append(line)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")

    print("OK: runtime role password set; DATABASE_RUNTIME_URL written to .env.development")
    print("    (value not displayed; rotate by re-running this script)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
