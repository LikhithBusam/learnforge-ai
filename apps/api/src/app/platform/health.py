"""Infrastructure health checks (liveness vs readiness, ADR-0019).

- Liveness (`/healthz`): process is up. NO dependency checks — a DB blip must
  not restart-loop healthy pods.
- Readiness (`/readyz`): required infrastructure reachable. Reports degraded
  (not error) in dev when optional pieces are unconfigured.

No secrets or credentials are ever included in health output.
"""

from __future__ import annotations

from app.platform import cache, db
from app.platform.storage import get_storage


def liveness() -> dict:
    return {"status": "ok"}


async def readiness(
    check_db: bool = True, check_cache: bool = True, check_storage: bool = True
) -> dict:
    components: dict = {}

    if check_db:
        components["database"] = await db.check_database()

    if check_cache:
        from app.platform.config import get_settings

        if get_settings().REDIS_URL:
            components["cache"] = {"status": "ok" if await cache.ping() else "error"}
        else:
            components["cache"] = {"status": "unconfigured"}

    if check_storage:
        try:
            components["storage"] = get_storage().healthcheck()
        except Exception as exc:  # noqa: BLE001 - probe must not raise
            components["storage"] = {"status": "error", "detail": type(exc).__name__}

    required = [c for name, c in components.items() if name in ("database", "cache")]
    degraded_or_down = any(c.get("status") not in ("ok", "unconfigured") for c in required)
    status = "degraded" if degraded_or_down else "ok"
    return {"status": status, "components": components}
