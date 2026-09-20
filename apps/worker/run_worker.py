"""Celery worker entrypoint (same image/codebase as API; different entry — ADR-0001).

Phase 0: consumes all queues from one worker; queue separation is already
configured so splitting per queue later is a config/deploy change only.
Start: python apps/worker/run_worker.py  (or the compose service)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "api" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.jobs.tasks import celery_app  # noqa: E402
from celery.signals import (  # noqa: E402
    after_setup_logger,
    after_setup_task_logger,
    setup_logging,
)


@setup_logging.connect
def _configure_worker_logging(**_kwargs):  # pragma: no cover - signal
    """Keep our JSON formatter (redaction + correlation fields) instead of Celery's hijack (ADR-0020)."""
    from app.platform.logging import configure_logging

    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))


@after_setup_logger.connect
@after_setup_task_logger.connect
def _enforce_json_logging(logger=None, **_kwargs):  # pragma: no cover - signal
    """Celery re-attaches its color formatter when (task) loggers are configured;
    re-assert our JSON formatter so redaction + correlation fields always win."""
    import logging

    from app.platform.logging import JsonFormatter

    if logger is not None:
        logger.handlers = [h for h in logger.handlers if isinstance(h.formatter, JsonFormatter)]
        logger.propagate = True
    root = logging.getLogger()
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.handlers = [handler]


def main() -> None:
    concurrency = int(os.environ.get("WORKER_CONCURRENCY", "2"))
    # Windows: Celery's prefork (billiard) pool is unsupported there — use solo/threads.
    default_pool = "solo" if sys.platform.startswith("win") else "prefork"
    pool = os.environ.get("WORKER_POOL", default_pool)
    # Celery 5 requires the sub-command in argv for worker_main.
    celery_app.worker_main(
        [
            "worker",
            "-Q",
            "documents,learning,analytics,evaluation,default",
            "--pool",
            pool,
            "--concurrency",
            str(concurrency),
            "--loglevel",
            os.environ.get("LOG_LEVEL", "INFO"),
            "--without-gossip",
            "--without-mingle",
        ]
    )


if __name__ == "__main__":
    main()
