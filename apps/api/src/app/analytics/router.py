"""Analytics & Learner Progress HTTP router (Phase 9).

All routes are project-scoped under /api/v1/projects/{project_id}/analytics.
Authorization: owner-only via RLS (session_scope binds user_id -> policies
enforce user_id = app_user_id()). Non-owned resources -> 404 (ADR-0002).
"""

from __future__ import annotations

import uuid

from app.analytics import service as analytics_service
from app.analytics.schemas import (
    ActivityAnalyticsDto,
    AnalyticsEventDto,
    AnalyticsEventInput,
    AssessmentAnalyticsDto,
    GrowthAnalyticsDto,
    MasteryAnalyticsDto,
    MaterialsAnalyticsDto,
    ProjectAnalyticsOverviewDto,
    RecommendationsAnalyticsDto,
    TutorAnalyticsDto,
)
from app.identity.dependencies import CurrentPrincipal
from fastapi import APIRouter, Query

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/analytics",
    tags=["analytics"],
)


@router.get(
    "/overview",
    response_model=ProjectAnalyticsOverviewDto,
    summary="Get project analytics overview",
    description="Returns comprehensive aggregated metrics across all learning domains for the project.",
)
async def get_project_overview(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    range: str = Query("30d", description="Time window: 7d, 30d, 90d, all"),
) -> ProjectAnalyticsOverviewDto:
    owner_id = uuid.UUID(principal.user_id)
    return await analytics_service.get_project_overview(
        owner_id=owner_id, project_id=project_id, range_str=range
    )


@router.get(
    "/activity",
    response_model=ActivityAnalyticsDto,
    summary="Get learner activity analytics",
    description="Returns study frequency, active calendar days, and total study events.",
)
async def get_activity_analytics(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    range: str = Query("30d", description="Time window: 7d, 30d, 90d, all"),
) -> ActivityAnalyticsDto:
    owner_id = uuid.UUID(principal.user_id)
    return await analytics_service.get_activity_analytics(
        owner_id=owner_id, project_id=project_id, range_str=range
    )


@router.get(
    "/tutor",
    response_model=TutorAnalyticsDto,
    summary="Get tutor usage analytics",
    description="Returns conversation counts, message volume, grounded response rate, and citation usage.",
)
async def get_tutor_analytics(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    range: str = Query("30d", description="Time window: 7d, 30d, 90d, all"),
) -> TutorAnalyticsDto:
    owner_id = uuid.UUID(principal.user_id)
    return await analytics_service.get_tutor_analytics(
        owner_id=owner_id, project_id=project_id, range_str=range
    )


@router.get(
    "/assessment",
    response_model=AssessmentAnalyticsDto,
    summary="Get assessment analytics",
    description="Returns quiz completion rates, question attempts, and overall accuracy.",
)
async def get_assessment_analytics(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    range: str = Query("30d", description="Time window: 7d, 30d, 90d, all"),
) -> AssessmentAnalyticsDto:
    owner_id = uuid.UUID(principal.user_id)
    return await analytics_service.get_assessment_analytics(
        owner_id=owner_id, project_id=project_id, range_str=range
    )


@router.get(
    "/mastery",
    response_model=MasteryAnalyticsDto,
    summary="Get mastery analytics",
    description="Returns distribution of concepts across cognitive tiers (developing, progressing, mastered).",
)
async def get_mastery_analytics(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    range: str = Query("30d", description="Time window: 7d, 30d, 90d, all"),
) -> MasteryAnalyticsDto:
    owner_id = uuid.UUID(principal.user_id)
    return await analytics_service.get_mastery_analytics(
        owner_id=owner_id, project_id=project_id, range_str=range
    )


@router.get(
    "/growth",
    response_model=GrowthAnalyticsDto,
    summary="Get growth analytics",
    description="Returns concept trajectory breakdown (improving, stable, declining) and attention requirements.",
)
async def get_growth_analytics(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    range: str = Query("30d", description="Time window: 7d, 30d, 90d, all"),
) -> GrowthAnalyticsDto:
    owner_id = uuid.UUID(principal.user_id)
    return await analytics_service.get_growth_analytics(
        owner_id=owner_id, project_id=project_id, range_str=range
    )


@router.get(
    "/recommendations",
    response_model=RecommendationsAnalyticsDto,
    summary="Get recommendations analytics",
    description="Returns recommendation lifecycle funnel and completion rate.",
)
async def get_recommendations_analytics(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    range: str = Query("30d", description="Time window: 7d, 30d, 90d, all"),
) -> RecommendationsAnalyticsDto:
    owner_id = uuid.UUID(principal.user_id)
    return await analytics_service.get_recommendations_analytics(
        owner_id=owner_id, project_id=project_id, range_str=range
    )


@router.get(
    "/materials",
    response_model=MaterialsAnalyticsDto,
    summary="Get materials analytics",
    description="Returns material uploads, processing completion counts, and page volumes.",
)
async def get_materials_analytics(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    range: str = Query("30d", description="Time window: 7d, 30d, 90d, all"),
) -> MaterialsAnalyticsDto:
    owner_id = uuid.UUID(principal.user_id)
    return await analytics_service.get_materials_analytics(
        owner_id=owner_id, project_id=project_id, range_str=range
    )


@router.post(
    "/events",
    response_model=AnalyticsEventDto,
    summary="Ingest analytics event",
    description="Records an immutable analytics event into the project event stream.",
)
async def ingest_event(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    input_data: AnalyticsEventInput,
) -> AnalyticsEventDto:
    owner_id = uuid.UUID(principal.user_id)
    return await analytics_service.record_event(
        owner_id=owner_id,
        project_id=project_id,
        input_data=input_data,
    )
