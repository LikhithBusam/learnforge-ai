"""Analytics authorization policies (Phase 9).

Authorization predicates for Analytics domain.
All analytics resources are owner-scoped: non-owned resources -> NotFound (ADR-0002).
RLS provides the database-level enforcement via user_id/owner_id = app_user_id().
"""

from __future__ import annotations

import uuid


def assert_analytics_owned(resource_owner_id: uuid.UUID, caller_id: uuid.UUID) -> None:
    """Raise if caller does not own the analytics resource (defense-in-depth)."""
    from app.platform.errors import NotFound

    if resource_owner_id != caller_id:
        raise NotFound("Analytics resource not found")
