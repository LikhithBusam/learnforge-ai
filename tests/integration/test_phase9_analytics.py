"""Integration tests for Phase 9 Analytics & Progress Dashboard (against cloud Supabase DB).

Tests end-to-end event recording, activity metrics, overview aggregation,
and daily rollup persistence.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from app.analytics import service as analytics_service
from app.analytics.schemas import AnalyticsEventInput
from app.mastery import service as mastery_service


@pytest.mark.asyncio
async def test_full_analytics_lifecycle_e2e(cloud_settings, engines, seed_user, seed_project):
    """Full pipeline: Ingest events -> Record mastery -> Fetch overview -> Refresh rollups."""
    user = await seed_user("p9-analytics-user")
    _, project = await seed_project(user.id, "Cloud Analytics Project")

    concept_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. Ingest analytics events
    ev1 = await analytics_service.record_event(
        owner_id=user.id,
        project_id=project.id,
        input_data=AnalyticsEventInput(
            event_type="study_session_started",
            entity_type="session",
            occurred_at=now - datetime.timedelta(days=1),
            metadata_payload={"device": "desktop"},
        ),
    )
    assert ev1.id is not None
    assert ev1.project_id == project.id

    ev2 = await analytics_service.record_event(
        owner_id=user.id,
        project_id=project.id,
        input_data=AnalyticsEventInput(
            event_type="document_viewed",
            entity_type="material",
            occurred_at=now,
            metadata_payload={"page": 1},
        ),
    )
    assert ev2.id is not None

    # 2. Record mastery evidence to exercise cross-domain aggregation
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

    # 3. Query activity analytics
    activity = await analytics_service.get_activity_analytics(
        owner_id=user.id,
        project_id=project.id,
        range_str="30d",
    )
    assert activity.study_events >= 2
    assert activity.active_days >= 1

    # 4. Query comprehensive project overview
    overview = await analytics_service.get_project_overview(
        owner_id=user.id,
        project_id=project.id,
        range_str="30d",
    )
    assert overview.project_id == project.id
    assert overview.activity.study_events >= 2
    assert overview.mastery.total_concepts >= 1

    # 5. Precompute daily rollups
    await analytics_service.refresh_project_rollups(
        owner_id=user.id,
        project_id=project.id,
        target_date=now.date(),
    )
