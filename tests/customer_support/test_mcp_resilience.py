from __future__ import annotations

import asyncio
from collections import Counter

import pytest
from pydantic import create_model

import customer_support.mcp_client as client
from core.settings import settings


@pytest.fixture(autouse=True)
def isolated_resilience_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(client, "_read_cache", client._ReadCache())
    monkeypatch.setattr(client, "_circuits", {name: client._Circuit() for name in client.TOOL_NAMES})
    monkeypatch.setattr(settings, "MCP_CIRCUIT_FAILURE_THRESHOLD", 3)
    monkeypatch.setattr(settings, "MCP_CIRCUIT_RESET_SECONDS", 0.02)
    monkeypatch.setattr(settings, "MCP_TOOL_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(settings, "MCP_TICKET_TIMEOUT_SECONDS", 0.02)


def make_tool(name: str, function):
    async def invoke(arguments):
        return await function(**arguments)

    fields = {key: (value, ...) for key, value in function.__annotations__.items()
              if key != "return"}
    if name == "create_support_ticket":
        fields["approval_token"] = (str, "")
    return type("FakeMCPTool", (), {
        "name": name,
        "description": "test MCP tool",
        "args_schema": create_model("Args", **fields).model_json_schema(),
        "ainvoke": staticmethod(invoke),
    })()


@pytest.mark.asyncio
async def test_read_cache_copies_results_and_separates_arguments():
    calls = Counter()

    async def lookup(order_id: str, phone_last4: str):
        calls[order_id] += 1
        return {"ok": True, "order_id": order_id, "nested": {"items": [1]}}

    wrapped = client._tool_wrapper(make_tool("get_order_status", lookup), "secret")
    first = await wrapped.ainvoke({"order_id": "ORD1001", "phone_last4": "8821"})
    first["nested"]["items"].append(2)
    second = await wrapped.ainvoke({"order_id": "ORD1001", "phone_last4": "8821"})
    third = await wrapped.ainvoke({"order_id": "ORD1002", "phone_last4": "8821"})

    assert second["nested"]["items"] == [1]
    assert third["order_id"] == "ORD1002"
    assert calls == Counter({"ORD1001": 1, "ORD1002": 1})


@pytest.mark.asyncio
async def test_policy_results_are_cached_at_search_entry_not_mcp_wrapper():
    calls = 0
    corpus = "v1"

    async def search(query: str):
        nonlocal calls
        calls += 1
        return {"ok": True, "title": corpus, "references": []}

    wrapped = client._tool_wrapper(make_tool("search_policy", search), "secret")
    assert (await wrapped.ainvoke({"query": "return"}))["title"] == "v1"
    await wrapped.ainvoke({"query": "return"})
    corpus = "v2"
    assert (await wrapped.ainvoke({"query": "return"}))["title"] == "v2"
    assert calls == 3


def test_cache_expires_at_ttl(monkeypatch: pytest.MonkeyPatch):
    now = 100.0
    monkeypatch.setattr(client.time, "monotonic", lambda: now)
    cache = client._ReadCache()
    cache.put("key", {"ok": True}, ttl=15)
    assert cache.get("key") == {"ok": True}
    now += 15.1
    assert cache.get("key") is None


@pytest.mark.asyncio
async def test_business_failure_does_not_trip_circuit():
    calls = 0

    async def missing_order(order_id: str, phone_last4: str):
        nonlocal calls
        calls += 1
        return {"ok": False, "error_code": "ORDER_NOT_FOUND_OR_VERIFICATION_FAILED"}

    wrapped = client._tool_wrapper(make_tool("get_order_status", missing_order), "secret")
    for _ in range(4):
        result = await wrapped.ainvoke({"order_id": "ORD9999", "phone_last4": "8821"})
        assert result["error_code"] == "ORDER_NOT_FOUND_OR_VERIFICATION_FAILED"
    assert calls == 4


@pytest.mark.asyncio
async def test_circuit_opens_and_allows_a_single_recovery_probe():
    calls = 0
    fail = True

    async def lookup(order_id: str, phone_last4: str):
        nonlocal calls
        calls += 1
        if fail:
            raise ConnectionError("offline")
        return {"ok": True, "order_id": order_id}

    wrapped = client._tool_wrapper(make_tool("get_order_status", lookup), "secret")
    args = {"order_id": "ORD1001", "phone_last4": "8821"}
    for _ in range(3):
        assert (await wrapped.ainvoke(args))["error_code"] == "MCP_TOOL_UNAVAILABLE"
    assert (await wrapped.ainvoke(args))["error_code"] == "CIRCUIT_OPEN"
    assert calls == 3
    await asyncio.sleep(0.03)
    fail = False
    assert (await wrapped.ainvoke(args))["ok"] is True
    assert calls == 4


@pytest.mark.asyncio
async def test_timeouts_degrade_and_ticket_is_never_retried():
    calls = 0

    async def create(order_id: str, phone_last4: str, category: str, summary: str,
                     approval_token: str = ""):
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)
        return {"ok": True, "ticket_id": "T1"}

    wrapped = client._tool_wrapper(make_tool("create_support_ticket", create), "secret")
    args = {"order_id": "ORD1001", "phone_last4": "8821", "category": "logistics",
            "summary": "delayed"}
    first = await wrapped.ainvoke(args)
    assert first["error_code"] == "TICKET_STATUS_UNKNOWN"
    assert "核查工单状态" in first["error"]
    assert calls == 1
