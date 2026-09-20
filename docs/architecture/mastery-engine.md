# Phase 6 — Concept Mastery Engine Architecture

## 1. Overview

The **Mastery Engine** converts structured learning evidence produced by Phase 5 Assessment into a persistent, mathematically sound, and explainable mastery state for each `(project, concept)` tuple.

```text
Phase 5 Assessment (Quiz / Question Attempt)
                ↓
           quiz_evidence
                ↓
    Mastery Service / Job Processing
                ↓
    Pure BKT Calculator (No DB, No LLM)
                ↓
      concept_mastery & mastery_events (DB + RLS)
                ↓
    Future Growth & Recommendation Engines (Phase 7+)
```

---

## 2. Mathematical Model (Bayesian Knowledge Tracing)

The engine uses a deterministic 4-parameter Bayesian Knowledge Tracing (BKT) formulation with continuous partial-credit interpolation, symmetric difficulty weighting, and evidence-volume confidence saturation.

### Configurable Baseline Parameters

| Parameter | Default | Description |
|---|---|---|
| $P_{init}$ | `0.20` | Prior probability that a concept is mastered upon first encounter |
| $P_{learn}$ | `0.10` | Transition probability from unmastered to mastered per learning opportunity |
| $P_{guess}$ | `0.20` | Probability of answering correctly given the concept is NOT mastered |
| $P_{slip}$ | `0.10` | Probability of answering incorrectly given the concept IS mastered |
| $w_{partial}$ | `0.50` | Default score weight for partial credit responses when score is unspecified |
| $w_{easy}$ | `0.80` | Difficulty evidence multiplier for easy questions |
| $w_{medium}$ | `1.00` | Difficulty evidence multiplier for medium questions |
| $w_{hard}$ | `1.20` | Difficulty evidence multiplier for hard questions |
| $k$ | `5.0` | Saturation constant for confidence calculation |

> [!NOTE]
> Current BKT parameters are configurable baseline assumptions and have not yet been empirically calibrated against a sufficiently large learner dataset.

---

### Update Formulas

#### 1. Binary Observations

- **Correct Response ($s = 1.0$)**:
  $$P(\text{mastered} \mid \text{correct}) = \frac{p \cdot (1 - P_{slip})}{p \cdot (1 - P_{slip}) + (1 - p) \cdot P_{guess}}$$
  $$p_{next} = P(\text{mastered} \mid \text{correct}) + (1 - P(\text{mastered} \mid \text{correct})) \cdot P_{learn}$$

- **Incorrect Response ($s = 0.0$)**:
  $$P(\text{mastered} \mid \text{incorrect}) = \frac{p \cdot P_{slip}}{p \cdot P_{slip} + (1 - p) \cdot (1 - P_{guess})}$$
  $$p_{next} = P(\text{mastered} \mid \text{incorrect}) + (1 - P(\text{mastered} \mid \text{incorrect})) \cdot P_{learn}$$

#### 2. Partial Credit Interpolation ($0 < s < 1$)

When grading yields a fractional score $s \in (0, 1)$, the posterior is computed as a linear convex combination of the incorrect and correct posteriors:
$$P_{obs} = (1 - s) \cdot P(\text{mastered} \mid \text{incorrect}) + s \cdot P(\text{mastered} \mid \text{correct})$$
$$p_{next} = P_{obs} + (1 - P_{obs}) \cdot P_{learn}$$

#### 3. Difficulty Weighting

Difficulty modulates the step change $\Delta p = p_{next} - p_{old}$:
- When $\Delta p \ge 0$ (gain): $\Delta p_{weighted} = \Delta p \cdot w_d$
- When $\Delta p < 0$ (drop): $\Delta p_{weighted} = \Delta p \cdot (2.0 - w_d)$
- Clamped strictly: $p_{final} = \text{clamp}(p_{old} + \Delta p_{weighted}, 0.001, 0.999)$

This guarantees that:
- Passing a **hard** question gives higher reward than passing an easy question.
- Failing an **easy** question penalizes more than failing a hard question.

#### 4. Confidence Saturation Formula

Confidence represents the volume and quality of evidence collected, bounded strictly within $[0, 1]$:
$$\text{confidence} = 1 - e^{-\frac{n_{eff}}{k}}$$
where $n_{eff}$ is the effective count of completed evidence events.

---

## 3. Database & RLS Model

### Schema Design

1. **`concept_mastery`**: Holds current state for each `(project_id, concept_id)`.
   - Primary key: `id` (UUIDv7)
   - Unique key: `(project_id, concept_id)`
   - Checks: `mastery_probability BETWEEN 0 AND 1`, `confidence BETWEEN 0 AND 1`
   - Trigger: `trg_concept_mastery_touch_updated_at`

2. **`mastery_events`**: Immutable audit trail for every BKT transition.
   - Primary key: `id` (UUIDv7)
   - Unique key: `(source, source_id, concept_id)` $\rightarrow$ **Durable Idempotency Anchor**
   - Stores `mastery_before`, `mastery_after`, `confidence_before`, `confidence_after`, `result`, `score`, `difficulty`, `occurred_at`.

### RLS Policies
Both tables enforce row-level security:
```sql
CREATE POLICY concept_mastery_all_access ON concept_mastery
FOR ALL TO studycompanion_runtime
USING (owner_id = app_user_id())
WITH CHECK (owner_id = app_user_id());
```

---

## 4. Idempotency & Concurrency Strategy

- **Idempotency**: Processing the same evidence multiple times (whether synchronously or via retryable worker jobs) hits the unique constraint on `(source, source_id, concept_id)` in `mastery_events`. The repository returns the existing mastery state with zero state mutation or count inflation.
- **Pending Review Safety**: Evidence flagged as `pending_review` is ignored until final AI grading or manual review resolves it.
- **Recomputation**: The entire concept state can be rebuilt purely from the chronological evidence trail via `recompute_mastery`.
