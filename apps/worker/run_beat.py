"""Celery Beat entrypoint — Phase 0 schedules only (infrastructure heartbeat)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "api" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.jobs.tasks import celery_app  # noqa: E402
from celery.signals import setup_logging  # noqa: E402


@setup_logging.connect
def _configure_beat_logging(**_kwargs):  # pragma: no cover - signal
    """Keep our JSON formatter (redaction + correlation fields) worker-plane-wide (ADR-0020)."""
    from app.platform.logging import configure_logging

    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))


def main() -> None:
    celery_app.bin.beat(
        loglevel=os.environ.get("LOG_LEVEL", "INFO"),
    )


if __name__ == "__main__":
    main()
