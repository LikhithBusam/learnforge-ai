"""Benchmark Evaluation Suite for Phase 8 Recommendation Engine.

Tests 12 canonical pedagogical recommendation scenarios against deterministic expectations:
1. Weak + Declining
2. Weak but Improving
3. Strong but Declining
4. Strong and Stable (No-op)
5. Low Confidence
6. Material Available
7. Material Missing
8. Recent Duplicate (Cooldown Penalty)
9. Valid & Invalid Lifecycle Transitions
10. Multiple Weak Concepts (Top-K & Stable Tie-break)
11. Cold Start
12. Determinism / Reproducibility (10 identical runs)
"""

from __future__ import annotations

import uuid

from app.recommendations.calculator import (
    ConceptContext,
    ReasonCode,
    RecommendationPriorityLevel,
    RecommendationStatus,
    RecommendationType,
    generate_candidates_for_concept,
    is_valid_status_transition,
    rank_and_filter_recommendations,
    score_candidate,
)


def test_scenario_1_weak_plus_declining():
    ctx = ConceptContext(
        concept_id=uuid.uuid4(),
        mastery_probability=0.35,
        confidence=0.85,
        growth_trend="declining",
        short_term_delta=-0.20,
        recent_failure_rate=0.80,
        attention_required=True,
        material_ids=[uuid.uuid4()],
        material_titles=["Relational Joins"],
    )

    candidates = generate_candidates_for_concept(ctx)
    assert len(candidates) >= 1

    top = candidates[0]
    assert top.priority_score >= 0.60
    assert top.priority_level == RecommendationPriorityLevel.HIGH
    assert ReasonCode.LOW_MASTERY in top.reason_codes
    assert ReasonCode.DECLINING_TREND in top.reason_codes
    assert ReasonCode.RECENT_FAILURES in top.reason_codes


def test_scenario_2_weak_but_improving():
    ctx = ConceptContext(
        concept_id=uuid.uuid4(),
        mastery_probability=0.40,
        confidence=0.60,
        growth_trend="improving",
        short_term_delta=0.20,
        recent_failure_rate=0.0,
        attention_required=False,
        material_ids=[uuid.uuid4()],
        material_titles=["Relational Joins"],
    )

    candidates = generate_candidates_for_concept(ctx)
    assert len(candidates) >= 1

    top = candidates[0]
    # Should not be high emergency because trend is improving and failure rate is 0
    assert top.priority_score < 0.70
    assert ReasonCode.DECLINING_TREND not in top.reason_codes


def test_scenario_3_strong_but_declining():
    ctx = ConceptContext(
        concept_id=uuid.uuid4(),
        mastery_probability=0.82,
        confidence=0.90,
        growth_trend="declining",
        short_term_delta=-0.15,
        recent_failure_rate=0.40,
        attention_required=True,
        material_ids=[uuid.uuid4()],
    )

    candidates = generate_candidates_for_concept(ctx)
    assert len(candidates) >= 1
    # Decline creates remediation recommendation despite mastery >= 0.80
    rec_types = [c.recommendation_type for c in candidates]
    assert (
        RecommendationType.REVISIT_MATERIAL in rec_types
        or RecommendationType.REVIEW_MISTAKES in rec_types
    )


def test_scenario_4_strong_and_stable():
    ctx = ConceptContext(
        concept_id=uuid.uuid4(),
        mastery_probability=0.90,
        confidence=0.90,
        growth_trend="stable",
        short_term_delta=0.0,
        recent_failure_rate=0.0,
        attention_required=False,
    )

    candidates = generate_candidates_for_concept(ctx)
    assert len(candidates) == 0


def test_scenario_5_low_confidence():
    ctx = ConceptContext(
        concept_id=uuid.uuid4(),
        mastery_probability=0.40,
        confidence=0.10,
        growth_trend="stable",
        short_term_delta=0.0,
        recent_failure_rate=0.0,
        attention_required=False,
    )

    score, _, reasons = score_candidate(ctx, RecommendationType.PRACTICE_CONCEPT)
    assert ReasonCode.LOW_CONFIDENCE in reasons
    # Low confidence moderates weakness panic
    assert score < 0.50


