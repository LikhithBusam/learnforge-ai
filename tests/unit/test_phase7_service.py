"""Unit tests for Phase 7 Growth service helper functions and DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.growth.calculator import AttentionLevel, GrowthTrend
from app.growth.models import ConceptGrowth, GrowthEvent
from app.growth.schemas import (
    ConceptGrowthDto,
    EvaluateGrowthInput,
    GrowthEventDto,
)
from app.growth.service import _event_to_dto, _growth_to_dto


def test_growth_to_dto_mapping():
    growth = ConceptGrowth(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        concept_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        current_mastery=0.7500,
        previous_mastery=0.6000,
        short_term_delta=0.1500,
        long_term_delta=0.3500,
        trend="improving",
        short_term_trend="improving",
        long_term_trend="improving",
        confidence=0.8000,
        evidence_count=6,
        recent_failure_rate=0.1000,
        attention_score=0.1200,
        attention_level="low",
        attention_required=False,
        algorithm_version="growth-1.0",
        last_evaluated_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    dto = _growth_to_dto(growth)
    assert isinstance(dto, ConceptGrowthDto)
    assert dto.current_mastery == 0.75
    assert dto.trend == GrowthTrend.IMPROVING
    assert dto.attention_level == AttentionLevel.LOW
    assert dto.attention_required is False
    assert dto.short_term_delta == 0.15
    assert dto.evidence_count == 6


def test_growth_event_to_dto_mapping():
    event = GrowthEvent(
        id=uuid.uuid4(),
        growth_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        concept_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        source_mastery_event_id=uuid.uuid4(),
        previous_trend="stable",
        new_trend="improving",
        previous_attention_score=0.2000,
        new_attention_score=0.1200,
        previous_mastery=0.6000,
        new_mastery=0.7500,
        short_term_delta=0.1500,
        long_term_delta=0.3500,
        algorithm_version="growth-1.0",
        occurred_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )

    dto = _event_to_dto(event)
    assert isinstance(dto, GrowthEventDto)
    assert dto.previous_trend == GrowthTrend.STABLE
    assert dto.new_trend == GrowthTrend.IMPROVING
    assert dto.new_attention_score == 0.12
    assert dto.short_term_delta == 0.15


def test_evaluate_growth_input():
    mid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    inp = EvaluateGrowthInput(
        source_mastery_event_id=mid,
        occurred_at=now,
    )
    assert inp.source_mastery_event_id == mid
    assert inp.occurred_at == now
