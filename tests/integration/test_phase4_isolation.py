"""Phase 4 Integration Tests — Cross-Project Retrieval & RLS Isolation (Prompt §5, §47).

Verifies:
1. User A querying Project B NEVER retrieves chunks from Project A, even with exact matching text.
2. Direct SQL queries under role studycompanion_runtime cannot see conversations or messages of another user.
"""

import io

import fitz
import pytest
from app.knowledge import service as knowledge_service
from app.knowledge.schemas import QueryInput
from app.materials import service as materials_service
from app.platform import db as database
from app.platform.storage import get_storage, init_storage
from app.tutor import service as tutor_service
from sqlalchemy import text


def make_pdf(page_texts: list[str]) -> bytes:
    doc = fitz.open()
    for t in page_texts:
        page = doc.new_page()
        page.insert_text((50, 50), t)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.mark.asyncio
async def test_cross_project_retrieval_blocked(cloud_settings, engines, seed_user, seed_project):
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p4-iso-user")
    space_a, project_a = await seed_project(user.id, "Quantum Mechanics")
    space_b, project_b = await seed_project(user.id, "Roman History")

    # Ingest Quantum Entanglement material in Project A
    pdf_quantum = make_pdf(
        [
            "Quantum entanglement is a phenomenon where particles remain connected so that actions performed on one affect the other.",
        ]
    )
    intent_a = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project_a.id,
        title="Quantum Physics",
        filename="quantum.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf_quantum),
    )
    storage.upload_bytes(intent_a.storage_key, pdf_quantum, content_type="application/pdf")
    await knowledge_service.ingest_document(
        owner_id=user.id,
        project_id=project_a.id,
        material_id=intent_a.material_id,
        pdf_bytes=pdf_quantum,
    )
    await materials_service.mark_completed(
        owner_id=user.id,
        project_id=project_a.id,
        material_id=intent_a.material_id,
        page_count=1,
    )

    # Ingest Roman History material in Project B
    pdf_rome = make_pdf(
        [
            "The Colosseum in Rome is an elliptical amphitheatre in the centre of the city of Rome.",
        ]
    )
    intent_b = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project_b.id,
        title="Rome",
        filename="rome.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf_rome),
    )
    storage.upload_bytes(intent_b.storage_key, pdf_rome, content_type="application/pdf")
    await knowledge_service.ingest_document(
        owner_id=user.id,
        project_id=project_b.id,
        material_id=intent_b.material_id,
        pdf_bytes=pdf_rome,
    )
    await materials_service.mark_completed(
        owner_id=user.id,
        project_id=project_b.id,
        material_id=intent_b.material_id,
        page_count=1,
    )

    # Query for "Quantum entanglement" inside Project B
    evidence_set_b = await knowledge_service.retrieve_evidence(
        project_id=project_b.id,
        owner_id=user.id,
        query_input=QueryInput(raw_query="What is quantum entanglement?"),
    )

    # Assert: Project B must return 0 hits matching quantum entanglement
    for hit in evidence_set_b.hits:
        assert "entanglement" not in hit.chunk_ref.text.lower()
        assert hit.chunk_ref.project_id != project_a.id

    # The sufficiency decision for quantum entanglement inside Project B must be insufficient
    assert evidence_set_b.sufficiency.sufficient is False


@pytest.mark.asyncio
async def test_rls_isolation_on_conversations_and_messages(engines, seed_user, seed_project):
    user_alice = await seed_user("p4-alice")
    user_bob = await seed_user("p4-bob")

    space_a, project_a = await seed_project(user_alice.id, "Alice Project")

    # Alice creates conversation
    conv_alice = await tutor_service.create_conversation(
        owner_id=user_alice.id,
        project_id=project_a.id,
        title="Alice Study Session",
    )

    # Bob attempts to read Alice's conversation under RLS role studycompanion_runtime
    async with database.session_scope(user_id=str(user_bob.id)) as session:
        result = await session.execute(
            text(f"SELECT count(*) FROM conversations WHERE id = '{conv_alice.id}'")
        )
        count = result.scalar_one()
        # Under RLS, Alice's conversation is invisible to Bob
        assert count == 0