def test_scenario_6_material_available():
    mat_id = uuid.uuid4()
    ctx = ConceptContext(
        concept_id=uuid.uuid4(),
        mastery_probability=0.50,
        confidence=0.70,
        growth_trend="stable",
        short_term_delta=0.0,
        recent_failure_rate=0.20,
        attention_required=False,
        material_ids=[mat_id],
        material_titles=["Distributed Consensus"],
    )

    candidates = generate_candidates_for_concept(ctx)
    revisit = next(
        (c for c in candidates if c.recommendation_type == RecommendationType.REVISIT_MATERIAL),
        None,
    )
    assert revisit is not None
    assert revisit.action_target == str(mat_id)
    assert ReasonCode.MATERIAL_AVAILABLE in revisit.reason_codes


def test_scenario_7_material_missing():
    ctx = ConceptContext(
        concept_id=uuid.uuid4(),
        mastery_probability=0.50,
        confidence=0.70,
        growth_trend="stable",
        short_term_delta=0.0,
        recent_failure_rate=0.20,
        attention_required=False,
        material_ids=[],
    )

    candidates = generate_candidates_for_concept(ctx)
    revisit = next(
        (c for c in candidates if c.recommendation_type == RecommendationType.REVISIT_MATERIAL),
        None,
    )
    assert revisit is None  # Never fabricate a nonexistent material recommendation


def test_scenario_8_recent_duplicate_cooldown():
    cid = uuid.uuid4()
    ctx_new = ConceptContext(
        concept_id=cid,
        mastery_probability=0.40,
        confidence=0.70,
        growth_trend="declining",
        short_term_delta=-0.15,
        recent_failure_rate=0.40,
        attention_required=True,
        recently_recommended=False,
    )

    ctx_cooldown = ConceptContext(
        concept_id=cid,
        mastery_probability=0.40,
        confidence=0.70,
        growth_trend="declining",
        short_term_delta=-0.15,
        recent_failure_rate=0.40,
        attention_required=True,
        recently_recommended=True,
    )

    score_new, _, _ = score_candidate(ctx_new, RecommendationType.PRACTICE_CONCEPT)
    score_cooldown, _, reasons_cd = score_candidate(
        ctx_cooldown, RecommendationType.PRACTICE_CONCEPT
    )

    assert score_cooldown < score_new
    assert ReasonCode.RECENTLY_RECOMMENDED in reasons_cd


def test_scenario_9_lifecycle_transitions():
    assert is_valid_status_transition(RecommendationStatus.PENDING, RecommendationStatus.VIEWED)
    assert is_valid_status_transition(RecommendationStatus.VIEWED, RecommendationStatus.STARTED)
    assert is_valid_status_transition(RecommendationStatus.STARTED, RecommendationStatus.COMPLETED)
    assert is_valid_status_transition(RecommendationStatus.PENDING, RecommendationStatus.DISMISSED)
    # Invalid
    assert not is_valid_status_transition(
        RecommendationStatus.COMPLETED, RecommendationStatus.STARTED
    )


def test_scenario_10_multiple_weak_concepts_top_k():
    candidates = []
    for i in range(12):
        cid = uuid.uuid4()
        ctx = ConceptContext(
            concept_id=cid,
            mastery_probability=0.10 + (i * 0.05),
            confidence=0.75,
            growth_trend="declining" if i % 2 == 0 else "stable",
            short_term_delta=-0.15 if i % 2 == 0 else 0.0,
            recent_failure_rate=0.60 if i % 2 == 0 else 0.20,
            attention_required=True,
        )
        candidates.extend(generate_candidates_for_concept(ctx))

    top_5 = rank_and_filter_recommendations(candidates, top_k=5)
    assert len(top_5) == 5

    # Check unique concept deduplication
    concept_ids = [c.concept_id for c in top_5 if c.concept_id]
    assert len(concept_ids) == len(set(concept_ids))


def test_scenario_11_cold_start():
    # Cold start: 0 candidates generated when no concept context is supplied
    candidates = rank_and_filter_recommendations([], top_k=5)
    assert len(candidates) == 0


def test_scenario_12_determinism_reproducibility():
    ctx = ConceptContext(
        concept_id=uuid.uuid4(),
        mastery_probability=0.45,
        confidence=0.80,
        growth_trend="declining",
        short_term_delta=-0.15,
        recent_failure_rate=0.50,
        attention_required=True,
        material_ids=[uuid.uuid4()],
        material_titles=["Algorithms"],
    )

    baseline = generate_candidates_for_concept(ctx)
    for _ in range(10):
        run = generate_candidates_for_concept(ctx)
        assert run == baseline
