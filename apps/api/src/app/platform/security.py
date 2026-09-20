"""Authorization foundation + secret-handling primitives (Phase 1).

Distinguishes (Part 16): authenticated user · resource owner · project
member · admin. Posture (ADR-0002 + ADR-0021/Q5):

* **404** for role/existence concealment (non-owner on someone else's
  resource — including admin-route non-admins): no existence leak.
* **403** only for capability/policy denial on a KNOWN resource.

The DB layer enforces isolation independently (RLS) — this module is layer 1
of the four-layer model; never a substitute for `db.session_scope` context.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Literal

from app.platform.errors import NotFound

Role = Literal["learner", "admin"]
AccountStatus = Literal["active", "disabled"]


@dataclass(frozen=True)
class Principal:
    """The authenticated caller (constructed from a verified JWT at the edge)."""

    user_id: str
    role: Role = "learner"
    session_id: str | None = None  # refresh-session id (audit/debug linkage)
    request_id: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@dataclass(frozen=True)
class ProjectScope:
    """Resolved, explicitly-passed project context (module-contracts scope rule)."""

    project_id: str
    space_id: str
    owner_id: str
    principal: Principal


def resolve_role_or_404(principal: Principal | None) -> Principal:
    """404-posture: an unauthenticated/non-admin caller on an admin capability
    must not learn that the capability exists. Returns the principal when the
    admin role is present; raises NotFound otherwise (ADR-0021/Q5)."""
    if principal is None or not principal.is_admin:
        raise NotFound("Resource not found")
    return principal


def resolve_project_scope(
    principal: Principal,
    *,
    project_id: str,
    space_id: str,
    owner_id: str,
) -> ProjectScope:
    """Owner/member resolution: non-owner (including admin) → 404-equivalent.

    Admin has no direct route to user data (A-01 read-only admin plane;
    aggregated views arrive with the Admin module) — modeled here as the same
    404 concealment, which is what makes the posture uniform everywhere.
    """
    if principal.user_id != owner_id:
        raise NotFound("Project not found")
    return ProjectScope(
        project_id=project_id, space_id=space_id, owner_id=owner_id, principal=principal
    )


# --- Error types: the canonical taxonomy lives in platform.errors -------------
# (NotFound → 404 concealment, AuthorizationError → 403 capability denial,
# ConflictError → 409). This module adds no competing error classes.

# --- Secret handling primitives (ADR-0018) ---------------------------------


def hash_password(password: str) -> str:
    """Argon2id PHC string; never plaintext in the database."""
    from argon2 import PasswordHasher

    return PasswordHasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-time verify; malformed/invalid input verifies False (fail closed)."""
    try:
        from argon2 import PasswordHasher
        from argon2.exceptions import Argon2Error, InvalidHashError

        PasswordHasher().verify(password_hash, password)
        return True
    except (Argon2Error, InvalidHashError, ValueError):
        # InvalidHashError subclasses ValueError; catch both explicitly.
        return False


def hash_refresh_token(raw_token: str) -> str:
    """SHA-256 hex of the opaque refresh token — raw tokens are NEVER stored
    (ADR-0018). High-entropy tokens make precomputation infeasible."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def new_refresh_token() -> str:
    """256-bit opaque token (urlsafe); the DB stores only its hash."""
    import secrets

    return secrets.token_urlsafe(32)


def parse_uuid(value: str, *, what: str = "identifier") -> str:
    """Strict UUID parsing — malformed identifiers fail closed (Part 18)."""
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"Malformed {what}") from exc
