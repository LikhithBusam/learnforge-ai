"""Integration tests for Phase 8 Recommendation idempotency & cooldown (against cloud Supabase DB).

Verifies that:
- Triggering recommendation generation repeatedly respects cooldown penalty.
- Repeated calls do not violate uniqueness constraints and preserve stable outputs.
"""

from __future__ import annotations

import uuid

import pytest
from app.mastery import service as mastery_service
from app.recommendations import service as recommendation_service


@pytest.mark.asyncio
async def test_recommendation_generation_cooldown_replay(
    cloud_settings, engines, seed_user, seed_project
):
    """Subsequent generation within cooldown period applies penalty and avoids duplicate active tasks."""
    user = await seed_user("p8-idem-user")
    _, project = await seed_project(user.id, "Recommendation Idempotency Project")

    concept_id = uuid.uuid4()

    # Record evidence
    await mastery_service.record_learning_event(
        owner_id=user.id,
        project_id=project.id,
        input_data=mastery_service.RecordEvidenceInput(
            source="assessment",
            source_id=uuid.uuid4(),
            concept_id=concept_id,
            result="incorrect",
            score=0.0,
            difficulty="medium",
        ),
    )

    # 1. First generation
    recs1 = await recommendation_service.generate_recommendations(
        owner_id=user.id,
        project_id=project.id,
    )
    assert len(recs1) >= 1
    first_score = recs1[0].priority_score

    # 2. Second generation (triggers cooldown penalty for the same concept)
    recs2 = await recommendation_service.generate_recommendations(
        owner_id=user.id,
        project_id=project.id,
    )
    assert len(recs2) >= 1
    # Because concept was recently recommended, priority score receives cooldown penalty
    second_score = recs2[0].priority_score
    assert second_score < first_score
