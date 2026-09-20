"""AI infrastructure routes — Phase 0 introspection only (no product endpoints).

Exposes gateway/provider status and the in-memory telemetry spine so the
vertical slice and developers can inspect AI call metadata. Product features
(tutor etc.) arrive in later phases and will NOT be defined here.
"""

from __future__ import annotations

from app.ai import telemetry
from app.ai.gateway import get_registry
from app.platform.config import get_settings
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/internal/ai", tags=["ai-infrastructure"])


@router.get("/status")
async def ai_status() -> dict:
    settings = get_settings()
    registry = get_registry()
    return {
        "registry": settings.AI_PROVIDER_REGISTRY,
        "registered_providers": sorted(
            registry._adapters.keys()
        ),  # noqa: SLF001 - introspection route
        "roles": {
            "generation": [settings.AI_GENERATION_PROVIDER, settings.AI_GENERATION_MODEL],
            "structured": [settings.AI_STRUCTURED_PROVIDER, settings.AI_STRUCTURED_MODEL],
            "embedding": [settings.AI_EMBEDDING_PROVIDER, settings.AI_EMBEDDING_MODEL],
            "rerank": [settings.AI_RERANKER_PROVIDER, settings.AI_RERANKER_MODEL],
            "evaluation": [settings.AI_EVALUATION_PROVIDER, settings.AI_EVALUATION_MODEL],
            "vision": [settings.AI_VISION_PROVIDER, settings.AI_VISION_MODEL],
        },
    }


@router.get("/telemetry")
async def ai_telemetry() -> dict:
    records = telemetry.all_records()
    return {
        "count": len(records),
        "records": [
            {
                "ai_request_id": r.meta.ai_request_id,
                "correlation_id": r.meta.correlation_id,
                "request_id": r.meta.request_id,
                "feature": r.meta.feature,
                "model_role": r.meta.model_role,
                "provider": r.meta.provider,
                "model": r.meta.model,
                "status": r.status,
                "error_type": r.error_type,
                "latency_ms": r.meta.usage.latency_ms,
                "input_tokens": r.meta.usage.input_tokens,
                "output_tokens": r.meta.usage.output_tokens,
                "estimated_cost_usd": r.meta.cost.estimated_cost_usd,
                "fallback_from": r.meta.fallback_from,
            }
            for r in records
        ],
    }


@router.get("/telemetry/{ai_request_id}")
async def ai_telemetry_record(ai_request_id: str) -> dict:
    record = telemetry.find_by_request(ai_request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="AI request record not found")
    return {
        "ai_request_id": record.meta.ai_request_id,
        "correlation_id": record.meta.correlation_id,
        "feature": record.meta.feature,
        "provider": record.meta.provider,
        "model": record.meta.model,
        "status": record.status,
        "latency_ms": record.meta.usage.latency_ms,
    }
