"""Celery application — worker foundation (ADR-0014).

Queues reflect the approved architecture: documents, learning, analytics,
evaluation (+ default for relay/cleanup). Redis is the broker only — the
durable record of work remains the database outbox (next phase). Beat runs
only infrastructure-level schedules in Phase 0.
"""

from __future__ import annotations

from dataclasses import fields

from app.platform.context import ContextSnapshot
from celery import Celery
from celery.signals import task_prerun

QUEUES = ["documents", "learning", "analytics", "evaluation", "default"]


def make_celery_app(broker_url: str, backend_url: str) -> Celery:
    app = Celery(
        "studycompanion",
        broker=broker_url,
        backend=backend_url,
        include=["app.jobs.tasks"],
    )
    app.conf.update(
        task_default_queue="default",
        task_queues=_configure_queues(),
        task_routes={
            "app.jobs.tasks.infrastructure_probe": {"queue": "default"},
            "app.jobs.tasks.enqueue_ai_probe": {"queue": "learning"},
            "app.jobs.tasks.process_material_document": {"queue": "documents"},
            "app.jobs.tasks.*": {"queue": "default"},
        },
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_track_started=True,
        broker_transport_options={"visibility_timeout": 3600},
        worker_prefetch_multiplier=1,
        beat_schedule={
            "infrastructure-heartbeat": {
                "task": "app.jobs.tasks.infrastructure_probe",
                "schedule": 300.0,
                "options": {"queue": "default"},
            },
        },
        timezone="UTC",
    )
    return app


def _configure_queues():
    from kombu import Queue

    return [Queue(q) for q in QUEUES]


@task_prerun.connect
def _bind_context_from_envelope(
    task_id=None, task=None, kwargs=None, **_kwargs
):  # pragma: no cover - signal
    """Re-bind request context from the task envelope so worker-side logs/telemetry join the trace."""
    envelope = (kwargs or {}).get("context") or {}
    if isinstance(envelope, dict) and envelope:
        # Envelope keys are exactly ContextSnapshot fields (incl. event_id) — build directly.
        known = {
            k: v for k, v in envelope.items() if k in {f.name for f in fields(ContextSnapshot)}
        }
        ContextSnapshot(**known).apply()


def task_envelope(*, user_id=None, project_id=None, event_id=None) -> dict:
    """Standard envelope every task accepts: ownership + correlation context (§E, ADR-0002)."""

    snapshot = ContextSnapshot.capture()
    return {
        "request_id": snapshot.request_id,
        "correlation_id": snapshot.correlation_id,
        "user_id": user_id if user_id is not None else snapshot.user_id,
        "project_id": project_id if project_id is not None else snapshot.project_id,
        "event_id": event_id,
        "extra": snapshot.extra,
    }
