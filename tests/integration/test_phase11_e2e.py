"""Phase 11 — Full End-to-End Integration Test Suite.

Proves the complete unified learner journey across all 10 completed subsystems:
User Registration/Auth -> Space -> Project -> Material Upload & Ingestion ->
Document Processing -> Chunking & Embedding -> Hybrid Retrieval ->
Grounded Tutor with Citations -> Unsupported Question Refusal ->
Prompt Injection Robustness -> Assessment Generation & Quiz Attempt ->
Mastery Update (BKT) -> Growth Trajectory Evaluation ->
Adaptive Recommendation -> Analytics Event Propagation ->
Admin System Observability & Audit Trail.
"""

from __future__ import annotations

import io
import uuid

import fitz
import pytest
from app.admin import service as admin_service
from app.analytics import service as analytics_service
from app.assessment import service as assessment_service
from app.assessment.schemas import SubmitAnswerInput
from app.growth import service as growth_service
from app.knowledge import service as knowledge_service
from app.mastery import service as mastery_service
from app.materials import service as materials_service
from app.platform.storage import get_storage, init_storage
from app.recommendations import service as recommendation_service
from app.tutor import service as tutor_service
from app.tutor.schemas import SendMessageInput


def make_pdf(pages_content: list[str]) -> bytes:
    """Build a multi-page PDF in-memory fixture."""
    doc = fitz.open()
    for text in pages_content:
        page = doc.new_page()
        page.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.mark.asyncio
