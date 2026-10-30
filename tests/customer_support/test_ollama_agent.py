from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.language_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import agents.customer_support_agent as module
import customer_support.store as store
from core import settings


class FakeToolModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


@pytest.mark.asyncio
async def test_ollama_mode_builds_local_model_without_cloud_key(monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_SUPPORT_MODE", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "qwen3:4b")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setattr(settings, "OLLAMA_REQUEST_TIMEOUT", 45)
    monkeypatch.setattr(module.CustomerSupportAgent, "_check_ollama", AsyncMock())
    captured = {}

    def build(model, **kwargs):
        captured.update(model=model, **kwargs)
        return Mock()

    monkeypatch.setattr(module, "build_customer_support_graph", build)
    agent = module.CustomerSupportAgent()
    await agent.load()

    assert agent._loaded
    assert captured["model"].model == "qwen3:4b"
    assert captured["model"].base_url == "http://127.0.0.1:11434"
    assert captured["model"].client_kwargs["timeout"] == 45
    assert captured["provider"] == "ollama"
    assert captured["force_routing"] is False


@pytest.mark.asyncio
async def test_unavailable_ollama_never_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_SUPPORT_MODE", "ollama")
    monkeypatch.setattr(
        module.CustomerSupportAgent,
        "_check_ollama",
        AsyncMock(side_effect=RuntimeError("unavailable")),
    )
    agent = module.CustomerSupportAgent()

    with pytest.raises(RuntimeError, match="unavailable"):
        await agent.load()
    assert agent._loaded is False


@pytest.mark.asyncio
async def test_model_tool_result_returns_to_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DEFAULT_DB_PATH", tmp_path / "business.db")
    model = FakeToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="get_order_status",
                        args={"order_id": "ORD1001", "phone_last4": "8821"},
                        id="order",
                    )
                ],
            ),
            AIMessage(content="查询完成"),
        ]
    )
    graph = module.build_customer_support_graph(model, provider="ollama", force_routing=False)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="看看我的包裹走到哪里了，订单号 ORD1001，尾号 8821")]}
    )

    assert any(
        isinstance(message, ToolMessage) and '"status": "运输中"' in message.content
        for message in result["messages"]
    )
    assert result["messages"][-1].content == "查询完成"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("not_a_real_tool", {"order_id": "ORD1001", "phone_last4": "8821"}),
        ("get_order_status", {"order_id": "ORD1001"}),
    ],
)
async def test_invalid_model_tool_call_cannot_read_order(tmp_path, monkeypatch, tool_name, args):
    monkeypatch.setattr(store, "DEFAULT_DB_PATH", tmp_path / "business.db")
    read = Mock(wraps=store.get_order_status)
    monkeypatch.setattr("customer_support.tools.get_order_status", read)
    model = FakeToolModel(
        responses=[
            AIMessage(content="", tool_calls=[ToolCall(name=tool_name, args=args, id="bad")]),
            AIMessage(content="无法完成查询"),
        ]
    )
    graph = module.build_customer_support_graph(model, provider="ollama", force_routing=False)
    result = await graph.ainvoke({"messages": [HumanMessage(content="帮我看看订单")]})

    read.assert_not_called()
    assert any(
        isinstance(message, ToolMessage) and message.status == "error"
        for message in result["messages"]
    )


@pytest.mark.asyncio
async def test_ticket_rejection_keeps_database_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DEFAULT_DB_PATH", tmp_path / "business.db")
    store.initialize_database()
    model = FakeToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="create_support_ticket",
                        args={
                            "order_id": "ORD1001",
                            "phone_last4": "8821",
                            "category": "物流",
                            "summary": "物流未更新",
                        },
                        id="ticket",
                    )
                ],
            ),
            AIMessage(content="已取消"),
        ]
    )
    graph = module.build_customer_support_graph(model, provider="ollama", force_routing=False)
    graph.checkpointer = MemorySaver()
    config = {"configurable": {"thread_id": "reject-ticket"}}
    first = await graph.ainvoke({"messages": [HumanMessage(content="创建售后工单")]}, config=config)
    assert first["__interrupt__"]
    await graph.ainvoke(Command(resume={"decisions": [{"type": "reject"}]}), config=config)
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM support_tickets").fetchone()[0] == 0
