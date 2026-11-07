"""Check the opt-in compaction view at the actual LangGraph model boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from agents import customer_support_agent as agent
from core.settings import settings
from memory.compaction import _fingerprint


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,summary_budget,expected", [
    (False, 320, "default"),
    (True, 320, "replaced"),
    (True, 1, "fallback"),
])
async def test_graph_model_view_uses_cursor_summary_only_when_enabled(
    monkeypatch, enabled, summary_budget, expected
):
    old = [HumanMessage(content="订单 ORD1001 不要创建工单", id="old-user"),
           AIMessage(content="收到", id="old-ai")]
    recent = [HumanMessage(content="请先查退款", id="recent-user"),
              AIMessage(content="正在核验", id="recent-ai")]
    current = HumanMessage(content="如果不行就查维修", id="current-user")
    summary = {"constraints": ["不要创建工单"], "entities": ["ORD1001"]}
    record = {"cursor": f"1:{_fingerprint(old[1])}", "summary": summary}
    compactor = SimpleNamespace(
        maybe_compact=AsyncMock(return_value=(summary, {})),
        store=SimpleNamespace(session=AsyncMock(return_value={"compaction": record})),
    )
    monkeypatch.setattr(agent, "get_compactor", lambda: compactor)
    monkeypatch.setattr(settings, "CONTEXT_COMPACTION_ENABLED", enabled)
    monkeypatch.setattr(settings, "CONTEXT_HISTORY_SUMMARY_BUDGET", summary_budget)
    seen = []
    original_generate = FakeMessagesListChatModel._generate

    def capture(self, messages, *args, **kwargs):
        seen.append(messages)
        return original_generate(self, messages, *args, **kwargs)

    monkeypatch.setattr(FakeMessagesListChatModel, "_generate", capture)
    graph = agent.build_customer_support_graph(
        FakeMessagesListChatModel(responses=[AIMessage(content="请提供更多信息")]),
        enable_router=False, force_routing=False, tools=[],
    )
    await graph.ainvoke(
        {"messages": [*old, *recent, current]},
        config={"configurable": {"user_id": "u1", "thread_id": "t1"}},
    )
    assert len(seen) == 1
    visible = "\n".join(str(message.content) for message in seen[0])
    assert "如果不行就查维修" in visible
    assert "请先查退款" in visible
    if expected == "replaced":
        assert "压缩历史" in visible
        assert "订单 ORD1001 不要创建工单" not in visible
    else:
        assert "订单 ORD1001 不要创建工单" in visible
    if expected == "default":
        compactor.store.session.assert_not_awaited()
    else:
        compactor.store.session.assert_awaited_once()


@pytest.mark.asyncio
async def test_graph_surfaces_redis_failure_when_compaction_enabled(monkeypatch):
    compactor = SimpleNamespace(
        maybe_compact=AsyncMock(return_value=(None, {})),
        store=SimpleNamespace(session=AsyncMock(side_effect=RuntimeError("Redis unavailable"))),
    )
    monkeypatch.setattr(agent, "get_compactor", lambda: compactor)
    monkeypatch.setattr(settings, "CONTEXT_COMPACTION_ENABLED", True)
    graph = agent.build_customer_support_graph(
        FakeMessagesListChatModel(responses=[AIMessage(content="ok")]),
        enable_router=False, force_routing=False, tools=[],
    )
    with pytest.raises(RuntimeError, match="Redis unavailable"):
        await graph.ainvoke(
            {"messages": [HumanMessage(content="你好")]},
            config={"configurable": {"user_id": "u1", "thread_id": "t1"}},
        )
