"""FastAPI application factory — API entrypoint (modular monolith, ADR-0001).

Phase 0 registers: platform middleware + health, AI infrastructure routes,
jobs infrastructure routes. Domain routers arrive with their phases and mount
under /api/v1 (module-contracts).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from app.platform import cache, db
from app.platform.config import get_settings
from app.platform.logging import configure_logging, get_logger
from app.platform.router import (
    build_health_routers,
    install_exception_handlers,
    install_middlewares,
)
from app.platform.storage import init_storage
from fastapi import FastAPI

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    logger.info("starting", extra={"details": settings.safe_summary()})
    # Infrastructure providers initialize lazily/tolerantly: missing local
    # infra degrades readiness rather than preventing boot (dev convenience).
    if settings.DATABASE_URL:
        try:
            db.init_engine(settings)
        except RuntimeError as exc:
            logger.warning("database_init_skipped", extra={"details": {"reason": str(exc)}})
        if settings.DATABASE_RUNTIME_URL:
            try:
                db.init_runtime_engine(settings)
            except RuntimeError as exc:
                logger.warning(
                    "runtime_engine_init_skipped", extra={"details": {"reason": str(exc)}}
                )
        else:
            logger.warning(
                "runtime_engine_unconfigured",
                extra={"details": {"reason": "DATABASE_RUNTIME_URL not set"}},
            )
    if settings.REDIS_URL:
        try:
            cache.init_cache(settings)
        except RuntimeError as exc:
            logger.warning("cache_init_skipped", extra={"details": {"reason": str(exc)}})
    try:
        init_storage(settings)
    except Exception as exc:  # noqa: BLE001
        logger.warning("storage_init_skipped", extra={"details": {"reason": type(exc).__name__}})
    yield
    await db.close_engine()
    await cache.close_cache()
    logger.info("stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AI Study Companion API",
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    install_middlewares(app)
    install_exception_handlers(app)

    from app.admin.router import router as admin_router
    from app.ai.router import router as ai_router
    from app.analytics.router import router as analytics_router
    from app.assessment.router import router as assessment_router
    from app.growth.router import router as growth_router
    from app.identity.router import router as auth_router
    from app.jobs.router import router as jobs_router
    from app.mastery.router import router as mastery_router
    from app.materials.router import router as materials_router
    from app.recommendations.router import router as recommendations_router
    from app.tutor.router import router as tutor_router
    from app.workspace.router import router as workspace_router

    for router in build_health_routers():
        app.include_router(router)
    app.include_router(ai_router)
    app.include_router(jobs_router)
    app.include_router(auth_router)
    app.include_router(workspace_router)
    app.include_router(materials_router)
    app.include_router(tutor_router)
    app.include_router(assessment_router)
    app.include_router(mastery_router)
    app.include_router(growth_router)
    app.include_router(recommendations_router)
    app.include_router(analytics_router)
    app.include_router(admin_router)

    return app


app = create_app()
