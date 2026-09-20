"""Mastery service facade (Phase 6).

Implements the public business interface for Concept Mastery (module-contracts §M.7):
- Evidence ingestion and idempotent Bayesian Knowledge Tracing updates
- Recompute from immutable evidence trail
- Concept and project-level queries and summaries
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.assessment import service as assessment_service
from app.mastery.calculator import (
    BktParameters,
    compute_bkt_update,
    compute_confidence,
    get_mastery_category,
)
from app.mastery.models import ConceptMastery, MasteryEvent
from app.mastery.repository import MasteryRepository
from app.mastery.schemas import (
    MasteryCategory,
    MasteryEventDto,
    MasteryStateDto,
    MasterySummaryDto,
    RecordEvidenceInput,
)
from app.platform import db as database
from app.platform.config import get_settings
from app.platform.errors import NotFound
from app.platform.ids import uuid7
from app.platform.logging import get_logger

logger = get_logger(__name__)


def _get_bkt_params() -> BktParameters:
    settings = get_settings()
    return BktParameters(
        p_init=settings.MASTERY_P_INIT,
        p_learn=settings.MASTERY_P_LEARN,
        p_guess=settings.MASTERY_P_GUESS,
        p_slip=settings.MASTERY_P_SLIP,
        partial_credit_weight=settings.MASTERY_PARTIAL_CREDIT_WEIGHT,
        easy_weight=settings.MASTERY_EASY_WEIGHT,
        medium_weight=settings.MASTERY_MEDIUM_WEIGHT,
        hard_weight=settings.MASTERY_HARD_WEIGHT,
        confidence_k=settings.MASTERY_CONFIDENCE_K,
    )


def _mastery_to_dto(m: ConceptMastery) -> MasteryStateDto:
    category = get_mastery_category(m.mastery_probability)
    return MasteryStateDto(
        id=m.id,
        project_id=m.project_id,
        concept_id=m.concept_id,
        mastery_probability=round(m.mastery_probability, 4),
        confidence=round(m.confidence, 4),
        category=category,
        evidence_count=m.evidence_count,
        correct_count=m.correct_count,
        incorrect_count=m.incorrect_count,
        partial_count=m.partial_count,
        consecutive_correct=m.consecutive_correct,
        last_evidence_at=m.last_evidence_at,
        algorithm_version=m.algorithm_version,
        updated_at=m.updated_at,
    )


def _event_to_dto(e: MasteryEvent) -> MasteryEventDto:
    return MasteryEventDto(
        id=e.id,
        project_id=e.project_id,
        concept_id=e.concept_id,
        source=e.source,
        source_id=e.source_id,
        mastery_before=round(e.mastery_before, 4),
        mastery_after=round(e.mastery_after, 4),
        confidence_before=round(e.confidence_before, 4),
        confidence_after=round(e.confidence_after, 4),
        result=e.result,
        score=round(e.score, 4),
        difficulty=e.difficulty,
        algorithm_version=e.algorithm_version,
        occurred_at=e.occurred_at,
    )


async def process_quiz_evidence(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    evidence_id: uuid.UUID,
) -> MasteryStateDto | None:
    """Process a completed Phase 5 QuizEvidence row into an updated mastery state.

    Guarantees:
    - Atomicity: Event record and state update commit in the same transaction.
    - Idempotency: Duplicate calls with the same evidence_id produce 0 duplicate updates.
    - Safety: pending_review evidence is rejected.
    """
    params = _get_bkt_params()
    settings = get_settings()

    evidence = await assessment_service.get_quiz_evidence(
        owner_id=owner_id, project_id=project_id, evidence_id=evidence_id
    )
    if evidence is None:
        raise NotFound("Quiz evidence not found in this project")

    # Skip pending_review evidence until resolved
    if evidence.grading_method.value == "pending_review":
        logger.info(
            "skip_pending_review_evidence", extra={"details": {"evidence_id": str(evidence_id)}}
        )
        return None

    concept_id = evidence.concept_id
    if concept_id is None:
        # Concept not attached to question yet
        logger.info(
            "skip_evidence_without_concept",
            extra={"details": {"evidence_id": str(evidence_id)}},
        )
        return None

    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MasteryRepository(session)

        # Check idempotency: has this evidence already been applied to this concept?
        if await repo.is_evidence_processed(
            source=evidence.source or "assessment",
            source_id=evidence.evidence_id,
            concept_id=concept_id,
        ):
            logger.info(
                "evidence_already_processed_idempotent",
                extra={"details": {"evidence_id": str(evidence_id)}},
            )
            existing = await repo.get_concept_mastery(
                project_id=project_id, concept_id=concept_id, owner_id=owner_id
            )
            if existing is not None:
                return _mastery_to_dto(existing)

        # Load or initialize current concept mastery
        current = await repo.get_concept_mastery(
            project_id=project_id, concept_id=concept_id, owner_id=owner_id
        )

        p_before = current.mastery_probability if current else params.p_init
        c_before = current.confidence if current else 0.0

        # Calculate BKT step
        p_after = compute_bkt_update(
            p_current=p_before,
            result=evidence.result,
            score=evidence.score,
            difficulty=evidence.difficulty.value,
            params=params,
        )

        # Update evidence statistics
        ev_count = (current.evidence_count if current else 0) + 1
        corr_count = (current.correct_count if current else 0) + (
            1 if evidence.result == "correct" else 0
        )
        incorr_count = (current.incorrect_count if current else 0) + (
            1 if evidence.result == "incorrect" else 0
        )
        part_count = (current.partial_count if current else 0) + (
            1 if evidence.result == "partial" else 0
        )

        consec_corr = (
            ((current.consecutive_correct if current else 0) + 1)
            if evidence.result == "correct"
            else 0
        )

        # Calculate new confidence
        c_after = compute_confidence(ev_count, k=params.confidence_k)

        mastery_id = current.id if current else uuid7()
        occurred_at = evidence.attempted_at or datetime.now(timezone.utc)

        # 1. Persist or update ConceptMastery first (satisfies FK constraint)
        if current is None:
            mastery_record = await repo.save_concept_mastery(
                mastery_id=mastery_id,
                project_id=project_id,
                concept_id=concept_id,
                owner_id=owner_id,
                mastery_probability=p_after,
                confidence=c_after,
                evidence_count=ev_count,
                correct_count=corr_count,
                incorrect_count=incorr_count,
                partial_count=part_count,
                consecutive_correct=consec_corr,
                last_evidence_at=occurred_at,
                algorithm_version=settings.MASTERY_ALGORITHM_VERSION,
            )
        else:
            mastery_record = await repo.update_concept_mastery(
                current,
                mastery_probability=p_after,
                confidence=c_after,
                evidence_count=ev_count,
                correct_count=corr_count,
                incorrect_count=incorr_count,
                partial_count=part_count,
                consecutive_correct=consec_corr,
                last_evidence_at=occurred_at,
                algorithm_version=settings.MASTERY_ALGORITHM_VERSION,
            )

        # 2. Persist audit event
        event_id = uuid7()
        await repo.save_mastery_event(
            event_id=event_id,
            mastery_id=mastery_id,
            project_id=project_id,
            concept_id=concept_id,
            owner_id=owner_id,
            source=evidence.source or "assessment",
            source_id=evidence.evidence_id,
            mastery_before=p_before,
            mastery_after=p_after,
            confidence_before=c_before,
            confidence_after=c_after,
            result=evidence.result,
            score=evidence.score,
            difficulty=evidence.difficulty.value,
            algorithm_version=settings.MASTERY_ALGORITHM_VERSION,
            occurred_at=occurred_at,
        )

        logger.info(
            "mastery_updated",
            extra={
                "details": {
                    "project_id": str(project_id),
                    "concept_id": str(concept_id),
                    "p_before": p_before,
                    "p_after": p_after,
                    "confidence": c_after,
                }
            },
        )
        return _mastery_to_dto(mastery_record)


async def record_learning_event(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    input_data: RecordEvidenceInput,
) -> MasteryStateDto:
    """Record direct learning evidence and update concept mastery atomically."""
    params = _get_bkt_params()
    settings = get_settings()

    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MasteryRepository(session)

        # Check idempotency
        if await repo.is_evidence_processed(
            source=input_data.source,
            source_id=input_data.source_id,
            concept_id=input_data.concept_id,
        ):
            existing = await repo.get_concept_mastery(
                project_id=project_id, concept_id=input_data.concept_id, owner_id=owner_id
            )
            if existing is not None:
                return _mastery_to_dto(existing)

        current = await repo.get_concept_mastery(
            project_id=project_id, concept_id=input_data.concept_id, owner_id=owner_id
        )

        p_before = current.mastery_probability if current else params.p_init
        c_before = current.confidence if current else 0.0

        p_after = compute_bkt_update(
            p_current=p_before,
            result=input_data.result,
            score=input_data.score,
            difficulty=input_data.difficulty,
            params=params,
        )

        ev_count = (current.evidence_count if current else 0) + 1
        corr_count = (current.correct_count if current else 0) + (
            1 if input_data.result == "correct" else 0
        )
        incorr_count = (current.incorrect_count if current else 0) + (
            1 if input_data.result == "incorrect" else 0
        )
        part_count = (current.partial_count if current else 0) + (
            1 if input_data.result == "partial" else 0
        )
        consec_corr = (
            ((current.consecutive_correct if current else 0) + 1)
            if input_data.result == "correct"
            else 0
        )

        c_after = compute_confidence(ev_count, k=params.confidence_k)

        mastery_id = current.id if current else uuid7()
        occurred_at = input_data.occurred_at or datetime.now(timezone.utc)

        # 1. Persist or update ConceptMastery first (satisfies FK constraint)
        if current is None:
            mastery_record = await repo.save_concept_mastery(
                mastery_id=mastery_id,
                project_id=project_id,
                concept_id=input_data.concept_id,
                owner_id=owner_id,
                mastery_probability=p_after,
                confidence=c_after,
                evidence_count=ev_count,
                correct_count=corr_count,
                incorrect_count=incorr_count,
                partial_count=part_count,
                consecutive_correct=consec_corr,
                last_evidence_at=occurred_at,
                algorithm_version=settings.MASTERY_ALGORITHM_VERSION,
            )
        else:
            mastery_record = await repo.update_concept_mastery(
                current,
                mastery_probability=p_after,
                confidence=c_after,
                evidence_count=ev_count,
                correct_count=corr_count,
                incorrect_count=incorr_count,
                partial_count=part_count,
                consecutive_correct=consec_corr,
                last_evidence_at=occurred_at,
                algorithm_version=settings.MASTERY_ALGORITHM_VERSION,
            )

        # 2. Persist audit event
        event_id = uuid7()
        await repo.save_mastery_event(
            event_id=event_id,
            mastery_id=mastery_id,
            project_id=project_id,
            concept_id=input_data.concept_id,
            owner_id=owner_id,
            source=input_data.source,
            source_id=input_data.source_id,
            mastery_before=p_before,
            mastery_after=p_after,
            confidence_before=c_before,
            confidence_after=c_after,
            result=input_data.result,
            score=input_data.score,
            difficulty=input_data.difficulty,
            algorithm_version=settings.MASTERY_ALGORITHM_VERSION,
            occurred_at=occurred_at,
        )

        return _mastery_to_dto(mastery_record)


async def recompute_mastery(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
) -> MasteryStateDto:
    """Deterministically recompute mastery for a concept from its raw evidence trail."""
    params = _get_bkt_params()
    settings = get_settings()

    evidence_list = await assessment_service.list_evidence_for_concept(
        owner_id=owner_id, project_id=project_id, concept_id=concept_id
    )

    p = params.p_init
    ev_count = 0
    corr_count = 0
    incorr_count = 0
    part_count = 0
    consec_corr = 0
    last_ev_at = None

    for ev in evidence_list:
        if ev.grading_method.value == "pending_review":
            continue

        p = compute_bkt_update(
            p_current=p,
            result=ev.result,
            score=ev.score,
            difficulty=ev.difficulty.value,
            params=params,
        )
        ev_count += 1
        if ev.result == "correct":
            corr_count += 1
            consec_corr += 1
        elif ev.result == "incorrect":
            incorr_count += 1
            consec_corr = 0
        else:
            part_count += 1
            consec_corr = 0
        last_ev_at = ev.attempted_at

    conf = compute_confidence(ev_count, k=params.confidence_k)

    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MasteryRepository(session)

        current = await repo.get_concept_mastery(
            project_id=project_id, concept_id=concept_id, owner_id=owner_id
        )

        if current is None:
            mastery_id = uuid7()
            mastery_record = await repo.save_concept_mastery(
                mastery_id=mastery_id,
                project_id=project_id,
                concept_id=concept_id,
                owner_id=owner_id,
                mastery_probability=p,
                confidence=conf,
                evidence_count=ev_count,
                correct_count=corr_count,
                incorrect_count=incorr_count,
                partial_count=part_count,
                consecutive_correct=consec_corr,
                last_evidence_at=last_ev_at,
                algorithm_version=settings.MASTERY_ALGORITHM_VERSION,
            )
        else:
            mastery_record = await repo.update_concept_mastery(
                current,
                mastery_probability=p,
                confidence=conf,
                evidence_count=ev_count,
                correct_count=corr_count,
                incorrect_count=incorr_count,
                partial_count=part_count,
                consecutive_correct=consec_corr,
                last_evidence_at=last_ev_at,
                algorithm_version=settings.MASTERY_ALGORITHM_VERSION,
            )

        return _mastery_to_dto(mastery_record)


async def get_concept_mastery(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
) -> MasteryStateDto | None:
    """Retrieve current mastery state for a single concept."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MasteryRepository(session)
        record = await repo.get_concept_mastery(
            project_id=project_id, concept_id=concept_id, owner_id=owner_id
        )
        if record is None:
            return None
        return _mastery_to_dto(record)


