"""Materials Pydantic schemas — request and response contracts (Phase 3)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CreateMaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/pdf")
    size_bytes: int = Field(gt=0)
    checksum_sha256: str | None = Field(default=None, max_length=64)


class UploadIntentResponse(BaseModel):
    material_id: str
    project_id: str
    title: str
    storage_key: str
    upload_url: str
    expires_in: int


class CompleteUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checksum_sha256: str | None = Field(default=None, max_length=64)


class MaterialResponse(BaseModel):
    id: str
    project_id: str
    title: str
    mime_type: str
    size_bytes: int
    page_count: int | None
    status: str
    failure_reason: str | None
    created_at: str
    updated_at: str
