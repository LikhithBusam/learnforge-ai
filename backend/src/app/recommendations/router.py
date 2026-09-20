"""Recommendation HTTP router (Phase 8).

All routes are project-scoped under /api/v1/projects/{project_id}/recommendations.

Authorization: owner-only via RLS (session_scope binds user_id → policies
enforce owner_id = app_user_id()). Non-owned resources → 404 (ADR-0002).
"""

from __future__ import annotations

import uuid

from app.identity.dependencies import CurrentPrincipal
from app.platform.errors import NotFound
from app.recommendations import service as recommendation_service
from app.recommendations.calculator import RecommendationStatus
from app.recommendations.schemas import (
    GenerateRecommendationsInput,
    RecommendationDto,
    RecommendationFeedbackInput,
    RecommendationListDto,
)
from fastapi import APIRouter, Query

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/recommendations",
    tags=["recommendations"],
)


@router.get(
    "",
    response_model=RecommendationListDto,
    summary="Get active recommendations",
    description="Returns top-K personalized learning recommendations for the project.",
)
async def list_active_recommendations(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    limit: int = Query(20, ge=1, le=100),
) -> RecommendationListDto:
    owner_id = uuid.UUID(principal.user_id)
    return await recommendation_service.get_active_recommendations(
        owner_id=owner_id,
        project_id=project_id,
        limit=limit,
    )


@router.post(
    "/generate",
    response_model=list[RecommendationDto],
    summary="Generate new recommendations",
    description="Deterministically generates and persists new recommendations based on latest evidence.",
)
async def generate_recommendations(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    input_data: GenerateRecommendationsInput | None = None,
) -> list[RecommendationDto]:
    owner_id = uuid.UUID(principal.user_id)
    source_event_id = input_data.source_growth_event_id if input_data else None
    return await recommendation_service.generate_recommendations(
        owner_id=owner_id,
        project_id=project_id,
        source_growth_event_id=source_event_id,
    )


@router.get(
    "/{recommendation_id}",
    response_model=RecommendationDto,
    summary="Get recommendation details",
    description="Returns a specific recommendation by ID.",
)
async def get_recommendation(
    project_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> RecommendationDto:
    owner_id = uuid.UUID(principal.user_id)
    dto = await recommendation_service.get_recommendation(
        owner_id=owner_id,
        project_id=project_id,
        recommendation_id=recommendation_id,
    )
    if dto is None:
        raise NotFound("Recommendation not found")
    return dto


@router.post(
    "/{recommendation_id}/view",
    response_model=RecommendationDto,
    summary="Mark recommendation as viewed",
)
async def mark_viewed(
    project_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> RecommendationDto:
    owner_id = uuid.UUID(principal.user_id)
    return await recommendation_service.update_recommendation_status(
        owner_id=owner_id,
        project_id=project_id,
        recommendation_id=recommendation_id,
        new_status=RecommendationStatus.VIEWED,
    )


@router.post(
    "/{recommendation_id}/start",
    response_model=RecommendationDto,
    summary="Mark recommendation as started",
)
async def mark_started(
    project_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> RecommendationDto:
    owner_id = uuid.UUID(principal.user_id)
    return await recommendation_service.update_recommendation_status(
        owner_id=owner_id,
        project_id=project_id,
        recommendation_id=recommendation_id,
        new_status=RecommendationStatus.STARTED,
    )


@router.post(
    "/{recommendation_id}/complete",
    response_model=RecommendationDto,
    summary="Mark recommendation as completed",
)
async def mark_completed(
    project_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> RecommendationDto:
    owner_id = uuid.UUID(principal.user_id)
    return await recommendation_service.update_recommendation_status(
        owner_id=owner_id,
        project_id=project_id,
        recommendation_id=recommendation_id,
        new_status=RecommendationStatus.COMPLETED,
    )


@router.post(
    "/{recommendation_id}/dismiss",
    response_model=RecommendationDto,
    summary="Dismiss recommendation",
)
async def mark_dismissed(
    project_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> RecommendationDto:
    owner_id = uuid.UUID(principal.user_id)
    return await recommendation_service.update_recommendation_status(
        owner_id=owner_id,
        project_id=project_id,
        recommendation_id=recommendation_id,
        new_status=RecommendationStatus.DISMISSED,
    )


@router.post(
    "/{recommendation_id}/feedback",
    response_model=RecommendationDto,
    summary="Submit feedback on recommendation",
)
async def submit_feedback(
    project_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    principal: CurrentPrincipal,
    input_data: RecommendationFeedbackInput,
) -> RecommendationDto:
    owner_id = uuid.UUID(principal.user_id)
    target_status = RecommendationStatus(input_data.action.upper())
    return await recommendation_service.update_recommendation_status(
        owner_id=owner_id,
        project_id=project_id,
        recommendation_id=recommendation_id,
        new_status=target_status,
        feedback_text=input_data.feedback_text,
    )
