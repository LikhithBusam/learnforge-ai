"""Integration tests for Phase 7 Growth concurrency (against cloud Supabase DB).

Verifies that concurrent evaluation requests for the same concept handle database
concurrency safely and preserve state consistency.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from app.growth import service as growth_service
from app.mastery import service as mastery_service


@pytest.mark.asyncio
async def test_concurrent_growth_evaluations(cloud_settings, engines, seed_user, seed_project):
    """Multiple concurrent evaluations for the same concept execute cleanly."""
    user = await seed_user("p7-concur-user")
    _, project = await seed_project(user.id, "Growth Concurrency Project")

    concept_id = uuid.uuid4()

    # Record 3 mastery events first
    for _ in range(3):
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

    # Launch 5 concurrent evaluations
    tasks = [
        growth_service.evaluate_concept_growth(
            owner_id=user.id,
            project_id=project.id,
            concept_id=concept_id,
        )
        for _ in range(5)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # At least one or all must succeed, with valid ConceptGrowthDto returned
    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(successes) >= 1

    # Verify final state is valid and consistent
    final = await growth_service.get_concept_growth(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
    )
    assert final is not None
    assert final.evidence_count == 3
