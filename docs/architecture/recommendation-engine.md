# Recommendation Engine Architecture (Phase 8)

## 1. Objective & Scope
The Recommendation Engine converts structured learner evidence from **Mastery (Phase 6)** and **Growth (Phase 7)** into explainable, actionable, project-scoped study tasks.

> **Disclaimer**: Recommendation scores and priority thresholds are configurable deterministic heuristics and are not scientifically validated measures of learner behavior or educational effectiveness.

---

## 2. Architectural Pipeline

```text
[Assessment Domain] (Phase 5)
       ↓
[Mastery Domain] (Phase 6 - BKT Probability + Confidence)
       ↓
[Growth Domain] (Phase 7 - Trends + Attention Score)
       ↓
[Recommendation Engine] (Phase 8)
   ├── 1. Candidate Generation (ConceptContext)
   ├── 2. Multi-Signal Scoring (Weakness, Decline, Failures, Uncertainty, Materials)
   ├── 3. Eligibility & Constraint Filtering
   ├── 4. Deduplication & Cooldown Penalty (24hr window)
   ├── 5. Stable Tie-Break Ranking (Top-K = 5)
   └── 6. Atomic Persistence & Lifecycle Tracking (PostgreSQL RLS)
```

---

## 3. Recommendation Taxonomy

| Type | Action Type | Preconditions | Intended Action |
| :--- | :--- | :--- | :--- |
| `REVISIT_MATERIAL` | `open_material` | Material available + (Mastery < 0.75 or Decline) | Directs learner to study specific project documents |
| `REVIEW_MISTAKES` | `review_quiz_attempts` | Recent failure rate $\ge 30\%$ | Guides learner through recent erroneous attempts |
| `PRACTICE_CONCEPT` | `start_practice_quiz` | Mastery < 0.80 or Confidence < 0.60 | Generates targeted practice quiz |
| `REVIEW_CONCEPT` | `view_concept_summary` | Mastery < 0.60, No material available | Directs learner to high-level concept summary |
| `CONTINUE_PROGRESS`| `start_next_module` | Mastery $\ge 0.70$ and Improving | Encourages advancing to new concepts |
| `TAKE_ASSESSMENT` | `take_diagnostic_quiz`| Cold start (0 prior evidence) | Suggests initial diagnostic assessment |

---

## 4. Mathematical Scoring Model

$$\text{PriorityScore} = \text{clamp}_{[0, 1]}\left( w_w \cdot S_w + w_d \cdot S_d + w_f \cdot S_f + w_u \cdot S_u + w_m \cdot S_m - P_{rec} \cdot S_{rec} \right)$$

### Default Configured Weights:
- $w_w = 0.30$ (Weakness factor: $(1 - \text{Mastery}) \times \text{Confidence}$)
- $w_d = 0.25$ (Decline factor: $\max(0, -2 \times \Delta_{ST})$)
- $w_f = 0.20$ (Recent failure rate $\in [0, 1]$)
- $w_u = 0.10$ (Uncertainty / low confidence: $1 - \text{Confidence}$)
- $w_m = 0.15$ (Material availability: $1.0$ if project material present)
- $P_{rec} = 0.40$ (Cooldown penalty if recommended in last 24 hours)

### Priority Levels:
- **HIGH**: $\text{Score} \ge 0.70$
- **MEDIUM**: $0.40 \le \text{Score} < 0.70$
- **LOW**: $\text{Score} < 0.40$

---

## 5. Lifecycle State Machine

```text
       ┌──────────────┐
       │   PENDING    │
       └──────┬───────┘
              │
    ┌─────────┼─────────┐
    │         │         │
    ▼         ▼         ▼
┌───────┐ ┌───────┐ ┌───────────┐
│VIEWED │ │STARTED│ │ DISMISSED │
└───┬───┘ └───┬───┘ └───────────┘
    │         │
    └────┬────┘
         ▼
  ┌─────────────┐
  │  COMPLETED  │
  └─────────────┘
```

Transitions are strictly validated via `is_valid_status_transition()`.

---

## 6. Security & Multi-Tenancy
- **PostgreSQL RLS**: `recommendations` and `recommendation_feedback` enforce `owner_id = app_user_id()`.
- **Cross-Project Isolation**: Queries verify ownership at service and database levels. Non-owned resources return `404 Not Found`.
