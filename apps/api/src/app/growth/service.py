"""Growth service facade (Phase 7).

Implements the public business interface for Concept Growth Engine (module-contracts §M.8):
- Trajectory and trend analysis (short-term vs long-term)
- Multi-factor weakness and attention detection
- Event evaluation, atomic persistence, and idempotency guarantees
- Project-level growth summaries and audit history
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.growth.calculator import (
    AttentionLevel,
    GrowthParameters,
    GrowthTrend,
    analyze_concept_trajectory,
)
from app.growth.models import ConceptGrowth, GrowthEvent
from app.growth.repository import GrowthRepository
from app.growth.schemas import (
    ConceptGrowthDto,
    GrowthEventDto,
    ProjectGrowthSummaryDto,
)
from app.mastery import service as mastery_service
from app.platform import db as database
from app.platform.config import get_settings
from app.platform.errors import NotFound
from app.platform.ids import uuid7
from app.platform.logging import get_logger

logger = get_logger(__name__)


def _get_growth_params() -> GrowthParameters:
    settings = get_settings()
    return GrowthParameters(
        min_observations=settings.GROWTH_MIN_OBSERVATIONS,
        stability_delta=settings.GROWTH_STABILITY_DELTA,
        significant_delta=settings.GROWTH_SIGNIFICANT_DELTA,
        short_term_window=settings.GROWTH_SHORT_TERM_WINDOW,
        long_term_window=settings.GROWTH_LONG_TERM_WINDOW,
        attention_threshold=settings.GROWTH_ATTENTION_THRESHOLD,
        weight_weakness=settings.GROWTH_ATTENTION_WEIGHT_WEAKNESS,
        weight_decline=settings.GROWTH_ATTENTION_WEIGHT_DECLINE,
        weight_mistakes=settings.GROWTH_ATTENTION_WEIGHT_MISTAKES,
        weight_inactivity=settings.GROWTH_ATTENTION_WEIGHT_INACTIVITY,
    )


def _growth_to_dto(g: ConceptGrowth) -> ConceptGrowthDto:
    return ConceptGrowthDto(
        id=g.id,
        project_id=g.project_id,
        concept_id=g.concept_id,
        current_mastery=round(g.current_mastery, 4),
        previous_mastery=round(g.previous_mastery, 4) if g.previous_mastery is not None else None,
        short_term_delta=round(g.short_term_delta, 4),
        long_term_delta=round(g.long_term_delta, 4),
        trend=GrowthTrend(g.trend),
        short_term_trend=GrowthTrend(g.short_term_trend),
        long_term_trend=GrowthTrend(g.long_term_trend),
        confidence=round(g.confidence, 4),
        evidence_count=g.evidence_count,
        attention_score=round(g.attention_score, 4),
        attention_level=AttentionLevel(g.attention_level),
        attention_required=g.attention_required,
        recent_failure_rate=round(g.recent_failure_rate, 4),
        algorithm_version=g.algorithm_version,
        last_evaluated_at=g.last_evaluated_at,
        updated_at=g.updated_at,
    )


def _event_to_dto(e: GrowthEvent) -> GrowthEventDto:
    return GrowthEventDto(
        id=e.id,
        project_id=e.project_id,
        concept_id=e.concept_id,
        source_mastery_event_id=e.source_mastery_event_id,
        previous_trend=GrowthTrend(e.previous_trend) if e.previous_trend else None,
        new_trend=GrowthTrend(e.new_trend),
        previous_attention_score=(
            round(e.previous_attention_score, 4) if e.previous_attention_score is not None else None
        ),
        new_attention_score=round(e.new_attention_score, 4),
        previous_mastery=round(e.previous_mastery, 4) if e.previous_mastery is not None else None,
        new_mastery=round(e.new_mastery, 4),
        short_term_delta=round(e.short_term_delta, 4),
        long_term_delta=round(e.long_term_delta, 4),
        algorithm_version=e.algorithm_version,
        occurred_at=e.occurred_at,
    )


async def evaluate_concept_growth(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
    source_mastery_event_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
) -> ConceptGrowthDto:
    """Evaluate and persist growth trajectory for a concept from its mastery history.

    Guarantees:
    - Atomicity: ConceptGrowth and GrowthEvent persist in the same transaction.
    - Idempotency: Duplicate calls for the same source_mastery_event_id produce 0 duplicate transitions.
    - Isolation: RLS scopes all reads and writes to (owner_id = app_user_id()).
    """
    params = _get_growth_params()
    settings = get_settings()

    # 1. Fetch current concept mastery and evidence trail from Mastery facade
    mastery_state = await mastery_service.get_concept_mastery(
        owner_id=owner_id, project_id=project_id, concept_id=concept_id
    )
    if mastery_state is None:
        raise NotFound("Concept mastery record not found in this project")

    events = await mastery_service.get_evidence_trail(
        owner_id=owner_id,
        project_id=project_id,
        concept_id=concept_id,
        limit=params.long_term_window * 2,
    )

    if events:
        mastery_history = [e.mastery_after for e in events]
        recent_results = [e.result for e in events]
    else:
        mastery_history = [mastery_state.mastery_probability]
        recent_results = []

    # 2. Pure deterministic calculation
    analysis = analyze_concept_trajectory(
        mastery_history=mastery_history,
        recent_results=recent_results,
        current_confidence=mastery_state.confidence,
        params=params,
    )

    eval_time = occurred_at or datetime.now(timezone.utc)

    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = GrowthRepository(session)

        # Idempotency check
        if source_mastery_event_id is not None and await repo.is_growth_event_processed(
            project_id=project_id,
            concept_id=concept_id,
            source_mastery_event_id=source_mastery_event_id,
        ):
            existing = await repo.get_concept_growth(
                project_id=project_id, concept_id=concept_id, owner_id=owner_id
            )
            if existing is not None:
                return _growth_to_dto(existing)

        current = await repo.get_concept_growth(
            project_id=project_id, concept_id=concept_id, owner_id=owner_id
        )

        growth_id = current.id if current else uuid7()
        prev_trend = current.trend if current else None
        prev_att_score = current.attention_score if current else None
        prev_mastery = current.current_mastery if current else None

        # 1. Persist or update ConceptGrowth first (satisfies FK on events)
        if current is None:
            growth_record = await repo.save_concept_growth(
                growth_id=growth_id,
                project_id=project_id,
                concept_id=concept_id,
                owner_id=owner_id,
                current_mastery=analysis.current_mastery,
                previous_mastery=analysis.previous_mastery,
                short_term_delta=analysis.short_term_delta,
                long_term_delta=analysis.long_term_delta,
                trend=analysis.trend.value,
                short_term_trend=analysis.short_term_trend.value,
                long_term_trend=analysis.long_term_trend.value,
                confidence=analysis.confidence,
                evidence_count=analysis.evidence_count,
                attention_score=analysis.attention_score,
                attention_level=analysis.attention_level.value,
                attention_required=analysis.attention_required,
                recent_failure_rate=analysis.recent_failure_rate,
                algorithm_version=settings.GROWTH_ALGORITHM_VERSION,
                last_evaluated_at=eval_time,
            )
        else:
            growth_record = await repo.update_concept_growth(
                current,
                current_mastery=analysis.current_mastery,
                previous_mastery=analysis.previous_mastery,
                short_term_delta=analysis.short_term_delta,
                long_term_delta=analysis.long_term_delta,
                trend=analysis.trend.value,
                short_term_trend=analysis.short_term_trend.value,
                long_term_trend=analysis.long_term_trend.value,
                confidence=analysis.confidence,
                evidence_count=analysis.evidence_count,
                attention_score=analysis.attention_score,
                attention_level=analysis.attention_level.value,
                attention_required=analysis.attention_required,
                recent_failure_rate=analysis.recent_failure_rate,
                algorithm_version=settings.GROWTH_ALGORITHM_VERSION,
                last_evaluated_at=eval_time,
            )

        # 2. Persist audit event
        event_id = uuid7()
        await repo.save_growth_event(
            event_id=event_id,
            growth_id=growth_id,
            project_id=project_id,
            concept_id=concept_id,
            owner_id=owner_id,
            source_mastery_event_id=source_mastery_event_id,
            previous_trend=prev_trend,
            new_trend=analysis.trend.value,
            previous_attention_score=prev_att_score,
            new_attention_score=analysis.attention_score,
            previous_mastery=prev_mastery,
            new_mastery=analysis.current_mastery,
            short_term_delta=analysis.short_term_delta,
            long_term_delta=analysis.long_term_delta,
            algorithm_version=settings.GROWTH_ALGORITHM_VERSION,
            occurred_at=eval_time,
        )

        logger.info(
            "growth_evaluated",
            extra={
                "details": {
                    "project_id": str(project_id),
                    "concept_id": str(concept_id),
                    "trend": analysis.trend.value,
                    "attention_score": analysis.attention_score,
                    "attention_required": analysis.attention_required,
                }
            },
        )
        return _growth_to_dto(growth_record)


async def evaluate_project_growth(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
) -> ProjectGrowthSummaryDto:
    """Evaluate and update growth states for all concepts in a project."""
    mastery_list = await mastery_service.get_project_mastery(
        owner_id=owner_id, project_id=project_id
    )

    growth_dtos: list[ConceptGrowthDto] = []
    for m in mastery_list:
        dto = await evaluate_concept_growth(
            owner_id=owner_id,
            project_id=project_id,
            concept_id=m.concept_id,
        )
        growth_dtos.append(dto)

    improving = sum(1 for g in growth_dtos if g.trend == GrowthTrend.IMPROVING)
    stable = sum(1 for g in growth_dtos if g.trend == GrowthTrend.STABLE)
    declining = sum(1 for g in growth_dtos if g.trend == GrowthTrend.DECLINING)
    insufficient = sum(1 for g in growth_dtos if g.trend == GrowthTrend.INSUFFICIENT_DATA)
    attention_concepts = [g.concept_id for g in growth_dtos if g.attention_required]

    avg_mastery = (
        sum(g.current_mastery for g in growth_dtos) / len(growth_dtos) if growth_dtos else 0.0
    )
    avg_confidence = (
        sum(g.confidence for g in growth_dtos) / len(growth_dtos) if growth_dtos else 0.0
    )

    return ProjectGrowthSummaryDto(
        project_id=project_id,
        concept_count=len(growth_dtos),
        improving_count=improving,
        stable_count=stable,
        declining_count=declining,
        insufficient_data_count=insufficient,
        attention_count=len(attention_concepts),
        attention_concepts=attention_concepts,
        average_mastery=round(avg_mastery, 4),
        average_confidence=round(avg_confidence, 4),
        concepts=growth_dtos,
        generated_at=datetime.now(timezone.utc),
    )


async def get_concept_growth(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
) -> ConceptGrowthDto | None:
    """Retrieve current growth state for a single concept."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = GrowthRepository(session)
        record = await repo.get_concept_growth(
            project_id=project_id, concept_id=concept_id, owner_id=owner_id
        )
        if record is None:
            return None
        return _growth_to_dto(record)


