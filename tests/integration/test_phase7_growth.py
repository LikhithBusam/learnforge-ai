"""Integration tests for Phase 7 Growth Engine (against cloud Supabase DB).

Tests end-to-end growth trajectory evaluation, multi-event progression,
attention classification, audit history trail, and project-level summary.
"""

from __future__ import annotations

import io
import uuid

import fitz
import pytest
from app.growth import service as growth_service
from app.growth.schemas import AttentionLevel, GrowthTrend
from app.mastery import service as mastery_service


def make_pdf(texts: list[str] | str) -> bytes:
    doc = fitz.open()
    if isinstance(texts, str):
        texts = [texts]
    for text in texts:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    stream = io.BytesIO()
    doc.save(stream)
    doc.close()
    return stream.getvalue()


@pytest.mark.asyncio
async def test_full_growth_lifecycle_e2e(cloud_settings, engines, seed_user, seed_project):
    """Full pipeline: Assessment evidence -> Mastery -> Growth Evaluation -> Summary."""
    user = await seed_user("p7-growth-user")
    _, project = await seed_project(user.id, "Cloud Growth Project")

    # 1. Record multiple mastery events for a concept to simulate a learning sequence
    concept_id = uuid.uuid4()

    # Attempt 1: correct
    await mastery_service.record_learning_event(
        owner_id=user.id,
        project_id=project.id,
        input_data=mastery_service.RecordEvidenceInput(
            source="assessment",
            source_id=uuid.uuid4(),
            concept_id=concept_id,
            result="correct",
            score=1.0,
            difficulty="medium",
        ),
    )
    trail1 = await mastery_service.get_evidence_trail(
        owner_id=user.id, project_id=project.id, concept_id=concept_id
    )
    mastery_event_1_id = trail1[0].id

    # Evaluate growth after 1 observation
    growth1 = await growth_service.evaluate_concept_growth(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
        source_mastery_event_id=mastery_event_1_id,
    )
    assert growth1.concept_id == concept_id
    assert growth1.evidence_count == 1
    assert growth1.trend == GrowthTrend.INSUFFICIENT_DATA

    # Attempt 2: correct
    await mastery_service.record_learning_event(
        owner_id=user.id,
        project_id=project.id,
        input_data=mastery_service.RecordEvidenceInput(
            source="assessment",
            source_id=uuid.uuid4(),
            concept_id=concept_id,
            result="correct",
            score=1.0,
            difficulty="hard",
        ),
    )
    trail2 = await mastery_service.get_evidence_trail(
        owner_id=user.id, project_id=project.id, concept_id=concept_id
    )
    mastery_event_2_id = trail2[-1].id

    # Evaluate growth after 2 observations
    growth2 = await growth_service.evaluate_concept_growth(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
        source_mastery_event_id=mastery_event_2_id,
    )
    assert growth2.evidence_count == 2
    assert growth2.trend == GrowthTrend.IMPROVING
    assert growth2.short_term_delta > 0
    assert growth2.attention_level == AttentionLevel.LOW

    # 3. Add a second concept with struggles (starts high then drops sharply)
    concept_2_id = uuid.uuid4()
    # 2 correct answers to raise mastery to ~0.80
    for _ in range(2):
        await mastery_service.record_learning_event(
            owner_id=user.id,
            project_id=project.id,
            input_data=mastery_service.RecordEvidenceInput(
                source="assessment",
                source_id=uuid.uuid4(),
                concept_id=concept_2_id,
                result="correct",
                score=1.0,
                difficulty="hard",
            ),
        )

    # 3 incorrect answers to drop mastery
    for _ in range(3):
        await mastery_service.record_learning_event(
            owner_id=user.id,
            project_id=project.id,
            input_data=mastery_service.RecordEvidenceInput(
                source="assessment",
                source_id=uuid.uuid4(),
                concept_id=concept_2_id,
                result="incorrect",
                score=0.0,
                difficulty="medium",
            ),
        )

    trail_c2 = await mastery_service.get_evidence_trail(
        owner_id=user.id, project_id=project.id, concept_id=concept_2_id
    )
    growth_c2 = await growth_service.evaluate_concept_growth(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_2_id,
        source_mastery_event_id=trail_c2[-1].id,
    )
    assert growth_c2.trend == GrowthTrend.DECLINING
    assert growth_c2.short_term_delta < -0.05
    assert growth_c2.attention_required is True

    # 4. Check project-level growth summary
    summary = await growth_service.get_project_growth(
        owner_id=user.id,
        project_id=project.id,
    )
    assert summary.concept_count >= 2
    assert summary.improving_count >= 1
    assert summary.declining_count >= 1
    assert summary.attention_count >= 1
    assert concept_2_id in summary.attention_concepts

    # 5. Check audit history for concept 1
    history = await growth_service.get_growth_history(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
    )
    assert len(history) == 2
    assert history[0].new_trend in (GrowthTrend.IMPROVING, GrowthTrend.INSUFFICIENT_DATA)
