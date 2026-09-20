"""Growth repository — project-scoped data access (module-contracts §M.8).

All queries carry both owner_id and project_id for RLS alignment.
The repository never performs trend calculation or policy decisions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.growth.models import ConceptGrowth, GrowthEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class GrowthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Concept Growth State
    # ------------------------------------------------------------------

    async def get_concept_growth(
        self,
        *,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> ConceptGrowth | None:
        """Fetch current growth and trajectory state for a concept in a project."""
        stmt = (
            select(ConceptGrowth)
            .options(selectinload(ConceptGrowth.events))
            .where(
                ConceptGrowth.project_id == project_id,
                ConceptGrowth.concept_id == concept_id,
                ConceptGrowth.owner_id == owner_id,
            )
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_project_growth(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[ConceptGrowth]:
        """Fetch all concept growth states for a project."""
        stmt = (
            select(ConceptGrowth)
            .options(selectinload(ConceptGrowth.events))
            .where(
                ConceptGrowth.project_id == project_id,
                ConceptGrowth.owner_id == owner_id,
            )
            .order_by(ConceptGrowth.attention_score.desc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def save_concept_growth(
        self,
        *,
        growth_id: uuid.UUID,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        owner_id: uuid.UUID,
        current_mastery: float,
        previous_mastery: float | None,
        short_term_delta: float,
        long_term_delta: float,
        trend: str,
        short_term_trend: str,
        long_term_trend: str,
        confidence: float,
        evidence_count: int,
        attention_score: float,
        attention_level: str,
        attention_required: bool,
        recent_failure_rate: float,
        algorithm_version: str,
        last_evaluated_at: datetime,
    ) -> ConceptGrowth:
        """Insert a brand new concept growth record."""
        growth = ConceptGrowth(
            id=growth_id,
            project_id=project_id,
            concept_id=concept_id,
            owner_id=owner_id,
            current_mastery=current_mastery,
            previous_mastery=previous_mastery,
            short_term_delta=short_term_delta,
            long_term_delta=long_term_delta,
            trend=trend,
            short_term_trend=short_term_trend,
            long_term_trend=long_term_trend,
            confidence=confidence,
            evidence_count=evidence_count,
            attention_score=attention_score,
            attention_level=attention_level,
            attention_required=attention_required,
            recent_failure_rate=recent_failure_rate,
            algorithm_version=algorithm_version,
            last_evaluated_at=last_evaluated_at,
        )
        self._session.add(growth)
        await self._session.flush()
        return growth

    async def update_concept_growth(
        self,
        growth: ConceptGrowth,
        *,
        current_mastery: float,
        previous_mastery: float | None,
        short_term_delta: float,
        long_term_delta: float,
        trend: str,
        short_term_trend: str,
        long_term_trend: str,
        confidence: float,
        evidence_count: int,
        attention_score: float,
        attention_level: str,
        attention_required: bool,
        recent_failure_rate: float,
        algorithm_version: str,
        last_evaluated_at: datetime,
    ) -> ConceptGrowth:
        """Update existing concept growth metrics."""
        growth.current_mastery = current_mastery
        growth.previous_mastery = previous_mastery
        growth.short_term_delta = short_term_delta
        growth.long_term_delta = long_term_delta
        growth.trend = trend
        growth.short_term_trend = short_term_trend
        growth.long_term_trend = long_term_trend
        growth.confidence = confidence
        growth.evidence_count = evidence_count
        growth.attention_score = attention_score
        growth.attention_level = attention_level
        growth.attention_required = attention_required
        growth.recent_failure_rate = recent_failure_rate
        growth.algorithm_version = algorithm_version
        growth.last_evaluated_at = last_evaluated_at
        growth.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return growth

    # ------------------------------------------------------------------
    # Growth Events / Audit Trail
    # ------------------------------------------------------------------

    async def is_growth_event_processed(
        self,
        *,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        source_mastery_event_id: uuid.UUID | None,
    ) -> bool:
        """Check if a growth evaluation has already been processed for this mastery event."""
        if source_mastery_event_id is None:
            return False
        stmt = select(GrowthEvent.id).where(
            GrowthEvent.project_id == project_id,
            GrowthEvent.concept_id == concept_id,
            GrowthEvent.source_mastery_event_id == source_mastery_event_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none() is not None

    async def save_growth_event(
        self,
        *,
        event_id: uuid.UUID,
        growth_id: uuid.UUID | None,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        owner_id: uuid.UUID,
        source_mastery_event_id: uuid.UUID | None,
        previous_trend: str | None,
        new_trend: str,
        previous_attention_score: float | None,
        new_attention_score: float,
        previous_mastery: float | None,
        new_mastery: float,
        short_term_delta: float,
        long_term_delta: float,
        algorithm_version: str,
        occurred_at: datetime,
    ) -> GrowthEvent:
        """Persist an immutable growth evaluation event."""
        event = GrowthEvent(
            id=event_id,
            growth_id=growth_id,
            project_id=project_id,
            concept_id=concept_id,
            owner_id=owner_id,
            source_mastery_event_id=source_mastery_event_id,
            previous_trend=previous_trend,
            new_trend=new_trend,
            previous_attention_score=previous_attention_score,
            new_attention_score=new_attention_score,
            previous_mastery=previous_mastery,
            new_mastery=new_mastery,
            short_term_delta=short_term_delta,
            long_term_delta=long_term_delta,
            algorithm_version=algorithm_version,
            occurred_at=occurred_at,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_growth_events(
        self,
        *,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        owner_id: uuid.UUID,
        limit: int = 100,
    ) -> list[GrowthEvent]:
        """Fetch audit trail of growth evaluations for a given concept in a project."""
        stmt = (
            select(GrowthEvent)
            .where(
                GrowthEvent.project_id == project_id,
                GrowthEvent.concept_id == concept_id,
                GrowthEvent.owner_id == owner_id,
            )
            .order_by(GrowthEvent.occurred_at.asc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
