"""Recommendation repository (Phase 8).

Encapsulates database operations for Recommendations and Feedback tables.
All queries are scoped by project_id and owner_id under PostgreSQL RLS.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.platform.ids import uuid7
from app.recommendations.models import Recommendation, RecommendationFeedback
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession


class RecommendationRepository:
    """Data access layer for recommendation records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_recommendation(
        self,
        *,
        recommendation_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Recommendation | None:
        """Fetch a single recommendation by ID scoped to project and owner."""
        stmt = select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.project_id == project_id,
            Recommendation.owner_id == owner_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_active_recommendations(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        limit: int = 20,
    ) -> list[Recommendation]:
        """Fetch active (unresolved) recommendations ordered by priority score descending."""
        stmt = (
            select(Recommendation)
            .where(
                Recommendation.project_id == project_id,
                Recommendation.owner_id == owner_id,
                Recommendation.status.in_(["PENDING", "VIEWED", "STARTED"]),
            )
            .order_by(
                desc(Recommendation.priority_score),
                desc(Recommendation.created_at),
            )
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def list_all_recommendations(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        limit: int = 50,
    ) -> list[Recommendation]:
        """Fetch all recommendations (including completed/dismissed) ordered by recency."""
        stmt = (
            select(Recommendation)
            .where(
                Recommendation.project_id == project_id,
                Recommendation.owner_id == owner_id,
            )
            .order_by(desc(Recommendation.created_at))
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def get_recent_recommendations_for_concept(
        self,
        *,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        owner_id: uuid.UUID,
        since: datetime,
    ) -> list[Recommendation]:
        """Fetch recommendations created for a concept since a given timestamp for cooldown check."""
        stmt = (
            select(Recommendation)
            .where(
                Recommendation.project_id == project_id,
                Recommendation.concept_id == concept_id,
                Recommendation.owner_id == owner_id,
                Recommendation.created_at >= since,
            )
            .order_by(desc(Recommendation.created_at))
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def save_recommendation(
        self,
        *,
        recommendation_id: uuid.UUID | None = None,
        project_id: uuid.UUID,
        concept_id: uuid.UUID | None = None,
        owner_id: uuid.UUID,
        type: str,
        title: str,
        description: str,
        priority_score: float,
        priority_level: str,
        reason_codes: list[str],
        evidence_refs: dict,
        action_type: str,
        action_target: str | None = None,
        status: str = "PENDING",
        algorithm_version: str = "rec-1.0",
        source_growth_event_id: uuid.UUID | None = None,
        expires_at: datetime | None = None,
    ) -> Recommendation:
        """Persist a new recommendation."""
        rec = Recommendation(
            id=recommendation_id or uuid7(),
            project_id=project_id,
            concept_id=concept_id,
            owner_id=owner_id,
            type=type,
            title=title,
            description=description,
            priority_score=priority_score,
            priority_level=priority_level,
            reason_codes=reason_codes,
            evidence_refs=evidence_refs,
            action_type=action_type,
            action_target=action_target,
            status=status,
            algorithm_version=algorithm_version,
            source_growth_event_id=source_growth_event_id,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._session.add(rec)
        await self._session.flush()
        return rec

    async def update_recommendation_status(
        self,
        recommendation: Recommendation,
        *,
        new_status: str,
    ) -> Recommendation:
        """Update status of an existing recommendation."""
        recommendation.status = new_status
        recommendation.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return recommendation

    async def save_feedback(
        self,
        *,
        feedback_id: uuid.UUID | None = None,
        recommendation_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        action: str,
        feedback_text: str | None = None,
    ) -> RecommendationFeedback:
        """Persist a learner feedback event."""
        fb = RecommendationFeedback(
            id=feedback_id or uuid7(),
            recommendation_id=recommendation_id,
            project_id=project_id,
            owner_id=owner_id,
            action=action,
            feedback_text=feedback_text,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(fb)
        await self._session.flush()
        return fb

    async def list_feedback(
        self,
        *,
        recommendation_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[RecommendationFeedback]:
        """Fetch audit log of feedbacks for a recommendation."""
        stmt = (
            select(RecommendationFeedback)
            .where(
                RecommendationFeedback.recommendation_id == recommendation_id,
                RecommendationFeedback.project_id == project_id,
                RecommendationFeedback.owner_id == owner_id,
            )
            .order_by(RecommendationFeedback.created_at.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
