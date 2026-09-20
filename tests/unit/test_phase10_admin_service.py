"""Unit tests for Phase 10 Admin service and policies."""

from __future__ import annotations

import uuid

import pytest
from app.admin.policies import assert_admin_role
from app.platform.errors import NotFound
from app.platform.security import Principal


def test_assert_admin_role_policy():
    """Verify that assert_admin_role rejects non-admin users with NotFound (404 concealment posture)."""
    admin_principal = Principal(user_id=str(uuid.uuid4()), role="admin")
    learner_principal = Principal(user_id=str(uuid.uuid4()), role="learner")

    # Admin should pass
    assert_admin_role(admin_principal)

    # Learner should raise NotFound (404 concealment)
    with pytest.raises(NotFound):
        assert_admin_role(learner_principal)


def test_admin_principal_attributes():
    """Verify Principal properties for role checks."""
    p_admin = Principal(user_id=str(uuid.uuid4()), role="admin")
    p_learner = Principal(user_id=str(uuid.uuid4()), role="learner")

    assert p_admin.is_admin is True
    assert p_learner.is_admin is False
