"""Unit tests — Adaptive Selection Policy (Phase 5).

Tests: adaptive.py AdaptivePolicy.select_next with deterministic learner history.
All tests are pure (no I/O, no database, no AI) to validate the scoring formula.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from app.assessment.adaptive import (
    AdaptivePolicy,
    AttemptRecord,
    CandidateQuestion,
    SelectionSignals,
    get_adaptive_policy,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ago(seconds: int) -> datetime:
    return _now() - timedelta(seconds=seconds)


def make_q(qid: str, concept: str | None = "c1", difficulty: str = "medium") -> CandidateQuestion:
    return CandidateQuestion(
        question_id=qid,
        concept_id=concept,
        difficulty=difficulty,
        question_type="mcq",
    )


def make_attempt(
    qid: str,
    concept: str | None = "c1",
    is_correct: bool = True,
    difficulty: str = "medium",
    seconds_ago: int = 60,
) -> AttemptRecord:
    return AttemptRecord(
        question_id=qid,
        concept_id=concept,
        is_correct=is_correct,
        difficulty=difficulty,
        attempted_at=_ago(seconds_ago),
    )


class TestAdaptivePolicy:
    def setup_method(self):
        self.policy = AdaptivePolicy()

    def test_novel_question_scores_full_novelty(self):
        """A never-attempted question gets novelty_signal = 1.0."""
        q = make_q("q-novel", concept="c1")
        history = [make_attempt("q-other", concept="c2", is_correct=True)]
        signals = self.policy._compute_signals(q, history, target_difficulty="medium")
        assert signals.novelty_signal == 1.0

    def test_previously_attempted_question_scores_zero_novelty(self):
        """Already-attempted question gets novelty_signal = 0.0."""
        q = make_q("q-seen")
        history = [make_attempt("q-seen", is_correct=True)]
        signals = self.policy._compute_signals(q, history, target_difficulty="medium")
        assert signals.novelty_signal == 0.0

    def test_weakness_signal_high_for_recent_wrongs(self):
        """3 recent wrong answers on same concept → weakness_signal = 1.0."""
        q = make_q("q-new", concept="c-weak")
        history = [
            make_attempt("q-1", concept="c-weak", is_correct=False),
            make_attempt("q-2", concept="c-weak", is_correct=False),
            make_attempt("q-3", concept="c-weak", is_correct=False),
        ]
        signals = self.policy._compute_signals(q, history, target_difficulty="medium")
        assert signals.weakness_signal == 1.0

    def test_weakness_signal_low_for_correct_answers(self):
        """All recent correct on concept → weakness_signal = 0.0."""
        q = make_q("q-new", concept="c-strong")
        history = [
            make_attempt("q-a", concept="c-strong", is_correct=True),
            make_attempt("q-b", concept="c-strong", is_correct=True),
            make_attempt("q-c", concept="c-strong", is_correct=True),
        ]
        signals = self.policy._compute_signals(q, history, target_difficulty="medium")
        assert signals.weakness_signal == 0.0

    def test_coverage_signal_full_for_unseen_concept(self):
        """Unseen concept → coverage_signal = 1.0."""
        q = make_q("q-new", concept="c-unseen")
        history = [make_attempt("q-a", concept="c-other", is_correct=True)]
        signals = self.policy._compute_signals(q, history, target_difficulty="medium")
        assert signals.coverage_signal == 1.0

    def test_coverage_signal_zero_for_already_covered_concept(self):
        """Already-seen concept → coverage_signal = 0.0."""
        q = make_q("q-new", concept="c-seen")
        history = [make_attempt("q-a", concept="c-seen", is_correct=True)]
        signals = self.policy._compute_signals(q, history, target_difficulty="medium")
        assert signals.coverage_signal == 0.0

    def test_difficulty_fit_exact_match_scores_one(self):
        """Exact difficulty match → difficulty_fit = 1.0."""
        q = make_q("q-hard", difficulty="hard")
        history = []
        signals = self.policy._compute_signals(q, history, target_difficulty="hard")
        assert signals.difficulty_fit == 1.0

    def test_difficulty_fit_one_step_off_scores_half(self):
        """One step off → difficulty_fit = 0.5."""
        q = make_q("q-easy", difficulty="easy")
        signals = self.policy._compute_signals(q, [], target_difficulty="medium")
        assert signals.difficulty_fit == 0.5

    def test_difficulty_fit_two_steps_off_scores_zero(self):
        """Two steps off → difficulty_fit = 0.0."""
        q = make_q("q-easy", difficulty="easy")
        signals = self.policy._compute_signals(q, [], target_difficulty="hard")
        assert signals.difficulty_fit == 0.0

    def test_recency_signal_full_for_unseen(self):
        """Never-seen question → recency_signal = 1.0."""
        q = make_q("q-new")
        signals = self.policy._compute_signals(q, [], target_difficulty=None)
        assert signals.recency_signal == 1.0

    def test_recency_signal_penalizes_recent(self):
        """Question seen 30 seconds ago is heavily penalized."""
        q = make_q("q-recent")
        history = [make_attempt("q-recent", seconds_ago=30)]
        signals = self.policy._compute_signals(q, history, target_difficulty=None)
        # 30/300 = 0.10 decay ratio
        assert signals.recency_signal == pytest.approx(0.10, abs=0.02)

    def test_recency_signal_recovers_after_decay_window(self):
        """Question seen 10 minutes ago has recovered recency signal."""
        q = make_q("q-old")
        history = [make_attempt("q-old", seconds_ago=600)]  # past decay window
        signals = self.policy._compute_signals(q, history, target_difficulty=None)
        assert signals.recency_signal == 1.0

    def test_select_next_prefers_weak_novel_concept(self):
        """select_next prefers a novel question on a weak concept over a seen concept."""
        weak_q = make_q("q-weak-concept", concept="c-weak", difficulty="medium")
        strong_q = make_q("q-strong-concept", concept="c-strong", difficulty="medium")
        history = [
            make_attempt("q-prev-1", concept="c-weak", is_correct=False),
            make_attempt("q-prev-2", concept="c-weak", is_correct=False),
            make_attempt("q-prev-3", concept="c-strong", is_correct=True),
        ]
        result = self.policy.select_next([weak_q, strong_q], history, target_difficulty="medium")
        assert result is not None
        assert result.question_id == "q-weak-concept"

    def test_select_next_prefers_novel_over_seen(self):
        """select_next strongly prefers a novel question over one already seen."""
        novel_q = make_q("q-novel", concept="c-new")
        seen_q = make_q("q-seen", concept="c-new")
        history = [make_attempt("q-seen", concept="c-new", is_correct=True)]
        result = self.policy.select_next([novel_q, seen_q], history)
        assert result is not None
        assert result.question_id == "q-novel"

    def test_select_next_returns_none_on_empty_candidates(self):
        """Empty candidates → None."""
        result = self.policy.select_next([], [])
        assert result is None

    def test_select_next_is_deterministic(self):
        """Same inputs always produce the same result (no random)."""
        candidates = [make_q(f"q-{i}", concept=f"c-{i}") for i in range(5)]
        history = [make_attempt("q-1", is_correct=False)]
        result1 = self.policy.select_next(candidates, history)
        result2 = self.policy.select_next(candidates, history)
        assert result1 is not None
        assert result2 is not None
        assert result1.question_id == result2.question_id

    def test_explain_returns_all_signals(self):
        """explain() returns a dict with all 5 signals + total."""
        q = make_q("q-1")
        explained = self.policy.explain(q, [])
        assert set(explained.keys()) == {
            "weakness_signal",
            "novelty_signal",
            "coverage_signal",
            "difficulty_fit",
            "recency_signal",
            "total_score",
        }
        # All signals in [0, 1]
        for k, v in explained.items():
            assert 0.0 <= v <= 1.0, f"{k} = {v} is out of [0, 1]"

    def test_get_adaptive_policy_returns_singleton(self):
        """Module-level factory returns the same instance."""
        p1 = get_adaptive_policy()
        p2 = get_adaptive_policy()
        assert p1 is p2

    def test_total_score_weights_sum_to_one(self):
        """Weights in formula sum to 1.0."""
        sig = SelectionSignals(
            weakness_signal=1.0,
            novelty_signal=1.0,
            coverage_signal=1.0,
            difficulty_fit=1.0,
            recency_signal=1.0,
        )
        assert sig.total_score == pytest.approx(1.0, abs=1e-9)

    def test_weakness_signal_partial_for_one_wrong(self):
        """One recent wrong → weakness_signal = 1/3 ≈ 0.33."""
        q = make_q("q-new", concept="c-partial")
        history = [make_attempt("q-prev", concept="c-partial", is_correct=False)]
        signals = self.policy._compute_signals(q, history, target_difficulty=None)
        assert signals.weakness_signal == pytest.approx(1 / 3.0, abs=0.01)
