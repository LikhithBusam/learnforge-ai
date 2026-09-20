"""Integration tests for the real Google Gemini provider via AI Gateway (Phase 12.2).

Runs ONLY when `GEMINI_API_KEY` is present in the environment or settings.
Tests minimal unstructured generation, structured generation with Pydantic validation,
honest refusal on insufficient evidence, and telemetry recording, all via the existing AI Gateway.
NEVER prints or stores API keys in test outputs or artifacts.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from app.ai.gateway import get_gateway, reset_gateway
from app.ai.schemas import GenerationRequest, StructuredRequest
from app.assessment.schemas import (
    MCQGenerationPayload,
    OpenEndedGradingPayload,
)
from app.platform.config import get_settings, reset_settings_cache
from app.platform.errors import AIProviderDown
from app.tutor.schemas import TutorGenerationPayload
from pydantic import BaseModel, Field


class CapitalCityInfo(BaseModel):
    country: str
    capital: str
    confidence: float = Field(ge=0.0, le=1.0)


@pytest.fixture
async def gemini_configured():
    reset_settings_cache()
    settings = get_settings()
    api_key = getattr(settings, "GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        pytest.skip("SKIPPED — GEMINI_API_KEY not configured")
    # Ensure provider is configured for gemini during the test
    settings.AI_PROVIDER = "gemini"
    settings.AI_GENERATION_PROVIDER = "gemini"
    settings.AI_STRUCTURED_PROVIDER = "gemini"
    settings.AI_GENERATION_MODEL = settings.GEMINI_MODEL or "gemini-2.5-flash"
    settings.AI_STRUCTURED_MODEL = settings.GEMINI_MODEL or "gemini-2.5-flash"
    reset_gateway()
    await asyncio.sleep(2.0)
    yield settings
    from app.ai.gateway import _registry

    gemini_adapter = _registry._adapters.get("gemini")
    if gemini_adapter and hasattr(gemini_adapter, "aclose"):
        await gemini_adapter.aclose()
    reset_settings_cache()
    reset_gateway()


@pytest.mark.asyncio
async def test_gemini_unstructured_generation(gemini_configured):
    gateway = get_gateway()
    req = GenerationRequest(
        feature="test_generation",
        model_role="generation",
        prompt="Respond with exactly one word: 'CONFIRMED'",
    )

    result = await gateway.generate(req)

    assert result.text is not None
    assert len(result.text.strip()) > 0
    assert result.finish_reason is not None
    # Verify metadata and telemetry
    assert result.meta.provider == "gemini"
    assert "gemini" in result.meta.model.lower()
    assert result.meta.usage.input_tokens > 0
    assert result.meta.usage.output_tokens > 0
    assert result.meta.usage.latency_ms > 0
    # Crucial security check: ensure API key is never in result or metadata
    settings = gemini_configured
    key = getattr(settings, "GEMINI_API_KEY", "")
    if key:
        assert key not in result.text
        assert key not in str(result.meta)


@pytest.mark.asyncio
async def test_gemini_structured_generation_with_schema(gemini_configured):
    gateway = get_gateway()
    req: StructuredRequest[CapitalCityInfo] = StructuredRequest(
        feature="test_structured",
        model_role="structured",
        prompt="What is the capital of France? Return country, capital, and confidence score.",
        schema_model=CapitalCityInfo,
        output_schema_name="CapitalCityInfo",
    )

    result = await gateway.generate_structured(req)

    assert result.validated is True
    assert result.data is not None
    assert isinstance(result.data, dict)

    # Validate against Pydantic model
    validated_obj = CapitalCityInfo.model_validate(result.data)
    assert validated_obj.country.lower() == "france"
    assert "paris" in validated_obj.capital.lower()
    assert 0.0 <= validated_obj.confidence <= 1.0

    # Verify telemetry metadata
    assert result.meta.provider == "gemini"
    assert "gemini" in result.meta.model.lower()
    assert result.meta.usage.input_tokens > 0
    assert result.meta.usage.output_tokens > 0
    assert result.meta.usage.latency_ms > 0


@pytest.mark.asyncio
async def test_gemini_grounded_tutor_schema(gemini_configured):
    gateway = get_gateway()
    prompt = (
        "You are an AI tutor. Based ONLY on this evidence: <retrieved_evidence>"
        '<chunk id="d290f1ee-6c54-4b01-90e6-d701748f0851" page_start="1" page_end="1">'
        "Photosynthesis converts sunlight into chemical energy stored in glucose molecules."
        "</chunk></retrieved_evidence>\n"
        "Question: What does photosynthesis convert sunlight into?"
    )
    req: StructuredRequest[TutorGenerationPayload] = StructuredRequest(
        feature="tutor_answer",
        model_role="structured",
        prompt=prompt,
        schema_model=TutorGenerationPayload,
        output_schema_name="tutor_generation",
    )

    result = await gateway.generate_structured(req)

    assert result.validated is True
    assert result.data is not None
    payload = TutorGenerationPayload.model_validate(result.data)
    assert payload.grounded is True
    assert not payload.refusal
    assert "chemical energy" in payload.answer.lower() or "glucose" in payload.answer.lower()
    assert len(payload.citations) >= 1
    assert str(payload.citations[0].chunk_id) == "d290f1ee-6c54-4b01-90e6-d701748f0851"


@pytest.mark.asyncio
async def test_gemini_honest_refusal_when_insufficient_evidence(gemini_configured):
    gateway = get_gateway()
    prompt = (
        "You are an AI tutor. You must follow this strict rule: If the retrieved evidence does not contain "
        "sufficient facts to answer the question, you MUST set refusal=true and grounded=false.\n\n"
        "<retrieved_evidence>\nNo relevant evidence found.\n</retrieved_evidence>\n\n"
        "Question: What is the warp drive speed limit in Star Trek?"
    )
    req: StructuredRequest[TutorGenerationPayload] = StructuredRequest(
        feature="tutor_answer",
        model_role="structured",
        prompt=prompt,
        schema_model=TutorGenerationPayload,
        output_schema_name="tutor_generation",
    )

    result = await gateway.generate_structured(req)

    assert result.validated is True
    assert result.data is not None
    payload = TutorGenerationPayload.model_validate(result.data)
    assert payload.refusal is True or payload.grounded is False


@pytest.mark.asyncio
async def test_gemini_assessment_mcq_generation(gemini_configured):
    gateway = get_gateway()
    evidence = (
        '<chunk id="chunk-101">\n'
        "Mitochondria are membrane-bound cell organelles that generate most of the chemical "
        "energy needed to power the cell's biochemical reactions. Chemical energy produced by the "
        "mitochondria is stored in a small molecule called adenosine triphosphate (ATP).\n"
        "</chunk>"
    )
    prompt = (
        f"Generate ONE EASY difficulty MCQ question based ONLY on this evidence:\n{evidence}\n"
        "Requirements:\n"
        "- Exactly 4 options with ids A, B, C, D\n"
        "- correct_option must be A, B, C, or D\n"
        "- source_chunk_ids must contain ['chunk-101']\n"
    )
    req: StructuredRequest[MCQGenerationPayload] = StructuredRequest(
        feature="assessment_question_generation",
        model_role="structured",
        prompt=prompt,
        schema_model=MCQGenerationPayload,
        output_schema_name="MCQGenerationPayload",
    )

    result = await gateway.generate_structured(req)

    assert result.validated is True
    assert result.data is not None
    payload = MCQGenerationPayload.model_validate(result.data)
    assert payload.question_type == "mcq"
    assert len(payload.options) == 4
    assert payload.correct_option in {"A", "B", "C", "D"}
    assert "chunk-101" in payload.source_chunk_ids


@pytest.mark.asyncio
async def test_gemini_assessment_open_ended_grading(gemini_configured):
    gateway = get_gateway()
    prompt = (
        "Grade this learner answer against the rubric.\n\n"
        "QUESTION: What molecule stores energy produced by mitochondria?\n"
        "REFERENCE ANSWER: Adenosine triphosphate (ATP) stores the chemical energy produced by mitochondria.\n"
        "RUBRIC CRITERIA:\n"
        "- criterion: Identifies ATP as the energy storage molecule, weight: 1.0\n\n"
        "<learner_answer>\nThe molecule is ATP (adenosine triphosphate).</learner_answer>\n"
    )
    req: StructuredRequest[OpenEndedGradingPayload] = StructuredRequest(
        feature="assessment_open_ended_grading",
        model_role="structured",
        prompt=prompt,
        schema_model=OpenEndedGradingPayload,
        output_schema_name="OpenEndedGradingPayload",
    )

    result = await gateway.generate_structured(req)

    assert result.validated is True
    assert result.data is not None
    payload = OpenEndedGradingPayload.model_validate(result.data)
    assert payload.correct is True
    assert payload.score >= 0.7
    assert len(payload.criteria) >= 1


@pytest.mark.asyncio
async def test_gemini_auth_failure_handling():
    """Verify that an invalid API key immediately raises AIProviderDown without looping."""
    from app.ai.gemini import GeminiProvider
    from app.platform.config import Settings

    bad_settings = Settings(
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="invalid-key-test-abc-123",
        GEMINI_MODEL="gemini-2.5-flash",
    )
    provider = GeminiProvider()
    req = GenerationRequest(
        feature="test_auth_fail",
        model_role="generation",
        prompt="Say hello",
    )
    try:
        with pytest.raises(AIProviderDown) as exc_info:
            await provider.generate(req, bad_settings)
        assert (
            "authentication" in str(exc_info.value).lower() or "api" in str(exc_info.value).lower()
        )
    finally:
        await provider.aclose()
