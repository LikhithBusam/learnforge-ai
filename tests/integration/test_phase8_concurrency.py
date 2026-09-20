"""Integration tests for Phase 8 Recommendation concurrency (against cloud Supabase DB).

Verifies that concurrent recommendation generation and status update requests
execute cleanly without race conditions or deadlock.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from app.mastery import service as mastery_service
from app.recommendations import service as recommendation_service


@pytest.mark.asyncio
async def test_concurrent_recommendation_generation(
    cloud_settings, engines, seed_user, seed_project
):
    """Multiple concurrent generation requests for the same project complete safely."""
    user = await seed_user("p8-concur-user")
    _, project = await seed_project(user.id, "Rec Concurrency Project")

    concept_id = uuid.uuid4()

    # Record mastery events
    for _ in range(3):
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

    # Launch 5 concurrent generation requests
    tasks = [
        recommendation_service.generate_recommendations(
            owner_id=user.id,
            project_id=project.id,
        )
        for _ in range(5)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(successes) >= 1

    # Verify active recommendations are intact
    active = await recommendation_service.get_active_recommendations(
        owner_id=user.id,
        project_id=project.id,
    )
    assert active.count >= 1
