import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agents.customer_support_agent import build_customer_support_graph
from memory.context_manager import ContextManager, TokenBudget, count_tokens, query_terms


def test_overlapping_chinese_terms_keep_semantic_episode_in_context():
    assert {"台灯", "工单"}.issubset(query_terms("另开一段对话看台灯工单"))
    result, system = manager(total=1800).assemble(
        messages=[HumanMessage(content="另开一段对话看台灯工单")],
        system=SystemMessage(content="按规则回答"), state={},
        memory={"notes": [{"kind": "episode", "value": "售后事件：售后工单创建；商品：台灯"}]},
    )
    assert result[-1].content == "另开一段对话看台灯工单"
    assert system is not None and "售后工单创建" in system.content


def manager(total=1200):
    return ContextManager(
        TokenBudget(total=total, system=500, history=400, memory=300, rag=350, tools=300)
    )


def test_task_assembly_selects_relevant_memory_and_keeps_current_request():
    user = HumanMessage(content="这个订单耳机维修政策是什么")
    result, system = manager().assemble(
        messages=[HumanMessage(content="上个月查询物流"), user],
        system=SystemMessage(content="系统规则：业务事实以工具为准"),
        state={"route": {"intents": ["repair_query"]}},
        memory={
            "working": {"current_order": "ORD1001", "verified": True},
            "summary": "上次咨询维修",
            "notes": [
                {"kind": "support_summary", "value": "耳机维修", "updated_at": "2026-11-06"},
                {"kind": "support_summary", "value": "发票税号", "updated_at": "2026-11-05"},
            ],
        },
    )
    assert result[-1] is user
    assert system is not None
    assert "耳机维修" in system.content
    assert "发票税号" not in system.content
    assert "ORD1001" in system.content


def test_current_route_replaces_stale_working_task():
    _, system = manager().assemble(
        messages=[HumanMessage(content="七天无理由政策")],
        system=SystemMessage(content="规则"),
        state={"route": {"intents": ["policy_query"], "entities": {}}},
        memory={"working": {"intents": ["order_query"], "current_order": "ORD1001"}},
    )
    assert system is not None
    assert "policy_query" in system.content
    assert "ORD1001" not in system.content


def test_long_history_budget_evicts_old_messages():
    history = [HumanMessage(content="旧咨询" * 100) for _ in range(20)]
    current = HumanMessage(content="现在查询订单")
    result, system = manager(total=450).assemble(
        messages=[*history, current], system=SystemMessage(content="规则"), state={}, memory=None
    )
    assert result[-1] is current
    assert len(result) < len(history) + 1
    assert count_tokens(result + ([system] if system else [])) <= 450


def test_tool_pair_stays_intact_and_current_turn_order_is_preserved():
    user = HumanMessage(content="查退款政策")
    call = AIMessage(content="", tool_calls=[{"name": "search_policy", "args": {}, "id": "t1"}])
    result = ToolMessage(content="七天无理由需保持完好", name="search_policy", tool_call_id="t1")
    output, _ = manager().assemble(
        messages=[user, call, result], system=None, state={}, memory=None
    )
    assert output == [user, call, result]


def test_orphan_tool_result_and_irrelevant_old_rag_are_dropped():
    old = HumanMessage(content="退货政策")
    call = AIMessage(content="", tool_calls=[{"name": "search_policy", "args": {}, "id": "old"}])
    result = ToolMessage(content="旧证据", name="search_policy", tool_call_id="old")
    orphan = ToolMessage(content="孤立", name="get_order_status", tool_call_id="missing")
    current = HumanMessage(content="你好")
    output, _ = manager().assemble(
        messages=[old, call, result, orphan, current], system=None, state={}, memory=None
    )
    assert current in output
    assert call not in output and result not in output and orphan not in output


def test_oversize_rules_do_not_remove_user_request():
    current = HumanMessage(content="确认创建工单")
    output, system = manager(total=100).assemble(
        messages=[current],
        system=SystemMessage(content="安全审批规则" * 100),
        state={"plan": {"steps": [{"action": "create_support_ticket"}]}},
        memory=None,
    )
    assert output == [current]
    assert system is not None and "安全审批规则" in system.content


def test_current_tool_result_is_kept_even_if_it_exceeds_budget():
    user = HumanMessage(content="查询订单")
    call = AIMessage(
        content="", tool_calls=[{"name": "get_order_status", "args": {}, "id": "order"}]
    )
    result = ToolMessage(
        content="已核验的本轮订单结果" * 100, name="get_order_status", tool_call_id="order"
    )
    output, _ = manager(total=100).assemble(
        messages=[user, call, result], system=None, state={}, memory=None
    )
    assert output == [user, call, result]


def test_recent_relevant_memory_wins_when_memory_budget_is_small():
    user = HumanMessage(content="耳机维修")
    _, system = ContextManager(
        TokenBudget(total=500, system=100, history=100, memory=45, rag=100, tools=100)
    ).assemble(
        messages=[user],
        system=None,
        state={},
        memory={
            "notes": [
                {"kind": "support_summary", "value": "耳机维修", "updated_at": "2026-11-06"},
                {"kind": "support_summary", "value": "耳机维修旧记录", "updated_at": "2025-01-01"},
            ]
        },
    )
    assert system is not None and "耳机维修" in system.content
    assert "旧记录" not in system.content


@pytest.mark.asyncio
async def test_graph_receives_request_scoped_memory_metadata(monkeypatch):
    seen = []
    original = ContextManager.assemble

    def capture(self, **kwargs):
        seen.append(kwargs["memory"])
        return original(self, **kwargs)

    monkeypatch.setattr(ContextManager, "assemble", capture)
    graph = build_customer_support_graph(
        FakeMessagesListChatModel(responses=[AIMessage(content="您好")]),
        enable_router=False,
        force_routing=False,
        tools=[],
    )
    await graph.ainvoke(
        {"messages": [HumanMessage(content="你好")]},
        config={"metadata": {"memory_context": {"summary": "上次咨询物流"}}},
    )
    assert seen and seen[0] == {"summary": "上次咨询物流"}
