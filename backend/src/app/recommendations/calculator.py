"""Pure mathematical Recommendation Engine calculator (Phase 8).

Implements deterministic candidate generation, multi-signal scoring,
constraint filtering, deduplication, cooldown penalties, and stable ranking.
Contains ZERO database, network, or AI dependencies.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class RecommendationType(str, Enum):
    REVIEW_CONCEPT = "REVIEW_CONCEPT"
    PRACTICE_CONCEPT = "PRACTICE_CONCEPT"
    REVISIT_MATERIAL = "REVISIT_MATERIAL"
    TAKE_ASSESSMENT = "TAKE_ASSESSMENT"
    REVIEW_MISTAKES = "REVIEW_MISTAKES"
    CONTINUE_PROGRESS = "CONTINUE_PROGRESS"


class RecommendationPriorityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationStatus(str, Enum):
    PENDING = "PENDING"
    VIEWED = "VIEWED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    DISMISSED = "DISMISSED"
    EXPIRED = "EXPIRED"


VALID_STATUS_TRANSITIONS: dict[RecommendationStatus, set[RecommendationStatus]] = {
    RecommendationStatus.PENDING: {
        RecommendationStatus.VIEWED,
        RecommendationStatus.STARTED,
        RecommendationStatus.COMPLETED,
        RecommendationStatus.DISMISSED,
        RecommendationStatus.EXPIRED,
    },
    RecommendationStatus.VIEWED: {
        RecommendationStatus.STARTED,
        RecommendationStatus.COMPLETED,
        RecommendationStatus.DISMISSED,
        RecommendationStatus.EXPIRED,
    },
    RecommendationStatus.STARTED: {
        RecommendationStatus.COMPLETED,
        RecommendationStatus.DISMISSED,
        RecommendationStatus.EXPIRED,
    },
    RecommendationStatus.COMPLETED: set(),
    RecommendationStatus.DISMISSED: set(),
    RecommendationStatus.EXPIRED: set(),
}


def is_valid_status_transition(current: RecommendationStatus, target: RecommendationStatus) -> bool:
    """Validate lifecycle state machine transition."""
    if current == target:
        return True
    return target in VALID_STATUS_TRANSITIONS.get(current, set())


class ReasonCode(str, Enum):
    LOW_MASTERY = "LOW_MASTERY"
    DECLINING_TREND = "DECLINING_TREND"
    HIGH_ATTENTION = "HIGH_ATTENTION"
    RECENT_FAILURES = "RECENT_FAILURES"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INSUFFICIENT_PRACTICE = "INSUFFICIENT_PRACTICE"
    STRONG_PROGRESS = "STRONG_PROGRESS"
    MATERIAL_AVAILABLE = "MATERIAL_AVAILABLE"
    RECENTLY_RECOMMENDED = "RECENTLY_RECOMMENDED"
    COLD_START = "COLD_START"


@dataclass(frozen=True)
class RecommendationParameters:
    """Configurable weights and limits for recommendation scoring and ranking."""

    top_k: int = 5
    cooldown_hours: int = 24
    weight_weakness: float = 0.30
    weight_decline: float = 0.25
    weight_failures: float = 0.20
    weight_low_conf: float = 0.10
    weight_material: float = 0.15
    penalty_recent_rec: float = 0.40
    threshold_high: float = 0.60
    threshold_medium: float = 0.35


DEFAULT_REC_PARAMS = RecommendationParameters()


@dataclass(frozen=True)
class ConceptContext:
    """Input evidence snapshot for a concept in a project."""

    concept_id: uuid.UUID
    mastery_probability: float
    confidence: float
    growth_trend: str  # "improving", "stable", "declining", "insufficient_data"
    short_term_delta: float
    recent_failure_rate: float
    attention_required: bool
    material_ids: list[uuid.UUID] = field(default_factory=list)
    material_titles: list[str] = field(default_factory=list)
    recently_recommended: bool = False
    mastery_state_id: uuid.UUID | None = None
    growth_state_id: uuid.UUID | None = None
    recent_evidence_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass(frozen=True)
class ScoredRecommendationCandidate:
    """A scored, ranked, and fully structured recommendation candidate."""

    concept_id: uuid.UUID | None
    recommendation_type: RecommendationType
    title: str
    description: str
    priority_score: float
    priority_level: RecommendationPriorityLevel
    reason_codes: list[ReasonCode]
    evidence_refs: dict[str, str | list[str] | float | int]
    action_type: str
    action_target: str | None


def score_candidate(
    ctx: ConceptContext,
    candidate_type: RecommendationType,
    params: RecommendationParameters = DEFAULT_REC_PARAMS,
) -> tuple[float, RecommendationPriorityLevel, list[ReasonCode]]:
    """Compute deterministic priority score, priority level, and reason codes."""
    reason_codes: list[ReasonCode] = []

    # 1. Weakness signal: (1 - mastery) * confidence
    weakness_factor = max(0.0, min(1.0, (1.0 - ctx.mastery_probability) * ctx.confidence))
    if ctx.mastery_probability < 0.60:
        reason_codes.append(ReasonCode.LOW_MASTERY)

    # 2. Decline signal
    if ctx.growth_trend == "declining":
        decline_factor = max(0.0, min(1.0, -ctx.short_term_delta * 2.0))
        reason_codes.append(ReasonCode.DECLINING_TREND)
    else:
        decline_factor = 0.0

    # 3. Recent failures
    failure_factor = max(0.0, min(1.0, ctx.recent_failure_rate))
    if ctx.recent_failure_rate > 0.0:
        reason_codes.append(ReasonCode.RECENT_FAILURES)

    # 4. Low confidence
    low_conf_factor = max(0.0, min(1.0, 1.0 - ctx.confidence))
    if ctx.confidence < 0.40:
        reason_codes.append(ReasonCode.LOW_CONFIDENCE)

    # 5. Attention required
    if ctx.attention_required:
        reason_codes.append(ReasonCode.HIGH_ATTENTION)

    # 6. Material availability
    has_materials = len(ctx.material_ids) > 0
    material_factor = 1.0 if has_materials else 0.0
    if has_materials:
        reason_codes.append(ReasonCode.MATERIAL_AVAILABLE)

    # 7. Strong progress
    if ctx.growth_trend == "improving" and ctx.mastery_probability >= 0.70:
        reason_codes.append(ReasonCode.STRONG_PROGRESS)

    # 8. Penalty for recently recommended
    penalty_factor = 1.0 if ctx.recently_recommended else 0.0
    if ctx.recently_recommended:
        reason_codes.append(ReasonCode.RECENTLY_RECOMMENDED)

    # Adjust weights depending on recommendation type focus
    raw_score = (
        params.weight_weakness * weakness_factor
        + params.weight_decline * decline_factor
        + params.weight_failures * failure_factor
        + params.weight_low_conf * low_conf_factor
        + params.weight_material * material_factor
        - params.penalty_recent_rec * penalty_factor
    )

    # Boost score slightly for targeted remediation type
    if candidate_type == RecommendationType.REVIEW_MISTAKES:
        raw_score += 0.10 * failure_factor
    elif candidate_type == RecommendationType.REVISIT_MATERIAL and has_materials:
        raw_score += 0.05

    priority_score = round(max(0.0, min(1.0, raw_score)), 4)

    if priority_score >= params.threshold_high:
        priority_level = RecommendationPriorityLevel.HIGH
    elif priority_score >= params.threshold_medium:
        priority_level = RecommendationPriorityLevel.MEDIUM
    else:
        priority_level = RecommendationPriorityLevel.LOW

    return priority_score, priority_level, reason_codes


def generate_candidates_for_concept(
    ctx: ConceptContext,
    params: RecommendationParameters = DEFAULT_REC_PARAMS,
) -> list[ScoredRecommendationCandidate]:
    """Generate all eligible recommendation candidates for a given concept context."""
    candidates: list[ScoredRecommendationCandidate] = []
    has_materials = len(ctx.material_ids) > 0

    # Case 1: Strong and stable with no attention required -> no remediation needed
    if (
        ctx.mastery_probability >= 0.85
        and ctx.growth_trend in ("stable", "improving")
        and ctx.recent_failure_rate == 0.0
        and not ctx.attention_required
    ):
        return []

    # Candidate 1: REVISIT_MATERIAL (only if material is actually available)
    if has_materials and (ctx.mastery_probability < 0.75 or ctx.growth_trend == "declining"):
        score, level, reasons = score_candidate(ctx, RecommendationType.REVISIT_MATERIAL, params)
        target_mat_id = str(ctx.material_ids[0])
        mat_title = ctx.material_titles[0] if ctx.material_titles else "Relevant Study Material"
        candidates.append(
            ScoredRecommendationCandidate(
                concept_id=ctx.concept_id,
                recommendation_type=RecommendationType.REVISIT_MATERIAL,
                title=f"Revisit study material: {mat_title}",
                description=f"Review '{mat_title}' to reinforce foundational understanding (current mastery: {ctx.mastery_probability:.2f}).",
                priority_score=score,
                priority_level=level,
                reason_codes=reasons,
                evidence_refs={
                    "concept_id": str(ctx.concept_id),
                    "material_id": target_mat_id,
                    "mastery_probability": ctx.mastery_probability,
                    "confidence": ctx.confidence,
                    "growth_trend": ctx.growth_trend,
                },
                action_type="open_material",
                action_target=target_mat_id,
            )
        )

    # Candidate 2: REVIEW_MISTAKES (if recent failures occurred)
    if ctx.recent_failure_rate >= 0.30:
        score, level, reasons = score_candidate(ctx, RecommendationType.REVIEW_MISTAKES, params)
        candidates.append(
            ScoredRecommendationCandidate(
                concept_id=ctx.concept_id,
                recommendation_type=RecommendationType.REVIEW_MISTAKES,
                title="Review recent assessment mistakes",
                description=f"Analyze recent incorrect attempts (recent failure rate: {int(ctx.recent_failure_rate * 100)}%) to identify misconceptions.",
                priority_score=score,
                priority_level=level,
                reason_codes=reasons,
                evidence_refs={
                    "concept_id": str(ctx.concept_id),
                    "recent_failure_rate": ctx.recent_failure_rate,
                    "evidence_ids": [str(e) for e in ctx.recent_evidence_ids],
                },
                action_type="review_quiz_attempts",
                action_target=str(ctx.concept_id),
            )
        )

    # Candidate 3: PRACTICE_CONCEPT (if practice is needed to build confidence/mastery)
    if ctx.mastery_probability < 0.80 or ctx.confidence < 0.60:
        score, level, reasons = score_candidate(ctx, RecommendationType.PRACTICE_CONCEPT, params)
        candidates.append(
            ScoredRecommendationCandidate(
                concept_id=ctx.concept_id,
                recommendation_type=RecommendationType.PRACTICE_CONCEPT,
                title="Practice concept exercises",
                description=f"Take a targeted practice quiz to strengthen mastery (current: {ctx.mastery_probability:.2f}, confidence: {ctx.confidence:.2f}).",
                priority_score=score,
                priority_level=level,
                reason_codes=reasons,
                evidence_refs={
                    "concept_id": str(ctx.concept_id),
                    "mastery_probability": ctx.mastery_probability,
                    "confidence": ctx.confidence,
                },
                action_type="start_practice_quiz",
                action_target=str(ctx.concept_id),
            )
        )

    # Candidate 4: REVIEW_CONCEPT (general conceptual review)
    if not has_materials and (ctx.mastery_probability < 0.60 or ctx.growth_trend == "declining"):
        score, level, reasons = score_candidate(ctx, RecommendationType.REVIEW_CONCEPT, params)
        candidates.append(
            ScoredRecommendationCandidate(
                concept_id=ctx.concept_id,
                recommendation_type=RecommendationType.REVIEW_CONCEPT,
                title="Review concept fundamentals",
                description=f"Focus study time on this concept (mastery: {ctx.mastery_probability:.2f}, trend: {ctx.growth_trend}).",
                priority_score=score,
                priority_level=level,
                reason_codes=reasons,
                evidence_refs={
                    "concept_id": str(ctx.concept_id),
                    "mastery_probability": ctx.mastery_probability,
                    "growth_trend": ctx.growth_trend,
                },
                action_type="view_concept_summary",
                action_target=str(ctx.concept_id),
            )
        )

    return candidates


def rank_and_filter_recommendations(
    candidates: list[ScoredRecommendationCandidate],
    top_k: int = DEFAULT_REC_PARAMS.top_k,
) -> list[ScoredRecommendationCandidate]:
    """Sort candidates by priority score descending with deterministic tie-breaking.

    Tie-break order:
    1. priority_score DESC
    2. priority_level (HIGH > MEDIUM > LOW)
    3. concept_id (str) ASC
    4. recommendation_type (str) ASC
    """
    level_order = {
        RecommendationPriorityLevel.HIGH: 3,
        RecommendationPriorityLevel.MEDIUM: 2,
        RecommendationPriorityLevel.LOW: 1,
    }

    def sort_key(c: ScoredRecommendationCandidate) -> tuple:
        return (
            -c.priority_score,
            -level_order.get(c.priority_level, 0),
            str(c.concept_id or ""),
            c.recommendation_type.value,
        )

    sorted_candidates = sorted(candidates, key=sort_key)

    # Deduplicate: Keep the single highest-priority recommendation per concept
    seen_concepts: set[uuid.UUID] = set()
    filtered: list[ScoredRecommendationCandidate] = []

    for c in sorted_candidates:
        if c.concept_id is not None:
            if c.concept_id in seen_concepts:
                continue
            seen_concepts.add(c.concept_id)
        filtered.append(c)

        if len(filtered) >= top_k:
            break

    return filtered