async def get_project_growth(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
) -> ProjectGrowthSummaryDto:
    """Retrieve or compute project-level growth summary."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = GrowthRepository(session)
        records = await repo.list_project_growth(project_id=project_id, owner_id=owner_id)

    if not records:
        return await evaluate_project_growth(owner_id=owner_id, project_id=project_id)

    growth_dtos = [_growth_to_dto(r) for r in records]
    improving = sum(1 for g in growth_dtos if g.trend == GrowthTrend.IMPROVING)
    stable = sum(1 for g in growth_dtos if g.trend == GrowthTrend.STABLE)
    declining = sum(1 for g in growth_dtos if g.trend == GrowthTrend.DECLINING)
    insufficient = sum(1 for g in growth_dtos if g.trend == GrowthTrend.INSUFFICIENT_DATA)
    attention_concepts = [g.concept_id for g in growth_dtos if g.attention_required]

    avg_mastery = (
        sum(g.current_mastery for g in growth_dtos) / len(growth_dtos) if growth_dtos else 0.0
    )
    avg_confidence = (
        sum(g.confidence for g in growth_dtos) / len(growth_dtos) if growth_dtos else 0.0
    )

    return ProjectGrowthSummaryDto(
        project_id=project_id,
        concept_count=len(growth_dtos),
        improving_count=improving,
        stable_count=stable,
        declining_count=declining,
        insufficient_data_count=insufficient,
        attention_count=len(attention_concepts),
        attention_concepts=attention_concepts,
        average_mastery=round(avg_mastery, 4),
        average_confidence=round(avg_confidence, 4),
        concepts=growth_dtos,
        generated_at=datetime.now(timezone.utc),
    )


async def get_growth_history(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
    limit: int = 100,
) -> list[GrowthEventDto]:
    """Retrieve immutable audit history of growth evaluations for a concept."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = GrowthRepository(session)
        events = await repo.list_growth_events(
            project_id=project_id,
            concept_id=concept_id,
            owner_id=owner_id,
            limit=limit,
        )
        return [_event_to_dto(e) for e in events]
