"""Materials HTTP Router — /api/v1/projects/{project_id}/materials (Phase 3).

Endpoints:
- POST /: initiate PDF upload intent and receive presigned URL.
- POST /{material_id}/complete: confirm upload, verify PDF, enqueue background ingestion.
- GET /: list materials in project.
- GET /{material_id}: retrieve material details.
- DELETE /{material_id}: delete material.
"""

from __future__ import annotations

import uuid

from app.identity.dependencies import CurrentPrincipal
from app.materials import service
from app.materials.schemas import (
    CompleteUploadRequest,
    CreateMaterialRequest,
    MaterialResponse,
    UploadIntentResponse,
)
from fastapi import APIRouter, Response, status

router = APIRouter(prefix="/api/v1/projects/{project_id}/materials", tags=["materials"])


def _dto_to_response(dto: service.MaterialDto) -> MaterialResponse:
    return MaterialResponse(
        id=str(dto.id),
        project_id=str(dto.project_id),
        title=dto.title,
        mime_type=dto.mime_type,
        size_bytes=dto.size_bytes,
        page_count=dto.page_count,
        status=dto.status,
        failure_reason=dto.failure_reason,
        created_at=dto.created_at.isoformat(),
        updated_at=dto.updated_at.isoformat(),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_upload_intent(
    project_id: uuid.UUID,
    payload: CreateMaterialRequest,
    principal: CurrentPrincipal,
) -> UploadIntentResponse:
    user_id = uuid.UUID(principal.user_id)
    intent = await service.create_upload_intent(
        owner_id=user_id,
        project_id=project_id,
        title=payload.title,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        checksum_sha256=payload.checksum_sha256,
    )
    return UploadIntentResponse(
        material_id=str(intent.material_id),
        project_id=str(intent.project_id),
        title=intent.title,
        storage_key=intent.storage_key,
        upload_url=intent.upload_url,
        expires_in=intent.expires_in,
    )


@router.post("/{material_id}/complete", status_code=status.HTTP_200_OK)
async def complete_upload(
    project_id: uuid.UUID,
    material_id: uuid.UUID,
    payload: CompleteUploadRequest,
    principal: CurrentPrincipal,
) -> MaterialResponse:
    user_id = uuid.UUID(principal.user_id)
    material = await service.complete_upload(
        owner_id=user_id,
        project_id=project_id,
        material_id=material_id,
        checksum_sha256=payload.checksum_sha256,
    )
    return _dto_to_response(material)


@router.get("", status_code=status.HTTP_200_OK)
async def list_materials(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> list[MaterialResponse]:
    user_id = uuid.UUID(principal.user_id)
    materials = await service.list_materials(
        owner_id=user_id,
        project_id=project_id,
    )
    return [_dto_to_response(m) for m in materials]


@router.get("/{material_id}", status_code=status.HTTP_200_OK)
async def get_material(
    project_id: uuid.UUID,
    material_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> MaterialResponse:
    user_id = uuid.UUID(principal.user_id)
    material = await service.get_material(
        owner_id=user_id,
        project_id=project_id,
        material_id=material_id,
    )
    return _dto_to_response(material)


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    project_id: uuid.UUID,
    material_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> Response:
    user_id = uuid.UUID(principal.user_id)
    await service.delete_material(
        owner_id=user_id,
        project_id=project_id,
        material_id=material_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
