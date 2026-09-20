"""Unit tests for Phase 6 Mastery service helper functions and DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.mastery.calculator import MasteryCategory
from app.mastery.models import ConceptMastery, MasteryEvent
from app.mastery.schemas import (
    MasteryEventDto,
    MasteryStateDto,
    RecordEvidenceInput,
)
from app.mastery.service import _event_to_dto, _mastery_to_dto


def test_mastery_to_dto_mapping():
    m = ConceptMastery(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        concept_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        mastery_probability=0.823456,
        confidence=0.678912,
        evidence_count=5,
        correct_count=4,
        incorrect_count=1,
        partial_count=0,
        consecutive_correct=2,
        last_evidence_at=datetime.now(timezone.utc),
        algorithm_version="bkt-1.0",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    dto = _mastery_to_dto(m)
    assert isinstance(dto, MasteryStateDto)
    assert dto.mastery_probability == 0.8235
    assert dto.confidence == 0.6789
    assert dto.category == MasteryCategory.MASTERED
    assert dto.evidence_count == 5
    assert dto.correct_count == 4


def test_event_to_dto_mapping():
    e = MasteryEvent(
        id=uuid.uuid4(),
        mastery_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        concept_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        source="assessment",
        source_id=uuid.uuid4(),
        mastery_before=0.2000,
        mastery_after=0.5294,
        confidence_before=0.0000,
        confidence_after=0.1813,
        result="correct",
        score=1.0,
        difficulty="medium",
        algorithm_version="bkt-1.0",
        occurred_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )

    dto = _event_to_dto(e)
    assert isinstance(dto, MasteryEventDto)
    assert dto.mastery_before == 0.2000
    assert dto.mastery_after == 0.5294
    assert dto.result == "correct"


def test_record_evidence_input_validation():
    cid = uuid.uuid4()
    sid = uuid.uuid4()
    payload = RecordEvidenceInput(
        source="assessment",
        source_id=sid,
        concept_id=cid,
        result="correct",
        score=1.0,
        difficulty="hard",
    )
    assert payload.source == "assessment"
    assert payload.score == 1.0
    assert payload.difficulty == "hard"
