"""Adaptive question selection policy (Phase 5 signals only).

This module is a pure function — no I/O, no database access, no AI calls.
It is independently testable with deterministic inputs.

IMPORTANT: This uses ONLY Phase 5 signals (attempt history, difficulty,
recency, coverage). It does NOT use mastery probabilities, BKT, or
any growth calculations. Those belong to Phase 6.

Selection score formula:
    selection_score =
        0.30 * weakness_signal      (recent wrong answers on concept/question)
      + 0.25 * novelty_signal       (prefer never-attempted questions)
      + 0.20 * coverage_signal      (prefer questions covering unseen concepts)
      + 0.15 * difficulty_fit       (alignment with target difficulty)
      + 0.10 * recency_signal       (penalize questions seen very recently)

All signals are in [0.0, 1.0]. Higher score = higher priority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AttemptRecord:
    """Minimal attempt data the policy needs — no answer content."""

    question_id: str
    concept_id: str | None
    is_correct: bool | None
    difficulty: str
    attempted_at: datetime


@dataclass
class SelectionSignals:
    """Decomposed adaptive signals for one candidate question."""

    weakness_signal: float = 0.0
    novelty_signal: float = 0.0
    coverage_signal: float = 0.0
    difficulty_fit: float = 0.0
    recency_signal: float = 0.0

    @property
    def total_score(self) -> float:
        return (
            0.30 * self.weakness_signal
            + 0.25 * self.novelty_signal
            + 0.20 * self.coverage_signal
            + 0.15 * self.difficulty_fit
            + 0.10 * self.recency_signal
        )


@dataclass
class CandidateQuestion:
    """Question candidate for adaptive selection."""

    question_id: str
    concept_id: str | None
    difficulty: str
    question_type: str
    # Extra fields passed through unchanged
    extra: dict[str, Any] = field(default_factory=dict)


class AdaptivePolicy:
    """Phase 5 adaptive question selection policy.

    Uses only assessment/history signals. Explicitly does NOT use mastery values.
    The policy is deterministic: same inputs always produce the same ranking.
    """

    # How many recent attempts to examine for weakness/recency signals
    RECENCY_WINDOW = 10
    # Seconds after which a recent penalty fully decays
    RECENCY_DECAY_SECONDS = 300  # 5 minutes — short window for in-session recency

    def select_next(
        self,
        candidates: list[CandidateQuestion],
        attempt_history: list[AttemptRecord],
        *,
        target_difficulty: str | None = None,
    ) -> CandidateQuestion | None:
        """Select the highest-priority unanswered question.

        Returns None when candidates list is empty.
        """
        if not candidates:
            return None

        scored = [
            (self._compute_signals(c, attempt_history, target_difficulty), c) for c in candidates
        ]
        # Deterministic tie-breaking: sort by (score desc, question_id asc)
        scored.sort(key=lambda x: (-x[0].total_score, x[1].question_id))
        return scored[0][1]

    def _compute_signals(
        self,
        candidate: CandidateQuestion,
        history: list[AttemptRecord],
        target_difficulty: str | None,
    ) -> SelectionSignals:
        sig = SelectionSignals()

        # 1. Novelty signal — has this exact question been attempted before?
        attempted_ids = {a.question_id for a in history}
        sig.novelty_signal = 0.0 if candidate.question_id in attempted_ids else 1.0

        # If already attempted, it's not a valid unanswered candidate —
        # but we still score it so the caller can use the policy for re-exposure.

        # 2. Weakness signal — recent wrong answers on this concept
        if candidate.concept_id:
            recent = [
                a for a in history[-self.RECENCY_WINDOW :] if a.concept_id == candidate.concept_id
            ]
            if recent:
                wrong_count = sum(1 for a in recent if a.is_correct is False)
                # Scale: 3+ wrongs in recent window → full signal
                sig.weakness_signal = min(1.0, wrong_count / 3.0)
            else:
                # Concept not seen recently — moderate weakness assumption
                sig.weakness_signal = 0.3
        else:
            sig.weakness_signal = 0.0

        # 3. Coverage signal — prefer concepts not yet seen in this session
        seen_concepts = {a.concept_id for a in history if a.concept_id is not None}
        if candidate.concept_id is None:
            sig.coverage_signal = 0.5  # no concept info, neutral
        elif candidate.concept_id not in seen_concepts:
            sig.coverage_signal = 1.0  # unseen concept → high coverage value
        else:
            sig.coverage_signal = 0.0  # concept already covered this session

        # 4. Difficulty fit signal — alignment with target difficulty
        difficulty_order = {"easy": 0, "medium": 1, "hard": 2}
        cand_d = difficulty_order.get(candidate.difficulty, 1)
        if target_difficulty is None:
            # No target — prefer medium
            target_d = 1
        else:
            target_d = difficulty_order.get(target_difficulty, 1)
        distance = abs(cand_d - target_d)
        # 0 distance → 1.0, 1 distance → 0.5, 2 distance → 0.0
        sig.difficulty_fit = max(0.0, 1.0 - distance * 0.5)

        # 5. Recency signal — penalize questions seen very recently
        now = datetime.now(timezone.utc)
        recent_attempts_for_q = [a for a in history if a.question_id == candidate.question_id]
        if not recent_attempts_for_q:
            sig.recency_signal = 1.0  # not seen → high recency score
        else:
            last = max(recent_attempts_for_q, key=lambda a: a.attempted_at)
            seconds_ago = (now - last.attempted_at).total_seconds()
            # Decay: fully penalized if within 5 min, fully recovered after 5 min
            decay_ratio = min(1.0, seconds_ago / self.RECENCY_DECAY_SECONDS)
            sig.recency_signal = decay_ratio

        return sig

    def explain(
        self,
        candidate: CandidateQuestion,
        attempt_history: list[AttemptRecord],
        target_difficulty: str | None = None,
    ) -> dict[str, float]:
        """Return decomposed signals for observability and testing."""
        sig = self._compute_signals(candidate, attempt_history, target_difficulty)
        return {
            "weakness_signal": sig.weakness_signal,
            "novelty_signal": sig.novelty_signal,
            "coverage_signal": sig.coverage_signal,
            "difficulty_fit": sig.difficulty_fit,
            "recency_signal": sig.recency_signal,
            "total_score": sig.total_score,
        }


# Module-level singleton — stateless, safe to reuse
_policy: AdaptivePolicy | None = None


def get_adaptive_policy() -> AdaptivePolicy:
    global _policy
    if _policy is None:
        _policy = AdaptivePolicy()
    return _policy
