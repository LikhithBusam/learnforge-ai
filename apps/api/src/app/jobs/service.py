"""Jobs service — public facade for the jobs worker plane (module-contracts §M.13)."""

from __future__ import annotations

import uuid


def dispatch_document_processing(
    *, user_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID
) -> str:
    """Dispatch document ingestion background job to the 'documents' queue."""
    from app.jobs.celery_app import task_envelope
    from app.jobs.tasks import process_material_document

    env = task_envelope(user_id=str(user_id), project_id=str(project_id))
    task = process_material_document.delay(context=env, material_id=str(material_id))
    return str(task.id)
