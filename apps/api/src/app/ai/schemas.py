"""Provider-neutral AI schemas (ADR-0015 interface envelopes).

Common envelope on every result: correlation/version/usage/cost metadata.
Domain code depends on these types and on `AIGateway` only — never on a
provider SDK (enforced by scripts/check_boundaries.py in CI).
"""

from __future__ import annotations

import time
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

ModelRole = str  # "generation" | "structured" | "embedding" | "rerank" | "evaluation" | "vision"


class UsageMetadata(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    items: int | None = None
    latency_ms: int
    time_to_first_token_ms: int | None = None


class CostMetadata(BaseModel):
    estimated_cost_usd: float | None = None
    price_table_ref: str | None = None


class CallMetadata(BaseModel):
    ai_request_id: str
    correlation_id: str | None = None
    request_id: str | None = None
    feature: str
    model_role: ModelRole
    provider: str
    model: str
    prompt_id: str | None = None
    prompt_version: str | None = None
    fallback_from: str | None = None
    usage: UsageMetadata
    cost: CostMetadata = Field(default_factory=CostMetadata)


T = TypeVar("T")


class GenerationRequest(BaseModel):
    feature: str
    model_role: ModelRole = "generation"
    prompt_id: str | None = None
    prompt_version: str | None = None
    prompt: str
    system: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool = False


class GenerationResult(BaseModel):
    text: str
    finish_reason: str | None = None
    meta: CallMetadata


class StructuredRequest(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    feature: str
    model_role: ModelRole = "structured"
    prompt_id: str | None = None
    prompt_version: str | None = None
    prompt: str
    output_schema_name: str  # registered schema the result must validate against
    schema_model: type[BaseModel] | None = None  # caller-supplied pydantic model (preferred)
    max_tokens: int | None = None
    temperature: float = 0.0


class StructuredResult(BaseModel, Generic[T]):
    data: dict | None = None
    validated: bool = False
    validation_errors: list[str] | None = None
    attempts: int = 1
    meta: CallMetadata


class EmbeddingRequest(BaseModel):
    feature: str
    model_role: ModelRole = "embedding"
    texts: list[str]
    batch_size: int | None = None


class EmbeddingResult(BaseModel):
    vectors: list[list[float]]
    dimensions: int
    meta: CallMetadata


class RerankRequest(BaseModel):
    feature: str
    model_role: ModelRole = "rerank"
    query: str
    candidates: list[str]
    top_n: int | None = None


class RerankHit(BaseModel):
    index: int
    score: float


class RerankResult(BaseModel):
    ranked: list[RerankHit]
    meta: CallMetadata


class EvaluationRequest(BaseModel):
    feature: str
    model_role: ModelRole = "evaluation"
    rubric_ref: str | None = None
    subject: str
    output_schema_name: str
    schema_model: type[BaseModel] | None = None
    temperature: float = 0.0


class EvaluationResult(BaseModel):
    data: dict | None = None
    validated: bool = False
    validation_errors: list[str] | None = None
    meta: CallMetadata


class AIRequestRecord(BaseModel):
    """The `ai_requests`-style telemetry spine row (FR-81/82) — persisted per call."""

    meta: CallMetadata
    status: str  # success | timeout | provider_error | invalid_output | rate_limited | cancelled
    error_type: str | None = None
    created_at_epoch_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
