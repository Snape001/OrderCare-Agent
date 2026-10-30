from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest

import run_agent


@pytest.mark.asyncio
async def test_direct_runner_loads_before_getting_graph(monkeypatch):
    loaded = False
    graph = Mock()
    graph.ainvoke = AsyncMock(return_value={"messages": [Mock()]})

    async def load(_):
        nonlocal loaded
        loaded = True

    def get(_):
        assert loaded
        return graph

    saver = Mock()
    saver.setup = AsyncMock()
    store = Mock()
    store.setup = AsyncMock()

    @asynccontextmanager
    async def database():
        yield saver

    @asynccontextmanager
    async def memory():
        yield store

    monkeypatch.setattr(run_agent, "load_agent", load)
    monkeypatch.setattr(run_agent, "get_agent", get)
    monkeypatch.setattr(run_agent, "initialize_database", database)
    monkeypatch.setattr(run_agent, "initialize_store", memory)
    await run_agent.main()
    graph.ainvoke.assert_awaited_once()
    assert graph.checkpointer is saver
    assert graph.store is store
