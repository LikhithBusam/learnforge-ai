"""Workspace Pydantic schemas — request and response contracts (Phase 1 & Phase 13)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CreateSpaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class SpaceResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    description: str | None
    created_at: str | None = None


class SpaceListResponse(BaseModel):
    items: list[SpaceResponse]
    total: int


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    learning_goal: str | None = Field(default=None, max_length=1000)


class ProjectResponse(BaseModel):
    id: str
    space_id: str
    owner_id: str
    name: str
    description: str | None
    learning_goal: str | None
    status: str
    created_at: str | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
