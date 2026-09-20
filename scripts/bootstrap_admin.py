"""Admin bootstrap (Part 16) — operator-run CLI, NEVER an API endpoint.

Mechanism (ADR-0018 A-02: admin assigned out-of-band, no self-service):

    ADMIN_BOOTSTRAP_EMAIL=ops@yourdomain.com
    ADMIN_BOOTSTRAP_TOKEN=<one-time secret>
    python scripts/bootstrap_admin.py

Safeguards:
* Requires BOTH env values present and non-empty; otherwise refuses.
* The token must be at least 32 characters and is never printed; only a
  SHA-256 fingerprint prefix is logged for audit correlation. The one-time
  property comes from idempotency: re-running with an already-admin email is
  a no-op (exit 0, "already admin").
* Works ONLY through the runtime service path (no direct SQL role writes
  outside the service layer); the role check (`learner`) is enforced here.
* Existing learner registration is unaffected; there is no API route that
  can reach this logic.
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api" / "src"))

from app.platform.config import get_settings  # noqa: E402


def _fingerprint(token: str) -> str:
    """Safe audit handle: first 12 hex of the token's SHA-256 — cannot be
    reversed into the token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


async def _promote(email: str) -> str:
    from datetime import datetime, timezone

    from app.identity.models import User
    from app.platform import db as database
    from sqlalchemy import select, update

    async with database.admin_session_scope() as session:
        row = (
            await session.execute(select(User).where(User.email == email.strip().casefold()))
        ).scalar_one_or_none()
        if row is None:
            return "missing"
        if row.role == "admin":
            return "already_admin"
        await session.execute(
            update(User)
            .where(User.id == row.id)
            .values(role="admin", updated_at=datetime.now(timezone.utc))
        )
        return "promoted"


async def _create_admin(email: str, password: str) -> str:
    from app.identity import service as identity

    user = await identity.register_user(email=email, password=password)
    outcome = await _promote(email)
    if outcome == "promoted":
        print(f"admin account created for {user.email}")
        return "created"
    return outcome


def main() -> int:
    settings = get_settings()
    email = settings.ADMIN_BOOTSTRAP_EMAIL.strip().casefold()
    token = settings.ADMIN_BOOTSTRAP_TOKEN
    if not email or not token:
        print(
            "ERROR: set ADMIN_BOOTSTRAP_EMAIL and ADMIN_BOOTSTRAP_TOKEN in the "
            "environment (never commit them).",
            file=sys.stderr,
        )
        return 2
    if len(token) < 32:
        print("ERROR: ADMIN_BOOTSTRAP_TOKEN must be >= 32 characters.", file=sys.stderr)
        return 2
    if "@" not in email:
        print("ERROR: ADMIN_BOOTSTRAP_EMAIL is not a valid email.", file=sys.stderr)
        return 2

    from app.platform import db as database

    database.init_engine(settings)
    try:
        outcome = asyncio.run(_promote(email))
        if outcome == "missing":
            # Create-then-promote requires a password the operator supplies
            # interactively; never via argv (process-listing leak).
            import getpass

            password = getpass.getpass("New admin account password: ")
            if len(password) < 10:
                print("ERROR: password too short (min 10).", file=sys.stderr)
                return 2
            outcome = asyncio.run(_create_admin(email, password))
    finally:
        asyncio.run(database.close_engine())
    print(f"bootstrap outcome: {outcome} (token fingerprint {_fingerprint(token)})")
    return 0 if outcome in ("promoted", "already_admin", "created") else 1


if __name__ == "__main__":
    raise SystemExit(main())
