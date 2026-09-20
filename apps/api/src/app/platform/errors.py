"""Domain error taxonomy and problem+json mapping (RFC 9457).

Errors follow the contract in module-contracts: typed domain errors map to
stable machine-readable problem documents; internal details never reach the
client — the client receives the request/correlation ids it can quote.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

PROBLEM_BASE = "https://api.studycompanion.app/errors/"


class DomainError(Exception):
    """Base for all safe-to-show domain errors."""

    status_code = 400
    title = "Bad request"
    error_type = "bad-request"
    retryable = False

    def __init__(self, detail: str | None = None, **context: Any) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.context = context


class ValidationError(DomainError):
    status_code = 422
    title = "Validation failed"
    error_type = "validation-error"


class AuthenticationError(DomainError):
    """401 — missing/invalid credentials. Detail is deliberately generic:
    never reveals whether an email exists, a password was wrong, or a token
    failed signature vs. expiry (API error contract, Part 18)."""

    status_code = 401
    title = "Unauthorized"
    error_type = "unauthorized"


class RateLimitedError(DomainError):
    status_code = 429
    title = "Too many requests"
    error_type = "rate-limited"
    retryable = True


class NotFound(DomainError):
    """404 — used for non-owned resources too (never 403; ADR-0002/ADR-0021)."""

    status_code = 404
    title = "Not found"
    error_type = "not-found"


class AuthorizationError(DomainError):
    """403 — capability/policy denial only (ADR-0021/Q5)."""

    status_code = 403
    title = "Forbidden"
    error_type = "forbidden"


class ConflictError(DomainError):
    status_code = 409
    title = "Conflict"
    error_type = "conflict"


class IdempotentReplayError(ConflictError):
    title = "Request already processed with a different payload"
    error_type = "idempotency-conflict"


class DependencyError(DomainError):
    status_code = 503
    title = "Dependency unavailable"
    error_type = "dependency-unavailable"
    retryable = True


class ScopeViolation(DomainError):
    """Cross-scope access attempt — alert-worthy, never silently filtered (principles §2)."""

    status_code = 403
    title = "Scope violation"
    error_type = "scope-violation"


# --- AI error taxonomy (ADR-0015) — raised by the gateway, translated by callers ---


class AIError(DomainError):
    status_code = 502
    title = "AI provider error"
    error_type = "ai-error"
    retryable = True


class AITimeout(AIError):
    error_type = "ai-timeout"


class AIRateLimited(AIError):
    status_code = 429
    error_type = "ai-rate-limited"


class AIProviderDown(AIError):
    error_type = "ai-provider-down"


class AIInvalidOutput(AIError):
    status_code = 502
    title = "AI produced invalid output"
    error_type = "ai-invalid-output"
    retryable = False


class AIBudgetExhausted(AIError):
    status_code = 429
    title = "AI budget exhausted"
    error_type = "ai-budget-exhausted"
    retryable = False


def problem_response(request: Request, exc: DomainError) -> JSONResponse:
    from app.platform import context

    request_id = getattr(request.state, "request_id", None) or context.get_request_id()
    correlation_id = getattr(request.state, "correlation_id", None) or context.get_correlation_id()
    body = {
        "type": f"{PROBLEM_BASE}{exc.error_type}",
        "title": exc.title,
        "status": exc.status_code,
        "detail": exc.detail,
        "instance": request.url.path,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "retryable": exc.retryable,
    }
    return JSONResponse(
        status_code=exc.status_code, content=body, media_type="application/problem+json"
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, problem_response)  # type: ignore[arg-type]
