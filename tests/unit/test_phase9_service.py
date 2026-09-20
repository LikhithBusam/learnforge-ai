"""Unit tests for Phase 9 Analytics service and schema DTOs."""

from __future__ import annotations

import datetime
import uuid

from app.analytics.schemas import (
    ActivityAnalyticsDto,
    AssessmentAnalyticsDto,
    GrowthAnalyticsDto,
    MasteryAnalyticsDto,
    MaterialsAnalyticsDto,
    ProjectAnalyticsOverviewDto,
    RecommendationsAnalyticsDto,
    TutorAnalyticsDto,
)


def test_analytics_schemas_serialization():
    """Verify serialization of all typed analytics DTOs."""
    proj_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.timezone.utc)

    activity = ActivityAnalyticsDto(
        project_id=proj_id,
        range="30d",
        active_days=5,
        study_events=20,
        last_activity_at=now,
    )
    tutor = TutorAnalyticsDto(
        project_id=proj_id,
        range="30d",
        conversations=3,
        messages=15,
        grounded_responses=12,
        insufficient_evidence=3,
        citations_used=18,
        grounded_response_rate=0.80,
    )
    assessment = AssessmentAnalyticsDto(
        project_id=proj_id,
        range="30d",
        quizzes_started=4,
        quizzes_completed=4,
        completion_rate=1.0,
        question_attempts=20,
        correct_attempts=16,
        incorrect_attempts=4,
        pending_review_attempts=0,
        accuracy=0.80,
    )
    mastery = MasteryAnalyticsDto(
        project_id=proj_id,
        range="30d",
        developing=2,
        progressing=3,
        mastered=5,
        total_concepts=10,
    )
    growth = GrowthAnalyticsDto(
        project_id=proj_id,
        range="30d",
        improving=4,
        stable=4,
        declining=2,
        attention_required=2,
        total_evaluated=10,
    )
    recs = RecommendationsAnalyticsDto(
        project_id=proj_id,
        range="30d",
        generated=6,
        pending=2,
        viewed=1,
        started=1,
        completed=2,
        dismissed=0,
        completion_rate=0.3333,
    )
    materials = MaterialsAnalyticsDto(
        project_id=proj_id,
        range="30d",
        materials_uploaded=2,
        documents_processed=2,
        ready_documents=2,
        failed_documents=0,
        total_pages=45,
        total_chunks=135,
    )

    overview = ProjectAnalyticsOverviewDto(
        project_id=proj_id,
        range="30d",
        activity=activity,
        tutor=tutor,
        assessment=assessment,
        mastery=mastery,
        growth=growth,
        recommendations=recs,
        materials=materials,
    )

    dumped = overview.model_dump()
    assert dumped["project_id"] == proj_id
    assert dumped["activity"]["active_days"] == 5
    assert dumped["tutor"]["grounded_response_rate"] == 0.80
    assert dumped["mastery"]["mastered"] == 5
