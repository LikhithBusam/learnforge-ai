"""Integration tests for Phase 6 Mastery idempotency (against cloud Supabase DB).

Verifies that:
- Processing the exact same evidence multiple times produces 0 duplicate updates.
- Repeated calls return the existing mastery state safely without inflating counters.
"""

from __future__ import annotations

import uuid

import pytest
from app.mastery import service as mastery_service


@pytest.mark.asyncio
async def test_record_evidence_idempotency_replay(cloud_settings, engines, seed_user, seed_project):
    """Submitting the exact same evidence (source, source_id, concept_id) 3 times is idempotent."""
    user = await seed_user("p6-idem-user")
    _, project = await seed_project(user.id, "Idempotency Project")

    concept_id = uuid.uuid4()
    source_id = uuid.uuid4()

    input_payload = mastery_service.RecordEvidenceInput(
        source="assessment",
        source_id=source_id,
        concept_id=concept_id,
        result="correct",
        score=1.0,
        difficulty="medium",
    )

    # 1. First execution
    res1 = await mastery_service.record_learning_event(
        owner_id=user.id,
        project_id=project.id,
        input_data=input_payload,
    )
    assert res1.evidence_count == 1
    assert res1.correct_count == 1
    first_p = res1.mastery_probability
    first_conf = res1.confidence

    # 2. Second execution (exact same source_id)
    res2 = await mastery_service.record_learning_event(
        owner_id=user.id,
        project_id=project.id,
        input_data=input_payload,
    )
    assert res2.evidence_count == 1
    assert res2.correct_count == 1
    assert res2.mastery_probability == first_p
    assert res2.confidence == first_conf

    # 3. Third execution
    res3 = await mastery_service.record_learning_event(
        owner_id=user.id,
        project_id=project.id,
        input_data=input_payload,
    )
    assert res3.evidence_count == 1
    assert res3.correct_count == 1
    assert res3.mastery_probability == first_p

    # 4. Audit trail must contain exactly ONE event
    trail = await mastery_service.get_evidence_trail(
        owner_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
    )
    assert len(trail) == 1
    assert trail[0].source_id == source_id
