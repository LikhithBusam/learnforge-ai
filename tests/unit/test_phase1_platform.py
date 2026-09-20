"""Phase 1 unit tests — canonicalization, ids, authorization helpers.

These do NOT require database credentials (pure logic tests).
"""

from __future__ import annotations

import uuid

import pytest


def test_uuid7_monotonic_and_versioned():
    from app.platform.ids import uuid7

    ids = [uuid7() for _ in range(100)]
    assert all(a < b for a, b in zip(ids, ids[1:], strict=False))  # offset pairing
    assert all(i.hex[12] == "7" for i in ids)  # RFC 9562 version nibble


def test_email_canonicalization():
    from app.identity.service import _canonical_email

    assert _canonical_email("  USER@Example.COM ") == "user@example.com"
    assert _canonical_email("A@B.co") == "a@b.co"


def test_register_user_validation_rejects_bad_input():
    from app.identity import service as identity
    from app.platform.errors import ValidationError

    with pytest.raises(ValidationError):
        # No network/DB hit: validation precedes any I/O.
        import asyncio

        asyncio.run(identity.register_user(email="not-an-email", password="password-123456"))


def test_password_hashing_roundtrip():
    from app.platform.security import hash_password, verify_password

    h = hash_password("s3cret-password")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "s3cret-password")
    assert not verify_password(h, "wrong")


def test_refresh_token_hash_is_sha256_hex():
    from app.platform.security import hash_refresh_token, new_refresh_token

    raw = new_refresh_token()
    h = hash_refresh_token(raw)
    assert len(h) == 64
    assert int(h, 16) >= 0  # valid hex
    assert raw not in h


def test_resolve_project_scope_404_posture():
    from app.platform.errors import NotFound
    from app.platform.security import Principal, resolve_project_scope

    owner = Principal(user_id="11111111-1111-1111-1111-111111111111")
    other = Principal(user_id="22222222-2222-2222-2222-222222222222")
    scope = resolve_project_scope(
        owner,
        project_id=str(uuid.uuid4()),
        space_id=str(uuid.uuid4()),
        owner_id=owner.user_id,
    )
    assert scope.project_id
    with pytest.raises(NotFound):
        resolve_project_scope(
            other,
            project_id=str(uuid.uuid4()),
            space_id=str(uuid.uuid4()),
            owner_id=owner.user_id,
        )
    # Admin is NOT exempt from ownership scoping (A-01 posture: concealment).
    admin = Principal(user_id=other.user_id, role="admin")
    with pytest.raises(NotFound):
        resolve_project_scope(
            admin,
            project_id=str(uuid.uuid4()),
            space_id=str(uuid.uuid4()),
            owner_id=owner.user_id,
        )


def test_resolve_role_or_404():
    from app.platform.errors import NotFound
    from app.platform.security import Principal, resolve_role_or_404

    with pytest.raises(NotFound):
        resolve_role_or_404(None)
    with pytest.raises(NotFound):
        resolve_role_or_404(Principal(user_id=str(uuid.uuid4()), role="learner"))
    assert resolve_role_or_404(Principal(user_id=str(uuid.uuid4()), role="admin")).is_admin


def test_parse_uuid_rejects_malformed():
    from app.platform.security import parse_uuid

    with pytest.raises(ValueError):
        parse_uuid("not-a-uuid")
    with pytest.raises(ValueError):
        parse_uuid("")
    assert parse_uuid(str(uuid.uuid4()))


def test_workspace_service_rejects_blank_names():
    import asyncio

    from app.workspace import service as workspace

    with pytest.raises(ValueError):
        asyncio.run(
            workspace.create_project(owner_id=uuid.uuid4(), space_id=uuid.uuid4(), name="   ")
        )
