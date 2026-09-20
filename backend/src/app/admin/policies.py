"""Admin authorization policies (Phase 10).

Enforces strict RBAC gates for the Admin domain.
Non-admin callers receive 404 (ADR-0002 / ADR-0021 concealment) or 403.
"""

from __future__ import annotations

from app.platform.errors import NotFound
from app.platform.security import Principal


def assert_admin_role(principal: Principal) -> None:
    """Raise NotFound if principal is not an administrator (404 concealment posture)."""
    if not principal.is_admin:
        raise NotFound("Resource not found")
