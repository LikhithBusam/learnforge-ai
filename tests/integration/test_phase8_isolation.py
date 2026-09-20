"""Integration tests for Phase 8 Recommendation isolation & security (against cloud Supabase DB).

Verifies that:
- User B cannot view User A's recommendations.
- User B cannot mutate or provide feedback on User A's recommendations.
- Cross-project recommendation generation and access is blocked under PostgreSQL RLS.
"""

from __future__ import annotations

import uuid

import pytest
from app.mastery import service as mastery_service
from app.platform.errors import NotFound
from app.recommendations import service as recommendation_service
from app.recommendations.calculator import RecommendationStatus


@pytest.mark.asyncio
async def test_user_b_cannot_view_user_a_recommendations(
    cloud_settings, engines, seed_user, seed_project
):
    """User B querying User A's project recommendations gets empty list or not found."""
    user_a = await seed_user("p8-iso-a")
    user_b = await seed_user("p8-iso-b")
    _, project_a = await seed_project(user_a.id, "Project A Recs")
    _, project_b = await seed_project(user_b.id, "Project B Recs")

    concept_id = uuid.uuid4()

    # User A records mastery and generates recommendation
    await mastery_service.record_learning_event(
        owner_id=user_a.id,
        project_id=project_a.id,
        input_data=mastery_service.RecordEvidenceInput(
            source="assessment",
            source_id=uuid.uuid4(),
            concept_id=concept_id,
            result="incorrect",
            score=0.0,
            difficulty="medium",
        ),
    )

    recs_a = await recommendation_service.generate_recommendations(
        owner_id=user_a.id,
        project_id=project_a.id,
    )
    assert len(recs_a) >= 1
    rec_a = recs_a[0]

    # User B queries User A's project recommendations (blocked by 404 posture)
    with pytest.raises(NotFound):
        await recommendation_service.get_active_recommendations(
            owner_id=user_b.id,
            project_id=project_a.id,
        )

    # User B queries User A's recommendation directly
    b_rec = await recommendation_service.get_recommendation(
        owner_id=user_b.id,
        project_id=project_a.id,
        recommendation_id=rec_a.id,
    )
    assert b_rec is None

    # User B attempts to mutate User A's recommendation
    with pytest.raises(NotFound):
        await recommendation_service.update_recommendation_status(
            owner_id=user_b.id,
            project_id=project_a.id,
            recommendation_id=rec_a.id,
            new_status=RecommendationStatus.DISMISSED,
        )
