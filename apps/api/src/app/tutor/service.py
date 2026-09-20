"""Tutor service — the public facade of the tutor domain (module-contracts §M.5).

Phase 4 implements:
- Conversation lifecycle management (scoped by Project & Owner)
- Evidence-grounded answer generation with strict prompt injection defense
- Deterministic citation validation against retrieved evidence bounds
- Honest refusal path when evidence sufficiency is below threshold
- SSE event streaming & persistent interaction recording
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

from app.ai.gateway import get_gateway
from app.ai.schemas import StructuredRequest
from app.knowledge import service as knowledge_service
from app.knowledge.schemas import QueryInput
from app.platform import db as database
from app.platform.errors import NotFound
from app.platform.ids import uuid7
from app.platform.logging import get_logger
from app.tutor import citations as cit_validator
from app.tutor import context as context_composer
from app.tutor.models import MessageCitation
from app.tutor.repository import TutorRepository
from app.tutor.schemas import (
    CitationDto,
    ConversationDto,
    MessageDto,
    SendMessageInput,
    TutorGenerationPayload,
)

logger = get_logger(__name__)


async def create_conversation(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    title: str | None = None,
) -> ConversationDto:
    """Create a new project-scoped conversation session."""
    conv_id = uuid7()
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = TutorRepository(session)
        conv = await repo.create_conversation(
            conversation_id=conv_id,
            project_id=project_id,
            owner_id=owner_id,
            title=title or "Study Session",
        )
        return ConversationDto(
            id=conv.id,
            project_id=conv.project_id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )


async def get_conversation(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> ConversationDto:
    """Fetch conversation metadata."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = TutorRepository(session)
        conv = await repo.get_conversation(
            conversation_id=conversation_id,
            project_id=project_id,
            owner_id=owner_id,
        )
        if conv is None:
            raise NotFound("Conversation not found")
        return ConversationDto(
            id=conv.id,
            project_id=conv.project_id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )


async def list_conversations(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
) -> list[ConversationDto]:
    """List conversations for the current project."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = TutorRepository(session)
        convs = await repo.list_conversations(project_id=project_id, owner_id=owner_id)
        return [
            ConversationDto(
                id=c.id,
                project_id=c.project_id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in convs
        ]


async def get_messages(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    limit: int = 50,
) -> list[MessageDto]:
    """Retrieve message history for a conversation."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = TutorRepository(session)
        # Ensure conversation exists and belongs to owner
        conv = await repo.get_conversation(
            conversation_id=conversation_id,
            project_id=project_id,
            owner_id=owner_id,
        )
        if conv is None:
            raise NotFound("Conversation not found")

        messages = await repo.get_messages(
            conversation_id=conversation_id,
            project_id=project_id,
            owner_id=owner_id,
            limit=limit,
        )
        return [
            MessageDto(
                id=m.id,
                conversation_id=m.conversation_id,
                project_id=m.project_id,
                role=m.role,
                content=m.content,
                answer_status=m.answer_status,
                citations=[
                    CitationDto(
                        chunk_id=c.chunk_id,
                        document_id=c.document_id,
                        material_id=c.material_id,
                        page_number=c.page_number,
                        quote=c.quote,
                    )
                    for c in m.citations
                ],
                ai_request_id=m.ai_request_id,
                created_at=m.created_at,
            )
            for m in messages
        ]


