"""Growth authorization policies (Phase 7).

Authorization predicates for Growth Engine domain.
All growth resources are owner-scoped: non-owned resources → NotFound (ADR-0002).
RLS provides the database-level enforcement via owner_id = app_user_id().
"""

from __future__ import annotations

import uuid


def assert_growth_owned(resource_owner_id: uuid.UUID, caller_id: uuid.UUID) -> None:
    """Raise if caller does not own the growth resource (defense-in-depth)."""
    from app.platform.errors import NotFound

    if resource_owner_id != caller_id:
        raise NotFound("Growth resource not found")
