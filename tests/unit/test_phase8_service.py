"""Unit tests for Phase 8 Recommendation service DTOs and mapping helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.recommendations.calculator import (
    ReasonCode,
    RecommendationPriorityLevel,
    RecommendationStatus,
    RecommendationType,
)
from app.recommendations.models import Recommendation
from app.recommendations.schemas import (
    GenerateRecommendationsInput,
    RecommendationDto,
    RecommendationFeedbackInput,
)
from app.recommendations.service import _rec_to_dto


def test_rec_to_dto_mapping():
    rec = Recommendation(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        concept_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        type="PRACTICE_CONCEPT",
        title="Practice Concept",
        description="Practice exercises",
        priority_score=0.7500,
        priority_level="high",
        reason_codes=["LOW_MASTERY", "HIGH_ATTENTION"],
        evidence_refs={"mastery_probability": 0.35},
        action_type="start_practice_quiz",
        action_target="some-concept-id",
        status="PENDING",
        algorithm_version="rec-1.0",
        source_growth_event_id=uuid.uuid4(),
        expires_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    dto = _rec_to_dto(rec)
    assert isinstance(dto, RecommendationDto)
    assert dto.type == RecommendationType.PRACTICE_CONCEPT
    assert dto.priority_score == 0.75
    assert dto.priority_level == RecommendationPriorityLevel.HIGH
    assert ReasonCode.LOW_MASTERY in dto.reason_codes
    assert dto.status == RecommendationStatus.PENDING


def test_feedback_input_validation():
    inp = RecommendationFeedbackInput(
        action="completed",
        feedback_text="Very helpful recommendation.",
    )
    assert inp.action == "completed"
    assert inp.feedback_text == "Very helpful recommendation."


def test_generate_input():
    gid = uuid.uuid4()
    inp = GenerateRecommendationsInput(source_growth_event_id=gid)
    assert inp.source_growth_event_id == gid