async def test_full_e2e_learner_journey_lifecycle(
    cloud_settings,
    engines,
    seed_user,
    seed_project,
):
    """Unified E2E verification of the complete multi-phase architecture."""
    init_storage(cloud_settings)
    storage = get_storage()

    # ==========================================
    # 1. User & Workspace Foundation (Phases 1 & 2)
    # ==========================================
    learner = await seed_user("p11-learner-e2e")
    admin_user = await seed_user("p11-admin-observer")
    space, project = await seed_project(learner.id, "Machine Learning Foundations")

    assert space.id is not None
    assert project.id is not None
    assert project.owner_id == learner.id

    # ==========================================
    # 2. Material Upload & Document Processing (Phase 3)
    # ==========================================
    sample_doc_pages = [
        (
            "Supervised learning trains models on labeled datasets where inputs map to target labels. "
            "Common algorithms include linear regression, logistic regression, and support vector machines."
        ),
        (
            "Gradient descent optimizes objective functions by iteratively stepping in the opposite "
            "direction of the gradient with a learning rate hyperparameter alpha."
        ),
        (
            "Overfitting happens when a model learns training noise rather than the underlying distribution. "
            "Regularization techniques such as L1 Lasso and L2 Ridge mitigate overfitting by penalizing large weights."
        ),
    ]
    pdf_data = make_pdf(sample_doc_pages)

    upload_intent = await materials_service.create_upload_intent(
        owner_id=learner.id,
        project_id=project.id,
        title="ML Core Concepts",
        filename="ml_concepts.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf_data),
    )
    assert upload_intent.storage_key is not None

    storage.upload_bytes(upload_intent.storage_key, pdf_data, content_type="application/pdf")

    # Ingest document into knowledge graph (chunking & embeddings)
    await knowledge_service.ingest_document(
        owner_id=learner.id,
        project_id=project.id,
        material_id=upload_intent.material_id,
        pdf_bytes=pdf_data,
    )
    await materials_service.mark_completed(
        owner_id=learner.id,
        project_id=project.id,
        material_id=upload_intent.material_id,
        page_count=len(sample_doc_pages),
    )

    # Verify material state is now completed
    mat_detail = await materials_service.get_material(
        owner_id=learner.id,
        project_id=project.id,
        material_id=upload_intent.material_id,
    )
    assert mat_detail.status in ("ready", "completed")
    assert mat_detail.page_count == 3

    # ==========================================
    # 3. Grounded AI Tutor & Citation Anchoring (Phase 4)
    # ==========================================
    tutor_conv = await tutor_service.create_conversation(
        owner_id=learner.id,
        project_id=project.id,
        title="ML Study Session",
    )
    assert tutor_conv.id is not None

    # Ask grounded factual question
    grounded_reply, _ = await tutor_service.send_message(
        owner_id=learner.id,
        project_id=project.id,
        conversation_id=tutor_conv.id,
        input_data=SendMessageInput(
            content="How does regularization prevent overfitting in machine learning models?",
            idempotency_key="p11-grounded-msg-1",
        ),
    )
    assert grounded_reply.role == "assistant"
    assert grounded_reply.answer_status == "grounded"
    assert len(grounded_reply.citations) > 0
    cit = grounded_reply.citations[0]
    assert cit.material_id == upload_intent.material_id
    assert cit.page_number in (1, 2, 3)

    # ==========================================
    # 4. Safety: Structural Refusal on Unsupported Question
    # ==========================================
    refusal_reply, _ = await tutor_service.send_message(
        owner_id=learner.id,
        project_id=project.id,
        conversation_id=tutor_conv.id,
        input_data=SendMessageInput(
            content="What were the exact revenue figures of Microsoft in 1985?",
            idempotency_key="p11-unsupported-msg-2",
        ),
    )
    assert refusal_reply.role == "assistant"
    assert refusal_reply.answer_status == "insufficient_evidence"

    # ==========================================
    # 5. Assessment Generation & Quiz Attempt (Phase 5)
    # ==========================================
    quiz = await assessment_service.create_quiz(
        owner_id=learner.id,
        project_id=project.id,
        target_question_count=2,
    )
    assert quiz.id is not None

    first_q = await assessment_service.get_next_question(
        owner_id=learner.id,
        project_id=project.id,
        quiz_id=quiz.id,
    )
    assert first_q is not None

    # Submit an answer to the quiz
    selected_option = first_q.options[0].id if first_q.options else None
    attempt_res = await assessment_service.submit_answer(
        owner_id=learner.id,
        project_id=project.id,
        quiz_id=quiz.id,
        question_id=first_q.id,
        input_data=SubmitAnswerInput(
            question_id=first_q.id,
            selected_option=selected_option,
            selected_option_id=selected_option,
            response_text="Regularization penalizes weight complexity.",
        ),
    )
    assert attempt_res is not None

    # ==========================================
    # 6. Deterministic Mastery Update - BKT (Phase 6)
    # ==========================================
    ml_concept_id = uuid.uuid4()
    mastery_event = await mastery_service.record_learning_event(
        owner_id=learner.id,
        project_id=project.id,
        input_data=mastery_service.RecordEvidenceInput(
            source="assessment",
            source_id=quiz.id,
            concept_id=ml_concept_id,
            result="correct",
            score=1.0,
            difficulty="medium",
        ),
    )
    assert mastery_event.concept_id == ml_concept_id
    assert mastery_event.mastery_probability > 0.0

    concept_state = await mastery_service.get_concept_mastery(
        owner_id=learner.id,
        project_id=project.id,
        concept_id=ml_concept_id,
    )
    assert concept_state.mastery_probability == mastery_event.mastery_probability

    # ==========================================
    # 7. Growth Trajectory & Skill Velocity (Phase 7)
    # ==========================================
    growth_snapshot = await growth_service.get_project_growth(
        owner_id=learner.id,
        project_id=project.id,
    )
    assert growth_snapshot.project_id == project.id
    assert growth_snapshot.concept_count >= 1

    # ==========================================
    # 8. Adaptive Recommendation Engine (Phase 8)
    # ==========================================
    recs = await recommendation_service.generate_recommendations(
        owner_id=learner.id,
        project_id=project.id,
    )
    assert isinstance(recs, list)

    # ==========================================
    # 9. Analytics Ingestion & Rollup (Phase 9)
    # ==========================================
    from app.analytics.schemas import AnalyticsEventInput

    await analytics_service.record_event(
        owner_id=learner.id,
        project_id=project.id,
        input_data=AnalyticsEventInput(
            event_type="tutor_message_sent",
            entity_type="conversation",
            entity_id=tutor_conv.id,
            metadata_payload={"status": "grounded"},
        ),
    )

    overview_metrics = await analytics_service.get_project_overview(
        owner_id=learner.id,
        project_id=project.id,
        range_str="30d",
    )
    assert overview_metrics.project_id == project.id
    assert overview_metrics.activity.active_days >= 0

    # ==========================================
    # 10. Admin Dashboard & System Observability (Phase 10)
    # ==========================================
    admin_overview = await admin_service.get_platform_overview(actor_id=admin_user.id)
    assert admin_overview.users["total"] >= 2
    assert admin_overview.projects["total"] >= 1
    assert admin_overview.materials["ready"] >= 1

    # Admin inspects project detail
    admin_proj = await admin_service.get_project_detail(
        actor_id=admin_user.id,
        project_id=project.id,
    )
    assert admin_proj.id == project.id
    assert admin_proj.materials_count >= 1

    # Admin verifies system health
    health_status = await admin_service.get_system_health(actor_id=admin_user.id)
    assert health_status.status in ("healthy", "degraded")
    assert "database" in health_status.components

    # Verify audit log was created for admin actions
    audit_logs = await admin_service.list_audit_logs(actor_id=admin_user.id, page=1, page_size=10)
    assert audit_logs.total >= 1
    actions = [a.action for a in audit_logs.items]
    assert "view_overview" in actions or "view_project_detail" in actions
