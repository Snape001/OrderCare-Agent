import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI

from schema import AgentInfo


@pytest.mark.asyncio
async def test_default_memory_starts_with_service_and_checks_dependencies(monkeypatch) -> None:
    """A normal service lifespan initializes every enabled Memory layer without model API calls."""
    from customer_support import rag
    from memory.compaction import get_compactor
    from service import service

    @asynccontextmanager
    async def component():
        yield object()

    memory = SimpleNamespace(
        setup=AsyncMock(), close=AsyncMock(),
        redis=SimpleNamespace(ping=AsyncMock(return_value=True)),
    )
    embed_calls: list[str] = []
    collection_reads: list[bool] = []

    class FakeEpisode:
        def __init__(self, **kwargs):
            self.store = SimpleNamespace(get=lambda **kwargs: collection_reads.append(True))

    def embed_query(query: str) -> list[float]:
        embed_calls.append(query)
        return [0.1]

    monkeypatch.setattr(service.settings, "MEMORY_ENABLED", True)
    monkeypatch.setattr(service.settings, "EPISODIC_MEMORY_ENABLED", True)
    monkeypatch.setattr(service.settings, "REDIS_URL", "redis://127.0.0.1:6379/15")
    monkeypatch.setattr(service, "initialize_database", component)
    monkeypatch.setattr(service, "initialize_store", component)
    monkeypatch.setattr(service, "get_all_agent_info", lambda: [])
    monkeypatch.setattr(service, "LayeredMemory", lambda *args: memory)
    monkeypatch.setattr(service, "EpisodicMemory", FakeEpisode)
    monkeypatch.setattr(rag, "get_policy_knowledge_base", lambda: SimpleNamespace(
        persist_directory="unused", embedding=SimpleNamespace(embed_query=embed_query)
    ))
    test_app = FastAPI()
    async with service.lifespan(test_app):
        assert test_app.state.layered_memory is memory
        assert test_app.state.episodic_memory is not None
        assert get_compactor() is not None
        assert embed_calls == ["售后服务"]
        assert collection_reads == [True]
    memory.setup.assert_awaited_once()
    memory.close.assert_awaited_once()
    assert get_compactor() is None


