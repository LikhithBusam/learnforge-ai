# Adaptive Question Selection (Phase 5)

## Overview

The adaptive selection policy (`adaptive.py`) determines which question to present
next to a learner, using only Phase 5 assessment signals. **No mastery probabilities
are used.** No BKT, no growth classification. Those belong to Phase 6.

## Design Principle: Not Adaptive in the Naïve Sense

The quiz **does NOT** implement `correct → harder, wrong → easier` (naive adaptive).
This would discourage learners and produce poor coverage.

Instead, the policy maximizes **educational value** by balancing 5 signals.

## Selection Formula

```
selection_score =
    0.30 × weakness_signal
  + 0.25 × novelty_signal
  + 0.20 × coverage_signal
  + 0.15 × difficulty_fit
  + 0.10 × recency_signal
```

All signals are in `[0.0, 1.0]`. Higher score = higher priority.

## Signal Definitions

| Signal | Weight | Meaning |
|---|---|---|
| `weakness_signal` | 0.30 | Recent wrong answers on this concept → reinforce |
| `novelty_signal` | 0.25 | Never-attempted question → prefer exploration |
| `coverage_signal` | 0.20 | Concept not yet seen this session → broaden |
| `difficulty_fit` | 0.15 | Closeness to target difficulty |
| `recency_signal` | 0.10 | Not recently seen → avoid immediate repetition |

## Signal Computation Details

### Weakness Signal
- Look at the last 10 attempts on this concept
- 0 wrongs → 0.0, 1 wrong → 0.33, 2 wrongs → 0.67, 3+ wrongs → 1.0
- Unseen concept → 0.30 (moderate priority, encourage exploration)

### Novelty Signal
- 1.0 if this exact question was never attempted
- 0.0 if this question was attempted before

### Coverage Signal
- 1.0 if the concept has NOT been seen this session
- 0.0 if the concept was already covered this session
- 0.5 if concept_id is null (no concept information)

### Difficulty Fit
- 0 distance → 1.0
- 1 step distance → 0.5
- 2 steps distance → 0.0

### Recency Signal
- Not seen → 1.0
- Decays linearly from 1.0 → 0.0 within 5 minutes
- After 5 minutes → 1.0 (fully recovered)

## Properties

- **Deterministic**: same inputs always produce same ranking (no random)
- **Pure function**: no I/O, no database, no AI — independently testable
- **Tie-breaking**: `(score desc, question_id asc)` ensures stable ordering
- **Boundary**: Phase 5 signals only — no mastery values consumed

## Testing

All signals are individually tested in `tests/unit/test_phase5_adaptive.py`.
The `AdaptivePolicy.explain()` method provides full signal decomposition for
observability and test assertions.
