"""Unit tests for Phase 8 Recommendation Engine mathematical calculator."""

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


def test_status_transitions():
    assert is_valid_status_transition(RecommendationStatus.PENDING, RecommendationStatus.VIEWED)
    assert is_valid_status_transition(RecommendationStatus.PENDING, RecommendationStatus.STARTED)
    assert is_valid_status_transition(RecommendationStatus.VIEWED, RecommendationStatus.COMPLETED)
    assert is_valid_status_transition(RecommendationStatus.STARTED, RecommendationStatus.COMPLETED)
    assert is_valid_status_transition(RecommendationStatus.PENDING, RecommendationStatus.DISMISSED)
    # Invalid transitions
    assert not is_valid_status_transition(
        RecommendationStatus.COMPLETED, RecommendationStatus.PENDING
    )
    assert not is_valid_status_transition(
        RecommendationStatus.DISMISSED, RecommendationStatus.STARTED
    )


def test_score_candidate_weak_declining():
    ctx = ConceptContext(
        concept_id=uuid.uuid4(),
        mastery_probability=0.30,
        confidence=0.85,
        growth_trend="declining",
        short_term_delta=-0.25,
        recent_failure_rate=0.75,
        attention_required=True,
        material_ids=[uuid.uuid4()],
        material_titles=["Advanced Networking"],
    )

    score, level, reasons = score_candidate(ctx, RecommendationType.REVISIT_MATERIAL)
    assert score >= 0.60
    assert level == RecommendationPriorityLevel.HIGH
    assert ReasonCode.LOW_MASTERY in reasons
    assert ReasonCode.DECLINING_TREND in reasons
    assert ReasonCode.RECENT_FAILURES in reasons
    assert ReasonCode.MATERIAL_AVAILABLE in reasons


def test_score_candidate_cooldown_penalty():
    ctx_normal = ConceptContext(
        concept_id=uuid.uuid4(),
        mastery_probability=0.40,
        confidence=0.70,
        growth_trend="stable",
        short_term_delta=0.0,
        recent_failure_rate=0.20,
        attention_required=False,
        recently_recommended=False,
    )

    ctx_recent = ConceptContext(
        concept_id=ctx_normal.concept_id,
        mastery_probability=0.40,
        confidence=0.70,
        growth_trend="stable",
        short_term_delta=0.0,
        recent_failure_rate=0.20,
        attention_required=False,
        recently_recommended=True,
    )

    score_norm, _, _ = score_candidate(ctx_normal, RecommendationType.PRACTICE_CONCEPT)
    score_recent, _, _ = score_candidate(ctx_recent, RecommendationType.PRACTICE_CONCEPT)

    assert score_recent < score_norm


def test_rank_and_filter_top_k():
    candidates = []
    for i in range(10):
        c_id = uuid.uuid4()
        ctx = ConceptContext(
            concept_id=c_id,
            mastery_probability=0.20 + (i * 0.05),
            confidence=0.80,
            growth_trend="declining" if i < 5 else "stable",
            short_term_delta=-0.10 if i < 5 else 0.0,
            recent_failure_rate=0.50 if i < 5 else 0.10,
            attention_required=i < 5,
        )
        cands = generate_candidates_for_concept(ctx)
        candidates.extend(cands)

    ranked = rank_and_filter_recommendations(candidates, top_k=5)
    assert len(ranked) <= 5

    # Verify strictly descending order
    scores = [r.priority_score for r in ranked]
    assert scores == sorted(scores, reverse=True)
