# Phase 7 — Concept Growth Engine Architecture

## 1. Overview

The **Growth Engine** operates downstream of the Mastery Engine to track, classify, and explain learner progression trajectories over time.

```text
Phase 5 Assessment (Quiz / Question Attempt)
                ↓
           quiz_evidence
                ↓
     Mastery Engine (BKT Posterior)
                ↓
       concept_mastery & mastery_events
                ↓
     Growth Engine (Trend & Attention Analysis)
                ↓
       concept_growth & growth_events
                ↓
     Future Recommendation Engine (Phase 8+)
```

### Core Separation: Mastery vs. Growth
- **Mastery** answers: *"How confident are we that the learner knows this concept right now?"*
- **Growth** answers: *"How is this learner's knowledge changing over time, where are they struggling, and what areas require attention?"*

A learner with $p = 0.42$ who progressed from $0.20 \rightarrow 0.35 \rightarrow 0.42$ has an **IMPROVING** trend despite current low mastery. Conversely, a learner with $p = 0.65$ who dropped from $0.85 \rightarrow 0.75 \rightarrow 0.65$ has a **DECLINING** trend despite moderate mastery.

---

## 2. Mathematical & Classification Model

### Configurable Baseline Parameters

| Parameter | Default | Description |
|---|---|---|
| `GROWTH_MIN_OBSERVATIONS` | `2` | Minimum history points required before computing a trend |
| `GROWTH_STABILITY_DELTA` | `0.05` | Threshold band for stable classification ($|\Delta p| \le 0.05$) |
| `GROWTH_SIGNIFICANT_DELTA` | `0.10` | Threshold indicating substantial movement |
| `GROWTH_SHORT_TERM_WINDOW` | `3` | Number of recent observations for short-term trend |
| `GROWTH_LONG_TERM_WINDOW` | `10` | Number of observations for long-term baseline trajectory |
| `GROWTH_ATTENTION_THRESHOLD` | `0.50` | Cutoff score triggering `attention_required = True` |
| `GROWTH_ATTENTION_WEIGHT_WEAKNESS` | `0.40` | Weight for weakness factor |
| `GROWTH_ATTENTION_WEIGHT_DECLINE` | `0.30` | Weight for recent decline factor |
| `GROWTH_ATTENTION_WEIGHT_MISTAKES` | `0.30` | Weight for recent failure rate |
| `GROWTH_ATTENTION_WEIGHT_INACTIVITY` | `0.00` | Weight for inactivity factor (`ACTIVITY SIGNAL DEFERRED`) |
| `GROWTH_ALGORITHM_VERSION` | `"growth-1.0"` | Current algorithm version identifier |

> [!NOTE]
> Growth thresholds and attention weights are configurable baseline heuristics and are not empirically validated clinical or psychometric measurements.

---

### Trend Classifications

1. **`IMPROVING`**: Net mastery change $\Delta p > \text{stability\_delta}$.
2. **`DECLINING`**: Net mastery change $\Delta p < -\text{stability\_delta}$.
3. **`STABLE`**: Net mastery change $|\Delta p| \le \text{stability\_delta}$.
4. **`INSUFFICIENT_DATA`**: History length $N < \text{min\_observations}$.

### Short-Term vs. Long-Term Windows
Both signals are evaluated and preserved independently:
- **`short_term_trend`**: Computed over the last $K_{short}$ observations ($\le 3$).
- **`long_term_trend`**: Computed over the last $K_{long}$ observations ($\le 10$).
- **`trend`** (primary): Reflects the long-term trajectory if sufficient observations exist, falling back to short-term.

---

### Multi-Factor Attention Formula

The Attention Score $\in [0.0, 1.0]$ combines multi-dimensional indicators:

$$\text{attention\_score} = \text{clamp}(w_{weakness} \cdot F_{weakness} + w_{decline} \cdot F_{decline} + w_{mistakes} \cdot F_{mistakes} + w_{inactivity} \cdot F_{inactivity}, 0.0, 1.0)$$

Where:
- **Weakness Factor ($F_{weakness}$)**: $(1.0 - \text{mastery}) \cdot \text{confidence}$. A high-confidence low-mastery concept produces a high weakness signal.
- **Decline Factor ($F_{decline}$)**: $\text{clamp}(-2.0 \cdot \Delta p_{short}, 0.0, 1.0)$ if $\Delta p_{short} < 0$, else $0.0$.
- **Mistake Factor ($F_{mistakes}$)**: Fraction of recent attempts with `incorrect` or `partial` results.
- **Inactivity Factor ($F_{inactivity}$)**: Documented as `ACTIVITY SIGNAL DEFERRED` (default $0.0$).

#### Attention Level Classification
- $\text{score} \ge 0.60 \implies \text{HIGH}$
- $0.30 \le \text{score} < 0.60 \implies \text{MEDIUM}$
- $\text{score} < 0.30 \implies \text{LOW}$
- $\text{attention\_required} = \text{True}$ if $\text{score} \ge 0.50$ or $\text{level} == \text{HIGH}$.

---

## 3. Database Schema & RLS

### Tables

1. **`concept_growth`**: Current trajectory and attention metrics per `(project_id, concept_id)`.
   - Unique constraint: `(project_id, concept_id)`
   - Checks: `current_mastery`, `confidence`, `attention_score` bounded in $[0.0, 1.0]$.
   - Trigger: `trg_concept_growth_touch_updated_at`.

2. **`growth_events`**: Immutable audit log of trajectory evaluations.
   - Unique constraint: `(project_id, concept_id, source_mastery_event_id)` for atomic idempotency.

### Row-Level Security
Both tables strictly enforce isolation to the resource owner:
```sql
CREATE POLICY concept_growth_all_access ON concept_growth
FOR ALL TO studycompanion_runtime
USING (owner_id = app_user_id())
WITH CHECK (owner_id = app_user_id());
```

---

## 4. Idempotency & Concurrency

- **Idempotency**: Processing the same `source_mastery_event_id` hits the unique constraint on `(project_id, concept_id, source_mastery_event_id)`. The service returns the existing growth state with zero state mutation.
- **Concurrency**: Concurrent worker invocations are serialized safely via PostgreSQL unique constraints and transaction boundaries.
