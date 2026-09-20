"""Jobs infrastructure routes — probe dispatch and async-result inspection only.

The durable job/outbox model arrives with the database-schema phase; these
endpoints exist to validate the worker plane end-to-end (vertical slice).
"""

from __future__ import annotations

from app.jobs.celery_app import task_envelope
from app.platform.logging import get_logger
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = get_logger(__name__)
router = APIRouter(prefix="/internal/jobs", tags=["jobs-infrastructure"])

_async_results: dict[str, object] = {}


class ProbeRequest(BaseModel):
    prompt: str | None = None


@router.post("/probe")
async def dispatch_probe(body: ProbeRequest) -> dict:
    """Dispatch the infrastructure AI probe to the `learning` queue (vertical slice entrypoint)."""
    from app.jobs.tasks import enqueue_ai_probe

    envelope = task_envelope()
    async_result = enqueue_ai_probe.apply_async(
        kwargs={"context": envelope, "prompt": body.prompt or "vertical slice probe"}
    )
    _async_results[async_result.id] = envelope
    return {
        "job_id": async_result.id,
        "correlation_id": envelope["correlation_id"],
        "status": "queued",
    }


@router.get("/probe/{job_id}")
async def probe_status(job_id: str) -> dict:
    from app.jobs.tasks import enqueue_ai_probe

    async_result = enqueue_ai_probe.AsyncResult(job_id)
    if async_result.id is None and job_id not in _async_results:
        raise HTTPException(status_code=404, detail="Unknown job")
    payload: dict = {"job_id": job_id, "status": async_result.state}
    if async_result.successful():
        payload["result"] = async_result.result
    elif async_result.failed():
        # Never leak worker internals; the correlation id is the support handle.
        payload["error"] = "task failed; see logs by correlation id"
    return payload


@router.post("/heartbeat")
async def dispatch_heartbeat() -> dict:
    from app.jobs.tasks import infrastructure_probe

    envelope = task_envelope()
    async_result = infrastructure_probe.apply_async(kwargs={"context": envelope})
    return {
        "job_id": async_result.id,
        "correlation_id": envelope["correlation_id"],
        "status": "queued",
    }
