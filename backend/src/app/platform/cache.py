"""Redis cache provider — loss-tolerant by design (ADR-0014).

Redis is never the system of record: a cache failure is logged, counted, and
falls through; correctness never depends on cache contents.
"""

from __future__ import annotations

import json

from app.platform.config import Settings

_client = None
_metrics = {"hits": 0, "misses": 0, "errors": 0}


def init_cache(settings: Settings):
    global _client
    if _client is None:
        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is not configured")
        import redis.asyncio as aioredis

        _client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
    return _client


def get_client():
    return _client


async def close_cache() -> None:
    global _client
    if _client is not None:
        # redis-py 5 has aclose(); ignore is for lagging types-redis stubs.
        await _client.aclose()  # type: ignore[attr-defined]
    _client = None


def metrics() -> dict:
    return dict(_metrics)


def namespaced(key: str) -> str:

    return f"v{1}:{key}"  # CACHE_VERSION namespace; bump to invalidate wholesale


async def get_json(key: str) -> object | None:
    if _client is None:
        return None
    try:
        raw = await _client.get(namespaced(key))
        if raw is None:
            _metrics["misses"] += 1
            return None
        _metrics["hits"] += 1
        return json.loads(raw)
    except Exception:  # noqa: BLE001 - cache errors are never fatal
        _metrics["errors"] += 1
        return None


async def set_json(key: str, value: object, ttl_seconds: int) -> None:
    if _client is None:
        return
    try:
        await _client.set(namespaced(key), json.dumps(value), ex=ttl_seconds)
    except Exception:  # noqa: BLE001
        _metrics["errors"] += 1


async def evict(key: str) -> None:
    if _client is None:
        return
    try:
        await _client.delete(namespaced(key))
    except Exception:  # noqa: BLE001
        _metrics["errors"] += 1


async def ping() -> bool:
    if _client is None:
        return False
    try:
        return bool(await _client.ping())
    except Exception:  # noqa: BLE001
        return False
