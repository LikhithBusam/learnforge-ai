"""AI Gateway — the single egress to model providers (ADR-0007/0015).

Domain modules depend on `AIGateway` (or `get_gateway()`), never on provider
SDKs (enforced by scripts/check_boundaries.py). Every call passes through:
role routing → provider call (timeout/budget) → local validation for
structured output → typed error taxonomy → telemetry record.

Phase 0 registry contains only the deterministic `stub` provider (no network,
no keys). Real adapters land after the ADR-0015 vendor trial; the interface
envelopes here are already the contract.
"""

from __future__ import annotations

import time
import uuid
from typing import TypeVar

from app.ai import telemetry
from app.ai.adapter import ProviderAdapter
from app.ai.gemini import GeminiProvider
from app.ai.schemas import (
    AIRequestRecord,
    CallMetadata,
    CostMetadata,
    EmbeddingRequest,
    EmbeddingResult,
    EvaluationRequest,
    EvaluationResult,
    GenerationRequest,
    GenerationResult,
    RerankRequest,
    RerankResult,
    StructuredRequest,
    StructuredResult,
    UsageMetadata,
)
from app.platform import context
from app.platform.config import get_settings
from app.platform.errors import (
    AIBudgetExhausted,
    AIInvalidOutput,
    AIProviderDown,
    AIRateLimited,
    AITimeout,
)
from app.platform.logging import get_logger
from pydantic import BaseModel, ValidationError

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class StubProvider(ProviderAdapter):
    """Deterministic offline provider — identifies itself as `stub` everywhere.

    Deterministic for CI: no randomness, no network, no keys; structured
    output honors a `{"stub_payload": {...}}` directive embedded in the prompt
    (used by tests to force validation-failure paths deterministically).
    """

    name = "stub"

    async def generate(self, req, settings):
        started = time.perf_counter()
        text = f"[stub:{req.model_role}] {req.prompt}"
        usage = UsageMetadata(
            input_tokens=max(1, len(req.prompt) // 4),
            output_tokens=max(1, len(text) // 4),
            latency_ms=_elapsed_ms(started),
        )
        return text, "stop", usage, None

    async def generate_structured(self, req, settings):
        started = time.perf_counter()
        attempts = 1
        import json as _json
        import re as _re

        payload: dict | None = None
        if '{"stub_payload"' in req.prompt:
            try:
                start = req.prompt.index('{"stub_payload"')
                # raw_decode handles nested JSON correctly ("} search would not)
                payload, _ = _json.JSONDecoder().raw_decode(req.prompt[start:])
                payload = payload.get("stub_payload")
            except Exception:  # noqa: BLE001
                payload = None
        if payload is None:
            if "tutor" in req.feature:
                chunk_match = _re.search(r'<chunk id="([^"]+)"[^>]*page_start="(\d+)"', req.prompt)
                if chunk_match:
                    cid = chunk_match.group(1)
                    page = int(chunk_match.group(2))
                    payload = {
                        "answer": "Based on the project materials, here is the verified explanation.",
                        "citations": [
                            {"chunk_id": cid, "page": page, "quote": "verified explanation"}
                        ],
                        "grounded": True,
                        "refusal": False,
                    }
                else:
                    payload = {
                        "answer": "I could not find enough supporting information in the project materials to answer that reliably.",
                        "citations": [],
                        "grounded": False,
                        "refusal": True,
                        "refusal_reason": "no_evidence",
                    }
            elif "assessment_question_generation" in req.feature:
                # Extract chunk id from evidence for grounded stub output
                chunk_match = _re.search(r'<chunk id="([^"]+)"', req.prompt)
                chunk_id = chunk_match.group(1) if chunk_match else "stub-chunk-001"
                difficulty_match = _re.search(r"(easy|medium|hard)", req.prompt, _re.IGNORECASE)
                difficulty = difficulty_match.group(1).lower() if difficulty_match else "medium"
                is_open_ended = (
                    "open_ended" in req.output_schema_name or "OpenEnded" in req.output_schema_name
                )
                if is_open_ended:
                    payload = {
                        "question_type": "open_ended",
                        "difficulty": difficulty,
                        "question": "Explain the main concept described in the evidence material.",
                        "reference_answer": (
                            "The main concept described involves key principles from the study material. "
                            "A complete answer covers the primary mechanism, its purpose, and its implications."
                        ),
                        "rubric": [
                            {"criterion": "Describes the primary mechanism", "weight": 0.4},
                            {"criterion": "Explains the purpose or motivation", "weight": 0.35},
                            {"criterion": "Discusses implications or outcomes", "weight": 0.25},
                        ],
                        "source_chunk_ids": [chunk_id],
                    }
                else:
                    payload = {
                        "question_type": "mcq",
                        "difficulty": difficulty,
                        "question": "Which of the following best describes the concept from the evidence?",
                        "options": [
                            {"id": "A", "text": "The correct explanation from the evidence"},
                            {"id": "B", "text": "An incorrect but plausible alternative"},
                            {"id": "C", "text": "A different incorrect alternative"},
                            {"id": "D", "text": "Another incorrect alternative"},
                        ],
                        "correct_option": "A",
                        "explanation": "Option A is correct because it accurately reflects the evidence provided.",
                        "source_chunk_ids": [chunk_id],
                    }
            elif "assessment_open_ended_grading" in req.feature:
                # Stub grader: analyze overlap between reference answer and learner answer
                learner_match = _re.search(
                    r"<learner_answer>\s*(.*?)\s*</learner_answer>", req.prompt, _re.DOTALL
                )
                learner_text = learner_match.group(1) if learner_match else ""
                learner_words = set(_re.findall(r"\w+", learner_text.lower()))
                ref_words = set(_re.findall(r"\w+", req.prompt.lower()))
                # Simple overlap heuristic for deterministic stub scoring
                meaningful_ref = {w for w in ref_words if len(w) > 4} - {
                    "which",
                    "their",
                    "these",
                    "those",
                    "about",
                    "above",
                    "after",
                    "below",
                    "learner",
                    "answer",
                    "reference",
                    "rubric",
                    "question",
                    "explain",
                }
                overlap_ratio = len(learner_words & meaningful_ref) / max(len(meaningful_ref), 1)
                score = round(min(0.95, max(0.1, overlap_ratio * 1.5)), 2)
                correct = score >= 0.5
                # Check for obvious injection attempt
                if "ignore" in learner_text.lower() and (
                    "rubric" in learner_text.lower() or "100" in learner_text
                ):
                    # Grade the actual content, ignore the injection attempt
                    score = 0.15
                    correct = False
                payload = {
                    "score": score,
                    "criteria": [
                        {
                            "criterion": "Addresses the core concept",
                            "score": round(score, 2),
                            "feedback": (
                                "Good coverage of the main concept."
                                if correct
                                else "Insufficient coverage of the main concept."
                            ),
                        }
                    ],
                    "correct": correct,
                    "feedback": (
                        "Well done! Your answer demonstrates understanding of the material."
                        if correct
                        else "Your answer did not sufficiently address the required concepts."
                    ),
                    "confidence": 0.80,
                }
            else:
                payload = {"stub": True, "model_role": req.model_role}
        usage = UsageMetadata(
            input_tokens=max(1, len(req.prompt) // 4),
            output_tokens=16,
            latency_ms=_elapsed_ms(started),
        )
        return payload, True, None, attempts, usage, None

    async def embed(self, req, settings):
        started = time.perf_counter()
        dims = max(1, int(settings.AI_EMBEDDING_DIMENSIONS))
        vectors = [[float((len(t) * (i + 1)) % 7) + 0.1 for i in range(dims)] for t in req.texts]
        usage = UsageMetadata(items=len(req.texts), latency_ms=_elapsed_ms(started))
        return vectors, dims, usage, None

    async def rerank(self, req, settings):
        started = time.perf_counter()
        import re as _re

        stopwords = {
            "what",
            "is",
            "the",
            "a",
            "an",
            "and",
            "in",
            "of",
            "to",
            "for",
            "how",
            "does",
            "by",
            "with",
            "at",
            "from",
            "on",
            "are",
            "as",
            "this",
            "that",
            "it",
            "these",
            "those",
        }
        query_words = {
            w for w in _re.findall(r"\w+", req.query.lower()) if len(w) > 2 and w not in stopwords
        }

        scored: list[dict] = []
        for i, cand in enumerate(req.candidates):
            cand_words = {w for w in _re.findall(r"\w+", cand.lower()) if len(w) > 2}
            overlap = query_words & cand_words
            if query_words:
                ratio = len(overlap) / len(query_words)
            else:
                ratio = 0.0

            if ratio > 0:
                score = round(min(0.98, 0.60 + 0.38 * ratio), 4)
            else:
                score = 0.15
            scored.append({"index": i, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[: req.top_n or len(scored)]
        usage = UsageMetadata(items=len(req.candidates), latency_ms=_elapsed_ms(started))
        return top, usage, None

    async def evaluate(self, req, settings):
        started = time.perf_counter()
        data = {"stub": True, "scores": {"overall": 0.0}}
        usage = UsageMetadata(
            input_tokens=max(1, len(req.subject) // 4),
            output_tokens=8,
            latency_ms=_elapsed_ms(started),
        )
        return data, True, None, usage, None


def _elapsed_ms(started: float) -> int:
    return max(1, int((time.perf_counter() - started) * 1000))


class _Registry:
    def __init__(self) -> None:
        self._adapters: dict[str, ProviderAdapter] = {
            "stub": StubProvider(),
            "gemini": GeminiProvider(),
        }

    def resolve(self, provider_name: str) -> ProviderAdapter:
        adapter = self._adapters.get(provider_name)
        if adapter is None:
            raise AIProviderDown(f"AI provider '{provider_name}' is not registered")
        return adapter

    def register(self, adapter: ProviderAdapter) -> None:
        self._adapters[adapter.name] = adapter


_registry = _Registry()


def get_registry() -> _Registry:
    return _registry


class AIGateway:
    """The only path from domain code to model providers (module-contracts §M.11)."""

    def __init__(self) -> None:
        self._settings = get_settings()

    # -- internals --

    def _meta_builder(
        self,
        feature: str,
        role: str,
        provider: str,
        model: str,
        prompt_id=None,
        prompt_version=None,
        fallback_from=None,
    ):
        def build(ai_request_id: str, usage: UsageMetadata) -> CallMetadata:
            return CallMetadata(
                ai_request_id=ai_request_id,
                correlation_id=context.get_correlation_id(),
                request_id=context.get_request_id(),
                feature=feature,
                model_role=role,
                provider=provider,
                model=model,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                fallback_from=fallback_from,
                usage=usage,
                cost=self._estimate_cost(role, provider, model, usage),
            )

        return build

    def _estimate_cost(
        self, role: str, provider: str, model: str, usage: UsageMetadata
    ) -> CostMetadata:
        # Stub pricing table: zero cost, clearly labelled. Real table lands with the vendor trial (A-17).
        if provider == "stub":
            return CostMetadata(estimated_cost_usd=0.0, price_table_ref="stub:zero-cost")
        return CostMetadata(estimated_cost_usd=None, price_table_ref=None)

    def _budget_check(self, feature: str) -> None:
        # Phase 0: per-user daily budgets arrive with identity; the gate exists here so the
        # failure path is exercised by tests rather than bolted on later (ADR-0015).
        settings = self._settings
        if settings.AI_USER_DAILY_TOKEN_BUDGET and settings.AI_USER_DAILY_TOKEN_BUDGET < 0:
            raise AIBudgetExhausted("AI daily budget exhausted")

    def _resolve(self, role_settings: tuple[str, str]):
        provider_name, model = role_settings
        adapter = _registry.resolve(provider_name)
        return adapter, provider_name, model

    def _finish(self, record: AIRequestRecord) -> None:
        telemetry.record(record)

    def _fail(
        self,
        exc: Exception,
        feature: str,
        role: str,
        provider: str,
        model: str,
        started: float,
        prompt_id=None,
        prompt_version=None,
    ) -> Exception:
        error_type = (
            "timeout"
            if isinstance(exc, AITimeout)
            else (
                "rate_limited"
                if isinstance(exc, AIRateLimited)
                else "invalid_output" if isinstance(exc, AIInvalidOutput) else "provider_error"
            )
        )
        self._finish(
            AIRequestRecord(
                meta=self._meta_builder(feature, role, provider, model, prompt_id, prompt_version)(
                    ai_request_id=str(uuid.uuid4()),
                    usage=UsageMetadata(latency_ms=_elapsed_ms(started)),
                ),
                status=error_type,
                error_type=type(exc).__name__,
            )
        )
        return exc

    # -- operations --

    async def generate(self, req: GenerationRequest) -> GenerationResult:
        self._budget_check(req.feature)
        started = time.perf_counter()
        adapter, provider, model = self._resolve(
            (self._settings.AI_GENERATION_PROVIDER, self._settings.AI_GENERATION_MODEL)
        )
        build_meta = self._meta_builder(
            req.feature, req.model_role, provider, model, req.prompt_id, req.prompt_version
        )
        try:
            text, finish_reason, usage, error_type = await adapter.generate(req, self._settings)
            meta = build_meta(str(uuid.uuid4()), usage)
            status = "success" if error_type is None else "provider_error"
            self._finish(AIRequestRecord(meta=meta, status=status, error_type=error_type))
            return GenerationResult(text=text, finish_reason=finish_reason, meta=meta)
        except AITimeout as exc:
            raise self._fail(
                exc,
                req.feature,
                req.model_role,
                provider,
                model,
                started,
                req.prompt_id,
                req.prompt_version,
            ) from exc
        except (AIRateLimited, AIProviderDown) as exc:
            raise self._fail(
                exc,
                req.feature,
                req.model_role,
                provider,
                model,
                started,
                req.prompt_id,
                req.prompt_version,
            ) from exc

    async def generate_structured(self, req: StructuredRequest) -> StructuredResult:
        self._budget_check(req.feature)
        started = time.perf_counter()
        adapter, provider, model = self._resolve(
            (self._settings.AI_STRUCTURED_PROVIDER, self._settings.AI_STRUCTURED_MODEL)
        )
        build_meta = self._meta_builder(
            req.feature, req.model_role, provider, model, req.prompt_id, req.prompt_version
        )
        try:
            (
                data,
                validated,
                _errors,
                attempts,
                usage,
                error_type,
            ) = await adapter.generate_structured(req, self._settings)
            # Local validation is authoritative (principle §4): provider schema modes are not trusted.
            model_cls = req.schema_model
            if validated and model_cls is not None and data is not None:
                try:
                    model_cls.model_validate(data)
                except ValidationError:
                    validated = False
            if not validated:
                err = AIInvalidOutput("Structured output failed schema validation")
                self._finish(
                    AIRequestRecord(
                        meta=build_meta(str(uuid.uuid4()), usage),
                        status="invalid_output",
                        error_type="AIInvalidOutput",
                    )
                )
                raise err
            meta = build_meta(str(uuid.uuid4()), usage)
            self._finish(AIRequestRecord(meta=meta, status="success"))
            return StructuredResult(
                data=data, validated=True, validation_errors=None, attempts=attempts, meta=meta
            )
        except AIInvalidOutput as exc:
            raise self._fail(
                exc,
                req.feature,
                req.model_role,
                provider,
                model,
                started,
                req.prompt_id,
                req.prompt_version,
            ) from exc

    async def embed(self, req: EmbeddingRequest) -> EmbeddingResult:
        self._budget_check(req.feature)
        started = time.perf_counter()
        adapter, provider, model = self._resolve(
            (self._settings.AI_EMBEDDING_PROVIDER, self._settings.AI_EMBEDDING_MODEL)
        )
        build_meta = self._meta_builder(req.feature, req.model_role, provider, model)
        try:
            vectors, dims, usage, error_type = await adapter.embed(req, self._settings)
            meta = build_meta(str(uuid.uuid4()), usage)
            self._finish(
                AIRequestRecord(
                    meta=meta, status="success" if error_type is None else "provider_error"
                )
            )
            return EmbeddingResult(vectors=vectors, dimensions=dims, meta=meta)
        except (AITimeout, AIRateLimited, AIProviderDown) as exc:
            raise self._fail(exc, req.feature, req.model_role, provider, model, started) from exc

    async def rerank(self, req: RerankRequest) -> RerankResult:
        self._budget_check(req.feature)
        started = time.perf_counter()
        adapter, provider, model = self._resolve(
            (self._settings.AI_RERANKER_PROVIDER, self._settings.AI_RERANKER_MODEL)
        )
        build_meta = self._meta_builder(req.feature, req.model_role, provider, model)
        try:
            ranked, usage, error_type = await adapter.rerank(req, self._settings)
            meta = build_meta(str(uuid.uuid4()), usage)
            self._finish(
                AIRequestRecord(
                    meta=meta, status="success" if error_type is None else "provider_error"
                )
            )
            from app.ai.schemas import RerankHit

            return RerankResult(ranked=[RerankHit(**hit) for hit in ranked], meta=meta)
        except (AITimeout, AIRateLimited, AIProviderDown) as exc:
            raise self._fail(exc, req.feature, req.model_role, provider, model, started) from exc

    async def evaluate(self, req: EvaluationRequest) -> EvaluationResult:
        self._budget_check(req.feature)
        started = time.perf_counter()
        adapter, provider, model = self._resolve(
            (self._settings.AI_EVALUATION_PROVIDER, self._settings.AI_EVALUATION_MODEL)
        )
        build_meta = self._meta_builder(req.feature, req.model_role, provider, model)
        try:
            data, validated, errors, usage, error_type = await adapter.evaluate(req, self._settings)
            model_cls = req.schema_model
            if validated and model_cls is not None and data is not None:
                try:
                    model_cls.model_validate(data)
                except ValidationError as ve:
                    validated, errors = False, [str(e) for e in ve.errors()]
            meta = build_meta(str(uuid.uuid4()), usage)
            self._finish(
                AIRequestRecord(meta=meta, status="success" if validated else "invalid_output")
            )
            return EvaluationResult(
                data=data, validated=validated, validation_errors=errors, meta=meta
            )
        except (AITimeout, AIRateLimited, AIProviderDown) as exc:
            raise self._fail(exc, req.feature, req.model_role, provider, model, started) from exc


_gateway: AIGateway | None = None


def get_gateway() -> AIGateway:
    global _gateway
    if _gateway is None:
        _gateway = AIGateway()
    return _gateway


def reset_gateway() -> None:
    global _gateway
    _gateway = None
