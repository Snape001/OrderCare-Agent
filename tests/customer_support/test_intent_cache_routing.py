"""Router-graph tests for the Redis intent cache."""

import pytest
from langchain_core.language_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from agents.customer_support_agent import build_customer_support_graph
from customer_support.intent_cache import configure_intent_cache, reset_intent_cache
from customer_support.routing import Plan, Route


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail_get = False
        self.fail_set = False

    async def get(self, key: str) -> str | None:
        if self.fail_get:
            raise RuntimeError("redis read failed")
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        if self.fail_set:
            raise RuntimeError("redis write failed")
        self.values[key] = value
        return True

    async def delete(self, key: str) -> int:
        self.values.pop(key, None)
        return 1


class CountingRoutedModel(FakeMessagesListChatModel):
    route_result: dict
    route_calls: int = 0
    plan_calls: int = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        if schema is Route:

            def routed(_):
                self.route_calls += 1
                return self.route_result

            return RunnableLambda(routed)
        if schema is Plan:

            def planned(_):
                self.plan_calls += 1
                return {"steps": []}

            return RunnableLambda(planned)
        raise AssertionError(schema)


@pytest.fixture(autouse=True)
def clear_intent_cache():
    reset_intent_cache()
    yield
    reset_intent_cache()


@pytest.mark.asyncio
async def test_repeated_query_skips_router_model_call() -> None:
    model = CountingRoutedModel(
        responses=[AIMessage(content="你好"), AIMessage(content="再次你好")],
        route_result={"intents": ["general"], "entities": {}, "conditional": False},
    )
    configure_intent_cache(FakeRedis(), ttl=60)
    graph = build_customer_support_graph(model, enable_router=True)

    first = await graph.ainvoke({"messages": [HumanMessage(content="你好")]})
    second = await graph.ainvoke({"messages": [HumanMessage(content="你好")]})

    assert first["messages"][-1].content == "你好"
    assert second["messages"][-1].content == "再次你好"
    assert model.route_calls == 1


@pytest.mark.asyncio
async def test_cache_key_ignores_prior_human_history() -> None:
    model = CountingRoutedModel(
        responses=[AIMessage(content="第一次"), AIMessage(content="第二次")],
        route_result={"intents": ["general"], "entities": {}, "conditional": False},
    )
    configure_intent_cache(FakeRedis(), ttl=60)
    graph = build_customer_support_graph(model, enable_router=True)

    await graph.ainvoke({"messages": [HumanMessage(content="你好")]})
    await graph.ainvoke(
        {"messages": [HumanMessage(content="之前聊过"), HumanMessage(content="你好")]}
    )

    assert model.route_calls == 1


@pytest.mark.asyncio
async def test_different_query_still_calls_router() -> None:
    model = CountingRoutedModel(
        responses=[AIMessage(content="一"), AIMessage(content="二")],
        route_result={"intents": ["general"], "entities": {}, "conditional": False},
    )
    configure_intent_cache(FakeRedis(), ttl=60)
    graph = build_customer_support_graph(model, enable_router=True)

    await graph.ainvoke({"messages": [HumanMessage(content="你好")]})
    await graph.ainvoke({"messages": [HumanMessage(content="再见")]})

    assert model.route_calls == 2


@pytest.mark.asyncio
async def test_redis_failure_does_not_break_routing() -> None:
    redis = FakeRedis()
    redis.fail_get = True
    redis.fail_set = True
    model = CountingRoutedModel(
        responses=[AIMessage(content="你好")],
        route_result={"intents": ["general"], "entities": {}, "conditional": False},
    )
    configure_intent_cache(redis, ttl=60)
    graph = build_customer_support_graph(model, enable_router=True)

    result = await graph.ainvoke({"messages": [HumanMessage(content="你好")]})

    assert result["messages"][-1].content == "你好"
    assert model.route_calls == 1
