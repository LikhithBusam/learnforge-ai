"""Provider adapter interface for AI Gateway (ADR-0015)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.ai.schemas import (
        EmbeddingRequest,
        EvaluationRequest,
        GenerationRequest,
        RerankRequest,
        StructuredRequest,
        UsageMetadata,
    )
    from app.platform.config import Settings


class ProviderAdapter:
    """Interface every provider adapter implements (thin: auth + mapping + error normalization)."""

    name = "abstract"

    async def generate(
        self, req: GenerationRequest, settings: Settings
    ) -> tuple[str, str | None, UsageMetadata, str | None]:
        raise NotImplementedError  # returns (text, finish_reason, usage, error_type)

    async def generate_structured(
        self, req: StructuredRequest, settings: Settings
    ) -> tuple[dict | None, bool, list[str] | None, int, UsageMetadata, str | None]:
        raise NotImplementedError  # returns (data, validated, errors, attempts, usage, error_type)

    async def embed(
        self, req: EmbeddingRequest, settings: Settings
    ) -> tuple[list[list[float]], int, UsageMetadata, str | None]:
        raise NotImplementedError

    async def rerank(
        self, req: RerankRequest, settings: Settings
    ) -> tuple[list[Any], UsageMetadata, str | None]:
        raise NotImplementedError

    async def evaluate(
        self, req: EvaluationRequest, settings: Settings
    ) -> tuple[dict | None, bool, list[str] | None, UsageMetadata, str | None]:
        raise NotImplementedError
