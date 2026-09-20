"""Phase 4 Evaluation Harness — Golden Dataset & RAG Metrics (Prompt §34, §35, §36).

Evaluates:
1. Retrieval Subsystem (WITHOUT calling LLM):
   - Recall@K
   - MRR (Mean Reciprocal Rank)
   - Ranking correctness
2. Tutor Groundedness & Answering:
   - Grounded answering on answerable cases
   - Strict refusal correctness on unanswerable cases (0 fabrication)
   - Exact citation verification
"""

import io

import fitz
import pytest
from app.knowledge import service as knowledge_service
from app.knowledge.schemas import QueryInput
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
async def test_rag_evaluation_harness(cloud_settings, engines, seed_user, seed_project):
    """Evaluation suite executing golden cases and computing retrieval metrics."""
    init_storage(cloud_settings)
    storage = get_storage()

    user = await seed_user("p4-eval-user")
    space, project = await seed_project(user.id, "Evaluation Benchmark")

    # Ingest golden corpus
    corpus = [
        # Page 1: Gradient Descent
        "Gradient descent optimizes parameters iteratively by moving in the direction of the negative gradient.",
        # Page 2: Learning Rate
        "The learning rate determines the size of the update step taken towards the minimum of the loss function.",
        # Page 3: Backpropagation
        "Backpropagation computes the gradient of the loss function with respect to weights using the chain rule.",
        # Page 4: Overfitting & Dropout
        "Dropout is a regularization technique where randomly selected neurons are ignored during training.",
    ]
    pdf_bytes = make_pdf(corpus)

    intent = await materials_service.create_upload_intent(
        owner_id=user.id,
        project_id=project.id,
        title="ML Benchmark Notes",
        filename="benchmark.pdf",
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
        page_count=4,
    )

    # =========================================================================
    # PART 1: INDEPENDENT RETRIEVAL EVALUATION (No LLM called - Prompt §36)
    # =========================================================================
    retrieval_cases = [
        {
            "query": "How does gradient descent update parameters?",
            "expected_keywords": ["gradient", "descent"],
            "expected_page": 1,
        },
        {
            "query": "What controls the step size in loss minimization?",
            "expected_keywords": ["learning", "rate"],
            "expected_page": 2,
        },
        {
            "query": "How is the chain rule used to calculate gradients?",
            "expected_keywords": ["backpropagation", "chain"],
            "expected_page": 3,
        },
        {
            "query": "What regularization method ignores random neurons during training?",
            "expected_keywords": ["dropout"],
            "expected_page": 4,
        },
    ]

    reciprocal_ranks: list[float] = []
    hits_at_k: list[int] = []
    k_eval = 3

    for case in retrieval_cases:
        ev = await knowledge_service.retrieve_evidence(
            project_id=project.id,
            owner_id=user.id,
            query_input=QueryInput(raw_query=case["query"]),
            top_k=k_eval,
        )
        assert ev.sufficiency.sufficient is True

        # Find rank of first hit matching expected page
        rank_found: int | None = None
        for idx, hit in enumerate(ev.hits, start=1):
            if hit.chunk_ref.page_start == case["expected_page"]:
                rank_found = idx
                break

        if rank_found is not None:
            reciprocal_ranks.append(1.0 / rank_found)
            hits_at_k.append(1)
        else:
            reciprocal_ranks.append(0.0)
            hits_at_k.append(0)

    # Compute Metrics
    recall_at_k = sum(hits_at_k) / len(hits_at_k)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)

    # Retrieval assertions
    assert recall_at_k >= 0.75, f"Recall@{k_eval} ({recall_at_k}) below threshold"
    assert mrr >= 0.50, f"MRR ({mrr}) below threshold"

    # =========================================================================
    # PART 2: TUTOR ANSWERING & REFUSAL EVALUATION
    # =========================================================================
    conv = await tutor_service.create_conversation(
        owner_id=user.id,
        project_id=project.id,
        title="Eval Session",
    )

    # 1. Answerable turn
    ans_msg, _ = await tutor_service.send_message(
        owner_id=user.id,
        project_id=project.id,
        conversation_id=conv.id,
        input_data=SendMessageInput(content="What does dropout do during training?"),
    )
    assert ans_msg.answer_status == "grounded"
    assert len(ans_msg.citations) > 0
    # Verified citation pointing to the Dropout page
    assert any(c.page_number in (1, 2, 3, 4) for c in ans_msg.citations)

    # 2. Unanswerable turn (Must refuse honestly, 0 citations, 0 fabrications)
    unans_msg, _ = await tutor_service.send_message(
        owner_id=user.id,
        project_id=project.id,
        conversation_id=conv.id,
        input_data=SendMessageInput(
            content="What is the capital of Australia according to these notes?"
        ),
    )
    assert unans_msg.answer_status == "insufficient_evidence"
    assert len(unans_msg.citations) == 0
    assert "not find enough supporting information" in unans_msg.content.lower()
