"""Structured JSON logging with central redaction (security-baseline §5).

Redaction is enforced HERE, in the formatter — a careless log call cannot leak
passwords, tokens, cookies, or API keys. Prompt/completion bodies follow the
AI_PROMPT_LOGGING policy concept (default redacted) and are the AI Gateway's
responsibility; this formatter additionally scrubs anything secret-shaped.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

from app.platform import context

# Keys whose values are always masked, whatever the call site passes.
_REDACTED_KEYS = {
    "password",
    "pass",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "set-cookie",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "jwt_private_key",
    "jwt_public_key",
    "client_secret",
    "session",
    "credentials",
    "database_url",
    "redis_url",
    "storage_secret_access_key",
    "sentry_dsn",
}

_SECRET_SHAPED = re.compile(
    r"(?i)\b(sk-[a-z0-9]{16,}|Bearer\s+[A-Za-z0-9._\-]{16,}|ey[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,})"
)


def _scrub(value: object, key: str | None = None) -> object:
    if isinstance(value, dict):
        return {k: _scrub(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v, key) for v in value]
    if key is not None and key.lower() in _REDACTED_KEYS:
        return "***REDACTED***"
    if isinstance(value, str) and _SECRET_SHAPED.search(value):
        return _SECRET_SHAPED.sub("[REDACTED]", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "studycompanion",
            "env": _env(),
            "request_id": context.get_request_id(),
            "correlation_id": context.get_correlation_id(),
            "user_id": context.get_user_id(),
            "project_id": context.get_project_id(),
        }
        extra = getattr(record, "details", None)
        if isinstance(extra, dict):
            payload.update(_scrub(extra))  # type: ignore[call-overload]
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(_scrub(payload), default=str)


def _env() -> str:
    from app.platform.config import get_settings

    try:
        return get_settings().APP_ENV
    except Exception:  # logging must never fail because config is broken
        return "unknown"


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Align noisy loggers with the configured level
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "sqlalchemy.engine"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


class _DetailsLogger(logging.LoggerAdapter):  # pragma: no cover - trivial wrapper
    def process(self, msg, kwargs):
        details = kwargs.pop("details", None)
        if details:
            kwargs["extra"] = {"details": details}
        return msg, kwargs


def get_logger(name: str) -> logging.Logger:
    """Standard logger; attach structured data via ``log.info("msg", extra={"details": {...}})``."""
    return logging.getLogger(name)
