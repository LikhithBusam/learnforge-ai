"""Infrastructure-level tasks — Phase 0 only.

No document processing or learning workflows here (phase boundary). Tasks
accept the standard envelope (context) so correlation/ownership propagation
is exercised exactly as real workflows will use it.

Phase 10: every task records a JobExecutionRecord in admin_session_scope via
``_record_telemetry``. The call is fire-and-forget — DB unavailability must
never prevent task outcome propagation.
"""

from __future__ import annotations

import time

from app.jobs.celery_app import make_celery_app
from app.platform.asyncio_utils import run_coroutine_sync
from app.platform.config import get_settings
from app.platform.context import ContextSnapshot
from app.platform.logging import get_logger

logger = get_logger(__name__)

_settings = get_settings()
celery_app = make_celery_app(_settings.CELERY_BROKER_URL, _settings.CELERY_RESULT_BACKEND)


def _record_telemetry(
    *,
    task_name: str,
    queue: str,
    status: str,
    duration_ms: int,
    attempt: int = 1,
    correlation_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Fire-and-forget job execution telemetry — never raises (Phase 10)."""
    try:
        from app.admin import service as admin_service

        async def _record():
            await admin_service.record_job_execution(
                task_name=task_name,
                queue=queue,
                status=status,
                duration_ms=duration_ms,
                attempt=attempt,
                correlation_id=correlation_id,
                error_message=error_message,
            )

        run_coroutine_sync(_record)
    except Exception as exc:  # noqa: BLE001 - telemetry must never break task
        logger.warning(
            "job_telemetry_record_failed",
            extra={"details": {"task": task_name, "error": type(exc).__name__}},
        )


@celery_app.task(name="app.jobs.tasks.infrastructure_probe", bind=True, max_retries=3)
def infrastructure_probe(self, context: dict | None = None) -> dict:
    """Heartbeat task: verifies broker + worker path are alive; no business effects."""
    started = time.perf_counter()
    snapshot = ContextSnapshot(**(context or {}))
    snapshot.apply()
    result = {
        "ok": True,
        "task_id": self.request.id,
        "correlation_id": snapshot.correlation_id,
        "user_id": snapshot.user_id,
        "project_id": snapshot.project_id,
    }
    _record_telemetry(
        task_name="app.jobs.tasks.infrastructure_probe",
        queue="default",
        status="SUCCEEDED",
        duration_ms=int((time.perf_counter() - started) * 1000),
        correlation_id=snapshot.correlation_id,
    )
    return result


@celery_app.task(name="app.jobs.tasks.enqueue_ai_probe", bind=True, max_retries=3)
def enqueue_ai_probe(
    self, context: dict | None = None, prompt: str = "vertical slice probe"
) -> dict:
    """Vertical-slice task: worker → AI Gateway → stub provider, preserving correlation.

    Infrastructure validation only (phase-0-acceptance §vertical-slice); NOT a Tutor feature.
    """
    started = time.perf_counter()
    snapshot = ContextSnapshot(**(context or {}))
    snapshot.apply()  # worker side re-binds request/correlation context

    from app.ai.gateway import get_gateway
    from app.ai.schemas import GenerationRequest

    def _call():
        gateway = get_gateway()
        return gateway.generate(
            GenerationRequest(feature="infrastructure.probe", prompt=prompt, stream=False)
        )

    result = run_coroutine_sync(_call)
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "ai_probe_completed",
        extra={"details": {"correlation_id": snapshot.correlation_id, "duration_ms": duration_ms}},
    )
    _record_telemetry(
        task_name="app.jobs.tasks.enqueue_ai_probe",
        queue="default",
        status="SUCCEEDED",
        duration_ms=duration_ms,
        correlation_id=snapshot.correlation_id,
    )
    return {
        "ok": True,
        "task_id": self.request.id,
        "correlation_id": snapshot.correlation_id,
        "request_id": snapshot.request_id,
        "user_id": snapshot.user_id,
        "project_id": snapshot.project_id,
        "ai_request_id": result.meta.ai_request_id,
        "provider": result.meta.provider,
        "model": result.meta.model,
        "text": result.text,
        "duration_ms": duration_ms,
    }


@celery_app.task(name="app.jobs.tasks.process_material_document", bind=True, max_retries=3)
def process_material_document(self, context: dict | None = None, material_id: str = "") -> dict:
    """Document ingestion task: fetch from storage → extract pages → chunk → embed → persist."""
    import uuid

    from app.knowledge import service as knowledge_service
    from app.materials import service as materials_service
    from app.platform.storage import get_storage

    started = time.perf_counter()
    snapshot = ContextSnapshot(**(context or {}))
    snapshot.apply()

    mat_uuid = uuid.UUID(material_id)
    owner_uuid = uuid.UUID(snapshot.user_id) if snapshot.user_id else None
    proj_uuid = uuid.UUID(snapshot.project_id) if snapshot.project_id else None

    if not owner_uuid or not proj_uuid:
        logger.error(
            "process_material_document_missing_scope",
            extra={"details": {"material_id": material_id}},
        )
        return {"ok": False, "error": "missing_scope"}

    async def _process():
        # Transition status to processing
        material = await materials_service.begin_processing(
            owner_id=owner_uuid, project_id=proj_uuid, material_id=mat_uuid
        )
        storage = get_storage()
        pdf_bytes = storage.get_bytes(material.storage_key)
        if not pdf_bytes:
            raise RuntimeError(f"Storage object missing for key: {material.storage_key}")

        # Ingest document into knowledge
        result = await knowledge_service.ingest_document(
            owner_id=owner_uuid,
            project_id=proj_uuid,
            material_id=mat_uuid,
            pdf_bytes=pdf_bytes,
        )

        # Mark material as ready
        await materials_service.mark_completed(
            owner_id=owner_uuid,
            project_id=proj_uuid,
            material_id=mat_uuid,
            page_count=result.page_count,
        )
        return result

    try:
        res = run_coroutine_sync(_process)
        logger.info(
            "document_processing_succeeded",
            extra={
                "details": {
                    "material_id": material_id,
                    "pages": res.page_count,
                    "chunks": res.chunk_count,
                    "embeddings": res.embedding_count,
                }
            },
        )
        _record_telemetry(
            task_name="app.jobs.tasks.process_material_document",
            queue="documents",
            status="SUCCEEDED",
            duration_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=snapshot.correlation_id,
        )
        return {
            "ok": True,
            "material_id": material_id,
            "pages": res.page_count,
            "chunks": res.chunk_count,
            "embeddings": res.embedding_count,
        }
    except Exception as exc:
        logger.exception(
            "document_processing_failed",
            extra={"details": {"material_id": material_id, "error": str(exc)}},
        )
        safe_msg = f"Processing failed: {type(exc).__name__}"

        async def _fail():
            await materials_service.mark_failed(
                owner_id=owner_uuid,
                project_id=proj_uuid,
                material_id=mat_uuid,
                failure_reason=safe_msg,
            )

        run_coroutine_sync(_fail)
        _record_telemetry(
            task_name="app.jobs.tasks.process_material_document",
            queue="documents",
            status="FAILED",
            duration_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=snapshot.correlation_id,
            error_message=safe_msg,
        )
        return {"ok": False, "material_id": material_id, "error": safe_msg}


@celery_app.task(name="app.jobs.tasks.process_mastery_evidence", bind=True, max_retries=3)
def process_mastery_evidence(self, context: dict | None = None, evidence_id: str = "") -> dict:
    """Mastery background task: process a QuizEvidence row into updated ConceptMastery."""
    import uuid

    from app.mastery import service as mastery_service

    started = time.perf_counter()
    snapshot = ContextSnapshot(**(context or {}))
    snapshot.apply()

    ev_uuid = uuid.UUID(evidence_id)
    owner_uuid = uuid.UUID(snapshot.user_id) if snapshot.user_id else None
    proj_uuid = uuid.UUID(snapshot.project_id) if snapshot.project_id else None

    if not owner_uuid or not proj_uuid:
        logger.error(
            "process_mastery_evidence_missing_scope",
            extra={"details": {"evidence_id": evidence_id}},
        )
        return {"ok": False, "error": "Missing owner_id or project_id in context"}

    async def _process():
        return await mastery_service.process_quiz_evidence(
            owner_id=owner_uuid,
            project_id=proj_uuid,
            evidence_id=ev_uuid,
        )

    try:
        res = run_coroutine_sync(_process)
        _record_telemetry(
            task_name="app.jobs.tasks.process_mastery_evidence",
            queue="learning",
            status="SUCCEEDED",
            duration_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=snapshot.correlation_id,
        )
        return {
            "ok": True,
            "evidence_id": evidence_id,
            "concept_id": str(res.concept_id) if res else None,
            "mastery_probability": res.mastery_probability if res else None,
        }
    except Exception as exc:
        logger.exception(
            "process_mastery_evidence_failed",
            extra={"details": {"evidence_id": evidence_id, "error": str(exc)}},
        )
        safe_msg = f"Mastery failed: {type(exc).__name__}"
        _record_telemetry(
            task_name="app.jobs.tasks.process_mastery_evidence",
            queue="learning",
            status="FAILED",
            duration_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=snapshot.correlation_id,
            error_message=safe_msg,
        )
        return {"ok": False, "evidence_id": evidence_id, "error": str(exc)}


@celery_app.task(name="app.jobs.tasks.process_growth_evaluation", bind=True, max_retries=3)
def process_growth_evaluation(
    self,
    context: dict | None = None,
    concept_id: str = "",
    source_mastery_event_id: str | None = None,
) -> dict:
    """Growth background task: evaluate trajectory and attention for a concept."""
    import uuid

    from app.growth import service as growth_service

    started = time.perf_counter()
    snapshot = ContextSnapshot(**(context or {}))
    snapshot.apply()

    c_uuid = uuid.UUID(concept_id)
    ev_uuid = uuid.UUID(source_mastery_event_id) if source_mastery_event_id else None
    owner_uuid = uuid.UUID(snapshot.user_id) if snapshot.user_id else None
    proj_uuid = uuid.UUID(snapshot.project_id) if snapshot.project_id else None

    if not owner_uuid or not proj_uuid:
        logger.error(
            "process_growth_evaluation_missing_scope",
            extra={"details": {"concept_id": concept_id}},
        )
        return {"ok": False, "error": "Missing owner_id or project_id in context"}

    async def _process():
        return await growth_service.evaluate_concept_growth(
            owner_id=owner_uuid,
            project_id=proj_uuid,
            concept_id=c_uuid,
            source_mastery_event_id=ev_uuid,
        )

    try:
        res = run_coroutine_sync(_process)
        _record_telemetry(
            task_name="app.jobs.tasks.process_growth_evaluation",
            queue="learning",
            status="SUCCEEDED",
            duration_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=snapshot.correlation_id,
        )
        return {
            "ok": True,
            "concept_id": concept_id,
            "trend": res.trend.value,
            "attention_score": res.attention_score,
            "attention_required": res.attention_required,
        }
    except Exception as exc:
        logger.exception(
            "process_growth_evaluation_failed",
            extra={"details": {"concept_id": concept_id, "error": str(exc)}},
        )
        safe_msg = f"Growth failed: {type(exc).__name__}"
        _record_telemetry(
            task_name="app.jobs.tasks.process_growth_evaluation",
            queue="learning",
            status="FAILED",
            duration_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=snapshot.correlation_id,
            error_message=safe_msg,
        )
        return {"ok": False, "concept_id": concept_id, "error": str(exc)}


@celery_app.task(name="app.jobs.tasks.generate_project_recommendations", bind=True, max_retries=3)
def generate_project_recommendations(
    self,
    context: dict | None = None,
    source_growth_event_id: str | None = None,
) -> dict:
    """Recommendation background task: generate and persist project recommendations."""
    import uuid

    from app.recommendations import service as rec_service

    started = time.perf_counter()
    snapshot = ContextSnapshot(**(context or {}))
    snapshot.apply()

    ev_uuid = uuid.UUID(source_growth_event_id) if source_growth_event_id else None
    owner_uuid = uuid.UUID(snapshot.user_id) if snapshot.user_id else None
    proj_uuid = uuid.UUID(snapshot.project_id) if snapshot.project_id else None

    if not owner_uuid or not proj_uuid:
        logger.error(
            "generate_project_recommendations_missing_scope",
            extra={"details": {"project_id": snapshot.project_id}},
        )
        return {"ok": False, "error": "Missing owner_id or project_id in context"}

    async def _process():
        return await rec_service.generate_recommendations(
            owner_id=owner_uuid,
            project_id=proj_uuid,
            source_growth_event_id=ev_uuid,
        )

    try:
        dtos = run_coroutine_sync(_process)
        _record_telemetry(
            task_name="app.jobs.tasks.generate_project_recommendations",
            queue="learning",
            status="SUCCEEDED",
            duration_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=snapshot.correlation_id,
        )
        return {
            "ok": True,
            "project_id": str(proj_uuid),
            "recommendation_count": len(dtos),
            "recommendation_ids": [str(r.id) for r in dtos],
        }
    except Exception as exc:
        logger.exception(
            "generate_project_recommendations_failed",
            extra={"details": {"project_id": str(proj_uuid), "error": str(exc)}},
        )
        safe_msg = f"Recommendations failed: {type(exc).__name__}"
        _record_telemetry(
            task_name="app.jobs.tasks.generate_project_recommendations",
            queue="learning",
            status="FAILED",
            duration_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=snapshot.correlation_id,
            error_message=safe_msg,
        )
        return {"ok": False, "error": str(exc)}


@celery_app.task(name="app.jobs.tasks.ingest_analytics_event", bind=True, max_retries=3)
def ingest_analytics_event(
    self,
    context: dict | None = None,
    event_payload: dict | None = None,
) -> dict:
    """Analytics background task: ingest an event into the stream."""
    import uuid

    from app.analytics import service as analytics_service
    from app.analytics.schemas import AnalyticsEventInput

    started = time.perf_counter()
    snapshot = ContextSnapshot(**(context or {}))
    snapshot.apply()

    owner_uuid = uuid.UUID(snapshot.user_id) if snapshot.user_id else None
    proj_uuid = uuid.UUID(snapshot.project_id) if snapshot.project_id else None

    if not owner_uuid or not proj_uuid or not event_payload:
        logger.error(
            "ingest_analytics_event_missing_scope",
            extra={"details": {"project_id": snapshot.project_id}},
        )
        return {"ok": False, "error": "Missing owner_id, project_id, or event_payload"}

    input_data = AnalyticsEventInput(**event_payload)

    async def _process():
        return await analytics_service.record_event(
            owner_id=owner_uuid,
            project_id=proj_uuid,
            input_data=input_data,
        )

    try:
        dto = run_coroutine_sync(_process)
        _record_telemetry(
            task_name="app.jobs.tasks.ingest_analytics_event",
            queue="analytics",
            status="SUCCEEDED",
            duration_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=snapshot.correlation_id,
        )
        return {
            "ok": True,
            "event_id": str(dto.id),
            "event_type": dto.event_type,
        }
    except Exception as exc:
        logger.exception(
            "ingest_analytics_event_failed",
            extra={"details": {"project_id": str(proj_uuid), "error": str(exc)}},
        )
        safe_msg = f"Analytics event failed: {type(exc).__name__}"
        _record_telemetry(
            task_name="app.jobs.tasks.ingest_analytics_event",
            queue="analytics",
            status="FAILED",
            duration_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=snapshot.correlation_id,
            error_message=safe_msg,
        )
        return {"ok": False, "error": str(exc)}


@celery_app.task(name="app.jobs.tasks.refresh_project_analytics", bind=True, max_retries=3)
def refresh_project_analytics(
    self,
    context: dict | None = None,
    target_date_str: str | None = None,
) -> dict:
    """Analytics background task: precompute daily rollups for a project."""
    import datetime
    import uuid

    from app.analytics import service as analytics_service

    started = time.perf_counter()
    snapshot = ContextSnapshot(**(context or {}))
    snapshot.apply()

    owner_uuid = uuid.UUID(snapshot.user_id) if snapshot.user_id else None
    proj_uuid = uuid.UUID(snapshot.project_id) if snapshot.project_id else None

    if not owner_uuid or not proj_uuid:
        logger.error(
            "refresh_project_analytics_missing_scope",
            extra={"details": {"project_id": snapshot.project_id}},
        )
        return {"ok": False, "error": "Missing owner_id or project_id in context"}

    target_date = datetime.date.fromisoformat(target_date_str) if target_date_str else None

    async def _process():
        await analytics_service.refresh_project_rollups(
            owner_id=owner_uuid,
            project_id=proj_uuid,
            target_date=target_date,
        )

    try:
        run_coroutine_sync(_process)
        _record_telemetry(
            task_name="app.jobs.tasks.refresh_project_analytics",
            queue="analytics",
            status="SUCCEEDED",
            duration_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=snapshot.correlation_id,
        )
        return {
            "ok": True,
            "project_id": str(proj_uuid),
            "target_date": target_date.isoformat() if target_date else "today",
        }
    except Exception as exc:
        logger.exception(
            "refresh_project_analytics_failed",
            extra={"details": {"project_id": str(proj_uuid), "error": str(exc)}},
        )
        safe_msg = f"Analytics rollup failed: {type(exc).__name__}"
        _record_telemetry(
            task_name="app.jobs.tasks.refresh_project_analytics",
            queue="analytics",
            status="FAILED",
            duration_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=snapshot.correlation_id,
            error_message=safe_msg,
        )
        return {"ok": False, "error": str(exc)}
