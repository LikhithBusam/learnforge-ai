"""AI call telemetry — Phase 0 in-memory spine.

Records one entry per gateway call (success AND failure) with the fields the
architecture requires (FR-81/82): correlation, role, provider/model, feature,
latency, tokens, cost, status. Persistence into an `ai_requests`-class table
arrives with the database-schema phase; the record shape is already the
contract (app.ai.schemas.AIRequestRecord), so the swap is additive.
"""

from __future__ import annotations

import threading
from collections import deque

from app.ai.schemas import AIRequestRecord
from app.platform.logging import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_records: deque[AIRequestRecord] = deque(maxlen=1000)


def record(record_entry: AIRequestRecord) -> None:
    with _lock:
        _records.append(record_entry)
    # Structured log line with the identifiers (never prompt/completion bodies).
    logger.info(
        "ai_request",
        extra={
            "details": {
                "ai_request_id": record_entry.meta.ai_request_id,
                "correlation_id": record_entry.meta.correlation_id,
                "request_id": record_entry.meta.request_id,
                "feature": record_entry.meta.feature,
                "model_role": record_entry.meta.model_role,
                "provider": record_entry.meta.provider,
                "model": record_entry.meta.model,
                "prompt_id": record_entry.meta.prompt_id,
                "prompt_version": record_entry.meta.prompt_version,
                "status": record_entry.status,
                "error_type": record_entry.error_type,
                "input_tokens": record_entry.meta.usage.input_tokens,
                "output_tokens": record_entry.meta.usage.output_tokens,
                "latency_ms": record_entry.meta.usage.latency_ms,
                "ttft_ms": record_entry.meta.usage.time_to_first_token_ms,
                "estimated_cost_usd": record_entry.meta.cost.estimated_cost_usd,
                "fallback_from": record_entry.meta.fallback_from,
            }
        },
    )


def all_records() -> list[AIRequestRecord]:
    with _lock:
        return list(_records)


def find_by_correlation(correlation_id: str) -> list[AIRequestRecord]:
    with _lock:
        return [r for r in _records if r.meta.correlation_id == correlation_id]


def find_by_request(ai_request_id: str) -> AIRequestRecord | None:
    with _lock:
        for r in _records:
            if r.meta.ai_request_id == ai_request_id:
                return r
    return None


def reset() -> None:
    with _lock:
        _records.clear()
