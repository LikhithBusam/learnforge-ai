"""Shared FastAPI utilities: middleware chain and health routers.

Middleware order follows the approved chain (architecture baseline §10.3),
Phase 0 subset: request id + correlation id + structured log context +
security headers. Auth, rate limiting, RLS context, and idempotency land with
their owning phases; each is a dependency/middleware insertion point here.
"""

from __future__ import annotations

import time

from app.platform import context, health
from app.platform.errors import register_exception_handlers
from app.platform.logging import get_logger
from fastapi import APIRouter, FastAPI, Request, Response

logger = get_logger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    # CSP is enforced by the frontend deployment; API responses are JSON-only.
}


def install_middlewares(app: FastAPI) -> None:
    @app.middleware("http")
    async def context_and_logging_middleware(request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or context.new_id()
        correlation_id = request.headers.get("X-Correlation-ID") or request_id
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        context.set_request_id(request_id)
        context.set_correlation_id(correlation_id)
        # user/project context is set by the (future) auth dependency after token verification

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)

        logger.info(
            "http_request",
            extra={
                "details": {
                    "route": request.url.path,
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                }
            },
        )
        return response


def install_exception_handlers(app: FastAPI) -> None:
    register_exception_handlers(app)


def build_health_routers() -> list[APIRouter]:
    router = APIRouter(tags=["health"])

    @router.get("/healthz")
    async def healthz() -> dict:
        return health.liveness()

    @router.get("/readyz")
    async def readyz() -> dict:
        return await health.readiness()

    return [router]
