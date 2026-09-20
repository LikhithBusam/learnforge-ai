"""Benchmark Evaluation Suite for Phase 7 Growth Engine.

Tests 10 canonical pedagogical growth scenarios against deterministic expectations:
1. Strong Improvement Sequence
2. Decline Sequence
3. Stable Sequence
4. Insufficient Data Sequence
5. Weak but Improving
6. Strong but Declining
7. Low vs High Confidence
8. Recent Failure Burst
9. Inactivity Signal Deferred
10. Determinism / Reproducibility (10 identical runs)
"""

from __future__ import annotations

from app.growth.calculator import (
    AttentionLevel,
    GrowthTrend,
    analyze_concept_trajectory,
    compute_attention_score,
)


def test_scenario_1_strong_improvement():
    history = [0.20, 0.40, 0.65, 0.85]
    results = ["correct", "correct", "correct", "correct"]
    confidence = 0.85

    res = analyze_concept_trajectory(
        mastery_history=history,
        recent_results=results,
        current_confidence=confidence,
    )

    assert res.trend == GrowthTrend.IMPROVING
    assert res.short_term_trend == GrowthTrend.IMPROVING
    assert res.long_term_trend == GrowthTrend.IMPROVING
    assert res.short_term_delta > 0
    assert res.long_term_delta > 0
    assert res.attention_level == AttentionLevel.LOW
    assert res.attention_required is False


def test_scenario_2_decline_sequence():
    history = [0.85, 0.70, 0.50, 0.35]
    results = ["incorrect", "incorrect", "incorrect", "incorrect"]
    confidence = 0.85

    res = analyze_concept_trajectory(
        mastery_history=history,
        recent_results=results,
        current_confidence=confidence,
    )

    assert res.trend == GrowthTrend.DECLINING
    assert res.short_term_trend == GrowthTrend.DECLINING
    assert res.long_term_trend == GrowthTrend.DECLINING
    assert res.short_term_delta < -0.10
    assert res.long_term_delta < -0.10
    assert res.attention_level in (AttentionLevel.MEDIUM, AttentionLevel.HIGH)
    assert res.attention_required is True


def test_scenario_3_stable_sequence():
    history = [0.70, 0.72, 0.69, 0.71]
    results = ["correct", "partial", "correct", "correct"]
    confidence = 0.80

    res = analyze_concept_trajectory(
        mastery_history=history,
        recent_results=results,
        current_confidence=confidence,
    )

    assert res.trend == GrowthTrend.STABLE
    assert res.short_term_trend == GrowthTrend.STABLE
    assert res.long_term_trend == GrowthTrend.STABLE
    assert abs(res.short_term_delta) <= 0.05
    assert abs(res.long_term_delta) <= 0.05


def test_scenario_4_insufficient_data():
    history = [0.35]
    results = ["correct"]
    confidence = 0.15

    res = analyze_concept_trajectory(
        mastery_history=history,
        recent_results=results,
        current_confidence=confidence,
    )

    assert res.trend == GrowthTrend.INSUFFICIENT_DATA
    assert res.short_term_trend == GrowthTrend.INSUFFICIENT_DATA
    assert res.long_term_trend == GrowthTrend.INSUFFICIENT_DATA
    assert res.short_term_delta == 0.0
    assert res.long_term_delta == 0.0


def test_scenario_5_weak_but_improving():
    # Mastery is low (0.35), but rising from 0.15
    history = [0.15, 0.22, 0.35]
    results = ["correct", "correct", "correct"]
    confidence = 0.60

    res = analyze_concept_trajectory(
        mastery_history=history,
        recent_results=results,
        current_confidence=confidence,
    )

    assert res.trend == GrowthTrend.IMPROVING
    assert res.short_term_delta == 0.20
    # Current mastery is low (0.35), so weakness signal exists, but trend is positive (no decline penalty)
    assert res.attention_score < 0.60  # Not maximum emergency because it is actively improving


def test_scenario_6_strong_but_declining():
    # Mastery is still relatively high (0.75), but sharply dropped from 0.95
    history = [0.95, 0.88, 0.75]
    results = ["incorrect", "incorrect", "incorrect"]
    confidence = 0.90

    res = analyze_concept_trajectory(
        mastery_history=history,
        recent_results=results,
        current_confidence=confidence,
    )

    assert res.trend == GrowthTrend.DECLINING
    assert res.short_term_delta == -0.20
    assert res.recent_failure_rate == 1.0
    # Decline and mistakes boost attention even though mastery is 0.75
    assert res.attention_score >= 0.30


def test_scenario_7_low_vs_high_confidence():
    # Low confidence in low mastery vs High confidence in low mastery
    score_low_conf, _, _ = compute_attention_score(
        current_mastery=0.20,
        confidence=0.10,
        short_term_delta=0.0,
        recent_failure_rate=0.0,
    )
    score_high_conf, _, _ = compute_attention_score(
        current_mastery=0.20,
        confidence=0.90,
        short_term_delta=0.0,
        recent_failure_rate=0.0,
    )

    # High confidence confirms severe weakness, low confidence does not panic prematurely
    assert score_high_conf > score_low_conf


def test_scenario_8_recent_failure_burst():
    history = [0.80, 0.70, 0.60]
    results = ["incorrect", "incorrect", "incorrect"]
    confidence = 0.75

    res = analyze_concept_trajectory(
        mastery_history=history,
        recent_results=results,
        current_confidence=confidence,
    )

    assert res.recent_failure_rate == 1.0
    assert res.attention_score >= 0.50
    assert res.attention_required is True


def test_scenario_9_inactivity_signal_deferred():
    score, level, req = compute_attention_score(
        current_mastery=0.85,
        confidence=0.80,
        short_term_delta=0.05,
        recent_failure_rate=0.0,
    )
    # With default weight_inactivity = 0.0, healthy mastery gets low attention score
    assert score < 0.15
    assert level == AttentionLevel.LOW
    assert req is False


def test_scenario_10_determinism_reproducibility():
    history = [0.30, 0.45, 0.40, 0.55, 0.68]
    results = ["correct", "incorrect", "correct", "correct", "correct"]
    confidence = 0.72

    baseline = analyze_concept_trajectory(
        mastery_history=history,
        recent_results=results,
        current_confidence=confidence,
    )

    for _ in range(10):
        run = analyze_concept_trajectory(
            mastery_history=history,
            recent_results=results,
            current_confidence=confidence,
        )
        assert run == baseline
