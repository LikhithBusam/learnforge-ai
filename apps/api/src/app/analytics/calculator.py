"""Pure mathematical and statistical calculator for Analytics & Learner Progress.

Phase 9: Zero-dependency, deterministic aggregation and rate calculation.
Provides strict UTC time window parsing, safe division for ratios, active days calculation,
mastery/growth distribution aggregation, and recommendation/assessment funnel metrics.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from enum import Enum
from typing import Any


class TimeWindowRange(str, Enum):
    DAYS_7 = "7d"
    DAYS_30 = "30d"
    DAYS_90 = "90d"
    ALL_TIME = "all"


class MetricCategory(str, Enum):
    ACTIVITY = "activity"
    ASSESSMENT = "assessment"
    TUTOR = "tutor"
    MASTERY = "mastery"
    GROWTH = "growth"
    RECOMMENDATIONS = "recommendations"
    MATERIALS = "materials"


def parse_time_window(
    window_str: str | None, now_utc: datetime.datetime | None = None
) -> tuple[datetime.datetime | None, datetime.datetime]:
    """Parse time window parameter into (start_datetime_utc, end_datetime_utc).

    Supports '7d', '30d', '90d', 'all' (default: '30d').
    """
    now = now_utc or datetime.datetime.now(datetime.timezone.utc)
    if not window_str or window_str == TimeWindowRange.DAYS_30.value:
        return now - datetime.timedelta(days=30), now
    if window_str == TimeWindowRange.DAYS_7.value:
        return now - datetime.timedelta(days=7), now
    if window_str == TimeWindowRange.DAYS_90.value:
        return now - datetime.timedelta(days=90), now
    if window_str == TimeWindowRange.ALL_TIME.value:
        return None, now

    # Fallback to 30d if unrecognized
    return now - datetime.timedelta(days=30), now


def calculate_safe_ratio(numerator: int | float, denominator: int | float) -> float:
    """Calculate ratio with safe handling for zero denominators, rounded to 4 decimal places."""
    if denominator <= 0:
        return 0.0
    val = float(numerator) / float(denominator)
    return round(max(0.0, min(1.0, val)), 4)


def calculate_active_days(event_timestamps: Sequence[datetime.datetime]) -> int:
    """Calculate the number of distinct UTC calendar days containing at least one event."""
    distinct_dates = {dt.astimezone(datetime.timezone.utc).date() for dt in event_timestamps}
    return len(distinct_dates)


def aggregate_mastery_distribution(
    mastery_probabilities: Sequence[float],
) -> dict[str, int]:
    """Aggregate concept mastery probabilities into standard cognitive tiers:

    - developing: p < 0.50
    - progressing: 0.50 <= p < 0.85
    - mastered: p >= 0.85
    """
    developing = 0
    progressing = 0
    mastered = 0

    for p in mastery_probabilities:
        if p >= 0.85:
            mastered += 1
        elif p >= 0.50:
            progressing += 1
        else:
            developing += 1

    return {
        "developing": developing,
        "progressing": progressing,
        "mastered": mastered,
        "total_concepts": len(mastery_probabilities),
    }


def aggregate_growth_distribution(
    trends: Sequence[str], attention_flags: Sequence[bool]
) -> dict[str, int]:
    """Aggregate concept growth trajectories and attention counts.

    - improving
    - stable
    - declining
    - attention_required
    """
    improving = 0
    stable = 0
    declining = 0
    attention_required = sum(1 for a in attention_flags if a)

    for t in trends:
        trend_val = str(t).lower()
        if trend_val == "improving":
            improving += 1
        elif trend_val == "declining":
            declining += 1
        else:
            stable += 1

    return {
        "improving": improving,
        "stable": stable,
        "declining": declining,
        "attention_required": attention_required,
        "total_evaluated": len(trends),
    }


def aggregate_recommendations_funnel(
    statuses: Sequence[str],
) -> dict[str, Any]:
    """Aggregate recommendation lifecycle statuses and completion rate."""
    counts = {
        "pending": 0,
        "viewed": 0,
        "started": 0,
        "completed": 0,
        "dismissed": 0,
    }
    for s in statuses:
        val = str(s).lower()
        if val in counts:
            counts[val] += 1

    total = sum(counts.values())
    completion_rate = calculate_safe_ratio(counts["completed"], total)

    return {
        "generated": total,
        "pending": counts["pending"],
        "viewed": counts["viewed"],
        "started": counts["started"],
        "completed": counts["completed"],
        "dismissed": counts["dismissed"],
        "completion_rate": completion_rate,
    }


def aggregate_assessment_metrics(
    quizzes_started: int,
    quizzes_completed: int,
    question_attempts: int,
    correct_attempts: int,
    incorrect_attempts: int,
    pending_review_attempts: int = 0,
) -> dict[str, Any]:
    """Calculate assessment completion rates and accuracy."""
    graded_attempts = correct_attempts + incorrect_attempts
    accuracy = calculate_safe_ratio(correct_attempts, graded_attempts)
    completion_rate = calculate_safe_ratio(quizzes_completed, quizzes_started)

    return {
        "quizzes_started": quizzes_started,
        "quizzes_completed": quizzes_completed,
        "completion_rate": completion_rate,
        "question_attempts": question_attempts,
        "correct_attempts": correct_attempts,
        "incorrect_attempts": incorrect_attempts,
        "pending_review_attempts": pending_review_attempts,
        "accuracy": accuracy,
    }


def aggregate_tutor_metrics(
    conversations_count: int,
    messages_count: int,
    grounded_responses: int,
    insufficient_evidence_responses: int,
    citations_used: int = 0,
) -> dict[str, Any]:
    """Calculate tutor engagement and grounded response rate."""
    total_responses = grounded_responses + insufficient_evidence_responses
    grounded_rate = calculate_safe_ratio(grounded_responses, total_responses)

    return {
        "conversations": conversations_count,
        "messages": messages_count,
        "grounded_responses": grounded_responses,
        "insufficient_evidence": insufficient_evidence_responses,
        "citations_used": citations_used,
        "grounded_response_rate": grounded_rate,
    }


def aggregate_material_metrics(
    materials_uploaded: int,
    documents_processed: int,
    ready_documents: int,
    failed_documents: int,
    total_pages: int,
    total_chunks: int,
) -> dict[str, Any]:
    """Calculate material processing and ingestion stats."""
    return {
        "materials_uploaded": materials_uploaded,
        "documents_processed": documents_processed,
        "ready_documents": ready_documents,
        "failed_documents": failed_documents,
        "total_pages": total_pages,
        "total_chunks": total_chunks,
    }
