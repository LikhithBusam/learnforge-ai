"""Unit tests — AI Gateway envelope behavior, config fail-safety, log redaction."""

from __future__ import annotations

import logging

import pytest
from app.ai import telemetry
from app.ai.gateway import StubProvider, get_gateway, reset_gateway
from app.ai.schemas import (
    EmbeddingRequest,
    EvaluationRequest,
    GenerationRequest,
    RerankRequest,
    StructuredRequest,
)
from pydantic import BaseModel


class _Rating(BaseModel):
    score: float


@pytest.fixture(autouse=True)
def _reset():
    reset_gateway()
    telemetry.reset()
    yield
    reset_gateway()
    telemetry.reset()


@pytest.mark.asyncio
async def test_generate_returns_stub_metadata():
    result = await get_gateway().generate(
        GenerationRequest(feature="unit.probe", prompt="hello world")
    )
    assert result.meta.provider == "stub"
    assert result.meta.model == "stub-generation"
    assert result.text.startswith("[stub:generation]")
    assert result.meta.usage.latency_ms >= 1
    assert result.meta.cost.estimated_cost_usd == 0.0


@pytest.mark.asyncio
async def test_structured_validates_against_local_schema():
    result = await get_gateway().generate_structured(
        StructuredRequest(
            feature="unit.structured",
            prompt='{"stub_payload": {"score": 0.5}}',
            output_schema_name="unit.Rating",
            schema_model=_Rating,
        )
    )
    assert result.validated is True
    assert result.data == {"score": 0.5}
    record = telemetry.all_records()[-1]
    assert record.status == "success"
    assert record.meta.provider == "stub"


@pytest.mark.asyncio
async def test_structured_invalid_output_raises_typed_error_and_records():
    from app.platform.errors import AIInvalidOutput

    with pytest.raises(AIInvalidOutput):
        await get_gateway().generate_structured(
            StructuredRequest(
                feature="unit.structured.bad",
                prompt='{"stub_payload": {"unexpected": true}}',
                output_schema_name="unit.Rating",
                schema_model=_Rating,
            )
        )
    record = telemetry.all_records()[-1]
    assert record.status == "invalid_output"


@pytest.mark.asyncio
async def test_embed_dimensions_and_rerank_order():
    emb = await get_gateway().embed(EmbeddingRequest(feature="unit.embed", texts=["a", "bb"]))
    assert emb.dimensions >= 1
    assert len(emb.vectors) == 2
    rr = await get_gateway().rerank(
        RerankRequest(feature="unit.rerank", query="q", candidates=["c1", "c2", "c3"], top_n=2)
    )
    assert len(rr.ranked) == 2
    assert rr.ranked[0].score >= rr.ranked[1].score


@pytest.mark.asyncio
async def test_evaluation_records_usage():
    ev = await get_gateway().evaluate(
        EvaluationRequest(
            feature="unit.eval", subject="subject text", output_schema_name="unit.Rating"
        )
    )
    assert ev.validated is True
    record = telemetry.all_records()[-1]
    assert record.meta.usage.output_tokens is not None


def test_stub_provider_is_clearly_labelled():
    assert StubProvider.name == "stub"


def test_settings_safe_summary_has_no_secrets(monkeypatch):
    monkeypatch.setenv("STORAGE_ACCESS_KEY_ID", "supersecretkey123456")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    from app.platform.config import get_settings, reset_settings_cache

    reset_settings_cache()
    summary = get_settings().safe_summary()
    flat = str(summary)
    assert "supersecretkey123456" not in flat
    assert "postgresql+asyncpg" not in flat
    reset_settings_cache()


def test_production_config_requires_critical_settings(monkeypatch):
    from app.platform.config import Settings, reset_settings_cache

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("JWT_PRIVATE_KEY", raising=False)
    reset_settings_cache()
    with pytest.raises(RuntimeError, match="Refusing to boot"):
        Settings()
    reset_settings_cache()


def test_log_redaction_masks_secret_keys(caplog):
    from app.platform.logging import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="p",
        lineno=1,
        msg="attempt",
        args=(),
        exc_info=None,
    )
    record.details = {"password": "hunter2", "authorization": "Bearer abc", "note": "safe"}
    line = formatter.format(record)
    assert "hunter2" not in line
    assert "Bearer abc" not in line
    assert "safe" in line


def test_log_redaction_masks_secret_shaped_strings(caplog):
    from app.platform.logging import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="p",
        lineno=1,
        msg="leak",
        args=(),
        exc_info=None,
    )
    record.details = {"body": "token sk-abcdefghijklmnop1234 in text"}
    line = formatter.format(record)
    assert "sk-abcdefghijklmnop1234" not in line