@pytest.mark.asyncio
async def test_lifespan_configures_intent_cache_after_memory_setup(monkeypatch) -> None:
    from service import service

    @asynccontextmanager
    async def component():
        yield object()

    redis = object()
    memory = SimpleNamespace(setup=AsyncMock(), close=AsyncMock(), redis=redis)
    configure = Mock()
    reset = Mock()

    monkeypatch.setattr(service.settings, "MEMORY_ENABLED", True)
    monkeypatch.setattr(service.settings, "EPISODIC_MEMORY_ENABLED", False)
    monkeypatch.setattr(service.settings, "INTENT_CACHE_ENABLED", True)
    monkeypatch.setattr(service.settings, "REDIS_URL", "redis://127.0.0.1:6379/15")
    monkeypatch.setattr(service, "initialize_database", component)
    monkeypatch.setattr(service, "initialize_store", component)
    monkeypatch.setattr(service, "get_all_agent_info", lambda: [])
    monkeypatch.setattr(service, "LayeredMemory", lambda *args: memory)
    monkeypatch.setattr(service, "configure_intent_cache", configure)
    monkeypatch.setattr(service, "reset_intent_cache", reset)

    async with service.lifespan(FastAPI()):
        pass

    configure.assert_called_once_with(
        redis,
        ttl=service.settings.INTENT_CACHE_TTL_SECONDS,
        timeout=service.settings.INTENT_CACHE_TIMEOUT_SECONDS,
    )
    assert reset.call_count >= 1
    memory.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_enabled_memory_failure_aborts_startup(monkeypatch) -> None:
    from service import service

    @asynccontextmanager
    async def component():
        yield object()

    memory = SimpleNamespace(
        setup=AsyncMock(side_effect=RuntimeError("Redis offline")), close=AsyncMock()
    )
    monkeypatch.setattr(service.settings, "MEMORY_ENABLED", True)
    monkeypatch.setattr(service.settings, "REDIS_URL", "redis://127.0.0.1:6379/15")
    monkeypatch.setattr(service, "initialize_database", component)
    monkeypatch.setattr(service, "initialize_store", component)
    monkeypatch.setattr(service, "get_all_agent_info", lambda: [])
    monkeypatch.setattr(service, "LayeredMemory", lambda *args: memory)
    with pytest.raises(RuntimeError, match="Redis offline"):
        async with service.lifespan(FastAPI()):
            pytest.fail("Memory failure must stop startup")
    memory.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_episodic_startup_failure_is_explicit_and_closes_redis(monkeypatch) -> None:
    from customer_support import rag
    from memory.episodic import EpisodicMemoryUnavailable
    from service import service

    @asynccontextmanager
    async def component():
        yield object()

    memory = SimpleNamespace(setup=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(service.settings, "MEMORY_ENABLED", True)
    monkeypatch.setattr(service.settings, "EPISODIC_MEMORY_ENABLED", True)
    monkeypatch.setattr(service.settings, "REDIS_URL", "redis://127.0.0.1:6379/15")
    monkeypatch.setattr(service, "initialize_database", component)
    monkeypatch.setattr(service, "initialize_store", component)
    monkeypatch.setattr(service, "get_all_agent_info", lambda: [])
    monkeypatch.setattr(service, "LayeredMemory", lambda *args: memory)
    monkeypatch.setattr(rag, "get_policy_knowledge_base", lambda: SimpleNamespace(
        persist_directory="unused", embedding=SimpleNamespace(embed_query=lambda query: [0.1])
    ))

    def broken_get(**kwargs):
        raise OSError("Chroma offline")

    monkeypatch.setattr(service, "EpisodicMemory", lambda **kwargs: SimpleNamespace(
        store=SimpleNamespace(get=broken_get)
    ))
    with pytest.raises(EpisodicMemoryUnavailable, match="Episodic Memory unavailable"):
        async with service.lifespan(FastAPI()):
            pytest.fail("Chroma failure must stop startup")
    memory.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan(monkeypatch, caplog) -> None:
    """Test that the lifespan sets up the database and store, loads the agents, and logs errors."""
    from service import service

    fake_saver_setup = False
    fake_store_setup = False

    class FakeSaver:
        async def setup(self) -> None:
            nonlocal fake_saver_setup
            fake_saver_setup = True

    class FakeStore:
        async def setup(self) -> None:
            nonlocal fake_store_setup
            fake_store_setup = True

    fake_saver = FakeSaver()
    fake_store = FakeStore()

    @asynccontextmanager
    async def fake_initialize_database():
        yield fake_saver

    @asynccontextmanager
    async def fake_initialize_store():
        yield fake_store

    agents = {
        "good": type("Agent", (), {"checkpointer": None, "store": None})(),
        "bad": type("Agent", (), {"checkpointer": None, "store": None})(),
    }

    async def fake_load_agent(agent_key: str) -> None:
        if agent_key == "bad":
            raise RuntimeError("boom")

    def fake_get_agent(agent_key: str):
        if agent_key == "bad":
            raise RuntimeError("Agent not loaded")
        return agents[agent_key]

    monkeypatch.setattr(service, "initialize_database", fake_initialize_database)
    monkeypatch.setattr(service, "initialize_store", fake_initialize_store)
    monkeypatch.setattr(service, "load_agent", fake_load_agent)
    monkeypatch.setattr(service, "get_agent", fake_get_agent)
    monkeypatch.setattr(
        service,
        "get_all_agent_info",
        lambda: [
            AgentInfo(key="good", description=""),
            AgentInfo(key="bad", description=""),
        ],
    )

    caplog.set_level(logging.INFO, logger=service.logger.name)

    test_app = FastAPI()
    async with service.lifespan(test_app):
        pass

    assert fake_saver_setup
    assert fake_store_setup
    assert agents["good"].checkpointer is fake_saver
    assert agents["good"].store is fake_store
    assert agents["bad"].checkpointer is None
    assert agents["bad"].store is None
    assert test_app.state.unavailable_agents == {"bad"}

    assert "Agent loaded: good" in caplog.text
    assert "Failed to load agent bad" in caplog.text


@pytest.mark.asyncio
async def test_default_agent_failure_aborts_startup(monkeypatch):
    from unittest.mock import AsyncMock, Mock

    from service import service

    @asynccontextmanager
    async def component():
        yield object()

    monkeypatch.setattr(service, "initialize_database", component)
    monkeypatch.setattr(service, "initialize_store", component)
    monkeypatch.setattr(
        service,
        "get_all_agent_info",
        lambda: [AgentInfo(key=service.DEFAULT_AGENT, description="")],
    )
    monkeypatch.setattr(
        service, "load_agent", AsyncMock(side_effect=RuntimeError("provider failure"))
    )
    get = Mock()
    monkeypatch.setattr(service, "get_agent", get)
    with pytest.raises(RuntimeError, match="Default agent failed"):
        async with service.lifespan(FastAPI()):
            pytest.fail("Startup must not succeed without the default agent")
    get.assert_not_called()
