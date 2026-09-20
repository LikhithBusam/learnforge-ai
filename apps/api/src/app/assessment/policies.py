"""Assessment authorization policies (Phase 5).

Authorization predicates for Assessment domain.
All assessment resources are owner-scoped: non-owned resources → NotFound (ADR-0002).
RLS provides the database-level enforcement via owner_id = app_user_id().
"""

from __future__ import annotations

import uuid


def assert_quiz_owned(quiz_owner_id: uuid.UUID, caller_id: uuid.UUID) -> None:
    """Raise if the caller does not own the quiz.

    Per ADR-0021/Q5: ownership failures return 404, not 403.
    RLS enforces this at the database layer; this predicate is the
    application-layer guard for defense-in-depth.
    """
    from app.platform.errors import NotFound

    if quiz_owner_id != caller_id:
        raise NotFound("Quiz not found")


def assert_quiz_active(quiz_status: str) -> None:
    """Raise ConflictError if quiz is not in a state that accepts answers."""
    from app.platform.errors import ConflictError

    if quiz_status == "completed":
        raise ConflictError("Quiz is already completed.")
    if quiz_status == "abandoned":
        raise ConflictError("Quiz was abandoned.")
