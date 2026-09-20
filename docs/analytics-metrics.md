# Analytics Metric Definitions & Formulas (Phase 9)

This document establishes the authoritative definitions, data sources, time windows, and mathematical formulas for all learner progress metrics.

---

## 1. Activity & Engagement Metrics

### 1.1 Active Days
- **Definition**: Number of distinct UTC calendar days containing at least one recorded learning event within the time window.
- **Formula**: $\text{COUNT}(\text{DISTINCT } \text{DATE}(\text{occurred\_at}))$
- **Source**: `analytics_events` table.
- **Null/Zero Behavior**: Returns `0` if no events occurred.

### 1.2 Total Study Events
- **Definition**: Total count of all learning events within the time window.
- **Formula**: $\text{COUNT}(\text{event\_id})$
- **Source**: `analytics_events` table.
- **Null/Zero Behavior**: Returns `0`.

---

## 2. Tutor & Grounding Metrics

### 2.1 Conversations & Messages
- **Definition**: Total distinct tutor conversations and total user/assistant messages within the time window.
- **Source**: `tutor_service.list_conversations` and `tutor_service.get_messages`.

### 2.2 Grounded Response Rate
- **Definition**: Proportion of assistant responses that were verified grounded against retrieved material citations vs total assistant responses.
- **Formula**:
  $$\text{GroundedRate} = \begin{cases} \frac{\text{GroundedResponses}}{\text{GroundedResponses} + \text{InsufficientEvidenceResponses}}, & \text{if Denominator} > 0 \\ 0.0, & \text{otherwise} \end{cases}$$
- **Source**: `tutor_service`.
- **Null/Zero Behavior**: Returns `0.0`.

---

## 3. Assessment & Accuracy Metrics

### 3.1 Question Accuracy
- **Definition**: Proportion of correct question attempts over all graded attempts (excluding `pending_review`).
- **Formula**:
  $$\text{Accuracy} = \begin{cases} \frac{\text{CorrectAttempts}}{\text{CorrectAttempts} + \text{IncorrectAttempts}}, & \text{if Denominator} > 0 \\ 0.0, & \text{otherwise} \end{cases}$$
- **Source**: `assessment_service.get_assessment_history`.

### 3.2 Quiz Completion Rate
- **Definition**: Proportion of started quizzes that were completed.
- **Formula**:
  $$\text{CompletionRate} = \begin{cases} \frac{\text{CompletedQuizzes}}{\text{StartedQuizzes}}, & \text{if StartedQuizzes} > 0 \\ 0.0, & \text{otherwise} \end{cases}$$
- **Source**: `assessment_service`.

---

## 4. Mastery Distribution Metrics

Concepts are categorized into cognitive tiers based on BKT mastery probability $p$:
- **Developing**: $p < 0.50$
- **Progressing**: $0.50 \le p < 0.85$
- **Mastered**: $p \ge 0.85$
- **Source**: `mastery_service.get_project_mastery`.

---

## 5. Growth Trajectory Metrics

Concepts are categorized based on trajectory trend and attention flags:
- **Improving**: Positive short-term & long-term delta ($\Delta \ge +0.05$).
- **Stable**: Minimal delta ($|\Delta| < 0.05$).
- **Declining**: Negative short-term delta ($\Delta \le -0.05$).
- **Attention Required**: Attention score $\ge 0.50$.
- **Source**: `growth_service.get_project_growth`.

---

## 6. Recommendation Funnel Metrics

Tracks the distribution of generated recommendations across lifecycle states:
- `PENDING`, `VIEWED`, `STARTED`, `COMPLETED`, `DISMISSED`.
- **Completion Rate**:
  $$\text{RecCompletionRate} = \begin{cases} \frac{\text{Completed}}{\text{TotalGenerated}}, & \text{if TotalGenerated} > 0 \\ 0.0, & \text{otherwise} \end{cases}$$
- **Source**: `recommendation_service.get_active_recommendations`.
