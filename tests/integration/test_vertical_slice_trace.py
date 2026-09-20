"""PHASE 0 VERTICAL SLICE — infrastructure traceability validation (NOT a product feature).

Proves the chain: HTTP request → FastAPI (request/correlation ids) → Celery
task (envelope propagation) → AI Gateway → stub provider → recorded AI
telemetry — with ONE correlation id observable across every hop.

Runs against an in-process worker (task_always_eager) so CI needs no broker;
the eager path still executes the real task code, the real gateway, the real
telemetry, and the same envelope mechanism the distributed worker uses
(`task_prerun` re-binds context from the envelope).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AI_PROVIDER_REGISTRY", "stub")
    monkeypatch.setenv("AI_GENERATION_PROVIDER", "stub")
    monkeypatch.setenv("AI_GENERATION_MODEL", "stub-generation")
    # Explicit empty overrides (not just delenv): .env.development now exists,
    # and pydantic-settings reads it — this test must stay a NO-INFRA scenario.
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATABASE_RUNTIME_URL", "")
    monkeypatch.setenv("REDIS_URL", "")

    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api" / "src"))

    from app.main import create_app
    from app.platform.config import reset_settings_cache

    reset_settings_cache()
    app = create_app()
    with TestClient(app) as c:
        yield c
    from app.platform.config import reset_settings_cache

    reset_settings_cache()


@pytest.fixture()
def eager_worker(monkeypatch):
    """In-process task execution with the same code paths as the real worker."""
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "cache+memory://")
    import importlib

    import app.jobs.tasks as tasks

    importlib.reload(tasks)
    tasks.celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        task_store_eager_result=True,  # make AsyncResult(job_id).state readable after eager runs
    )
    yield tasks
    tasks.celery_app.conf.update(
        task_always_eager=False,
        task_eager_propagates=False,
        task_store_eager_result=False,
    )


def test_vertical_slice_correlation_id_consistent(client, eager_worker):
    from app.ai import telemetry as ai_telemetry

    ai_telemetry.reset()
    correlation_id = str(uuid.uuid4())

    # 1–2. API receives the request; request id created by the middleware.
    response = client.post(
        "/internal/jobs/probe",
        json={"prompt": "vertical slice trace probe"},
        headers={"X-Correlation-ID": correlation_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    job_id = body["job_id"]

    # 3. Correlation id accepted (not replaced) by the API.
    assert body["correlation_id"] == correlation_id
    assert response.headers["X-Correlation-ID"] == correlation_id
    assert response.headers["X-Request-ID"]

    # 4–5. Task executes (eager worker) and receives/preserves the correlation id.
    status = client.get(f"/internal/jobs/probe/{job_id}")
    assert status.status_code == 200, status.text
    result = status.json()
    assert result["status"] == "SUCCESS", result
    task_result = result["result"]
    assert task_result["correlation_id"] == correlation_id, task_result
    assert task_result["user_id"] is None  # envelope carries ownership only when present

    # 6–7. Worker called the AI Gateway, which called the stub provider.
    assert task_result["provider"] == "stub"
    assert task_result["model"] == "stub-generation"
    assert task_result["text"].startswith("[stub:generation]")

    # 8. AI call recorded observability metadata.
    records = ai_telemetry.find_by_correlation(correlation_id)
    assert len(records) == 1
    record = records[0]
    assert record.meta.correlation_id == correlation_id
    assert record.meta.request_id == task_result["request_id"]
    assert record.meta.feature == "infrastructure.probe"
    assert record.meta.model_role == "generation"
    assert record.status == "success"
    assert record.meta.usage.latency_ms >= 1
    assert record.meta.cost.price_table_ref == "stub:zero-cost"

    # 9. Worker completed successfully (implicit in SUCCESS above) and returned
    #    the AI request linkage for support/debug (FR-82 shape).
    assert task_result["ai_request_id"] == record.meta.ai_request_id

    # 10. Correlation id consistent across every hop (asserted at each step above).
    #     Also verifiable via the status endpoint payload for a fresh call:
    probe2 = client.post(
        "/internal/jobs/probe",
        json={"prompt": "second"},
        headers={"X-Correlation-ID": correlation_id},
    )
    job2 = probe2.json()["job_id"]
    result2 = client.get(f"/internal/jobs/probe/{job2}").json()["result"]
    assert result2["correlation_id"] == correlation_id
    assert len(ai_telemetry.find_by_correlation(correlation_id)) == 2


def test_vertical_slice_generates_request_id_when_absent(client, eager_worker):
    """Without client headers, the middleware creates a request id and a matching correlation id."""
    ai_telemetry = __import__("app.ai.telemetry", fromlist=["telemetry"])
    ai_telemetry.reset()
    response = client.post("/internal/jobs/probe", json={"prompt": "no headers"})
    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]
    correlation_id = response.headers["X-Correlation-ID"]
    assert request_id and correlation_id
    job_id = response.json()["job_id"]
    result = client.get(f"/internal/jobs/probe/{job_id}").json()["result"]
    assert result["correlation_id"] == correlation_id
    assert result["request_id"] == request_id


def test_health_endpoints(client):
    live = client.get("/healthz")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"

    ready = client.get("/readyz")
    assert ready.status_code == 200
    body = ready.json()
    # Dev without infra: components report unconfigured/degraded — never a crash, never secrets.
    assert body["status"] in ("ok", "degraded")
    flat = str(body)
    assert "CHANGE_ME" not in flat
    assert "password" not in flat.lower()
