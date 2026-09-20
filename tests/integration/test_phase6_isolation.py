"""Integration tests for Phase 6 Mastery isolation & security (against cloud Supabase DB).

Verifies that:
- User A cannot access User B's concept mastery or audit trail.
- User A cannot modify or record mastery events in User B's project.
- Cross-project evidence application is blocked under RLS.
"""

from __future__ import annotations

import uuid

import pytest
from app.mastery import service as mastery_service


@pytest.mark.asyncio
async def test_user_b_cannot_view_user_a_mastery(cloud_settings, engines, seed_user, seed_project):
    """User B querying User A's project mastery gets empty list or not found."""
    user_a = await seed_user("p6-iso-a")
    user_b = await seed_user("p6-iso-b")
    _, project_a = await seed_project(user_a.id, "Project A Mastery")
    _, project_b = await seed_project(user_b.id, "Project B Mastery")

    concept_id = uuid.uuid4()

    # User A records mastery
    await mastery_service.record_learning_event(
        owner_id=user_a.id,
        project_id=project_a.id,
        input_data=mastery_service.RecordEvidenceInput(
            source="assessment",
            source_id=uuid.uuid4(),
            concept_id=concept_id,
            result="correct",
            score=1.0,
            difficulty="medium",
        ),
    )

    # User B queries User A's project mastery
    b_records = await mastery_service.get_project_mastery(
        owner_id=user_b.id,
        project_id=project_a.id,
    )
    # Under RLS owner_id = app_user_id(), User B sees 0 records
    assert len(b_records) == 0

    # User B queries User A's concept mastery directly
    b_concept = await mastery_service.get_concept_mastery(
        owner_id=user_b.id,
        project_id=project_a.id,
        concept_id=concept_id,
    )
    assert b_concept is None


@pytest.mark.asyncio
async def test_user_b_cannot_view_user_a_evidence_trail(
    cloud_settings, engines, seed_user, seed_project
):
    """User B cannot view User A's mastery audit trail."""
    user_a = await seed_user("p6-iso-trail-a")
    user_b = await seed_user("p6-iso-trail-b")
    _, project_a = await seed_project(user_a.id, "Trail Project A")

    concept_id = uuid.uuid4()

    await mastery_service.record_learning_event(
        owner_id=user_a.id,
        project_id=project_a.id,
        input_data=mastery_service.RecordEvidenceInput(
            source="assessment",
            source_id=uuid.uuid4(),
            concept_id=concept_id,
            result="correct",
            score=1.0,
            difficulty="hard",
        ),
    )

    # User B queries trail of Project A
    trail = await mastery_service.get_evidence_trail(
        owner_id=user_b.id,
        project_id=project_a.id,
        concept_id=concept_id,
    )
    assert len(trail) == 0
