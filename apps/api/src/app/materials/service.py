"""Materials service — public facade for the materials domain (module-contracts §M.3).

Authorization layer & transaction boundary:
- Project ownership verified via Workspace service before any upload intent.
- Presigned upload URLs generated through Platform StorageProvider (private bucket).
- Upload completion verifies object presence, size limits, and %PDF- magic bytes.
- Ingestion dispatch triggers background worker without blocking HTTP requests.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.jobs import service as jobs_service
from app.materials.models import Material
from app.materials.repository import MaterialRepository
from app.platform import db as database
from app.platform.config import get_settings
from app.platform.errors import ConflictError, NotFound, ValidationError
from app.platform.ids import uuid7
from app.platform.logging import get_logger
from app.platform.storage import get_storage
from app.workspace import service as workspace_service

logger = get_logger(__name__)


@dataclass(frozen=True)
class MaterialDto:
    id: uuid.UUID
    project_id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    mime_type: str
    size_bytes: int
    storage_key: str
    checksum_sha256: str
    page_count: int | None
    status: str
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class UploadIntentDto:
    material_id: uuid.UUID
    project_id: uuid.UUID
    title: str
    storage_key: str
    upload_url: str
    expires_in: int


def _to_dto(m: Material) -> MaterialDto:
    return MaterialDto(
        id=m.id,
        project_id=m.project_id,
        owner_id=m.owner_id,
        title=m.title,
        mime_type=m.mime_type,
        size_bytes=m.size_bytes,
        storage_key=m.storage_key,
        checksum_sha256=m.checksum_sha256,
        page_count=m.page_count,
        status=m.status,
        failure_reason=m.failure_reason,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


async def create_upload_intent(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    title: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    checksum_sha256: str | None = None,
) -> UploadIntentDto:
    """Create a new material record and issue a presigned upload URL."""
    settings = get_settings()

    # 1. Validate upload constraints first (fail fast)
    title = title.strip()
    if not title:
        raise ValidationError("Material title is required")

    normalized_type = content_type.strip().lower()
    if normalized_type not in ("application/pdf", "application/x-pdf"):
        raise ValidationError(f"Unsupported content-type '{content_type}'; only PDF is permitted")

    if size_bytes <= 0:
        raise ValidationError("File size must be greater than zero")
    if size_bytes > settings.MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"File size exceeds maximum permitted limit ({size_bytes} > {settings.MAX_UPLOAD_BYTES})"
        )

    clean_filename = filename.strip().lower()
    if not clean_filename.endswith(".pdf"):
        raise ValidationError("Filename must end with .pdf")

    # 2. Authorize project access via Workspace facade
    ctx = await workspace_service.get_project_in_scope(
        principal_user_id=owner_id, project_id=project_id
    )

    material_id = uuid7()
    # Server-controlled storage path: {space_id}/{project_id}/{material_id}/document.pdf
    storage_key = f"{ctx.space.id}/{project_id}/{material_id}/document.pdf"

    initial_checksum = (
        checksum_sha256.strip().lower() if checksum_sha256 else f"pending_{material_id}"
    )

    # 3. Check for duplicate checksum in project if provided
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MaterialRepository(session)
        if checksum_sha256:
            existing = await repo.find_by_checksum(project_id, initial_checksum)
            if existing:
                raise ConflictError("A material with this checksum already exists in this project")

        await repo.create(
            material_id=material_id,
            project_id=project_id,
            owner_id=owner_id,
            title=title,
            size_bytes=size_bytes,
            storage_key=storage_key,
            checksum_sha256=initial_checksum,
            mime_type="application/pdf",
            status="upload_pending",
        )

    # 4. Generate presigned upload URL via StorageProvider
    storage = get_storage()
    upload_url = storage.create_upload_url(storage_key, content_type="application/pdf")

    logger.info(
        "material_upload_intent_created",
        extra={
            "details": {
                "material_id": str(material_id),
                "project_id": str(project_id),
                "storage_key": storage_key,
            }
        },
    )

    return UploadIntentDto(
        material_id=material_id,
        project_id=project_id,
        title=title,
        storage_key=storage_key,
        upload_url=upload_url,
        expires_in=settings.STORAGE_PRESIGN_TTL_SECONDS,
    )


async def complete_upload(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    material_id: uuid.UUID,
    checksum_sha256: str | None = None,
) -> MaterialDto:
    """Verify uploaded object in storage, compute checksum, and enqueue ingestion."""
    settings = get_settings()

    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MaterialRepository(session)
        material = await repo.get_by_id_and_project(material_id, project_id)
        if material is None or material.owner_id != owner_id:
            raise NotFound("Material not found")

        if material.status not in ("upload_pending", "uploaded", "failed"):
            raise ValidationError(
                f"Cannot complete upload for material in status '{material.status}'"
            )

        # Verify object in storage
        storage = get_storage()
        meta = storage.head_object(material.storage_key)
        if meta is None:
            raise ValidationError("Uploaded file not found in storage")

        if meta.size_bytes is None or meta.size_bytes <= 0:
            raise ValidationError("Uploaded file is empty")
        if meta.size_bytes > settings.MAX_UPLOAD_BYTES:
            raise ValidationError(
                f"Uploaded file exceeds size limit ({meta.size_bytes} > {settings.MAX_UPLOAD_BYTES})"
            )

        # Verify PDF magic bytes
        data = storage.get_bytes(material.storage_key)
        if not data or len(data) < 5 or not data.startswith(b"%PDF-"):
            raise ValidationError("File content is not a valid PDF (invalid magic bytes)")

        # Compute SHA-256
        computed_checksum = hashlib.sha256(data).hexdigest()
        if checksum_sha256:
            if checksum_sha256.strip().lower() != computed_checksum:
                raise ValidationError(
                    "Checksum mismatch: file content does not match expected hash"
                )

        # Update material record
        material.size_bytes = len(data)
        material.checksum_sha256 = computed_checksum
        material.status = "uploaded"
        material.failure_reason = None
        await session.flush()
        result_dto = _to_dto(material)

    # Dispatch background document ingestion
    jobs_service.dispatch_document_processing(
        user_id=owner_id, project_id=project_id, material_id=material_id
    )

    logger.info(
        "material_upload_completed",
        extra={
            "details": {
                "material_id": str(material_id),
                "project_id": str(project_id),
                "size_bytes": result_dto.size_bytes,
                "checksum": computed_checksum,
            }
        },
    )

    return result_dto


async def get_material(
    *, owner_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID
) -> MaterialDto:
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MaterialRepository(session)
        material = await repo.get_by_id_and_project(material_id, project_id)
        if material is None or material.owner_id != owner_id:
            raise NotFound("Material not found")
        return _to_dto(material)


async def list_materials(*, owner_id: uuid.UUID, project_id: uuid.UUID) -> list[MaterialDto]:
    # Ensure project belongs to owner
    await workspace_service.get_project_in_scope(principal_user_id=owner_id, project_id=project_id)

    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MaterialRepository(session)
        items = await repo.list_by_project(project_id)
        return [_to_dto(m) for m in items]


async def delete_material(
    *, owner_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID
) -> None:
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MaterialRepository(session)
        material = await repo.get_by_id_and_project(material_id, project_id)
        if material is None or material.owner_id != owner_id:
            raise NotFound("Material not found")

        storage_key = material.storage_key
        await repo.delete(material_id)

    try:
        get_storage().delete_object(storage_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "storage_delete_failed", extra={"details": {"key": storage_key, "error": str(exc)}}
        )


# --- Worker lifecycle transition helpers ---


async def begin_processing(
    *, owner_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID
) -> MaterialDto:
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MaterialRepository(session)
        material = await repo.update_status(
            material_id,
            status="processing",
            processing_started=True,
            failure_reason=None,
        )
        if material is None:
            raise NotFound("Material not found")
        return _to_dto(material)


async def mark_completed(
    *, owner_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID, page_count: int
) -> MaterialDto:
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MaterialRepository(session)
        material = await repo.update_status(
            material_id,
            status="ready",
            page_count=page_count,
            processed=True,
            failure_reason=None,
        )
        if material is None:
            raise NotFound("Material not found")
        return _to_dto(material)


async def mark_failed(
    *, owner_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID, failure_reason: str
) -> MaterialDto:
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MaterialRepository(session)
        material = await repo.update_status(
            material_id,
            status="failed",
            failure_reason=failure_reason,
            processed=True,
        )
        if material is None:
            raise NotFound("Material not found")
        return _to_dto(material)
