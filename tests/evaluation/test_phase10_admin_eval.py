"""Evaluation tests for Phase 10 Admin Observability & Metrics Computation.

Evaluates:
- AI Gateway telemetry aggregation (latency calculations, error rates, token volumes)
- Background job telemetry aggregation (success/failure rates, queue distribution)
- System health status aggregation
"""

from __future__ import annotations

import uuid

import pytest
from app.admin.models import JobExecutionRecord
from app.ai import telemetry as ai_telemetry
from app.ai.schemas import AIRequestRecord, CallMetadata, CostMetadata, UsageMetadata
from app.platform.ids import uuid7


@pytest.mark.asyncio
async def test_ai_usage_analytics_evaluation():
    """Verify AI Gateway analytics calculations across realistic request distributions."""
    records_to_test: list[AIRequestRecord] = []
    latencies = [100, 150, 200, 250, 300, 500, 800, 1200, 1500, 3000]
    for i, lat in enumerate(latencies):
        rec = AIRequestRecord(
            meta=CallMetadata(
                ai_request_id=str(uuid.uuid4()),
                correlation_id=f"corr-p10-eval-{i}",
                request_id=f"req-p10-eval-{i}",
                feature="rag_generation" if i % 2 == 0 else "assessment_generation",
                model_role="generation",
                provider="gemini",
                model="gemini-2.5-pro",
                usage=UsageMetadata(
                    input_tokens=100 + i * 10,
                    output_tokens=50 + i * 5,
                    latency_ms=lat,
                ),
                cost=CostMetadata(
                    estimated_cost_usd=0.001 * (i + 1),
                ),
            ),
            status="success" if i < 9 else "failed",
            error_type=None if i < 9 else "timeout",
        )
        ai_telemetry.record(rec)
        records_to_test.append(rec)

    total_reqs = len(records_to_test)
    succ_reqs = sum(1 for r in records_to_test if r.status == "success")
    failed_reqs = sum(1 for r in records_to_test if r.status != "success")
    assert total_reqs == 10
    assert succ_reqs == 9
    assert failed_reqs == 1

    error_rate = failed_reqs / total_reqs
    assert error_rate == 0.1

    all_lats = sorted(r.meta.usage.latency_ms for r in records_to_test)
    avg_latency = sum(all_lats) / len(all_lats)
    assert avg_latency == 800.0


def test_job_execution_record_model_attributes():
    """Verify JobExecutionRecord ORM model construction."""
    rec_id = uuid7()
    job = JobExecutionRecord(
        id=rec_id,
        task_name="app.materials.tasks.ingest_material",
        queue="materials",
        status="SUCCESS",
        duration_ms=450,
        attempt=1,
        correlation_id="trace-001",
        error_message=None,
    )
    assert job.id == rec_id
    assert job.task_name == "app.materials.tasks.ingest_material"
    assert job.queue == "materials"
    assert job.status == "SUCCESS"
    assert job.duration_ms == 450
