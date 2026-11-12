"""Unit tests for the Redis-backed router intent cache."""

import asyncio
import json

import pytest

from customer_support.intent_cache import (
    IntentCache,
    configure_intent_cache,
    get_intent_cache,
    reset_intent_cache,
)
from customer_support.routing import Entities, Intent, Route


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int | None] = {}
        self.deleted: list[str] = []
        self.fail_get = False
        self.fail_set = False
        self.delay = 0.0

    async def get(self, key: str) -> str | None:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_get:
            raise RuntimeError("redis read failed")
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        if self.fail_set:
            raise RuntimeError("redis write failed")
        self.values[key] = value
        self.expirations[key] = ex
        return True

    async def delete(self, key: str) -> int:
        self.deleted.append(key)
        self.values.pop(key, None)
        return 1


def make_route() -> Route:
    return Route(
        intents=[Intent.REFUND, Intent.ORDER],
        entities=Entities(
            order_id="ORD1001",
            phone_last4="8821",
            product_name="无线耳机",
            issue="退款没到账",
        ),
        conditional=False,
    )


def test_key_uses_normalized_query_only() -> None:
    cache = IntentCache(FakeRedis())

    assert cache.key(" 退款\t多久 ") == cache.key("退款 多久")
    assert cache.key("退款多久") != cache.key("退货多久")


@pytest.mark.asyncio
async def test_set_writes_ttl_and_omits_sensitive_entities() -> None:
    redis = FakeRedis()
    cache = IntentCache(redis, ttl=120)
    key = cache.key("退款多久到账")

    await cache.set(key, make_route())

    payload = json.loads(redis.values[key])
    assert payload == {
        "v": 1,
        "intents": ["refund_check", "order_query"],
        "conditional": False,
        "product_name": "无线耳机",
    }
    assert redis.expirations[key] == 120
    assert "ORD1001" not in redis.values[key]
    assert "8821" not in redis.values[key]
    assert "退款没到账" not in redis.values[key]


@pytest.mark.asyncio
async def test_get_or_load_hits_cache_on_second_call() -> None:
    cache = IntentCache(FakeRedis())
    calls = 0

    async def loader() -> Route:
        nonlocal calls
        calls += 1
        return make_route()

    first, first_status = await cache.get_or_load(cache.key("查退款"), loader)
    second, second_status = await cache.get_or_load(cache.key("查退款"), loader)

    assert calls == 1
    assert first_status == "miss"
    assert second_status == "hit"
    assert first.intents == second.intents


@pytest.mark.asyncio
async def test_different_query_does_not_share_cache() -> None:
    cache = IntentCache(FakeRedis())
    calls = 0

    async def loader() -> Route:
        nonlocal calls
        calls += 1
        return make_route()

    await cache.get_or_load(cache.key("查退款"), loader)
    await cache.get_or_load(cache.key("查退货"), loader)

    assert calls == 2


@pytest.mark.asyncio
async def test_corrupt_value_is_deleted_and_treated_as_miss() -> None:
    redis = FakeRedis()
    cache = IntentCache(redis)
    key = cache.key("查退款")
    redis.values[key] = "{not-json"

    assert await cache.get(key) is None
    assert key in redis.deleted


@pytest.mark.asyncio
async def test_redis_failure_fails_open() -> None:
    redis = FakeRedis()
    redis.fail_get = True
    redis.fail_set = True
    cache = IntentCache(redis)

    async def loader() -> Route:
        return make_route()

    route, status = await cache.get_or_load(cache.key("查退款"), loader)

    assert status == "error"
    assert route.intents == [Intent.REFUND, Intent.ORDER]


@pytest.mark.asyncio
async def test_redis_timeout_fails_open() -> None:
    redis = FakeRedis()
    redis.delay = 0.05
    cache = IntentCache(redis, timeout=0.01)

    async def loader() -> Route:
        return make_route()

    route, status = await cache.get_or_load(cache.key("查退款"), loader)

    assert status == "error"
    assert route.entities.product_name == "无线耳机"


@pytest.mark.asyncio
async def test_concurrent_misses_load_once() -> None:
    cache = IntentCache(FakeRedis())
    calls = 0

    async def loader() -> Route:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        return make_route()

    results = await asyncio.gather(
        *(cache.get_or_load(cache.key("查退款"), loader) for _ in range(5))
    )

    statuses = [status for _, status in results]
    assert calls == 1
    assert statuses.count("miss") == 1
    assert statuses.count("hit") == 4


def test_configure_and_reset_intent_cache() -> None:
    redis = FakeRedis()
    reset_intent_cache()
    assert get_intent_cache() is None

    configure_intent_cache(redis, ttl=60)
    assert get_intent_cache() is not None

    configure_intent_cache(None)
    assert get_intent_cache() is None
