"""Mastery authorization policies (Phase 6).

Authorization predicates for Mastery Engine domain.
All mastery resources are owner-scoped: non-owned resources → NotFound (ADR-0002).
RLS provides the database-level enforcement via owner_id = app_user_id().
"""

from __future__ import annotations

import uuid


def assert_mastery_owned(resource_owner_id: uuid.UUID, caller_id: uuid.UUID) -> None:
    """Raise if caller does not own the mastery resource (defense-in-depth)."""
    from app.platform.errors import NotFound

    if resource_owner_id != caller_id:
        raise NotFound("Mastery resource not found")
