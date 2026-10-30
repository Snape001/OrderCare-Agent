import json

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langgraph.types import Interrupt, StateSnapshot

from core import settings
from service.presentation import ThinkingFilter, public_customer_message


def _events(response):
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]


@pytest.mark.parametrize(
    "parts,expected",
    [
        (["<th", "ink>内部思考", "</th", "ink>订单运输中"], "订单运输中"),
        (["内部思考", "</thi", "nk>最终答复"], "最终答复"),
        (["订单状态：<pending>处理中</pending>"], "订单状态：<pending>处理中</pending>"),
    ],
)
def test_thinking_filter_handles_split_tags_and_preserves_other_text(parts, expected):
    filter_ = ThinkingFilter()
    for part in parts:
        filter_.feed(part)
    assert filter_.finish() == expected


def test_raw_tool_call_transcript_is_not_a_public_answer():
    assert public_customer_message(AIMessage(content="Tool Call: get_order_status\n{...}")) is None


@pytest.mark.parametrize(
    "answer",
    [
        "订单 ORD1001 当前状态为运输中。",
        "七天无理由退款需保持商品完好。来源：customer_service_policy.md",
        "你好，我可以帮助你处理订单、退款和售后问题。",
    ],
)
def test_ollama_public_stream_only_returns_final_answer(
    test_client, mock_agent, monkeypatch, answer
):
    monkeypatch.setattr(settings, "CUSTOMER_SUPPORT_MODE", "ollama")
    raw = "内部思考：手机号后四位 8821，Tool Call: get_order_status"
    tool_call = {"name": "get_order_status", "args": {"phone_last4": "8821"}, "id": "call-1"}

    async def events(**kwargs):
        for part in ["<th", "ink>", raw, "</th", "ink>"]:
            yield "messages", (AIMessageChunk(content=part), {"tags": []})
        yield "updates", {"model": {"messages": [AIMessage(content=raw, tool_calls=[tool_call])]}}
        yield "updates", {"tools": {"messages": [ToolMessage(content=raw, tool_call_id="call-1")]}}
        yield (
            "updates",
            {"model": {"messages": [AIMessage(content=f"<think>{raw}</think>{answer}")]}},
        )

    mock_agent.astream = events
    response = test_client.post("/stream", json={"message": "查询订单", "stream_tokens": True})
    assert response.status_code == 200
    payload = _events(response)
    assert len(payload) == 1
    assert payload[0]["type"] == "message"
    assert payload[0]["content"]["content"] == answer
    assert payload[0]["content"]["tool_calls"] == []
    assert raw not in response.text
    assert "8821" not in response.text
    assert "<think>" not in response.text
    assert "Tool Call:" not in response.text


def test_ollama_approval_prompt_hides_tool_arguments(test_client, mock_agent, monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_SUPPORT_MODE", "ollama")

    async def events(**kwargs):
        yield (
            "updates",
            {
                "model": {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "create_support_ticket",
                                    "args": {"phone_last4": "8821"},
                                    "id": "ticket",
                                }
                            ],
                        )
                    ]
                }
            },
        )
        yield (
            "updates",
            {
                "__interrupt__": [
                    Interrupt(
                        value={
                            "action_requests": [
                                {"name": "create_support_ticket", "args": {"phone_last4": "8821"}}
                            ]
                        }
                    )
                ]
            },
        )

    mock_agent.astream = events
    response = test_client.post("/stream", json={"message": "创建工单"})
    payload = _events(response)
    assert len(payload) == 1
    assert "确认" in payload[0]["content"]["content"]
    assert "8821" not in response.text
    assert "create_support_ticket" not in response.text


def test_ollama_invoke_and_history_hide_internal_messages(test_client, mock_agent, monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_SUPPORT_MODE", "ollama")
    raw = "内部思考手机号后四位 8821"
    mock_agent.ainvoke.return_value = [
        ("values", {"messages": [AIMessage(content=f"<think>{raw}</think>订单运输中")]})
    ]
    result = test_client.post("/invoke", json={"message": "查询订单"})
    assert result.json()["content"] == "订单运输中"

    mock_agent.aget_state.return_value = StateSnapshot(
        values={
            "messages": [
                AIMessage(
                    content=raw,
                    tool_calls=[
                        {
                            "name": "get_order_status",
                            "args": {"phone_last4": "8821"},
                            "id": "call-1",
                        }
                    ],
                ),
                ToolMessage(content=raw, tool_call_id="call-1"),
                AIMessage(content=f"<think>{raw}</think>订单运输中"),
            ]
        },
        next=(),
        config={"configurable": {"thread_id": "test"}},
        metadata=None,
        created_at=None,
        parent_config=None,
        tasks=(),
        interrupts=(),
    )
    history = test_client.post("/history", json={"thread_id": "test"})
    assert history.status_code == 200
    assert [item["content"] for item in history.json()["messages"]] == ["订单运输中"]
    assert raw not in history.text
