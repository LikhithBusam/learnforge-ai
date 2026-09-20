"""Integration tests for Phase 9 Analytics isolation & security (against cloud Supabase DB).

Verifies that:
- User B cannot view User A's analytics or event stream.
- Cross-project analytics queries are rejected with 404 under project scoping and RLS.
"""

from __future__ import annotations

import datetime

import pytest
from app.analytics import service as analytics_service
from app.analytics.schemas import AnalyticsEventInput
from app.platform.errors import NotFound


@pytest.mark.asyncio
async def test_user_b_cannot_view_user_a_analytics(
    cloud_settings, engines, seed_user, seed_project
):
    """User B querying User A's project analytics receives 404 NotFound."""
    user_a = await seed_user("p9-iso-a")
    user_b = await seed_user("p9-iso-b")
    _, project_a = await seed_project(user_a.id, "Project A Analytics")
    _, project_b = await seed_project(user_b.id, "Project B Analytics")

    # User A records an event
    await analytics_service.record_event(
        owner_id=user_a.id,
        project_id=project_a.id,
        input_data=AnalyticsEventInput(
            event_type="test_event",
            entity_type="test",
            occurred_at=datetime.datetime.now(datetime.timezone.utc),
        ),
    )

    # User B queries User A's overview (must raise 404 NotFound)
    with pytest.raises(NotFound):
        await analytics_service.get_project_overview(
            owner_id=user_b.id,
            project_id=project_a.id,
            range_str="30d",
        )

    # User B queries User A's activity analytics
    with pytest.raises(NotFound):
        await analytics_service.get_activity_analytics(
            owner_id=user_b.id,
            project_id=project_a.id,
            range_str="30d",
        )

    # User B tries to record an event in User A's project
    with pytest.raises(NotFound):
        await analytics_service.record_event(
            owner_id=user_b.id,
            project_id=project_a.id,
            input_data=AnalyticsEventInput(
                event_type="malicious_event",
                entity_type="attack",
            ),
        )
