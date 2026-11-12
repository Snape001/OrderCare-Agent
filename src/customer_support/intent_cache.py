"""Short-lived Redis cache for the customer-support router's structured Route."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import weakref
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pydantic import ValidationError

from customer_support.routing import Entities, Route

logger = logging.getLogger(__name__)

INTENT_CACHE_PREFIX = "ordercare:intent:"
INTENT_CACHE_VERSION = "intent-cache-v1"
_CACHE_VALUE_VERSION = 1


class RedisLike(Protocol):
    async def get(self, key: str) -> str | bytes | None: ...

    async def set(self, key: str, value: str, ex: int | None = None) -> Any: ...

    async def delete(self, key: str) -> Any: ...


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


class IntentCache:
    """Cache validated Route values without storing sensitive entities."""

    def __init__(self, redis: RedisLike, *, ttl: int = 300, timeout: float = 0.2) -> None:
        if ttl <= 0:
            raise ValueError("Intent cache TTL must be positive")
        if timeout <= 0:
            raise ValueError("Intent cache timeout must be positive")
        self._redis = redis
        self.ttl = ttl
        self._timeout = timeout
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

    def key(self, query: str) -> str:
        """Build a hashed key from the normalized query only."""
        payload = {
            "v": INTENT_CACHE_VERSION,
            "query": _normalize_text(query),
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return INTENT_CACHE_PREFIX + digest

    @staticmethod
    def _serialize(route: Route) -> str:
        return json.dumps(
            {
                "v": _CACHE_VALUE_VERSION,
                "intents": [intent.value for intent in route.intents],
                "conditional": bool(route.conditional),
                "product_name": route.entities.product_name,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _deserialize(raw: str | bytes) -> Route:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("v") != _CACHE_VALUE_VERSION:
            raise ValueError("unsupported intent cache value")
        intents = data.get("intents")
        if not isinstance(intents, list) or not intents:
            raise ValueError("invalid intent cache intents")
        return Route(
            intents=intents,
            entities=Entities(product_name=data.get("product_name")),
            conditional=bool(data.get("conditional", False)),
        )

    async def _read(self, key: str) -> tuple[Route | None, str]:
        try:
            raw = await asyncio.wait_for(self._redis.get(key), timeout=self._timeout)
        except Exception as exc:
            logger.warning("Intent cache read failed error_type=%s", type(exc).__name__)
            return None, "error"
        if raw is None:
            return None, "miss"
        try:
            return self._deserialize(raw), "hit"
        except (ValueError, TypeError, ValidationError):
            logger.warning("Intent cache value invalid; deleting key")
            await self._delete(key)
            return None, "error"

    async def _delete(self, key: str) -> None:
        try:
            await asyncio.wait_for(self._redis.delete(key), timeout=self._timeout)
        except Exception:
            logger.debug("Intent cache delete failed", exc_info=True)

    async def get(self, key: str) -> Route | None:
        route, _ = await self._read(key)
        return route

    async def set(self, key: str, route: Route) -> None:
        try:
            payload = self._serialize(route)
            await asyncio.wait_for(
                self._redis.set(key, payload, ex=self.ttl),
                timeout=self._timeout,
            )
        except Exception as exc:
            logger.warning("Intent cache write failed error_type=%s", type(exc).__name__)

    def _lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def get_or_load(
        self,
        key: str,
        loader: Callable[[], Awaitable[Route]],
    ) -> tuple[Route, str]:
        """Return a cached route or load it once per process/key."""
        cached, status = await self._read(key)
        if cached is not None:
            return cached, "hit"

        async with self._lock_for(key):
            second_status = status
            if status == "miss":
                cached, second_status = await self._read(key)
                if cached is not None:
                    return cached, "hit"
            route = await loader()
            await self.set(key, route)
            return route, "error" if "error" in (status, second_status) else "miss"


_cache: IntentCache | None = None


def configure_intent_cache(
    client: RedisLike | None,
    *,
    ttl: int = 300,
    timeout: float = 0.2,
    enabled: bool = True,
) -> None:
    """Configure the process-wide cache; no client means the cache is disabled."""
    global _cache
    if not enabled or client is None:
        _cache = None
        return
    _cache = IntentCache(client, ttl=ttl, timeout=timeout)


def reset_intent_cache() -> None:
    global _cache
    _cache = None


def get_intent_cache() -> IntentCache | None:
    return _cache
