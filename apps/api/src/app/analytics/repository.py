"""Repository for Analytics events and daily metric rollups (Phase 9).

Executes idempotent persistence and time-series aggregation queries.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime

from app.analytics.models import AnalyticsEvent, ProjectDailyMetric
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


class AnalyticsRepository:
    """Async database repository for analytics event streams and rollups."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_event(self, event: AnalyticsEvent) -> AnalyticsEvent:
        """Idempotently insert an analytics event using ON CONFLICT (id) DO NOTHING."""
        stmt = (
            insert(AnalyticsEvent)
            .values(
                id=event.id,
                event_type=event.event_type,
                user_id=event.user_id,
                project_id=event.project_id,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                occurred_at=event.occurred_at,
                ingested_at=event.ingested_at,
                schema_version=event.schema_version,
                metadata_payload=event.metadata_payload,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return event

    async def list_events(
        self,
        project_id: uuid.UUID,
        start_dt: datetime | None = None,
        end_dt: datetime | None = None,
        event_types: Sequence[str] | None = None,
    ) -> list[AnalyticsEvent]:
        """List events for a project within a time window, ordered chronologically."""
        q = select(AnalyticsEvent).where(AnalyticsEvent.project_id == project_id)
        if start_dt is not None:
            q = q.where(AnalyticsEvent.occurred_at >= start_dt)
        if end_dt is not None:
            q = q.where(AnalyticsEvent.occurred_at <= end_dt)
        if event_types:
            q = q.where(AnalyticsEvent.event_type.in_(event_types))

        q = q.order_by(AnalyticsEvent.occurred_at.asc())
        res = await self._session.execute(q)
        return list(res.scalars().all())

    async def save_daily_metric(self, metric: ProjectDailyMetric) -> ProjectDailyMetric:
        """Upsert a project daily metric rollup."""
        stmt = (
            insert(ProjectDailyMetric)
            .values(
                id=metric.id,
                project_id=metric.project_id,
                owner_id=metric.owner_id,
                date=metric.date,
                metric_category=metric.metric_category,
                metrics_payload=metric.metrics_payload,
                computed_at=metric.computed_at,
            )
            .on_conflict_do_update(
                index_elements=["project_id", "date", "metric_category"],
                set_={
                    "metrics_payload": metric.metrics_payload,
                    "computed_at": metric.computed_at,
                },
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return metric

    async def get_daily_metrics(
        self,
        project_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        categories: Sequence[str] | None = None,
    ) -> list[ProjectDailyMetric]:
        """Query daily metric rollups for a project."""
        q = select(ProjectDailyMetric).where(ProjectDailyMetric.project_id == project_id)
        if start_date is not None:
            q = q.where(ProjectDailyMetric.date >= start_date)
        if end_date is not None:
            q = q.where(ProjectDailyMetric.date <= end_date)
        if categories:
            q = q.where(ProjectDailyMetric.metric_category.in_(categories))

        q = q.order_by(ProjectDailyMetric.date.asc())
        res = await self._session.execute(q)
        return list(res.scalars().all())
