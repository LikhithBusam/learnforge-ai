"""Pure mathematical Growth Engine calculator (Phase 7).

Implements deterministic trend classification, short-term vs long-term delta
analysis, multi-factor weakness detection, and attention scoring.
Contains ZERO database, network, or AI dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GrowthTrend(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    INSUFFICIENT_DATA = "insufficient_data"


class AttentionLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class GrowthParameters:
    """Configurable baseline parameters for growth analysis."""

    min_observations: int = 2
    stability_delta: float = 0.05
    significant_delta: float = 0.10
    short_term_window: int = 3
    long_term_window: int = 10
    attention_threshold: float = 0.50
    weight_weakness: float = 0.40
    weight_decline: float = 0.30
    weight_mistakes: float = 0.30
    weight_inactivity: float = 0.00


DEFAULT_GROWTH_PARAMS = GrowthParameters()


def classify_trend(
    history: list[float],
    *,
    stability_delta: float = 0.05,
    min_obs: int = 2,
) -> tuple[GrowthTrend, float]:
    """Classify progression trend across a slice of mastery probabilities.

    Returns:
        (trend, delta) where delta = history[-1] - history[0]
    """
    if len(history) < min_obs:
        return GrowthTrend.INSUFFICIENT_DATA, 0.0

    delta = round(history[-1] - history[0], 4)

    if delta > stability_delta:
        return GrowthTrend.IMPROVING, delta
    if delta < -stability_delta:
        return GrowthTrend.DECLINING, delta
    return GrowthTrend.STABLE, delta


def compute_attention_score(
    *,
    current_mastery: float,
    confidence: float,
    short_term_delta: float,
    recent_failure_rate: float,
    params: GrowthParameters = DEFAULT_GROWTH_PARAMS,
) -> tuple[float, AttentionLevel, bool]:
    """Calculate transparent, multi-signal attention metrics.

    Signals:
    1. Weakness: (1 - mastery) * confidence (high confidence in low mastery is strong weakness)
    2. Decline: magnitude of negative short-term delta
    3. Mistakes: recent failure rate across recent attempts
    4. Inactivity: deferred (0.0)

    Returns:
        (attention_score, attention_level, attention_required)
    """
    # 1. Weakness factor [0, 1]
    weakness_factor = max(0.0, min(1.0, (1.0 - current_mastery) * confidence))

    # 2. Decline factor [0, 1] (drops are scaled)
    decline_factor = max(0.0, min(1.0, -short_term_delta * 2.0)) if short_term_delta < 0 else 0.0

    # 3. Mistake factor [0, 1]
    mistake_factor = max(0.0, min(1.0, recent_failure_rate))

    # 4. Inactivity factor (deferred in Phase 7)
    inactivity_factor = 0.0

    raw_score = (
        params.weight_weakness * weakness_factor
        + params.weight_decline * decline_factor
        + params.weight_mistakes * mistake_factor
        + params.weight_inactivity * inactivity_factor
    )

    attention_score = round(max(0.0, min(1.0, raw_score)), 4)

    if attention_score >= 0.60:
        level = AttentionLevel.HIGH
    elif attention_score >= 0.30:
        level = AttentionLevel.MEDIUM
    else:
        level = AttentionLevel.LOW

    attention_required = (
        attention_score >= params.attention_threshold or level == AttentionLevel.HIGH
    )

    return attention_score, level, attention_required


@dataclass(frozen=True)
class GrowthAnalysisResult:
    """Deterministic output of concept growth analysis."""

    current_mastery: float
    previous_mastery: float | None
    short_term_delta: float
    long_term_delta: float
    trend: GrowthTrend
    short_term_trend: GrowthTrend
    long_term_trend: GrowthTrend
    confidence: float
    evidence_count: int
    recent_failure_rate: float
    attention_score: float
    attention_level: AttentionLevel
    attention_required: bool


def analyze_concept_trajectory(
    *,
    mastery_history: list[float],
    recent_results: list[str],
    current_confidence: float,
    params: GrowthParameters = DEFAULT_GROWTH_PARAMS,
) -> GrowthAnalysisResult:
    """Analyze complete mastery sequence and produce structured growth signals."""
    if not mastery_history:
        return GrowthAnalysisResult(
            current_mastery=0.20,
            previous_mastery=None,
            short_term_delta=0.0,
            long_term_delta=0.0,
            trend=GrowthTrend.INSUFFICIENT_DATA,
            short_term_trend=GrowthTrend.INSUFFICIENT_DATA,
            long_term_trend=GrowthTrend.INSUFFICIENT_DATA,
            confidence=0.0,
            evidence_count=0,
            recent_failure_rate=0.0,
            attention_score=0.0,
            attention_level=AttentionLevel.LOW,
            attention_required=False,
        )

    current_mastery = mastery_history[-1]
    previous_mastery = mastery_history[-2] if len(mastery_history) >= 2 else None
    evidence_count = len(mastery_history)

    # 1. Short-term slice
    st_window = (
        mastery_history[-params.short_term_window :]
        if len(mastery_history) >= 2
        else mastery_history
    )
    st_trend, st_delta = classify_trend(
        st_window, stability_delta=params.stability_delta, min_obs=params.min_observations
    )

    # 2. Long-term slice
    lt_window = (
        mastery_history[-params.long_term_window :]
        if len(mastery_history) >= 2
        else mastery_history
    )
    lt_trend, lt_delta = classify_trend(
        lt_window, stability_delta=params.stability_delta, min_obs=params.min_observations
    )

    # Overall primary trend matches long-term if available, else short-term
    primary_trend = lt_trend if lt_trend != GrowthTrend.INSUFFICIENT_DATA else st_trend

    # 3. Calculate recent failure rate
    recent_slice = recent_results[-params.short_term_window :] if recent_results else []
    if recent_slice:
        failures = sum(1 for r in recent_slice if r in ("incorrect", "partial"))
        recent_failure_rate = failures / len(recent_slice)
    else:
        recent_failure_rate = 0.0

    # 4. Attention metrics
    attention_score, attention_level, attention_required = compute_attention_score(
        current_mastery=current_mastery,
        confidence=current_confidence,
        short_term_delta=st_delta,
        recent_failure_rate=recent_failure_rate,
        params=params,
    )

    return GrowthAnalysisResult(
        current_mastery=round(current_mastery, 4),
        previous_mastery=round(previous_mastery, 4) if previous_mastery is not None else None,
        short_term_delta=round(st_delta, 4),
        long_term_delta=round(lt_delta, 4),
        trend=primary_trend,
        short_term_trend=st_trend,
        long_term_trend=lt_trend,
        confidence=round(current_confidence, 4),
        evidence_count=evidence_count,
        recent_failure_rate=round(recent_failure_rate, 4),
        attention_score=attention_score,
        attention_level=attention_level,
        attention_required=attention_required,
    )
