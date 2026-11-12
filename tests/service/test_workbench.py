"""Workbench data must be real, scoped and sanitized."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.language_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolCall
from langgraph.checkpoint.memory import MemorySaver

from agents.customer_support_agent import build_customer_support_graph
from customer_support import store
from customer_support.tools import get_order_status_tool
from customer_support.trace import (
    safe_args,
    safe_plan,
    safe_route,
    safe_task_trace,
    safe_text,
    safe_tool_result,
)
from service import app, trace_store, workbench
from service import service as service_module


def test_trace_store_and_api_are_session_scoped(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(trace_store, "_path", lambda: tmp_path / "traces.db")
    owner_token = "a" * 64
    owner = hashlib.sha256(owner_token.encode()).hexdigest()
    trace_store.save_trace(
        trace_id="trace-1", owner=owner, thread_id="thread-1", agent_id="customer-support",
        status="completed", duration_ms=42.5, provider="deepseek", model="deepseek-flash",
        events=[{"kind": "tool", "name": "get_order_status", "arguments": {"phone_last4": "**21"}}],
        question="查询订单", answer="订单正在配送",
    )
    client = TestClient(app)
    own = {"X-Session-Token": owner_token}
    other = {"X-Session-Token": "b" * 64}
    assert len(client.get("/workbench/traces", headers=own).json()["traces"]) == 1
    assert client.get("/workbench/traces", headers=other).json()["traces"] == []
    assert client.get("/workbench/traces/trace-1", headers=other).status_code == 404
    detail = client.get("/workbench/traces/trace-1", headers=own).json()
    assert detail["events"][0]["arguments"]["phone_last4"] == "**21"
    assert detail["question"] == "查询订单"
    assert detail["answer"] == "订单正在配送"
    assert "owner" not in detail
    assert client.get("/workbench/status").status_code == 401


def test_existing_trace_database_is_extended_without_losing_records(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "traces.db"
    monkeypatch.setattr(trace_store, "_path", lambda: path)
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE agent_traces (
            trace_id TEXT PRIMARY KEY, owner TEXT NOT NULL, thread_id TEXT NOT NULL,
            agent_id TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL,
            duration_ms REAL NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
            events_json TEXT NOT NULL)""")
        db.execute("""INSERT INTO agent_traces VALUES
            ('old', 'owner', 'thread', 'customer-support', '2026-01-01', 'completed',
             3.0, 'ollama', 'qwen3:4b', '[]')""")
    trace_store.save_trace(
        trace_id="new", owner="owner", thread_id="thread", agent_id="customer-support",
        status="completed", duration_ms=4, provider="deepseek", model="deepseek-flash",
        events=[], question="退货政策", answer="七天内申请",
    )
    assert trace_store.get_trace("owner", "old")["question"] == ""
    assert trace_store.get_trace("owner", "new")["answer"] == "七天内申请"


def test_trace_redacts_credentials_and_only_keeps_business_fields() -> None:
    assert safe_args({"phone_last4": "8821", "api_key": "sk-secret123456", "order_id": "ORD1001"}) == {
        "phone_last4": "**21", "order_id": "ORD1001"
    }
    assert "12345678901" not in safe_text("手机号 13812345678，sk-secret123456")
    assert "8821" not in safe_text("手机号后四位 8821")
    route = safe_route({"intents": ["order_query"], "entities": {"phone_last4": "8821"}})
    assert route["entities"]["phone_last4"] == "**21"
    assert safe_args({"summary": "姓名张三，手机号 13812345678"}) == {
        "summary": "[问题描述已隐藏]"
    }
    assert safe_args({"phone_last4": None}) == {}
    assert safe_plan({"steps": [{"id": "a", "action": "search_policy", "when": "always", "secret": "sk-secret123456"}]}) == {
        "steps": [{"id": "a", "action": "search_policy", "when": "always"}]
    }
    assert safe_task_trace([{"id": "a", "status": "done", "secret": "private"}]) == [
        {"id": "a", "status": "done"}
    ]
    result = safe_tool_result("search_policy", {
        "ok": True,
        "references": [{"title": "保修", "source": "policy.md", "chunk_id": "abc", "score": .7, "content": "内部内容"}],
    })
    assert "content" not in result["query_results"][0]


def test_policy_api_lists_real_documents_and_searches_both_methods(monkeypatch) -> None:
    class FakeKnowledgeBase:
        def search(self, query, top_k, method):
            return [{"title": method, "source": "policy.md", "content": query,
                     "chunk_id": "chunk", "score": .8, "dense_relevance": .7,
                     "lexical_score": .4}][:top_k]

        def search_reranked_hybrid(self, query, top_k):
            return [{"title": "hybrid_rerank", "source": "policy.md", "content": query,
                     "chunk_id": "chunk", "score": .8, "dense_relevance": .7,
                     "lexical_score": .4}][:top_k]

    monkeypatch.setattr(workbench, "get_policy_knowledge_base", FakeKnowledgeBase)
    client = TestClient(app, headers={"X-Session-Token": "a" * 64})
    policies = client.get("/workbench/policies")
    assert policies.status_code == 200
    assert any(item["collection"] == "online" for item in policies.json()["documents"])
    response = client.post("/workbench/search", json={"query": "保修政策", "top_k": 2})
    assert response.status_code == 200
    assert [run["method"] for run in response.json()["runs"]] == ["dense", "hybrid_rerank"]
    assert response.json()["runs"][0]["hits"][0]["content"] == "保修政策"
    assert response.json()["rewrite"] is None


def test_system_status_uses_discovered_mcp_tools(monkeypatch) -> None:
    monkeypatch.setattr(workbench, "get_agent", lambda _: object())
    monkeypatch.setattr(workbench, "discovered_tool_names", lambda: ("search_policy",))
    client = TestClient(app, headers={"X-Session-Token": "a" * 64})
    result = client.get("/workbench/status")
    assert result.status_code == 200
    assert result.json()["mcp"]["tool_count"] == 1
    assert result.json()["mcp"]["tools"] == ["search_policy"]


def test_real_graph_tool_call_produces_sanitized_trace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(trace_store, "_path", lambda: tmp_path / "traces.db")
    monkeypatch.setattr(store, "DEFAULT_DB_PATH", tmp_path / "business.db")
    monkeypatch.setenv("BUSINESS_DATABASE_TYPE", "sqlite")

    class ToolModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = ToolModel(responses=[
        AIMessage(content="", tool_calls=[ToolCall(
            name="get_order_status", id="call-1",
            args={"order_id": "ORD1001", "phone_last4": "8821"},
        )]),
        AIMessage(content="订单正在配送。"),
    ])
    graph = build_customer_support_graph(
        model, force_routing=False, enable_router=False, tools=[get_order_status_tool]
    )
    graph.checkpointer = MemorySaver()
    monkeypatch.setattr(service_module, "get_agent", lambda _: graph)
    client = TestClient(app, headers={"X-Session-Token": "a" * 64})
    response = client.post("/invoke", json={
        "thread_id": "trace-thread", "message": "查询订单 ORD1001，手机号后四位 8821"
    })
    assert response.status_code == 200
    records = client.get("/workbench/traces", params={"thread_id": "trace-thread"}).json()["traces"]
    assert len(records) == 1
    detail = client.get("/workbench/traces/" + records[0]["trace_id"]).json()
    tools = [event for event in detail["events"] if event["kind"] == "tool"]
    assert tools[0]["name"] == "get_order_status"
    assert tools[0]["arguments"]["phone_last4"] == "**21"
    assert tools[0]["duration_ms"] >= 0
    assert any(event["kind"] == "llm" for event in detail["events"])
