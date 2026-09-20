"""Run async coroutines from synchronous contexts (worker tasks).

Two execution realities exist:

* Real Celery workers run tasks with **no** running event loop → plain
  ``asyncio.run`` is correct.
* Eager mode (tests, local dispatch) runs tasks *inside* the API's event
  loop → ``asyncio.run`` is illegal. We execute on a dedicated thread with
  its own loop, propagating the ambient contextvars (request id,
  correlation id, user/project/event ids) so gateway telemetry produced on
  that thread still joins the original trace.

Infrastructure only — no business logic.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_coroutine_sync(factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Await ``factory()``'s coroutine from sync code, preserving the context.

    ``factory`` is a zero-arg callable *returning* a coroutine (not the
    coroutine itself) so the coroutine is created inside the destination
    context/thread and no running-loop check fires at call time.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    ctx = contextvars.copy_context()

    def _on_thread() -> T:
        # Inside ctx.run the "current context" is our copy, so the task
        # asyncio.run creates inherits the propagated ids.
        return ctx.run(lambda: asyncio.run(factory()))

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="sync-bridge"
    ) as pool:
        return pool.submit(_on_thread).result()
