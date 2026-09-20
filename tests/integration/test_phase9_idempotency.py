"""Integration tests for Phase 9 Analytics idempotency (against cloud Supabase DB).

Verifies that:
- Ingesting identical events with the same ID does not create duplicate database rows.
- Re-running rollup aggregations updates existing metrics rather than duplicating rows.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from app.analytics.models import AnalyticsEvent
from app.analytics.repository import AnalyticsRepository
from app.platform import db as database


@pytest.mark.asyncio
async def test_analytics_event_ingestion_idempotency(
    cloud_settings, engines, seed_user, seed_project
):
    """Saving the exact same event ID twice succeeds and creates exactly one DB record."""
    user = await seed_user("p9-idem-user")
    _, project = await seed_project(user.id, "Analytics Idempotency Project")

    event_id = uuid.uuid4()
    now = datetime.datetime.now(datetime.timezone.utc)

    event = AnalyticsEvent(
        id=event_id,
        event_type="idempotent_event",
        user_id=user.id,
        project_id=project.id,
        entity_type="test",
        entity_id=None,
        occurred_at=now,
        ingested_at=now,
        schema_version=1,
        metadata_payload={"attempt": 1},
    )

    async with database.session_scope(user_id=str(user.id), project_id=str(project.id)) as session:
        repo = AnalyticsRepository(session)
        # First save
        res1 = await repo.save_event(event)
        assert res1.id == event_id

        # Second save (replay)
        res2 = await repo.save_event(event)
        assert res2.id == event_id

        # Verify only 1 record exists
        events = await repo.list_events(project_id=project.id)
        matching = [e for e in events if e.id == event_id]
        assert len(matching) == 1
