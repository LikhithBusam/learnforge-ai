"""Request context propagation.

Holds request-scoped identity (request id, correlation id, principal ids) in
context variables so logs, AI telemetry, and task envelopes can join one trace.
Tasks receive values explicitly in their envelope and re-bind them on the
worker side (see app.jobs.signals) — contextvars do not cross the broker.
"""

from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass, field

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)
_project_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("project_id", default=None)
_event_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("event_id", default=None)
_extra: contextvars.ContextVar[dict | None] = contextvars.ContextVar("context_extra", default=None)
# ContextVar.mapped default may be None (B039) — get_extra() guarantees a dict.


def new_id() -> str:
    return str(uuid.uuid4())


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def set_correlation_id(value: str | None) -> None:
    _correlation_id.set(value)


def set_user_id(value: str | None) -> None:
    _user_id.set(value)


def set_project_id(value: str | None) -> None:
    _project_id.set(value)


def set_event_id(value: str | None) -> None:
    """Bind the outbox event id that caused this work (Part 9 propagation)."""
    _event_id.set(value)


def set_extra(values: dict) -> None:
    _extra.set(values)


def get_request_id() -> str | None:
    return _request_id.get()


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def get_user_id() -> str | None:
    return _user_id.get()


def get_project_id() -> str | None:
    return _project_id.get()


def get_event_id() -> str | None:
    return _event_id.get()


def get_extra() -> dict:
    value = _extra.get()
    return value if isinstance(value, dict) else {}


@dataclass
class ContextSnapshot:
    """Serializable context for task envelopes / cross-boundary propagation."""

    request_id: str | None = None
    correlation_id: str | None = None
    user_id: str | None = None
    project_id: str | None = None
    event_id: str | None = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def capture(cls) -> ContextSnapshot:
        return cls(
            request_id=_request_id.get(),
            correlation_id=_correlation_id.get(),
            user_id=_user_id.get(),
            project_id=_project_id.get(),
            event_id=_event_id.get(),
            extra=dict(get_extra()),
        )

    def apply(self) -> None:
        """Re-bind into the current execution context (e.g. inside a worker task)."""
        set_request_id(self.request_id)
        set_correlation_id(self.correlation_id)
        set_user_id(self.user_id)
        set_project_id(self.project_id)
        set_event_id(self.event_id)
        set_extra(dict(self.extra))

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "event_id": self.event_id,
            "extra": dict(self.extra),
        }
