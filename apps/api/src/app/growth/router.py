"""Growth HTTP router (Phase 7).

All routes are project-scoped under /api/v1/projects/{project_id}/growth.

Authorization: owner-only via RLS (session_scope binds user_id → policies
enforce owner_id = app_user_id()). Non-owned resources → 404 (ADR-0002).
"""

from __future__ import annotations

import uuid

from app.growth import service as growth_service
from app.growth.schemas import (
    ConceptGrowthDto,
    EvaluateGrowthInput,
    GrowthEventDto,
    ProjectGrowthSummaryDto,
)
from app.identity.dependencies import CurrentPrincipal
from app.platform.errors import NotFound
from fastapi import APIRouter, Query

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/growth",
    tags=["growth"],
)


@router.get(
    "",
    response_model=ProjectGrowthSummaryDto,
    summary="Get project growth summary",
    description="Returns aggregate growth metrics, trend distributions, and attention concepts for the project.",
)
async def get_project_growth(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> ProjectGrowthSummaryDto:
    owner_id = uuid.UUID(principal.user_id)
    return await growth_service.get_project_growth(
        owner_id=owner_id,
        project_id=project_id,
    )


@router.get(
    "/{concept_id}",
    response_model=ConceptGrowthDto,
    summary="Get concept growth state",
    description="Returns the current progression trend, short/long term deltas, and attention signals for a concept.",
)
async def get_concept_growth(
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> ConceptGrowthDto:
    owner_id = uuid.UUID(principal.user_id)
    dto = await growth_service.get_concept_growth(
        owner_id=owner_id,
        project_id=project_id,
        concept_id=concept_id,
    )
    if dto is None:
        raise NotFound("Growth record not found for this concept")
    return dto


@router.get(
    "/{concept_id}/history",
    response_model=list[GrowthEventDto],
    summary="Get growth history for a concept",
    description="Returns the immutable audit history of growth evaluations for a concept.",
)
async def get_growth_history(
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
    principal: CurrentPrincipal,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[GrowthEventDto]:
    owner_id = uuid.UUID(principal.user_id)
    return await growth_service.get_growth_history(
        owner_id=owner_id,
        project_id=project_id,
        concept_id=concept_id,
        limit=limit,
    )


@router.post(
    "/{concept_id}/evaluate",
    response_model=ConceptGrowthDto,
    summary="Evaluate concept growth",
    description="Triggers a deterministic growth evaluation for a concept from its mastery history.",
)
async def evaluate_concept_growth(
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
    principal: CurrentPrincipal,
    body: EvaluateGrowthInput | None = None,
) -> ConceptGrowthDto:
    owner_id = uuid.UUID(principal.user_id)
    source_mastery_event_id = body.source_mastery_event_id if body else None
    occurred_at = body.occurred_at if body else None
    return await growth_service.evaluate_concept_growth(
        owner_id=owner_id,
        project_id=project_id,
        concept_id=concept_id,
        source_mastery_event_id=source_mastery_event_id,
        occurred_at=occurred_at,
    )