async def get_project_mastery(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
) -> list[MasteryStateDto]:
    """Retrieve mastery states for all concepts in a project."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MasteryRepository(session)
        records = await repo.list_project_mastery(project_id=project_id, owner_id=owner_id)
        return [_mastery_to_dto(r) for r in records]


async def get_mastery_summary(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    concept_ids: list[uuid.UUID] | None = None,
) -> MasterySummaryDto:
    """Compute aggregate mastery summary for a project."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MasteryRepository(session)
        records = await repo.list_project_mastery(project_id=project_id, owner_id=owner_id)

        if concept_ids:
            target_ids = set(concept_ids)
            records = [r for r in records if r.concept_id in target_ids]

        dtos = [_mastery_to_dto(r) for r in records]
        avg_mastery = sum(d.mastery_probability for d in dtos) / len(dtos) if dtos else 0.0

        # Attention concepts: low mastery (< 0.40) or low confidence (< 0.50)
        attention = [
            d.concept_id
            for d in dtos
            if d.category == MasteryCategory.DEVELOPING or d.confidence < 0.50
        ]

        return MasterySummaryDto(
            project_id=project_id,
            concepts=dtos,
            attention_concepts=attention,
            average_mastery=round(avg_mastery, 4),
            generated_at=datetime.now(timezone.utc),
        )


async def get_evidence_trail(
    *,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    concept_id: uuid.UUID,
    limit: int = 100,
) -> list[MasteryEventDto]:
    """Retrieve immutable audit trail of mastery events for a concept."""
    async with database.session_scope(user_id=str(owner_id), project_id=str(project_id)) as session:
        repo = MasteryRepository(session)
        events = await repo.list_mastery_events(
            project_id=project_id,
            concept_id=concept_id,
            owner_id=owner_id,
            limit=limit,
        )
        return [_event_to_dto(e) for e in events]
