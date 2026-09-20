"""Pure mathematical Bayesian Knowledge Tracing (BKT) calculator (Phase 6).

Implements deterministic BKT update equations, partial credit interpolation,
difficulty weighting, and evidence-volume confidence saturation.
Contains ZERO database, network, or AI dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class MasteryCategory(str, Enum):
    DEVELOPING = "developing"  # p < 0.40
    PROGRESSING = "progressing"  # 0.40 <= p < 0.75
    MASTERED = "mastered"  # p >= 0.75


@dataclass(frozen=True)
class BktParameters:
    """Configurable baseline parameters for Bayesian Knowledge Tracing."""

    p_init: float = 0.20  # Prior probability of initial mastery
    p_learn: float = 0.10  # Probability of transitioning from unmastered to mastered
    p_guess: float = 0.20  # Probability of answering correctly while unmastered
    p_slip: float = 0.10  # Probability of answering incorrectly while mastered
    partial_credit_weight: float = 0.50  # Default weight when score is not explicit
    easy_weight: float = 0.80  # Difficulty multiplier for easy items
    medium_weight: float = 1.00  # Difficulty multiplier for medium items
    hard_weight: float = 1.20  # Difficulty multiplier for hard items
    confidence_k: float = 5.0  # Saturation constant for confidence calculation


DEFAULT_BKT_PARAMS = BktParameters()


def get_difficulty_weight(difficulty: str, params: BktParameters = DEFAULT_BKT_PARAMS) -> float:
    """Map difficulty string to configured numerical weight."""
    diff_lower = difficulty.lower() if difficulty else "medium"
    if diff_lower == "easy":
        return params.easy_weight
    if diff_lower == "hard":
        return params.hard_weight
    return params.medium_weight


def compute_bkt_posterior(
    p: float,
    is_correct: bool,
    p_guess: float = DEFAULT_BKT_PARAMS.p_guess,
    p_slip: float = DEFAULT_BKT_PARAMS.p_slip,
) -> float:
    """Compute posterior mastery probability given observation (Bayes' Rule).

    P(L | correct)   = (p * (1 - p_slip)) / (p * (1 - p_slip) + (1 - p) * p_guess)
    P(L | incorrect) = (p * p_slip)       / (p * p_slip + (1 - p) * (1 - p_guess))
    """
    p = max(0.0001, min(0.9999, p))
    if is_correct:
        num = p * (1.0 - p_slip)
        denom = num + (1.0 - p) * p_guess
    else:
        num = p * p_slip
        denom = num + (1.0 - p) * (1.0 - p_guess)

    if denom <= 0.0:
        return p
    posterior = num / denom
    return max(0.0001, min(0.9999, posterior))


def compute_bkt_transition(
    p_posterior: float,
    p_learn: float = DEFAULT_BKT_PARAMS.p_learn,
) -> float:
    """Apply learning transition to posterior: P(L_t) = P(L_{t-1} | Obs) + (1 - P(L_{t-1} | Obs)) * p_learn."""
    p_new = p_posterior + (1.0 - p_posterior) * p_learn
    return max(0.0001, min(0.9999, p_new))


def compute_bkt_update(
    p_current: float,
    result: str,
    score: float | None = None,
    difficulty: str = "medium",
    params: BktParameters = DEFAULT_BKT_PARAMS,
) -> float:
    """Calculate the next mastery probability given an evidence observation.

    Handles:
    - Binary correct: result == "correct" or score >= 0.99
    - Binary incorrect: result == "incorrect" or score <= 0.01
    - Partial credit: interpolates between incorrect and correct posteriors
    - Difficulty weighting: modulates the shift in probability
    """
    p_old = max(0.0001, min(0.9999, p_current))
    res_lower = result.lower() if result else "incorrect"

    if res_lower == "correct" or (score is not None and score >= 0.99):
        post = compute_bkt_posterior(
            p_old, is_correct=True, p_guess=params.p_guess, p_slip=params.p_slip
        )
        raw_next = compute_bkt_transition(post, p_learn=params.p_learn)
    elif res_lower == "incorrect" or (score is not None and score <= 0.01):
        post = compute_bkt_posterior(
            p_old, is_correct=False, p_guess=params.p_guess, p_slip=params.p_slip
        )
        raw_next = compute_bkt_transition(post, p_learn=params.p_learn)
    else:
        # Partial credit: compute both posteriors and interpolate
        eff_score = score if score is not None else params.partial_credit_weight
        eff_score = max(0.0, min(1.0, eff_score))

        post_correct = compute_bkt_posterior(
            p_old, is_correct=True, p_guess=params.p_guess, p_slip=params.p_slip
        )
        post_incorrect = compute_bkt_posterior(
            p_old, is_correct=False, p_guess=params.p_guess, p_slip=params.p_slip
        )

        interpolated_post = (1.0 - eff_score) * post_incorrect + eff_score * post_correct
        raw_next = compute_bkt_transition(interpolated_post, p_learn=params.p_learn)

    # Apply difficulty weighting
    diff_weight = get_difficulty_weight(difficulty, params)
    delta = raw_next - p_old
    if delta >= 0:
        weighted_delta = delta * diff_weight
    else:
        # Failing an easy question penalizes more (1.2x) than failing a hard question (0.8x)
        inverted_weight = 2.0 - diff_weight
        weighted_delta = delta * inverted_weight

    p_final = p_old + weighted_delta

    return max(0.001, min(0.999, p_final))


def compute_confidence(
    evidence_count: int,
    effective_weight_sum: float | None = None,
    k: float = DEFAULT_BKT_PARAMS.confidence_k,
) -> float:
    """Compute confidence in [0, 1] as a monotonic saturation of evidence volume.

    confidence = 1 - e^(-n_eff / k)
    """
    if evidence_count <= 0:
        return 0.0

    n_eff = effective_weight_sum if effective_weight_sum is not None else float(evidence_count)
    if n_eff <= 0.0:
        return 0.0

    conf = 1.0 - math.exp(-n_eff / max(0.1, k))
    return max(0.0, min(1.0, conf))


def get_mastery_category(probability: float) -> MasteryCategory:
    """Determine descriptive category for a mastery probability score."""
    if probability >= 0.75:
        return MasteryCategory.MASTERED
    if probability >= 0.40:
        return MasteryCategory.PROGRESSING
    return MasteryCategory.DEVELOPING
