"""Mastery HTTP router (Phase 6).

All routes are project-scoped under /api/v1/projects/{project_id}/mastery.

Authorization: owner-only via RLS (session_scope binds user_id → policies
enforce owner_id = app_user_id()). Non-owned resources → 404 (ADR-0002).
"""

from __future__ import annotations

import uuid

from app.identity.dependencies import CurrentPrincipal
from app.mastery import service as mastery_service
from app.mastery.schemas import (
    MasteryEventDto,
    MasteryStateDto,
    MasterySummaryDto,
    RecordEvidenceInput,
)
from app.platform.errors import NotFound
from fastapi import APIRouter, Query, status

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/mastery",
    tags=["mastery"],
)


@router.get(
    "",
    response_model=list[MasteryStateDto],
    summary="Get all concept mastery states for a project",
    description="Returns the current mastery probability, confidence, and metrics for all concepts in the project.",
)
async def get_project_mastery(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> list[MasteryStateDto]:
    owner_id = uuid.UUID(principal.user_id)
    return await mastery_service.get_project_mastery(
        owner_id=owner_id,
        project_id=project_id,
    )


@router.get(
    "/summary",
    response_model=MasterySummaryDto,
    summary="Get mastery summary for a project",
    description="Returns aggregate mastery metrics and attention concepts for dashboards and recommendation planning.",
)
async def get_mastery_summary(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    concept_ids: list[uuid.UUID] | None = Query(default=None),
) -> MasterySummaryDto:
    owner_id = uuid.UUID(principal.user_id)
    return await mastery_service.get_mastery_summary(
        owner_id=owner_id,
        project_id=project_id,
        concept_ids=concept_ids,
    )


@router.get(
    "/{concept_id}",
    response_model=MasteryStateDto,
    summary="Get mastery state for a specific concept",
    description="Returns the current Bayesian Knowledge Tracing state for the concept within the project.",
)
async def get_concept_mastery(
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> MasteryStateDto:
    owner_id = uuid.UUID(principal.user_id)
    dto = await mastery_service.get_concept_mastery(
        owner_id=owner_id,
        project_id=project_id,
        concept_id=concept_id,
    )
    if dto is None:
        raise NotFound("Mastery record not found for this concept")
    return dto


@router.get(
    "/{concept_id}/history",
    response_model=list[MasteryEventDto],
    summary="Get mastery audit trail for a concept",
    description="Returns the immutable sequence of evidence events that produced the current mastery score.",
)
async def get_evidence_trail(
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
    principal: CurrentPrincipal,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[MasteryEventDto]:
    owner_id = uuid.UUID(principal.user_id)
    return await mastery_service.get_evidence_trail(
        owner_id=owner_id,
        project_id=project_id,
        concept_id=concept_id,
        limit=limit,
    )


@router.post(
    "/{concept_id}/recompute",
    response_model=MasteryStateDto,
    summary="Deterministically recompute mastery from evidence",
    description="Replays all valid assessment evidence for this concept from P_INIT.",
)
async def recompute_mastery(
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> MasteryStateDto:
    owner_id = uuid.UUID(principal.user_id)
    return await mastery_service.recompute_mastery(
        owner_id=owner_id,
        project_id=project_id,
        concept_id=concept_id,
    )


@router.post(
    "/events",
    response_model=MasteryStateDto,
    status_code=status.HTTP_201_CREATED,
    summary="Record learning evidence event",
    description="Directly records a learning event and updates the concept mastery score atomically.",
)
async def record_learning_event(
    project_id: uuid.UUID,
    body: RecordEvidenceInput,
    principal: CurrentPrincipal,
) -> MasteryStateDto:
    owner_id = uuid.UUID(principal.user_id)
    return await mastery_service.record_learning_event(
        owner_id=owner_id,
        project_id=project_id,
        input_data=body,
    )