async def send_message(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    input_data: SendMessageInput,
) -> tuple[MessageDto, list[dict]]:
    """Execute a complete grounded turn.

    Returns:
        (persisted_message_dto, stream_events)
    """
    events: list[dict] = []

    # 1. Check idempotency key if provided
    if input_data.idempotency_key:
        async with database.session_scope(
            user_id=str(owner_id), project_id=str(project_id)
        ) as session:
            repo = TutorRepository(session)
            existing = await repo.get_message_by_idempotency_key(
                conversation_id=conversation_id,
                idempotency_key=input_data.idempotency_key,
            )
            if existing is not None:
                logger.info(
                    "tutor_idempotent_replay",
                    extra={
                        "conversation_id": str(conversation_id),
                        "key": input_data.idempotency_key,
                    },
                )
                dto = MessageDto(
                    id=existing.id,
                    conversation_id=existing.conversation_id,
                    project_id=existing.project_id,
                    role=existing.role,
                    content=existing.content,
                    answer_status=existing.answer_status,
                    citations=[
                        CitationDto(
                            chunk_id=c.chunk_id,
                            document_id=c.document_id,
                            material_id=c.material_id,
                            page_number=c.page_number,
                            quote=c.quote,
                        )
                        for c in existing.citations
                    ],
                    ai_request_id=existing.ai_request_id,
                    created_at=existing.created_at,
                )
                events.append({"event": "message_start", "data": {"message_id": str(dto.id)}})
                events.append({"event": "token", "data": {"delta": dto.content}})
                events.append(
                    {
                        "event": "message_end",
                        "data": {
                            "message_id": str(dto.id),
                            "answer_status": dto.answer_status,
                            "citations_count": len(dto.citations),
                        },
                    }
                )
                return dto, events

    # 2. Verify conversation ownership & save user message
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = TutorRepository(session)
        conv = await repo.get_conversation(
            conversation_id=conversation_id,
            project_id=project_id,
            owner_id=owner_id,
        )
        if conv is None:
            raise NotFound("Conversation not found")

        # Save user message
        user_msg_id = uuid7()
        await repo.save_message(
            message_id=user_msg_id,
            conversation_id=conversation_id,
            project_id=project_id,
            owner_id=owner_id,
            role="user",
            content=input_data.content,
        )
        prior_messages = await repo.get_messages(
            conversation_id=conversation_id,
            project_id=project_id,
            owner_id=owner_id,
            limit=10,
        )

    # 3. Hybrid RAG Retrieval through Knowledge domain
    evidence_set = await knowledge_service.retrieve_evidence(
        project_id=project_id,
        owner_id=owner_id,
        query_input=QueryInput(raw_query=input_data.content),
    )

    events.append(
        {
            "event": "retrieval_complete",
            "data": {
                "hits_count": len(evidence_set.hits),
                "sufficient": evidence_set.sufficiency.sufficient,
                "top_score": evidence_set.sufficiency.top_score,
            },
        }
    )

    asst_msg_id = uuid7()
    ai_request_id: str | None = None
    valid_citations: list[cit_validator.ValidatedCitation] = []

    # 4. Evidence Sufficiency Decision (Prompt §17 & §18)
    if not evidence_set.sufficiency.sufficient:
        # Honest refusal: refuse explicitly without hallucinating
        final_answer = "I could not find enough supporting information in the project materials to answer that reliably."
        answer_status = "insufficient_evidence"
        events.append(
            {
                "event": "insufficient",
                "data": {
                    "reason_code": evidence_set.sufficiency.reason_code,
                    "message": final_answer,
                },
            }
        )
    else:
        # Evidence is sufficient: compose context and generate grounded answer via AI Gateway
        system_prompt, user_prompt = context_composer.compose_tutor_context(
            question=input_data.content,
            evidence_set=evidence_set,
            history=prior_messages[:-1],  # exclude current question
        )

        gateway = get_gateway()
        gen_req: StructuredRequest[TutorGenerationPayload] = StructuredRequest(
            feature="tutor_answer",
            prompt=f"{system_prompt}\n\n{user_prompt}",
            schema_model=TutorGenerationPayload,
            output_schema_name="tutor_generation",
        )
        ai_res = await gateway.generate_structured(gen_req)
        ai_request_id = ai_res.meta.ai_request_id
        payload = TutorGenerationPayload.model_validate(ai_res.data)

        if payload.refusal or not payload.grounded:
            final_answer = (
                payload.answer
                or "I could not find enough supporting information in the project materials to answer that reliably."
            )
            answer_status = "insufficient_evidence"
            events.append(
                {
                    "event": "insufficient",
                    "data": {
                        "reason_code": payload.refusal_reason or "model_refusal",
                        "message": final_answer,
                    },
                }
            )
        else:
            # Validate citations deterministically against retrieved evidence bounds
            valid_citations, warnings = cit_validator.validate_citations(
                claimed_citations=payload.citations,
                evidence_set=evidence_set,
                project_id=project_id,
            )

            if not valid_citations:
                # Model claimed groundedness but produced zero valid citations -> downgrade to refusal
                final_answer = "I could not find enough verified supporting information in the project materials to answer that reliably."
                answer_status = "insufficient_evidence"
                logger.warning(
                    "tutor_grounded_claim_lacked_valid_citations", extra={"warnings": warnings}
                )
            else:
                final_answer = payload.answer
                answer_status = "grounded"

    # 5. Build stream events for tokens and citations
    events.append(
        {
            "event": "message_start",
            "data": {"message_id": str(asst_msg_id), "ai_request_id": ai_request_id},
        }
    )
    events.append({"event": "token", "data": {"delta": final_answer}})
    for cit in valid_citations:
        events.append(
            {
                "event": "citation",
                "data": {
                    "chunk_id": str(cit.chunk_id),
                    "page": cit.page_number,
                    "quote": cit.quote,
                },
            }
        )
    events.append(
        {
            "event": "message_end",
            "data": {
                "message_id": str(asst_msg_id),
                "answer_status": answer_status,
                "citations_count": len(valid_citations),
            },
        }
    )

    # 6. Atomic DB persistence of assistant message and citations
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = TutorRepository(session)
        asst_msg = await repo.save_message(
            message_id=asst_msg_id,
            conversation_id=conversation_id,
            project_id=project_id,
            owner_id=owner_id,
            role="assistant",
            content=final_answer,
            answer_status=answer_status,
            ai_request_id=ai_request_id,
            idempotency_key=input_data.idempotency_key,
        )

        citation_entities = [
            MessageCitation(
                id=uuid7(),
                message_id=asst_msg_id,
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                material_id=c.material_id,
                project_id=project_id,
                owner_id=owner_id,
                page_number=c.page_number,
                quote=c.quote,
            )
            for c in valid_citations
        ]
        await repo.save_citations(citation_entities)
        await repo.touch_conversation(conversation_id)

    response_dto = MessageDto(
        id=asst_msg.id,
        conversation_id=asst_msg.conversation_id,
        project_id=asst_msg.project_id,
        role=asst_msg.role,
        content=asst_msg.content,
        answer_status=asst_msg.answer_status,
        citations=[
            CitationDto(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                material_id=c.material_id,
                page_number=c.page_number,
                quote=c.quote,
            )
            for c in valid_citations
        ],
        ai_request_id=asst_msg.ai_request_id,
        created_at=asst_msg.created_at,
    )

    return response_dto, events


async def stream_sse_events(events: list[dict]) -> AsyncGenerator[str, None]:
    """Format and stream SSE events."""
    for ev in events:
        event_name = ev.get("event", "message")
        event_data = json.dumps(ev.get("data", {}))
        yield f"event: {event_name}\ndata: {event_data}\n\n"
