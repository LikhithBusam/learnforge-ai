"""Materials repository — database access for Material entity (Phase 3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.materials.models import Material
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


class MaterialRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        *,
        material_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        title: str,
        size_bytes: int,
        storage_key: str,
        checksum_sha256: str,
        mime_type: str = "application/pdf",
        status: str = "upload_pending",
    ) -> Material:
        material = Material(
            id=material_id,
            project_id=project_id,
            owner_id=owner_id,
            title=title,
            mime_type=mime_type,
            size_bytes=size_bytes,
            storage_key=storage_key,
            checksum_sha256=checksum_sha256,
            status=status,
        )
        self._session.add(material)
        await self._session.flush()
        return material

    async def get_by_id(self, material_id: uuid.UUID) -> Material | None:
        result = await self._session.execute(select(Material).where(Material.id == material_id))
        return result.scalar_one_or_none()

    async def get_by_id_and_project(
        self, material_id: uuid.UUID, project_id: uuid.UUID
    ) -> Material | None:
        result = await self._session.execute(
            select(Material).where(
                Material.id == material_id,
                Material.project_id == project_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_by_checksum(
        self, project_id: uuid.UUID, checksum_sha256: str
    ) -> Material | None:
        result = await self._session.execute(
            select(Material).where(
                Material.project_id == project_id,
                Material.checksum_sha256 == checksum_sha256,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: uuid.UUID) -> list[Material]:
        result = await self._session.execute(
            select(Material)
            .where(Material.project_id == project_id)
            .order_by(Material.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        material_id: uuid.UUID,
        *,
        status: str,
        failure_reason: str | None = None,
        page_count: int | None = None,
        processing_started: bool = False,
        processed: bool = False,
    ) -> Material | None:
        material = await self.get_by_id(material_id)
        if material is None:
            return None
        material.status = status
        now = datetime.now(timezone.utc)
        material.updated_at = now
        if failure_reason is not None:
            material.failure_reason = failure_reason
        if page_count is not None:
            material.page_count = page_count
        if processing_started:
            material.processing_started_at = now
        if processed:
            material.processed_at = now
        await self._session.flush()
        return material

    async def delete(self, material_id: uuid.UUID) -> bool:
        result = await self._session.execute(delete(Material).where(Material.id == material_id))
        await self._session.flush()
        rowcount = getattr(result, "rowcount", 0)
        return bool(rowcount and rowcount > 0)
