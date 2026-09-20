"""Integration tests for Phase 8 Recommendation Engine (against cloud Supabase DB).

Tests end-to-end recommendation generation, priority scoring,
lifecycle state transitions, feedback auditing, and project-level queries.
"""

from __future__ import annotations

import uuid

import pytest
from app.growth import service as growth_service
from app.mastery import service as mastery_service
from app.recommendations import service as recommendation_service
from app.recommendations.calculator import (
    RecommendationStatus,
)


@pytest.mark.asyncio
async def test_full_recommendation_lifecycle_e2e(cloud_settings, engines, seed_user, seed_project):
    """Full pipeline: Mastery evidence -> Growth evaluation -> Recommendation generation -> Status lifecycle."""
    user = await seed_user("p8-rec-user")
    _, project = await seed_project(user.id, "Cloud Recommendation Project")

    concept_id = uuid.uuid4()

    # 1. Record struggling mastery sequence (starts high then drops sharply to create declining trend & high attention)
    # 2 correct
    for _ in range(2):
        await mastery_service.record_learning_event(
            owner_id=user.id,
            project_id=project.id,
            input_data=mastery_service.RecordEvidenceInput(
                source="assessment",
                source_id=uuid.uuid4(),
                concept_id=concept_id,
                result="correct",
                score=1.0,
                difficulty="hard",
            ),
        )

    # 3 incorrect
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

    trail = await mastery_service.get_evidence_trail(
        owner_id=user.id, project_id=project.id, concept_id=concept_id
    )

    # 2. Evaluate growth
    growth_dto = await growth_service.evaluate_concept_growth(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
        source_mastery_event_id=trail[-1].id,
    )
    assert growth_dto.trend.value == "declining"
    assert growth_dto.attention_required is True

    # 3. Generate recommendations
    recs = await recommendation_service.generate_recommendations(
        owner_id=user.id,
        project_id=project.id,
    )
    assert len(recs) >= 1

    rec = recs[0]
    assert rec.project_id == project.id
    assert rec.concept_id == concept_id
    assert rec.status == RecommendationStatus.PENDING
    assert rec.priority_score > 0.0

    # 4. Query active recommendations list
    active_list = await recommendation_service.get_active_recommendations(
        owner_id=user.id,
        project_id=project.id,
    )
    assert active_list.count >= 1
    assert any(r.id == rec.id for r in active_list.recommendations)

    # 5. Lifecycle transitions: PENDING -> VIEWED -> STARTED -> COMPLETED
    viewed = await recommendation_service.update_recommendation_status(
        owner_id=user.id,
        project_id=project.id,
        recommendation_id=rec.id,
        new_status=RecommendationStatus.VIEWED,
    )
    assert viewed.status == RecommendationStatus.VIEWED

    started = await recommendation_service.update_recommendation_status(
        owner_id=user.id,
        project_id=project.id,
        recommendation_id=rec.id,
        new_status=RecommendationStatus.STARTED,
    )
    assert started.status == RecommendationStatus.STARTED

    completed = await recommendation_service.update_recommendation_status(
        owner_id=user.id,
        project_id=project.id,
        recommendation_id=rec.id,
        new_status=RecommendationStatus.COMPLETED,
        feedback_text="Mastered the concept after review!",
    )
    assert completed.status == RecommendationStatus.COMPLETED
