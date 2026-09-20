"""Tutor HTTP Router — /api/v1/projects/{project_id}/tutor (Phase 4).

Endpoints:
- POST /conversations: create conversation session
- GET /conversations: list project conversations
- GET /conversations/{conversation_id}: retrieve conversation
- GET /conversations/{conversation_id}/messages: retrieve conversation history
- POST /conversations/{conversation_id}/messages: send message (supports text/event-stream or JSON)
"""

from __future__ import annotations

import uuid

from app.identity.dependencies import CurrentPrincipal
from app.tutor import service
from app.tutor.schemas import (
    ConversationDto,
    CreateConversationInput,
    MessageDto,
    SendMessageInput,
)
from fastapi import APIRouter, Header, Response, status
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/v1/projects/{project_id}/tutor", tags=["tutor"])


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    project_id: uuid.UUID,
    payload: CreateConversationInput,
    principal: CurrentPrincipal,
) -> ConversationDto:
    user_id = uuid.UUID(principal.user_id)
    return await service.create_conversation(
        owner_id=user_id,
        project_id=project_id,
        title=payload.title,
    )


@router.get("/conversations")
async def list_conversations(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> list[ConversationDto]:
    user_id = uuid.UUID(principal.user_id)
    return await service.list_conversations(
        owner_id=user_id,
        project_id=project_id,
    )


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> ConversationDto:
    user_id = uuid.UUID(principal.user_id)
    return await service.get_conversation(
        owner_id=user_id,
        project_id=project_id,
        conversation_id=conversation_id,
    )


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    principal: CurrentPrincipal,
) -> list[MessageDto]:
    user_id = uuid.UUID(principal.user_id)
    return await service.get_messages(
        owner_id=user_id,
        project_id=project_id,
        conversation_id=conversation_id,
    )


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: SendMessageInput,
    principal: CurrentPrincipal,
    accept: str | None = Header(default=None),
) -> Response:
    user_id = uuid.UUID(principal.user_id)
    msg_dto, events = await service.send_message(
        owner_id=user_id,
        project_id=project_id,
        conversation_id=conversation_id,
        input_data=payload,
    )

    if accept and "text/event-stream" in accept:
        return StreamingResponse(
            service.stream_sse_events(events),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Standard JSON response
    return Response(
        content=msg_dto.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
    )
