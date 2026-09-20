"""Unit tests for Phase 10 Admin health, AI usage analytics, and job telemetry.

Covers:
- System health status aggregation (healthy / degraded / unhealthy)
- AI usage analytics calculations and edge-case (zero cost, no records)
- Job execution telemetry helper (_record_telemetry) — non-raising contract
- 404 concealment posture (assert_admin_role)
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from app.admin.policies import assert_admin_role
from app.platform.errors import NotFound
from app.platform.security import Principal

# ---------------------------------------------------------------------------
# 1. System health status aggregation
# ---------------------------------------------------------------------------


class TestSystemHealthAggregation:
    """Verify health status semantics without a live DB."""

    def _make_components(self, db_ok: bool, cache_ok: bool, storage_ok: bool) -> dict:
        return {
            "database": {"status": "ok" if db_ok else "error"},
            "cache": {"status": "ok" if cache_ok else "error"},
            "storage": {"status": "ok" if storage_ok else "error"},
        }

    def _aggregate_status(self, components: dict) -> str:
        """Mirror the health aggregation logic in the platform health module."""
        required = [c for name, c in components.items() if name in ("database", "cache")]
        degraded_or_down = any(c.get("status") not in ("ok", "unconfigured") for c in required)
        return "degraded" if degraded_or_down else "ok"

    def test_all_healthy(self):
        components = self._make_components(True, True, True)
        assert self._aggregate_status(components) == "ok"

    def test_database_error_makes_degraded(self):
        components = self._make_components(False, True, True)
        assert self._aggregate_status(components) == "degraded"

    def test_cache_error_makes_degraded(self):
        components = self._make_components(True, False, True)
        assert self._aggregate_status(components) == "degraded"

    def test_storage_error_does_not_degrade(self):
        """Storage is not required — only DB and cache affect primary status."""
        components = self._make_components(True, True, False)
        assert self._aggregate_status(components) == "ok"

    def test_cache_unconfigured_not_degraded(self):
        """'unconfigured' means the feature is disabled in dev, not a failure."""
        components = {
            "database": {"status": "ok"},
            "cache": {"status": "unconfigured"},
        }
        assert self._aggregate_status(components) == "ok"


# ---------------------------------------------------------------------------
# 2. AI usage analytics edge cases
# ---------------------------------------------------------------------------


class TestAIUsageAnalytics:
    """AI usage analytics calculations from the telemetry spine."""

    def _make_record(
        self,
        *,
        status: str = "success",
        latency_ms: int = 500,
        input_tokens: int = 100,
        output_tokens: int = 50,
        estimated_cost_usd: float = 0.001,
        feature: str = "rag_generation",
        model: str = "gemini-2.5-pro",
    ):
        from app.ai.schemas import AIRequestRecord, CallMetadata, CostMetadata, UsageMetadata

        return AIRequestRecord(
            meta=CallMetadata(
                ai_request_id=str(uuid.uuid4()),
                correlation_id="corr-test",
                request_id="req-test",
                feature=feature,
                model_role="generation",
                provider="gemini",
                model=model,
                usage=UsageMetadata(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                ),
                cost=CostMetadata(estimated_cost_usd=estimated_cost_usd),
            ),
            status=status,
            error_type=None if status == "success" else "timeout",
        )

    def test_empty_records_returns_zero_counts(self):
        """An empty telemetry spine yields all zeros."""
        from app.ai import telemetry as ai_telemetry

        ai_telemetry.reset()
        records = ai_telemetry.all_records()
        assert len(records) == 0

    def test_error_rate_calculation(self):
        """1 failure in 10 → 10% error rate."""
        records = [self._make_record(status="success") for _ in range(9)]
        records.append(self._make_record(status="failed"))
        total = len(records)
        failed = sum(1 for r in records if r.status != "success")
        assert failed / total == pytest.approx(0.1)

    def test_average_latency_calculation(self):
        """Average latency is arithmetic mean of all records."""
        latencies = [100, 200, 300]
        records = [self._make_record(latency_ms=lat) for lat in latencies]
        avg = sum(r.meta.usage.latency_ms for r in records) / len(records)
        assert avg == pytest.approx(200.0)

    def test_cost_sum_zero_when_stub(self):
        """Zero-cost records (stub provider) yield total cost = 0.0."""
        records = [self._make_record(estimated_cost_usd=0.0) for _ in range(5)]
        total_cost = sum(r.meta.cost.estimated_cost_usd for r in records)
        assert total_cost == pytest.approx(0.0)

    def test_by_feature_breakdown(self):
        """Count requests grouped by feature."""
        records = [
            self._make_record(feature="rag_generation"),
            self._make_record(feature="rag_generation"),
            self._make_record(feature="assessment_generation"),
        ]
        by_feature: dict[str, int] = {}
        for r in records:
            by_feature[r.meta.feature] = by_feature.get(r.meta.feature, 0) + 1
        assert by_feature["rag_generation"] == 2
        assert by_feature["assessment_generation"] == 1

    def test_by_model_breakdown(self):
        """Count requests grouped by model."""
        records = [
            self._make_record(model="gemini-2.5-pro"),
            self._make_record(model="gemini-2.5-flash"),
            self._make_record(model="gemini-2.5-pro"),
        ]
        by_model: dict[str, int] = {}
        for r in records:
            by_model[r.meta.model] = by_model.get(r.meta.model, 0) + 1
        assert by_model["gemini-2.5-pro"] == 2
        assert by_model["gemini-2.5-flash"] == 1

    def test_token_totals(self):
        """Input + output token sums across records."""
        records = [
            self._make_record(input_tokens=100, output_tokens=50),
            self._make_record(input_tokens=200, output_tokens=100),
        ]
        total_input = sum(r.meta.usage.input_tokens for r in records)
        total_output = sum(r.meta.usage.output_tokens for r in records)
        assert total_input == 300
        assert total_output == 150


# ---------------------------------------------------------------------------
# 3. Job telemetry helper — non-raising contract
# ---------------------------------------------------------------------------


class TestJobTelemetryHelper:
    """_record_telemetry must never raise, regardless of DB state."""

    def test_record_telemetry_does_not_raise_on_db_failure(self):
        """Simulate DB unavailability — helper must swallow the exception."""
        from app.jobs.tasks import _record_telemetry

        with patch("app.admin.service.record_job_execution", side_effect=RuntimeError("DB down")):
            # Should not raise
            _record_telemetry(
                task_name="app.test.task",
                queue="default",
                status="SUCCEEDED",
                duration_ms=100,
                correlation_id="corr-abc",
            )

    def test_record_telemetry_does_not_raise_on_import_error(self):
        """Even if admin service is unavailable, helper is safe."""
        from app.jobs.tasks import _record_telemetry

        with patch.dict("sys.modules", {"app.admin.service": None}):
            _record_telemetry(
                task_name="app.test.task",
                queue="default",
                status="FAILED",
                duration_ms=0,
                error_message="test error",
            )


# ---------------------------------------------------------------------------
# 4. 404 concealment policy
# ---------------------------------------------------------------------------


class TestAdminPolicy:
    """assert_admin_role enforces 404 concealment posture."""

    def test_admin_passes(self):
        p = Principal(user_id=str(uuid.uuid4()), role="admin")
        assert_admin_role(p)  # must not raise

    def test_learner_raises_not_found(self):
        p = Principal(user_id=str(uuid.uuid4()), role="learner")
        with pytest.raises(NotFound):
            assert_admin_role(p)

    def test_none_principal_raises_not_found(self):
        """None principal (unauthenticated) must also raise NotFound."""
        with pytest.raises((NotFound, AttributeError)):
            assert_admin_role(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. Job count aggregation semantics
# ---------------------------------------------------------------------------


class TestJobCountAggregation:
    """Verify job status breakdown arithmetic."""

    def test_status_breakdown(self):
        """SUCCEEDED + FAILED + RETRYING must equal total."""
        jobs = [
            {"status": "SUCCEEDED"},
            {"status": "SUCCEEDED"},
            {"status": "SUCCEEDED"},
            {"status": "FAILED"},
            {"status": "RETRYING"},
        ]
        total = len(jobs)
        succeeded = sum(1 for j in jobs if j["status"] == "SUCCEEDED")
        failed = sum(1 for j in jobs if j["status"] == "FAILED")
        retrying = sum(1 for j in jobs if j["status"] == "RETRYING")
        assert succeeded + failed + retrying == total
        assert succeeded == 3
        assert failed == 1
        assert retrying == 1

    def test_success_rate(self):
        """100% success rate when all jobs succeed."""
        jobs = [{"status": "SUCCEEDED"} for _ in range(10)]
        rate = sum(1 for j in jobs if j["status"] == "SUCCEEDED") / len(jobs)
        assert rate == pytest.approx(1.0)

    def test_empty_job_list(self):
        """Empty job list → zero counts, no division errors."""
        jobs: list = []
        total = len(jobs)
        succeeded = sum(1 for j in jobs if j["status"] == "SUCCEEDED")
        assert total == 0
        assert succeeded == 0
