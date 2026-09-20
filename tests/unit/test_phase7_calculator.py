"""Unit tests for Phase 7 Growth Engine calculator."""

from __future__ import annotations

from app.growth.calculator import (
    AttentionLevel,
    GrowthParameters,
    GrowthTrend,
    analyze_concept_trajectory,
    classify_trend,
    compute_attention_score,
)


def test_classify_trend_insufficient_data():
    trend, delta = classify_trend([0.50], min_obs=2)
    assert trend == GrowthTrend.INSUFFICIENT_DATA
    assert delta == 0.0


def test_classify_trend_improving():
    trend, delta = classify_trend([0.30, 0.40, 0.50], stability_delta=0.05)
    assert trend == GrowthTrend.IMPROVING
    assert delta == 0.20


def test_classify_trend_declining():
    trend, delta = classify_trend([0.80, 0.70, 0.60], stability_delta=0.05)
    assert trend == GrowthTrend.DECLINING
    assert delta == -0.20


def test_classify_trend_stable():
    trend, delta = classify_trend([0.60, 0.62, 0.61], stability_delta=0.05)
    assert trend == GrowthTrend.STABLE
    assert abs(delta - 0.01) < 1e-6


def test_compute_attention_score_bounds():
    score, level, req = compute_attention_score(
        current_mastery=0.20,
        confidence=0.90,
        short_term_delta=-0.30,
        recent_failure_rate=1.0,
    )
    assert 0.0 <= score <= 1.0
    assert level == AttentionLevel.HIGH
    assert req is True


def test_compute_attention_score_low():
    score, level, req = compute_attention_score(
        current_mastery=0.95,
        confidence=0.90,
        short_term_delta=0.10,
        recent_failure_rate=0.0,
    )
    assert score < 0.30
    assert level == AttentionLevel.LOW
    assert req is False


def test_analyze_concept_trajectory_empty():
    res = analyze_concept_trajectory(
        mastery_history=[],
        recent_results=[],
        current_confidence=0.0,
    )
    assert res.trend == GrowthTrend.INSUFFICIENT_DATA
    assert res.evidence_count == 0


def test_analyze_concept_trajectory_short_vs_long_term():
    # Long term: 0.30 -> 0.75 (improving)
    # Recent: 0.75 -> 0.68 (declining)
    history = [0.30, 0.40, 0.55, 0.70, 0.75, 0.72, 0.68]
    res = analyze_concept_trajectory(
        mastery_history=history,
        recent_results=[
            "correct",
            "correct",
            "correct",
            "correct",
            "correct",
            "incorrect",
            "incorrect",
        ],
        current_confidence=0.85,
        params=GrowthParameters(short_term_window=3, long_term_window=7),
    )
    assert res.long_term_trend == GrowthTrend.IMPROVING
    assert res.short_term_trend == GrowthTrend.DECLINING
    assert res.trend == GrowthTrend.IMPROVING
