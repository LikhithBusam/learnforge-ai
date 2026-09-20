"""Recommendation service facade (Phase 8).

Implements the public business interface for Recommendation Engine (module-contracts §M.9):
- Evidence-driven candidate generation across Mastery, Growth, Materials, and Workspace
- Multi-signal deterministic scoring and ranking
- Cooldown tracking, deduplication, and persistence
- Recommendation lifecycle state transitions and feedback auditing
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.growth import service as growth_service
from app.mastery import service as mastery_service
from app.materials import service as materials_service
from app.platform import db as database
from app.platform.config import get_settings
from app.platform.errors import NotFound, ValidationError
from app.platform.ids import uuid7
from app.platform.logging import get_logger
from app.recommendations.calculator import (
    ConceptContext,
    ReasonCode,
    RecommendationParameters,
    RecommendationPriorityLevel,
    RecommendationStatus,
    RecommendationType,
    ScoredRecommendationCandidate,
    generate_candidates_for_concept,
    is_valid_status_transition,
    rank_and_filter_recommendations,
)
from app.recommendations.models import Recommendation
from app.recommendations.policies import assert_recommendation_owned
from app.recommendations.repository import RecommendationRepository
from app.recommendations.schemas import (
    RecommendationDto,
    RecommendationListDto,
)
from app.workspace import service as workspace_service

logger = get_logger(__name__)


def _get_recommendation_params() -> RecommendationParameters:
    settings = get_settings()
    return RecommendationParameters(
        top_k=settings.RECOMMENDATION_TOP_K,
        cooldown_hours=settings.RECOMMENDATION_COOLDOWN_HOURS,
        weight_weakness=settings.RECOMMENDATION_WEIGHT_WEAKNESS,
        weight_decline=settings.RECOMMENDATION_WEIGHT_DECLINE,
        weight_failures=settings.RECOMMENDATION_WEIGHT_FAILURES,
        weight_low_conf=settings.RECOMMENDATION_WEIGHT_LOW_CONF,
        weight_material=settings.RECOMMENDATION_WEIGHT_MATERIAL,
        penalty_recent_rec=settings.RECOMMENDATION_PENALTY_RECENT_REC,
    )


def _rec_to_dto(r: Recommendation) -> RecommendationDto:
    return RecommendationDto(
        id=r.id,
        project_id=r.project_id,
        concept_id=r.concept_id,
        type=RecommendationType(r.type),
        title=r.title,
        description=r.description,
        priority_score=round(r.priority_score, 4),
        priority_level=RecommendationPriorityLevel(r.priority_level),
        reason_codes=[ReasonCode(code) for code in r.reason_codes],
        evidence_refs=r.evidence_refs,
        action_type=r.action_type,
        action_target=r.action_target,
        status=RecommendationStatus(r.status),
        algorithm_version=r.algorithm_version,
        source_growth_event_id=r.source_growth_event_id,
        expires_at=r.expires_at,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


async def generate_recommendations(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    source_growth_event_id: uuid.UUID | None = None,
) -> list[RecommendationDto]:
    """Generate and persist prioritized recommendations for a project.

    Guarantees:
    - Zero LLM dependencies for candidate selection or scoring.
    - Strict architectural boundaries (reads via service facades).
    - Idempotency & Cooldown: prevents spamming repeated recommendations for recent concepts.
    - Project isolation: enforced via RLS.
    """
    params = _get_recommendation_params()
    settings = get_settings()

    # 1. Verify project in scope
    await workspace_service.get_project_in_scope(principal_user_id=owner_id, project_id=project_id)

    # 2. Gather signals from upstream domains
    mastery_list = await mastery_service.get_project_mastery(
        owner_id=owner_id, project_id=project_id
    )
    growth_summary = await growth_service.get_project_growth(
        owner_id=owner_id, project_id=project_id
    )
    materials = await materials_service.list_materials(owner_id=owner_id, project_id=project_id)

    ready_materials = [m for m in materials if m.status == "ready"]
    material_ids = [m.id for m in ready_materials]
    material_titles = [m.title for m in ready_materials]

    growth_by_concept = {g.concept_id: g for g in growth_summary.concepts}

    now = datetime.now(timezone.utc)
    cooldown_cutoff = now - timedelta(hours=params.cooldown_hours)

    all_candidates: list[ScoredRecommendationCandidate] = []

    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = RecommendationRepository(session)

        # Handle cold start: no concept mastery yet
        if not mastery_list:
            if ready_materials:
                # Suggest reviewing available material or taking diagnostic quiz
                mat = ready_materials[0]
                rec_record = await repo.save_recommendation(
                    recommendation_id=uuid7(),
                    project_id=project_id,
                    concept_id=None,
                    owner_id=owner_id,
                    type=RecommendationType.REVISIT_MATERIAL.value,
                    title=f"Get started with study material: {mat.title}",
                    description=f"Begin learning by reviewing the uploaded material '{mat.title}'.",
                    priority_score=0.60,
                    priority_level="medium",
                    reason_codes=[ReasonCode.COLD_START.value, ReasonCode.MATERIAL_AVAILABLE.value],
                    evidence_refs={"material_id": str(mat.id)},
                    action_type="open_material",
                    action_target=str(mat.id),
                    status=RecommendationStatus.PENDING.value,
                    algorithm_version=settings.RECOMMENDATION_ALGORITHM_VERSION,
                    source_growth_event_id=source_growth_event_id,
                )
                return [_rec_to_dto(rec_record)]
            return []

        # Process each concept
        for m in mastery_list:
            growth_dto = growth_by_concept.get(m.concept_id)

            # Check cooldown
            recent_recs = await repo.get_recent_recommendations_for_concept(
                project_id=project_id,
                concept_id=m.concept_id,
                owner_id=owner_id,
                since=cooldown_cutoff,
            )
            recently_rec = len(recent_recs) > 0

            # Get evidence trail for failure calculation
            trail = await mastery_service.get_evidence_trail(
                owner_id=owner_id,
                project_id=project_id,
                concept_id=m.concept_id,
                limit=5,
            )
            evidence_ids = [e.id for e in trail]
            if trail:
                failures = sum(1 for e in trail if e.result in ("incorrect", "partial"))
                failure_rate = failures / len(trail)
            else:
                failure_rate = 0.0

            ctx = ConceptContext(
                concept_id=m.concept_id,
                mastery_probability=m.mastery_probability,
                confidence=m.confidence,
                growth_trend=growth_dto.trend.value if growth_dto else "insufficient_data",
                short_term_delta=growth_dto.short_term_delta if growth_dto else 0.0,
                recent_failure_rate=failure_rate,
                attention_required=growth_dto.attention_required if growth_dto else False,
                material_ids=material_ids,
                material_titles=material_titles,
                recently_recommended=recently_rec,
                mastery_state_id=m.id,
                growth_state_id=growth_dto.id if growth_dto else None,
                recent_evidence_ids=evidence_ids,
            )

            concept_candidates = generate_candidates_for_concept(ctx, params)
            all_candidates.extend(concept_candidates)

        # 3. Rank and filter
        ranked = rank_and_filter_recommendations(all_candidates, top_k=params.top_k)

        # 4. Persist newly ranked recommendations
        persisted_dtos: list[RecommendationDto] = []
        for cand in ranked:
            rec_id = uuid7()
            rec = await repo.save_recommendation(
                recommendation_id=rec_id,
                project_id=project_id,
                concept_id=cand.concept_id,
                owner_id=owner_id,
                type=cand.recommendation_type.value,
                title=cand.title,
                description=cand.description,
                priority_score=cand.priority_score,
                priority_level=cand.priority_level.value,
                reason_codes=[r.value for r in cand.reason_codes],
                evidence_refs=cand.evidence_refs,
                action_type=cand.action_type,
                action_target=cand.action_target,
                status=RecommendationStatus.PENDING.value,
                algorithm_version=settings.RECOMMENDATION_ALGORITHM_VERSION,
                source_growth_event_id=source_growth_event_id,
            )
            persisted_dtos.append(_rec_to_dto(rec))

        logger.info(
            "recommendations_generated",
            extra={
                "details": {
                    "project_id": str(project_id),
                    "candidate_count": len(all_candidates),
                    "selected_count": len(persisted_dtos),
                }
            },
        )
        return persisted_dtos


async def get_active_recommendations(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    limit: int = 20,
) -> RecommendationListDto:
    """Retrieve active recommendations for a project, generating them if none exist."""
    # Ensure project belongs to caller (404 posture)
    await workspace_service.get_project_in_scope(principal_user_id=owner_id, project_id=project_id)

    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = RecommendationRepository(session)
        records = await repo.list_active_recommendations(
            project_id=project_id, owner_id=owner_id, limit=limit
        )

    if not records:
        dtos = await generate_recommendations(owner_id=owner_id, project_id=project_id)
    else:
        dtos = [_rec_to_dto(r) for r in records]

    return RecommendationListDto(
        project_id=project_id,
        count=len(dtos),
        recommendations=dtos,
        generated_at=datetime.now(timezone.utc),
    )


async def get_recommendation(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    recommendation_id: uuid.UUID,
) -> RecommendationDto | None:
    """Retrieve a single recommendation by ID."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = RecommendationRepository(session)
        record = await repo.get_recommendation(
            recommendation_id=recommendation_id,
            project_id=project_id,
            owner_id=owner_id,
        )
        if record is None:
            return None
        return _rec_to_dto(record)


async def update_recommendation_status(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    new_status: RecommendationStatus,
    feedback_text: str | None = None,
) -> RecommendationDto:
    """Transition recommendation state and record learner feedback."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = RecommendationRepository(session)
        record = await repo.get_recommendation(
            recommendation_id=recommendation_id,
            project_id=project_id,
            owner_id=owner_id,
        )
        if record is None:
            raise NotFound("Recommendation not found")

        assert_recommendation_owned(record.owner_id, owner_id)

        current_status = RecommendationStatus(record.status)
        if not is_valid_status_transition(current_status, new_status):
            raise ValidationError(
                f"Invalid status transition from {current_status.value} to {new_status.value}"
            )

        updated = await repo.update_recommendation_status(record, new_status=new_status.value)

        # Audit feedback action
        await repo.save_feedback(
            feedback_id=uuid7(),
            recommendation_id=recommendation_id,
            project_id=project_id,
            owner_id=owner_id,
            action=new_status.value.lower(),
            feedback_text=feedback_text,
        )

        return _rec_to_dto(updated)
