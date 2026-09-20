"""Unit tests for Phase 6 Bayesian Knowledge Tracing (BKT) calculator.

Tests the mathematical integrity of the BKT equations, bounds, partial credit,
difficulty weighting, and confidence saturation.
"""

from __future__ import annotations

import math

from app.mastery.calculator import (
    DEFAULT_BKT_PARAMS,
    MasteryCategory,
    compute_bkt_posterior,
    compute_bkt_transition,
    compute_bkt_update,
    compute_confidence,
    get_mastery_category,
)


class TestBktCoreEquations:
    """Core Bayes and transition calculations."""

    def test_posterior_correct_increases_probability(self):
        p_init = 0.20
        post = compute_bkt_posterior(p_init, is_correct=True, p_guess=0.20, p_slip=0.10)
        assert post > p_init
        # P(L|C) = (0.2 * 0.9) / (0.2 * 0.9 + 0.8 * 0.2) = 0.18 / (0.18 + 0.16) = 0.18 / 0.34 ≈ 0.5294
        assert abs(post - (0.18 / 0.34)) < 1e-4

    def test_posterior_incorrect_decreases_probability(self):
        p_init = 0.50
        post = compute_bkt_posterior(p_init, is_correct=False, p_guess=0.20, p_slip=0.10)
        assert post < p_init
        # P(L|I) = (0.5 * 0.1) / (0.5 * 0.1 + 0.5 * 0.8) = 0.05 / (0.05 + 0.40) = 0.05 / 0.45 ≈ 0.1111
        assert abs(post - (0.05 / 0.45)) < 1e-4

    def test_transition_applies_learning_rate(self):
        post = 0.50
        p_learn = 0.10
        next_p = compute_bkt_transition(post, p_learn=p_learn)
        # next_p = 0.50 + (1 - 0.50) * 0.10 = 0.55
        assert abs(next_p - 0.55) < 1e-4


class TestBktUpdateStep:
    """Full update step including difficulty and bounds."""

    def test_correct_response_increases_mastery(self):
        p_init = 0.20
        p_next = compute_bkt_update(p_init, result="correct", difficulty="medium")
        assert p_next > p_init

    def test_incorrect_response_decreases_mastery(self):
        p_init = 0.60
        p_next = compute_bkt_update(p_init, result="incorrect", difficulty="medium")
        assert p_next < p_init

    def test_partial_credit_interpolates(self):
        p_init = 0.50
        p_correct = compute_bkt_update(p_init, result="correct", score=1.0)
        p_incorrect = compute_bkt_update(p_init, result="incorrect", score=0.0)
        p_partial = compute_bkt_update(p_init, result="partial", score=0.5)

        assert p_incorrect < p_partial < p_correct

    def test_higher_partial_score_yields_higher_mastery(self):
        p_init = 0.40
        p_low = compute_bkt_update(p_init, result="partial", score=0.3)
        p_high = compute_bkt_update(p_init, result="partial", score=0.8)
        assert p_low < p_high

    def test_difficulty_hard_correct_yields_more_gain_than_easy_correct(self):
        p_init = 0.30
        p_easy = compute_bkt_update(p_init, result="correct", difficulty="easy")
        p_hard = compute_bkt_update(p_init, result="correct", difficulty="hard")
        assert p_hard > p_easy

    def test_difficulty_easy_incorrect_yields_more_drop_than_hard_incorrect(self):
        p_init = 0.60
        p_easy = compute_bkt_update(p_init, result="incorrect", difficulty="easy")
        p_hard = compute_bkt_update(p_init, result="incorrect", difficulty="hard")
        assert p_easy < p_hard

    def test_probability_clamped_strictly_within_bounds(self):
        # Repeated correct from high probability
        p = 0.99
        for _ in range(20):
            p = compute_bkt_update(p, result="correct")
            assert 0.001 <= p <= 0.999
            assert not math.isnan(p)
            assert not math.isinf(p)

        # Repeated incorrect from low probability
        p = 0.01
        for _ in range(20):
            p = compute_bkt_update(p, result="incorrect")
            assert 0.001 <= p <= 0.999
            assert not math.isnan(p)
            assert not math.isinf(p)


class TestConfidenceCalculation:
    """Confidence saturation formula."""

    def test_zero_evidence_yields_zero_confidence(self):
        assert compute_confidence(0) == 0.0
        assert compute_confidence(-1) == 0.0

    def test_confidence_monotonically_increases_with_evidence(self):
        c1 = compute_confidence(1)
        c3 = compute_confidence(3)
        c5 = compute_confidence(5)
        c10 = compute_confidence(10)
        c20 = compute_confidence(20)

        assert 0.0 < c1 < c3 < c5 < c10 < c20 <= 1.0

    def test_confidence_bounded_in_0_1(self):
        for n in range(0, 100):
            c = compute_confidence(n)
            assert 0.0 <= c <= 1.0
            assert not math.isnan(c)


class TestMasteryCategory:
    """Mastery category classification."""

    def test_category_cutoffs(self):
        assert get_mastery_category(0.10) == MasteryCategory.DEVELOPING
        assert get_mastery_category(0.39) == MasteryCategory.DEVELOPING
        assert get_mastery_category(0.40) == MasteryCategory.PROGRESSING
        assert get_mastery_category(0.74) == MasteryCategory.PROGRESSING
        assert get_mastery_category(0.75) == MasteryCategory.MASTERED
        assert get_mastery_category(0.95) == MasteryCategory.MASTERED


class TestDeterminism:
    """Determinism guarantee."""

    def test_identical_evidence_sequence_yields_identical_output(self):
        seq = [
            ("correct", 1.0, "medium"),
            ("incorrect", 0.0, "easy"),
            ("partial", 0.7, "hard"),
            ("correct", 1.0, "hard"),
        ]

        def _run_sequence():
            p = DEFAULT_BKT_PARAMS.p_init
            for res, sc, diff in seq:
                p = compute_bkt_update(p, result=res, score=sc, difficulty=diff)
            return p

        run1 = _run_sequence()
        run2 = _run_sequence()
        assert run1 == run2
