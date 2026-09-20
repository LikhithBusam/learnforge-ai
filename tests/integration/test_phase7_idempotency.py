"""Integration tests for Phase 7 Growth idempotency (against cloud Supabase DB).

Verifies that:
- Replaying the same source_mastery_event_id produces 0 duplicate evaluations.
- Repeated evaluations return the existing growth state safely without creating extra audit events.
"""

from __future__ import annotations

import uuid

import pytest
from app.growth import service as growth_service
from app.mastery import service as mastery_service


@pytest.mark.asyncio
async def test_evaluate_growth_idempotency_replay(cloud_settings, engines, seed_user, seed_project):
    """Evaluating growth with the exact same source_mastery_event_id is strictly idempotent."""
    user = await seed_user("p7-idem-user")
    _, project = await seed_project(user.id, "Growth Idempotency Project")

    concept_id = uuid.uuid4()

    # Record mastery event
    await mastery_service.record_learning_event(
        owner_id=user.id,
        project_id=project.id,
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
        owner_id=user.id, project_id=project.id, concept_id=concept_id
    )
    mastery_event_id = trail[0].id

    # 1. First evaluation
    res1 = await growth_service.evaluate_concept_growth(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
        source_mastery_event_id=mastery_event_id,
    )
    assert res1.evidence_count == 1
    first_updated_at = res1.updated_at

    # 2. Second evaluation (replaying same source_mastery_event_id)
    res2 = await growth_service.evaluate_concept_growth(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
        source_mastery_event_id=mastery_event_id,
    )
    assert res2.id == res1.id
    assert res2.evidence_count == 1
    assert res2.updated_at == first_updated_at

    # 3. Third evaluation
    res3 = await growth_service.evaluate_concept_growth(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
        source_mastery_event_id=mastery_event_id,
    )
    assert res3.id == res1.id

    # 4. Verify growth event log contains exactly 1 entry
    events = await growth_service.get_growth_history(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
    )
    assert len(events) == 1
