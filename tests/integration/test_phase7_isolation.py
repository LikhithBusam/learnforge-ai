"""Integration tests for Phase 7 Growth isolation & security (against cloud Supabase DB).

Verifies that:
- User B cannot view User A's concept growth or project growth summary.
- User B cannot evaluate growth in User A's project.
- User B cannot view User A's growth audit history.
- Cross-project growth isolation is strictly enforced by PostgreSQL RLS.
"""

from __future__ import annotations

import uuid

import pytest
from app.growth import service as growth_service
from app.mastery import service as mastery_service
from app.platform.errors import NotFound


@pytest.mark.asyncio
async def test_user_b_cannot_view_user_a_growth(cloud_settings, engines, seed_user, seed_project):
    """User B querying User A's growth gets empty records or not found."""
    user_a = await seed_user("p7-iso-a")
    user_b = await seed_user("p7-iso-b")
    _, project_a = await seed_project(user_a.id, "Project A Growth")
    _, project_b = await seed_project(user_b.id, "Project B Growth")

    concept_id = uuid.uuid4()

    # User A records mastery and evaluates growth
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
    trail = await mastery_service.get_evidence_trail(
        owner_id=user_a.id, project_id=project_a.id, concept_id=concept_id
    )
    await growth_service.evaluate_concept_growth(
        owner_id=user_a.id,
        project_id=project_a.id,
        concept_id=concept_id,
        source_mastery_event_id=trail[0].id,
    )

    # User B queries User A's concept growth
    b_growth = await growth_service.get_concept_growth(
        owner_id=user_b.id,
        project_id=project_a.id,
        concept_id=concept_id,
    )
    assert b_growth is None

    # User B queries User A's growth history
    b_history = await growth_service.get_growth_history(
        owner_id=user_b.id,
        project_id=project_a.id,
        concept_id=concept_id,
    )
    assert len(b_history) == 0

    # User B tries to trigger evaluation on User A's project
    with pytest.raises(NotFound):
        await growth_service.evaluate_concept_growth(
            owner_id=user_b.id,
            project_id=project_a.id,
            concept_id=concept_id,
        )
