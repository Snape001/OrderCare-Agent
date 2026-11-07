"""Opt-in integration tests against an isolated Redis-compatible server.

Run with ORDERCARE_TEST_REDIS_URL=redis://127.0.0.1:16379/0. The regular
test suite skips these tests unless a dedicated test server is selected.
"""

import asyncio
import json
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from memory.compaction import AutomaticCompactor
from memory.layers import LayeredMemory, MemoryUnavailable

TEST_URL = os.getenv("ORDERCARE_TEST_REDIS_URL")
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not TEST_URL, reason="no isolated Redis")]


def dialogue() -> list:
    return [
        HumanMessage(content="维修 ORD1001，手机号后四位 8821。不要创建工单。"),
        AIMessage(content="", tool_calls=[{"name": "search_policy", "args": {}, "id": "p1"}]),
        ToolMessage(
            content=json.dumps(
                {"ok": True, "references": [{"source": "policy.md", "title": "维修规则"}],
                 "content": "证据" * 300},
                ensure_ascii=False,
            ),
            name="search_policy",
            tool_call_id="p1",
        ),
        AIMessage(content="已查到维修政策"),
        HumanMessage(content="付款方式是银行卡，但不要记录支付信息"),
        AIMessage(content="收到"),
        HumanMessage(content="我希望使用文字客服"),
        AIMessage(content="收到"),
        HumanMessage(content="下一步是什么？"),
    ]


@pytest_asyncio.fixture
async def memory(tmp_path):
    assert TEST_URL is not None
    store = LayeredMemory(TEST_URL, tmp_path / "longterm.db", ttl=120)
    await store.setup()
    owner = f"integration-{uuid4().hex}"
    thread = f"thread-{uuid4().hex}"
    try:
        yield store, owner, thread
    finally:
        await store.delete_session(owner, thread)
        await store.delete_session(owner + "-other", thread)
        await store.close()


async def test_persistence_restart_cursor_and_isolation(memory):
    store, owner, thread = memory
    compactor = AutomaticCompactor(store, summary_budget=2000)
    messages = dialogue()
    summary, metrics = await compactor.maybe_compact(
        owner=owner, thread=thread, messages=messages, system=None, total_budget=300
    )
    assert metrics["triggered"] is True
    assert summary is not None
    assert "ORD1001" in summary["entities"]
    assert "8821" not in json.dumps(summary, ensure_ascii=False)
    assert "银行卡" not in json.dumps(summary, ensure_ascii=False)
    assert "policy.md#维修规则" in summary["citations"]
    saved = await store.session(owner, thread)
    assert saved["compaction"]["cursor"]
    assert await store.session(owner + "-other", thread) == {}
    assert await store.redis.ttl(store._key(owner, thread) + ":compaction") > 0

    # A fresh client simulates process restart; no checkpoint or local cache is used.
    restarted = LayeredMemory(TEST_URL, store.sqlite_path, ttl=120)  # type: ignore[arg-type]
    try:
        assert (await restarted.session(owner, thread))["compaction"] == saved["compaction"]
        same, duplicate = await AutomaticCompactor(
            restarted, summary_budget=2000
        ).maybe_compact(
            owner=owner, thread=thread, messages=messages, system=None, total_budget=300
        )
        assert same == summary and duplicate["triggered"] is False
        # CAS rejects a stale writer; the original summary and cursor survive.
        assert not await restarted.save_compaction(
            owner, thread, "stale-cursor", "wrong", {"goals": ["wrong"]}
        )
        assert (await restarted.session(owner, thread))["compaction"] == saved["compaction"]
    finally:
        await restarted.close()


async def test_concurrent_incremental_and_interruption_recovery(memory):
    store, owner, thread = memory
    compactor = AutomaticCompactor(store, summary_budget=2000)
    messages = dialogue()
    first, _ = await compactor.maybe_compact(
        owner=owner, thread=thread, messages=messages, system=None, total_budget=300
    )
    assert first is not None
    extended = [
        *messages, AIMessage(content="请继续"),
        HumanMessage(content="优先文字客服，确认后再办理"), AIMessage(content="收到"),
        HumanMessage(content="现在请继续"),
    ]
    results = await asyncio.gather(*[
        compactor.maybe_compact(
            owner=owner, thread=thread, messages=extended, system=None, total_budget=300
        ) for _ in range(6)
    ])
    assert sum(bool(metrics["triggered"]) for _, metrics in results) == 1
    saved = (await store.session(owner, thread))["compaction"]
    assert len(saved["summary"]["goals"]) == len(set(saved["summary"]["goals"]))

    # Simulate an interrupted write: the next attempt must see the Redis error,
    # then resume from the unchanged cursor when connectivity returns.
    original_eval = store.redis.eval

    async def interrupted(*args, **kwargs):
        raise ConnectionError("synthetic connection interruption")

    store.redis.eval = interrupted  # type: ignore[method-assign]
    more = [*extended, AIMessage(content="继续"), HumanMessage(content="请保留政策引用"),
            AIMessage(content="收到"), HumanMessage(content="请给出下一步")]
    with pytest.raises(MemoryUnavailable):
        await compactor.maybe_compact(
            owner=owner, thread=thread, messages=more, system=None, total_budget=300
        )
    assert (await store.session(owner, thread))["compaction"] == saved
    store.redis.eval = original_eval  # type: ignore[method-assign]
    recovered, metrics = await compactor.maybe_compact(
        owner=owner, thread=thread, messages=more, system=None, total_budget=300
    )
    assert metrics["triggered"] is True and recovered is not None


async def test_oversize_skips_without_advancing_cursor(memory):
    store, owner, thread = memory
    compactor = AutomaticCompactor(store, summary_budget=2000)
    messages = dialogue()
    first, _ = await compactor.maybe_compact(
        owner=owner, thread=thread, messages=messages, system=None, total_budget=300
    )
    assert first is not None
    saved = (await store.session(owner, thread))["compaction"]
    oversized = [
        *messages, AIMessage(content="继续"), HumanMessage(content="长内容" * 100),
        AIMessage(content="收到"), HumanMessage(content="第一步？"),
        AIMessage(content="解释"), HumanMessage(content="第二步？"),
    ]
    returned, metrics = await compactor.maybe_compact(
        owner=owner, thread=thread, messages=oversized, system=None, total_budget=300
    )
    assert returned == first and metrics["triggered"] is False
    assert (await store.session(owner, thread))["compaction"] == saved
