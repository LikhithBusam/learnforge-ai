"""Evaluation suite for Phase 9 Analytics & Learner Progress Dashboard.

Evaluates metric calculations, accuracy, ratios, distributions, and boundary properties
across 12 canonical educational progress scenarios.
"""

from __future__ import annotations

import datetime

from app.analytics import calculator


def test_eval_scenario_01_empty_project():
    """Scenario 1: New project with zero learner interactions."""
    dist = calculator.aggregate_mastery_distribution([])
    assert dist == {"developing": 0, "progressing": 0, "mastered": 0, "total_concepts": 0}

    tutor = calculator.aggregate_tutor_metrics(0, 0, 0, 0, 0)
    assert tutor["grounded_response_rate"] == 0.0

    assess = calculator.aggregate_assessment_metrics(0, 0, 0, 0, 0, 0)
    assert assess["accuracy"] == 0.0
    assert assess["completion_rate"] == 0.0


def test_eval_scenario_02_perfect_accuracy():
    """Scenario 2: Learner answers 10/10 questions correctly."""
    assess = calculator.aggregate_assessment_metrics(
        quizzes_started=2,
        quizzes_completed=2,
        question_attempts=10,
        correct_attempts=10,
        incorrect_attempts=0,
    )
    assert assess["accuracy"] == 1.0
    assert assess["completion_rate"] == 1.0


def test_eval_scenario_03_zero_accuracy():
    """Scenario 3: Learner answers 0/10 questions correctly."""
    assess = calculator.aggregate_assessment_metrics(
        quizzes_started=1,
        quizzes_completed=1,
        question_attempts=10,
        correct_attempts=0,
        incorrect_attempts=10,
    )
    assert assess["accuracy"] == 0.0


def test_eval_scenario_04_pending_review_exclusion():
    """Scenario 4: Pending review questions are excluded from accuracy denominator."""
    assess = calculator.aggregate_assessment_metrics(
        quizzes_started=1,
        quizzes_completed=1,
        question_attempts=10,
        correct_attempts=4,
        incorrect_attempts=1,
        pending_review_attempts=5,
    )
    # Graded attempts = 4 correct + 1 incorrect = 5 total. 4 / 5 = 0.80
    assert assess["accuracy"] == 0.80
    assert assess["pending_review_attempts"] == 5


def test_eval_scenario_05_high_grounding_tutor():
    """Scenario 5: Tutor sessions with high evidence grounding."""
    tutor = calculator.aggregate_tutor_metrics(
        conversations_count=2,
        messages_count=10,
        grounded_responses=8,
        insufficient_evidence_responses=2,
        citations_used=12,
    )
    assert tutor["grounded_response_rate"] == 0.80
    assert tutor["citations_used"] == 12


def test_eval_scenario_06_honest_refusal_tutor():
    """Scenario 6: Tutor sessions with 100% honest refusals due to missing evidence."""
    tutor = calculator.aggregate_tutor_metrics(
        conversations_count=1,
        messages_count=4,
        grounded_responses=0,
        insufficient_evidence_responses=4,
        citations_used=0,
    )
    assert tutor["grounded_response_rate"] == 0.0
    assert tutor["insufficient_evidence"] == 4


def test_eval_scenario_07_all_mastered_distribution():
    """Scenario 7: Advanced learner with all concepts mastered (p >= 0.85)."""
    probs = [0.88, 0.92, 0.95, 0.99]
    dist = calculator.aggregate_mastery_distribution(probs)
    assert dist["mastered"] == 4
    assert dist["developing"] == 0
    assert dist["progressing"] == 0


def test_eval_scenario_08_developing_struggling_distribution():
    """Scenario 8: Struggling learner with all concepts in developing tier."""
    probs = [0.10, 0.20, 0.35, 0.49]
    dist = calculator.aggregate_mastery_distribution(probs)
    assert dist["developing"] == 4
    assert dist["progressing"] == 0
    assert dist["mastered"] == 0


def test_eval_scenario_09_high_attention_growth():
    """Scenario 9: Multiple concepts requiring urgent attention."""
    trends = ["declining", "declining", "stable", "improving"]
    attention = [True, True, True, False]
    dist = calculator.aggregate_growth_distribution(trends, attention)
    assert dist["attention_required"] == 3
    assert dist["declining"] == 2


def test_eval_scenario_10_recommendation_high_completion():
    """Scenario 10: Active learner completes 5 of 5 recommendations."""
    statuses = ["COMPLETED"] * 5
    funnel = calculator.aggregate_recommendations_funnel(statuses)
    assert funnel["completed"] == 5
    assert funnel["completion_rate"] == 1.0


def test_eval_scenario_11_recommendation_all_dismissed():
    """Scenario 11: Learner dismisses all generated recommendations."""
    statuses = ["DISMISSED"] * 4
    funnel = calculator.aggregate_recommendations_funnel(statuses)
    assert funnel["dismissed"] == 4
    assert funnel["completion_rate"] == 0.0


def test_eval_scenario_12_time_window_filtering():
    """Scenario 12: Filtering events across strict UTC time windows."""
    now = datetime.datetime(2026, 9, 20, 0, 0, 0, tzinfo=datetime.timezone.utc)
    t_3d_ago = now - datetime.timedelta(days=3)
    t_10d_ago = now - datetime.timedelta(days=10)
    t_40d_ago = now - datetime.timedelta(days=40)

    # 7-day window contains t_3d_ago
    start_7d, end_7d = calculator.parse_time_window("7d", now_utc=now)
    events_7d = [t for t in [t_3d_ago, t_10d_ago, t_40d_ago] if start_7d <= t <= end_7d]
    assert len(events_7d) == 1

    # 30-day window contains t_3d_ago and t_10d_ago
    start_30d, end_30d = calculator.parse_time_window("30d", now_utc=now)
    events_30d = [t for t in [t_3d_ago, t_10d_ago, t_40d_ago] if start_30d <= t <= end_30d]
    assert len(events_30d) == 2
