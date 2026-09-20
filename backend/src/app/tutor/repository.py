"""Tutor repository — database access for conversations, messages, citations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.tutor.models import Conversation, Message, MessageCitation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class TutorRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_conversation(
        self,
        *,
        conversation_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        title: str | None = None,
    ) -> Conversation:
        conv = Conversation(
            id=conversation_id,
            project_id=project_id,
            owner_id=owner_id,
            title=title,
        )
        self._session.add(conv)
        await self._session.flush()
        return conv

    async def get_conversation(
        self,
        *,
        conversation_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.project_id == project_id,
            Conversation.owner_id == owner_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_conversations(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(
                Conversation.project_id == project_id,
                Conversation.owner_id == owner_id,
            )
            .order_by(Conversation.updated_at.desc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def get_message_by_idempotency_key(
        self,
        *,
        conversation_id: uuid.UUID,
        idempotency_key: str,
    ) -> Message | None:
        stmt = (
            select(Message)
            .options(selectinload(Message.citations))
            .where(
                Message.conversation_id == conversation_id,
                Message.idempotency_key == idempotency_key,
            )
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_messages(
        self,
        *,
        conversation_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        limit: int = 50,
    ) -> list[Message]:
        stmt = (
            select(Message)
            .options(selectinload(Message.citations))
            .where(
                Message.conversation_id == conversation_id,
                Message.project_id == project_id,
                Message.owner_id == owner_id,
            )
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def save_message(
        self,
        *,
        message_id: uuid.UUID,
        conversation_id: uuid.UUID,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        content: str,
        answer_status: str = "grounded",
        ai_request_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> Message:
        msg = Message(
            id=message_id,
            conversation_id=conversation_id,
            project_id=project_id,
            owner_id=owner_id,
            role=role,
            content=content,
            answer_status=answer_status,
            ai_request_id=ai_request_id,
            idempotency_key=idempotency_key,
        )
        self._session.add(msg)
        await self._session.flush()
        return msg

    async def save_citations(self, citations: list[MessageCitation]) -> None:
        for cit in citations:
            self._session.add(cit)
        await self._session.flush()

    async def touch_conversation(self, conversation_id: uuid.UUID) -> None:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        res = await self._session.execute(stmt)
        conv = res.scalar_one_or_none()
        if conv:
            conv.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
