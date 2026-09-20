"""Unit tests for Phase 9 Analytics pure mathematical calculator."""

from __future__ import annotations

import datetime

from app.analytics import calculator


def test_parse_time_window_standard():
    """Verify UTC time window parsing for standard ranges."""
    fixed_now = datetime.datetime(2026, 9, 20, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # 7d
    start_7d, end_7d = calculator.parse_time_window("7d", now_utc=fixed_now)
    assert start_7d == fixed_now - datetime.timedelta(days=7)
    assert end_7d == fixed_now

    # 30d
    start_30d, end_30d = calculator.parse_time_window("30d", now_utc=fixed_now)
    assert start_30d == fixed_now - datetime.timedelta(days=30)
    assert end_30d == fixed_now

    # 90d
    start_90d, end_90d = calculator.parse_time_window("90d", now_utc=fixed_now)
    assert start_90d == fixed_now - datetime.timedelta(days=90)
    assert end_90d == fixed_now

    # all
    start_all, end_all = calculator.parse_time_window("all", now_utc=fixed_now)
    assert start_all is None
    assert end_all == fixed_now

    # default/unrecognized
    start_def, end_def = calculator.parse_time_window(None, now_utc=fixed_now)
    assert start_def == fixed_now - datetime.timedelta(days=30)


def test_calculate_safe_ratio_and_zero_division():
    """Verify safe division and bounding to [0.0, 1.0]."""
    assert calculator.calculate_safe_ratio(5, 10) == 0.50
    assert calculator.calculate_safe_ratio(0, 10) == 0.0
    assert calculator.calculate_safe_ratio(10, 0) == 0.0  # Zero denominator
    assert calculator.calculate_safe_ratio(0, 0) == 0.0
    assert calculator.calculate_safe_ratio(-5, 10) == 0.0
    assert calculator.calculate_safe_ratio(15, 10) == 1.0  # Clamped to 1.0


def test_calculate_active_days():
    """Verify counting of distinct UTC calendar days."""
    t1 = datetime.datetime(2026, 9, 20, 10, 0, 0, tzinfo=datetime.timezone.utc)
    t2 = datetime.datetime(2026, 9, 20, 15, 30, 0, tzinfo=datetime.timezone.utc)
    t3 = datetime.datetime(2026, 9, 19, 23, 0, 0, tzinfo=datetime.timezone.utc)
    t4 = datetime.datetime(2026, 9, 15, 8, 0, 0, tzinfo=datetime.timezone.utc)

    # 4 timestamps across 3 distinct days
    assert calculator.calculate_active_days([t1, t2, t3, t4]) == 3
    assert calculator.calculate_active_days([]) == 0


def test_aggregate_mastery_distribution():
    """Verify categorization of concept mastery probabilities."""
    probs = [0.10, 0.45, 0.55, 0.70, 0.84, 0.85, 0.95]
    dist = calculator.aggregate_mastery_distribution(probs)

    assert dist["developing"] == 2  # 0.10, 0.45 (< 0.50)
    assert dist["progressing"] == 3  # 0.55, 0.70, 0.84 (0.50 <= p < 0.85)
    assert dist["mastered"] == 2  # 0.85, 0.95 (>= 0.85)
    assert dist["total_concepts"] == 7


def test_aggregate_growth_distribution():
    """Verify categorization of growth trends and attention count."""
    trends = ["improving", "improving", "stable", "declining", "stable"]
    attention = [False, False, True, True, False]

    dist = calculator.aggregate_growth_distribution(trends, attention)
    assert dist["improving"] == 2
    assert dist["stable"] == 2
    assert dist["declining"] == 1
    assert dist["attention_required"] == 2
    assert dist["total_evaluated"] == 5


def test_aggregate_recommendations_funnel():
    """Verify recommendation status aggregation and completion rate."""
    statuses = [
        "PENDING",
        "PENDING",
        "VIEWED",
        "STARTED",
        "COMPLETED",
        "COMPLETED",
        "DISMISSED",
    ]
    funnel = calculator.aggregate_recommendations_funnel(statuses)

    assert funnel["generated"] == 7
    assert funnel["pending"] == 2
    assert funnel["viewed"] == 1
    assert funnel["started"] == 1
    assert funnel["completed"] == 2
    assert funnel["dismissed"] == 1
    assert funnel["completion_rate"] == round(2 / 7, 4)
