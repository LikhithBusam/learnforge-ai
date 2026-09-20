"""Tutor schemas & DTOs (module-contracts §M.5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateConversationInput(BaseModel):
    title: str | None = Field(default=None, max_length=256)


class ConversationDto(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class SendMessageInput(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    idempotency_key: str | None = Field(default=None, max_length=128)


class CitationDto(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    material_id: uuid.UUID
    page_number: int
    quote: str | None = None


class MessageDto(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    project_id: uuid.UUID
    role: str
    content: str
    answer_status: str
    citations: list[CitationDto] = Field(default_factory=list)
    ai_request_id: str | None = None
    created_at: datetime


class CitationPayload(BaseModel):
    chunk_id: uuid.UUID
    page: int
    quote: str | None = None


class TutorGenerationPayload(BaseModel):
    answer: str
    citations: list[CitationPayload] = Field(default_factory=list)
    grounded: bool
    refusal: bool = False
    refusal_reason: str | None = None


# Typed events for SSE streaming
class StreamMessageStartEvent(BaseModel):
    event: Literal["message_start"] = "message_start"
    message_id: str
    ai_request_id: str | None = None


class StreamRetrievalCompleteEvent(BaseModel):
    event: Literal["retrieval_complete"] = "retrieval_complete"
    hits_count: int
    sufficient: bool
    top_score: float


class StreamTokenEvent(BaseModel):
    event: Literal["token"] = "token"
    delta: str


class StreamCitationEvent(BaseModel):
    event: Literal["citation"] = "citation"
    chunk_id: str
    page: int
    quote: str | None = None


class StreamInsufficientEvent(BaseModel):
    event: Literal["insufficient"] = "insufficient"
    reason_code: str
    message: str


class StreamMessageEndEvent(BaseModel):
    event: Literal["message_end"] = "message_end"
    message_id: str
    answer_status: str
    citations_count: int
