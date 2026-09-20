"""Phase 4 Integration Tests — Hybrid RAG Retrieval (Prompt §4, §13, §15, §45).

Verifies:
1. Retrieval is independently testable without Tutor.
2. Vector similarity search against pgvector HNSW index.
3. PostgreSQL full-text search using tsvector and plainto_tsquery.
4. Reciprocal Rank Fusion combining candidates.
5. AI Gateway reranking elevating relevant evidence.
6. Evidence sufficiency evaluation marked supported.
"""

import io

import fitz
import pytest
from app.knowledge import service as knowledge_service
from app.knowledge.schemas import QueryInput
from app.materials import service as materials_service
from app.platform.storage import get_storage, init_storage


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
async def test_hybrid_retrieval_and_reranking(cloud_settings, engines, seed_user, seed_project):
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p4-retrieval")
    space, project = await seed_project(user.id, "Computer Networks")

    # Ingest Material A: TCP Congestion Control
    pdf_a = make_pdf(
        [
            "TCP congestion control uses the Additive Increase Multiplicative Decrease (AIMD) algorithm.",
            "The congestion window grows linearly during congestion avoidance until packet loss occurs.",
            "Fast retransmit and fast recovery allow TCP to recover from isolated packet drops quickly.",
        ]
    )
    intent_a = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="TCP Congestion Control Notes",
        filename="tcp.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf_a),
    )
    storage.upload_bytes(intent_a.storage_key, pdf_a, content_type="application/pdf")
    await knowledge_service.ingest_document(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent_a.material_id,
        pdf_bytes=pdf_a,
    )
    await materials_service.mark_completed(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent_a.material_id,
        page_count=3,
    )

    # Ingest Material B: Routing Protocols (Distractor)
    pdf_b = make_pdf(
        [
            "BGP is the exterior gateway protocol used for inter-domain routing across autonomous systems.",
            "OSPF uses Dijkstra algorithm to compute shortest path tree based on link-state advertisements.",
        ]
    )
    intent_b = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="Routing Notes",
        filename="routing.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf_b),
    )
    storage.upload_bytes(intent_b.storage_key, pdf_b, content_type="application/pdf")
    await knowledge_service.ingest_document(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent_b.material_id,
        pdf_bytes=pdf_b,
    )
    await materials_service.mark_completed(
        owner_id=user.id,
        project_id=project.id,
        material_id=intent_b.material_id,
        page_count=2,
    )

    # Execute Independent Retrieval Query
    query = "How does AIMD adjust the window in congestion control?"
    evidence_set = await knowledge_service.retrieve_evidence(
        project_id=project.id,
        owner_id=user.id,
        query_input=QueryInput(raw_query=query),
    )

    # 1. Verification of candidate generation and fusion
    assert evidence_set.project_id == project.id
    assert len(evidence_set.hits) > 0
    assert evidence_set.retrieval_meta.vector_candidates_count > 0
    assert evidence_set.retrieval_meta.lexical_candidates_count > 0
    assert evidence_set.retrieval_meta.fusion_candidates_count > 0
    assert evidence_set.retrieval_meta.reranked is True

    # 2. Top hit must be the AIMD chunk from Material A
    top_hit = evidence_set.hits[0]
    assert "AIMD" in top_hit.chunk_ref.text or "congestion" in top_hit.chunk_ref.text.lower()
    assert top_hit.chunk_ref.material_id == intent_a.material_id
    assert top_hit.score > 0.50

    # 3. Evidence sufficiency decision must be supported
    assert evidence_set.sufficiency.sufficient is True
    assert evidence_set.sufficiency.reason_code == "supported"
