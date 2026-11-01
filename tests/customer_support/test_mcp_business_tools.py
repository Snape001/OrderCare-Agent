"""MCP STDIO integration using only an isolated SQLite test database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest
from langchain_core.language_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agents.customer_support_agent import build_customer_support_graph
from customer_support import store
from customer_support.mcp_approval import ticket_token
from customer_support.mcp_client import TOOL_NAMES, load_business_mcp_tools, normalize_result
from customer_support.mcp_server import mcp
from customer_support.routing import Plan, Route


class RoutedModel(FakeMessagesListChatModel):
    route_result: dict

    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        if schema is Route:
            return RunnableLambda(lambda _: self.route_result)
        if schema is Plan:
            raise AssertionError("Single-intent request must not use Planner")
        raise AssertionError(schema)


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "mcp-business.db"
    monkeypatch.setenv("CUSTOMER_SUPPORT_DB_PATH", str(path))
    monkeypatch.delenv("ORDERCARE_MCP_APPROVAL_SECRET", raising=False)
    monkeypatch.setattr(store, "DEFAULT_DB_PATH", path)
    return path


def ticket_count(path: Path) -> int:
    store.initialize_database(path)
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT count(*) FROM support_tickets").fetchone()[0]


@pytest.mark.asyncio
async def test_server_registers_four_tools_with_required_schema() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert set(tools) == TOOL_NAMES
    assert set(tools["get_order_status"].inputSchema["required"]) == {"order_id", "phone_last4"}
    assert set(tools["create_support_ticket"].inputSchema["required"]) == {
        "order_id",
        "phone_last4",
        "category",
        "summary",
    }
    assert tools["search_policy"].inputSchema["properties"]["query"]["minLength"] == 1


@pytest.mark.asyncio
async def test_stdio_discovery_and_order_refund_calls(isolated_db: Path) -> None:
    tools = {tool.name: tool for tool in await load_business_mcp_tools()}
    assert set(tools) == TOOL_NAMES
    assert "approval_token" not in tools["create_support_ticket"].args
    order = await tools["get_order_status"].ainvoke({"order_id": "ORD1001", "phone_last4": "8821"})
    assert order["ok"] is True
    assert order["order_id"] == "ORD1001"
    refund = await tools["check_refund_eligibility"].ainvoke(
        {"order_id": "ORD1002", "phone_last4": "8821"}
    )
    assert refund["ok"] is True
    assert refund["eligible"] is True
    denied = await tools["get_order_status"].ainvoke({"order_id": "ORD1001", "phone_last4": "0000"})
    assert denied["ok"] is False


@pytest.mark.asyncio
async def test_stdio_policy_search_uses_real_rag() -> None:
    tools = {tool.name: tool for tool in await load_business_mcp_tools()}
    result = await tools["search_policy"].ainvoke({"query": "七天无理由退货政策"})
    assert result["ok"] is True
    assert result["references"]


@pytest.mark.asyncio
async def test_policy_result_and_exception_are_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    import customer_support.mcp_server as server

    monkeypatch.setitem(
        server._business_tools,
        "search_policy",
        Mock(invoke=Mock(return_value={"title": "七天退货", "references": []})),
    )
    result = normalize_result(await mcp.call_tool("search_policy", {"query": "退货政策"}))
    assert result == {"ok": True, "title": "七天退货", "references": []}
    monkeypatch.setitem(
        server._business_tools,
        "search_policy",
        Mock(invoke=Mock(side_effect=RuntimeError("test failure"))),
    )
    failure = normalize_result(await mcp.call_tool("search_policy", {"query": "退货政策"}))
    assert failure["ok"] is False
    assert failure["error_code"] == "MCP_TOOL_ERROR"
    with pytest.raises(ValueError, match="invalid business result"):
        normalize_result([{"type": "text", "text": "{}"}])


def test_policy_import_failure_keeps_public_error_and_logs_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import customer_support.mcp_server as server

    monkeypatch.setitem(
        server._business_tools,
        "search_policy",
        Mock(invoke=Mock(side_effect=ImportError("cannot import TextEmbedding from fastembed"))),
    )
    result = server._execute("search_policy", {"query": "七天无理由退货"})
    assert result == {
        "ok": False, "error": "工具执行失败，请稍后重试。", "error_code": "MCP_TOOL_ERROR"
    }
    record = next(record for record in caplog.records if record.message.startswith("MCP business tool failed"))
    assert record.exc_info is not None
    assert "ImportError: cannot import TextEmbedding from fastembed" in caplog.text


@pytest.mark.asyncio
async def test_standalone_ticket_requires_gate_and_keeps_idempotency(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments = {
        "order_id": "ORD1001",
        "phone_last4": "8821",
        "category": "物流",
        "summary": "包裹丢失",
    }
    denied = normalize_result(await mcp.call_tool("create_support_ticket", arguments))
    assert denied["error_code"] == "APPROVAL_REQUIRED"
    assert ticket_count(isolated_db) == 0
    monkeypatch.setenv("ORDERCARE_MCP_APPROVAL_SECRET", "isolated-test-secret")
    invalid = normalize_result(
        await mcp.call_tool("create_support_ticket", {**arguments, "approval_token": "invalid"})
    )
    assert invalid["error_code"] == "APPROVAL_REQUIRED"
    assert ticket_count(isolated_db) == 0
    approved = {**arguments, "approval_token": ticket_token("isolated-test-secret", arguments)}
    first = normalize_result(await mcp.call_tool("create_support_ticket", approved))
    second = normalize_result(await mcp.call_tool("create_support_ticket", approved))
    assert first["ok"] is True
    assert first["ticket_id"] == second["ticket_id"]
    assert ticket_count(isolated_db) == 1


@pytest.mark.asyncio
async def test_langgraph_calls_mcp_order_tool(isolated_db: Path) -> None:
    tools = await load_business_mcp_tools()
    model = RoutedModel(
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
            AIMessage(content="订单正在运输中"),
        ],
        route_result={"intents": ["order_query"], "entities": {}, "conditional": False},
    )
    graph = build_customer_support_graph(model, enable_router=True, tools=tools)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="查订单 ORD1001，手机号后四位 8821")]}
    )
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert json.loads(str(tool_messages[0].content))["ok"] is True
    assert result["task_trace"][0]["status"] == "done"


@pytest.mark.asyncio
@pytest.mark.parametrize("decision,expected_count", [("approve", 1), ("reject", 0)])
async def test_ticket_mcp_tool_cannot_write_before_hitl_approval(
    isolated_db: Path, decision: str, expected_count: int
) -> None:
    tools = await load_business_mcp_tools()
    model = RoutedModel(
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
                            "summary": "包裹丢失",
                        },
                        id="ticket",
                    )
                ],
            ),
            AIMessage(content="工单已创建"),
        ],
        route_result={"intents": ["ticket_create"], "entities": {}, "conditional": False},
    )
    graph = build_customer_support_graph(model, enable_router=True, tools=tools)
    graph.checkpointer = MemorySaver()
    config: RunnableConfig = {"configurable": {"thread_id": "mcp-ticket-test"}}
    first = await graph.ainvoke(
        {"messages": [HumanMessage(content="请为订单 ORD1001 创建工单，手机号后四位 8821")]},
        config=config,
    )
    assert first["__interrupt__"]
    assert ticket_count(isolated_db) == 0
    resumed = await graph.ainvoke(Command(resume={"decisions": [{"type": decision}]}), config)
    assert ticket_count(isolated_db) == expected_count
    if decision == "approve":
        assert any(
            isinstance(message, ToolMessage) and message.name == "create_support_ticket"
            for message in resumed["messages"]
        )
