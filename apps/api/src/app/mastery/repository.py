"""Mastery repository — project-scoped data access (module-contracts §M.7).

All queries carry both owner_id and project_id for RLS alignment.
The repository never performs BKT math or policy decisions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.mastery.models import ConceptMastery, MasteryEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class MasteryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Concept Mastery
    # ------------------------------------------------------------------

    async def get_concept_mastery(
        self,
        *,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> ConceptMastery | None:
        """Fetch current mastery state for a concept within a project."""
        stmt = (
            select(ConceptMastery)
            .options(selectinload(ConceptMastery.events))
            .where(
                ConceptMastery.project_id == project_id,
                ConceptMastery.concept_id == concept_id,
                ConceptMastery.owner_id == owner_id,
            )
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_project_mastery(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[ConceptMastery]:
        """Fetch all concept mastery states for a project."""
        stmt = (
            select(ConceptMastery)
            .options(selectinload(ConceptMastery.events))
            .where(
                ConceptMastery.project_id == project_id,
                ConceptMastery.owner_id == owner_id,
            )
            .order_by(ConceptMastery.mastery_probability.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def save_concept_mastery(
        self,
        *,
        mastery_id: uuid.UUID,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        owner_id: uuid.UUID,
        mastery_probability: float,
        confidence: float,
        evidence_count: int,
        correct_count: int,
        incorrect_count: int,
        partial_count: int,
        consecutive_correct: int,
        last_evidence_at: datetime | None,
        algorithm_version: str,
    ) -> ConceptMastery:
        """Insert a brand new concept mastery row."""
        mastery = ConceptMastery(
            id=mastery_id,
            project_id=project_id,
            concept_id=concept_id,
            owner_id=owner_id,
            mastery_probability=mastery_probability,
            confidence=confidence,
            evidence_count=evidence_count,
            correct_count=correct_count,
            incorrect_count=incorrect_count,
            partial_count=partial_count,
            consecutive_correct=consecutive_correct,
            last_evidence_at=last_evidence_at,
            algorithm_version=algorithm_version,
        )
        self._session.add(mastery)
        await self._session.flush()
        return mastery

    async def update_concept_mastery(
        self,
        mastery: ConceptMastery,
        *,
        mastery_probability: float,
        confidence: float,
        evidence_count: int,
        correct_count: int,
        incorrect_count: int,
        partial_count: int,
        consecutive_correct: int,
        last_evidence_at: datetime | None,
        algorithm_version: str,
    ) -> ConceptMastery:
        """Update existing concept mastery metrics."""
        mastery.mastery_probability = mastery_probability
        mastery.confidence = confidence
        mastery.evidence_count = evidence_count
        mastery.correct_count = correct_count
        mastery.incorrect_count = incorrect_count
        mastery.partial_count = partial_count
        mastery.consecutive_correct = consecutive_correct
        mastery.last_evidence_at = last_evidence_at
        mastery.algorithm_version = algorithm_version
        mastery.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return mastery

    # ------------------------------------------------------------------
    # Mastery Events / Audit Trail
    # ------------------------------------------------------------------

    async def is_evidence_processed(
        self,
        *,
        source: str,
        source_id: uuid.UUID,
        concept_id: uuid.UUID,
    ) -> bool:
        """Check if an evidence item has already been applied to this concept."""
        stmt = select(MasteryEvent.id).where(
            MasteryEvent.source == source,
            MasteryEvent.source_id == source_id,
            MasteryEvent.concept_id == concept_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none() is not None

    async def save_mastery_event(
        self,
        *,
        event_id: uuid.UUID,
        mastery_id: uuid.UUID | None,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        owner_id: uuid.UUID,
        source: str,
        source_id: uuid.UUID,
        mastery_before: float,
        mastery_after: float,
        confidence_before: float,
        confidence_after: float,
        result: str,
        score: float,
        difficulty: str,
        algorithm_version: str,
        occurred_at: datetime,
    ) -> MasteryEvent:
        """Persist an immutable audit step."""
        event = MasteryEvent(
            id=event_id,
            mastery_id=mastery_id,
            project_id=project_id,
            concept_id=concept_id,
            owner_id=owner_id,
            source=source,
            source_id=source_id,
            mastery_before=mastery_before,
            mastery_after=mastery_after,
            confidence_before=confidence_before,
            confidence_after=confidence_after,
            result=result,
            score=score,
            difficulty=difficulty,
            algorithm_version=algorithm_version,
            occurred_at=occurred_at,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_mastery_events(
        self,
        *,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        owner_id: uuid.UUID,
        limit: int = 100,
    ) -> list[MasteryEvent]:
        """Fetch audit trail for a given concept in a project."""
        stmt = (
            select(MasteryEvent)
            .where(
                MasteryEvent.project_id == project_id,
                MasteryEvent.concept_id == concept_id,
                MasteryEvent.owner_id == owner_id,
            )
            .order_by(MasteryEvent.occurred_at.asc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())
