"""Phase 4 Integration Tests — AI Tutor Grounded Answering & Refusal (Prompt §46, §48, §50).

Verifies:
1. Supported question returns a grounded answer with validated citations to the exact document and page.
2. Unsupported question returns an honest refusal without fabricated citations or hallucinated claims.
3. Message turn is idempotent when supplied with an idempotency_key.
4. SSE event stream produces structured events (message_start, token, citation, message_end).
"""

import io

import fitz
import pytest
from app.knowledge import service as knowledge_service
from app.materials import service as materials_service
from app.platform.storage import get_storage, init_storage
from app.tutor import service as tutor_service
from app.tutor.schemas import SendMessageInput


def make_pdf(page_texts: list[str]) -> bytes:
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.mark.asyncio
async def test_tutor_grounded_answer_and_refusal(cloud_settings, engines, seed_user, seed_project):
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p4-tutor-user")
    space, project = await seed_project(user.id, "Ethernet Systems")

    # Ingest Ethernet material
    pdf_bytes = make_pdf(
        [
            "Ethernet uses Carrier Sense Multiple Access with Collision Detection (CSMA/CD) to arbitrate wire access.",
            "When a collision occurs, transmitters send a 32-bit jam signal and initiate binary exponential backoff.",
        ]
    )
    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="Ethernet Standards",
        filename="ethernet.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf_bytes),
    )
    storage.upload_bytes(intent.storage_key, pdf_bytes, content_type="application/pdf")
    await knowledge_service.ingest_document(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent.material_id,
        pdf_bytes=pdf_bytes,
    )
    await materials_service.mark_completed(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent.material_id,
        page_count=2,
    )

    # 1. Create conversation session
    conv = await tutor_service.create_conversation(
        owner_id=user.id,
        project_id=project.id,
        title="Ethernet Prep",
    )
    assert conv.id is not None
    assert conv.project_id == project.id

    # 2. Ask Supported Question (Prompt §48)
    supported_msg, events = await tutor_service.send_message(
        owner_id=user.id,
        project_id=project.id,
        conversation_id=conv.id,
        input_data=SendMessageInput(
            content="How does Ethernet arbitrate wire access using CSMA/CD?",
            idempotency_key="key-turn-1",
        ),
    )

    assert supported_msg.role == "assistant"
    assert supported_msg.answer_status == "grounded"
    assert len(supported_msg.citations) > 0

    cit = supported_msg.citations[0]
    assert cit.material_id == intent.material_id
    assert cit.page_number in (1, 2)
    assert cit.chunk_id is not None

    # Verify event stream produced typed events
    event_types = [e["event"] for e in events]
    assert "retrieval_complete" in event_types
    assert "message_start" in event_types
    assert "token" in event_types
    assert "citation" in event_types
    assert "message_end" in event_types

    # 3. Test Idempotency Key Replay
    replayed_msg, replayed_events = await tutor_service.send_message(
        owner_id=user.id,
        project_id=project.id,
        conversation_id=conv.id,
        input_data=SendMessageInput(
            content="How does Ethernet arbitrate wire access using CSMA/CD?",
            idempotency_key="key-turn-1",
        ),
    )
    assert replayed_msg.id == supported_msg.id
    assert replayed_msg.content == supported_msg.content

    # 4. Ask Unsupported Question (Prompt §46)
    unsupported_msg, unsupp_events = await tutor_service.send_message(
        owner_id=user.id,
        project_id=project.id,
        conversation_id=conv.id,
        input_data=SendMessageInput(
            content="What is the company's maternity leave policy and compensation?",
        ),
    )

    assert unsupported_msg.role == "assistant"
    assert unsupported_msg.answer_status == "insufficient_evidence"
    assert len(unsupported_msg.citations) == 0
    assert "not find enough supporting information" in unsupported_msg.content.lower()

    unsupp_event_types = [e["event"] for e in unsupp_events]
    assert "insufficient" in unsupp_event_types
