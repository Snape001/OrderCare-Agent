from pathlib import Path
from unittest.mock import Mock

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

import agents.customer_support_mock as customer_support_agent
import customer_support.store as store
from agents.customer_support_mock import builder, customer_support_node


@pytest.fixture
def isolated_business_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(store, "DEFAULT_DB_PATH", tmp_path / "support.db")

    def fake_policy_search(query: str):
        if "真人" in query:
            title = "客服升级与工单"
            content = "知识库无法回答时可以转人工处理。"
        elif "发票" in query:
            title = "发票服务"
            content = "订单完成后 45 天内可以申请电子发票。"
        else:
            title = "七天无理由退款"
            content = "商品保持未拆封且不影响二次销售时可以申请。"
        return {
            "title": title,
            "content": content,
            "source": "data/policies/customer_service_policy.md",
            "score": 0.18,
        }

    monkeypatch.setattr(
        customer_support_agent,
        "search_policy",
        fake_policy_search,
    )


async def _turn(graph, thread_id: str, text: str):
    return await graph.ainvoke(
        {"messages": [HumanMessage(content=text)]},
        config={"configurable": {"thread_id": thread_id}},
    )


def _spies(monkeypatch: pytest.MonkeyPatch):
    policy = Mock(wraps=customer_support_agent.search_policy)
    order = Mock(wraps=store.get_order_status)
    refund = Mock(wraps=store.refund_eligibility)
    monkeypatch.setattr(customer_support_agent, "search_policy", policy)
    monkeypatch.setattr(customer_support_agent, "get_order_status", order)
    monkeypatch.setattr(customer_support_agent, "refund_eligibility", refund)
    return policy, order, refund


@pytest.mark.asyncio
async def test_greeting_and_capability_intro_do_not_search(isolated_business_db, monkeypatch):
    policy, order, refund = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    result = await _turn(graph, "greeting", "你好，请简单介绍一下你能帮助我处理哪些售后问题。")

    assert "查询订单状态" in result["messages"][-1].content
    assert "检索分数" not in result["messages"][-1].content
    policy.assert_not_called()
    order.assert_not_called()
    refund.assert_not_called()


@pytest.mark.asyncio
async def test_policy_question_still_calls_search_and_cites_source(
    isolated_business_db, monkeypatch
):
    policy, order, refund = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    result = await _turn(graph, "policy", "订单完成40天后还能申请电子发票吗？")

    policy.assert_called_once_with("订单完成40天后还能申请电子发票吗？")
    assert "customer_service_policy.md" in result["messages"][-1].content
    order.assert_not_called()
    refund.assert_not_called()


@pytest.mark.asyncio
async def test_logistics_query_fills_order_and_phone_across_turns(
    isolated_business_db, monkeypatch
):
    policy, order, refund = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    first = await _turn(graph, "lookup", "我想查询一个订单的物流状态。")
    assert first["pending_query"] == {"intent": "order_status"}
    assert "订单号" in first["messages"][-1].content
    policy.assert_not_called()
    order.assert_not_called()

    wrong = await _turn(graph, "lookup", "C001。")
    assert wrong["pending_query"] == {"intent": "order_status"}
    assert "订单号格式不正确" in wrong["messages"][-1].content
    order.assert_not_called()

    third = await _turn(graph, "lookup", "ORD1001。")
    assert third["pending_query"] == {"intent": "order_status", "order_id": "ORD1001"}
    assert "手机号后四位" in third["messages"][-1].content
    order.assert_not_called()

    fourth = await _turn(graph, "lookup", "8821。")
    order.assert_called_once_with("ORD1001", "8821")
    assert "运输中" in fourth["messages"][-1].content
    assert fourth["pending_query"] is None
    policy.assert_not_called()
    refund.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_order_with_phone_does_not_call_tool(isolated_business_db, monkeypatch):
    _, order, refund = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    result = await _turn(graph, "invalid", "帮我查询订单 C001 的物流状态，手机号后四位 8821。")

    assert "订单号格式不正确" in result["messages"][-1].content
    assert result["pending_query"]["intent"] == "order_status"
    order.assert_not_called()
    refund.assert_not_called()


@pytest.mark.asyncio
async def test_wrong_phone_and_missing_order_share_private_failure(
    isolated_business_db, monkeypatch
):
    _, order, _ = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    wrong_phone = await _turn(graph, "bad-phone", "查询订单 ORD1001，手机号后四位 0000")
    missing_order = await _turn(graph, "missing-order", "查询订单 ORD9999，手机号后四位 0000")

    assert order.call_count == 2
    assert wrong_phone["messages"][-1].content == missing_order["messages"][-1].content
    assert "无线耳机" not in wrong_phone["messages"][-1].content
    assert "运输中" not in wrong_phone["messages"][-1].content
    assert wrong_phone["pending_query"] == {"intent": "order_status", "order_id": "ORD1001"}
    retry = await _turn(graph, "bad-phone", "8821")
    assert "运输中" in retry["messages"][-1].content


@pytest.mark.asyncio
async def test_query_state_is_isolated_by_checkpoint_thread(isolated_business_db, monkeypatch):
    _, order, _ = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    first_a = await _turn(graph, "session-a", "查询订单 ORD1001")
    first_b = await _turn(graph, "session-b", "8821")

    assert first_a["pending_query"] == {"intent": "order_status", "order_id": "ORD1001"}
    assert first_b.get("pending_query") is None
    order.assert_not_called()
    second_a = await _turn(graph, "session-a", "8821")
    assert "运输中" in second_a["messages"][-1].content
    order.assert_called_once_with("ORD1001", "8821")


@pytest.mark.asyncio
async def test_complete_order_query_calls_tool_without_reprompt(isolated_business_db, monkeypatch):
    policy, order, _ = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    result = await _turn(
        graph, "complete", "帮我查询订单 ORD1001 的物流状态，手机号后四位是 8821。"
    )

    order.assert_called_once_with("ORD1001", "8821")
    assert "运输中" in result["messages"][-1].content
    assert "请提供" not in result["messages"][-1].content
    assert result["pending_query"] is None
    policy.assert_not_called()


@pytest.mark.asyncio
async def test_natural_logistics_phrase_collects_order_instead_of_searching(
    isolated_business_db, monkeypatch
):
    policy, order, _ = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    result = await _turn(graph, "natural-logistics", "我想查一下我的快递到哪了")

    assert result["pending_query"] == {"intent": "order_status"}
    policy.assert_not_called()
    order.assert_not_called()


@pytest.mark.asyncio
async def test_phone_supplied_before_order_is_retained(isolated_business_db, monkeypatch):
    _, order, _ = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    first = await _turn(graph, "phone-first", "我想查询物流，手机号后四位 8821")
    assert first["pending_query"] == {"intent": "order_status", "phone_last4": "8821"}
    second = await _turn(graph, "phone-first", "ORD1001")

    order.assert_called_once_with("ORD1001", "8821")
    assert "运输中" in second["messages"][-1].content
    assert second["pending_query"] is None


@pytest.mark.asyncio
async def test_refund_eligibility_uses_business_tool(isolated_business_db, monkeypatch):
    policy, order, refund = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    first = await _turn(graph, "refund", "我想判断退款资格")
    assert first["pending_query"] == {"intent": "refund"}
    second = await _turn(graph, "refund", "ORD1002")
    assert second["pending_query"] == {"intent": "refund", "order_id": "ORD1002"}
    result = await _turn(graph, "refund", "8821")

    refund.assert_called_once_with("ORD1002", "8821")
    assert "可以申请" in result["messages"][-1].content
    assert result["pending_query"] is None
    policy.assert_not_called()
    order.assert_not_called()


@pytest.mark.asyncio
async def test_one_turn_refund_uses_tool_and_policy_question_uses_search(
    isolated_business_db, monkeypatch
):
    policy, order, refund = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    eligibility = await _turn(graph, "one-turn-refund", "订单 ORD1002 能退款吗？手机号后四位 8821")
    rules = await _turn(graph, "refund-rules", "退款资格需要满足什么条件？")

    refund.assert_called_once_with("ORD1002", "8821")
    assert "可以申请" in eligibility["messages"][-1].content
    policy.assert_called_once_with("退款资格需要满足什么条件？")
    assert "customer_service_policy.md" in rules["messages"][-1].content
    order.assert_not_called()


@pytest.mark.asyncio
async def test_can_i_return_phrase_uses_refund_tool(isolated_business_db, monkeypatch):
    policy, order, refund = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    result = await _turn(graph, "can-return", "ORD1002 能不能退？手机号后四位 8821")

    refund.assert_called_once_with("ORD1002", "8821")
    assert "可以申请" in result["messages"][-1].content
    policy.assert_not_called()
    order.assert_not_called()


@pytest.mark.asyncio
async def test_outside_scope_and_unclear_intent_do_not_search(isolated_business_db, monkeypatch):
    policy, order, refund = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    outside = await _turn(graph, "outside", "今天天气怎么样？")
    unclear = await _turn(graph, "unclear", "帮我看看")

    assert "只处理商城" in outside["messages"][-1].content
    assert "请问你想" in unclear["messages"][-1].content
    assert outside["messages"][-1].content != unclear["messages"][-1].content
    policy.assert_not_called()
    order.assert_not_called()
    refund.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_clears_pending_query(isolated_business_db, monkeypatch):
    _, order, _ = _spies(monkeypatch)
    graph = builder.compile(checkpointer=MemorySaver())

    await _turn(graph, "cancel", "查询订单 ORD1001")
    cancelled = await _turn(graph, "cancel", "取消查询")
    after = await _turn(graph, "cancel", "8821")

    assert cancelled["pending_query"] is None
    assert after["pending_query"] is None
    order.assert_not_called()


@pytest.mark.asyncio
async def test_policy_question_returns_source(isolated_business_db):
    result = await customer_support_node(
        {"messages": [HumanMessage(content="七天无理由退款有什么要求？")]}
    )

    answer = result["messages"][-1].content
    assert "未拆封" in answer
    assert "customer_service_policy.md" in answer


@pytest.mark.asyncio
async def test_policy_synonym_is_routed_to_rag(isolated_business_db):
    result = await customer_support_node(
        {"messages": [HumanMessage(content="机器人答不上来，我想找真人处理。")]}
    )

    answer = result["messages"][-1].content
    assert "客服升级与工单" in answer
    assert "转人工" in answer


@pytest.mark.asyncio
async def test_policy_question_with_order_word_is_not_misrouted(isolated_business_db):
    result = await customer_support_node(
        {"messages": [HumanMessage(content="订单完成40天后还能申请电子发票吗？")]}
    )

    answer = result["messages"][-1].content
    assert "发票服务" in answer
    assert "45 天" in answer
    assert "请提供订单号" not in answer


@pytest.mark.asyncio
async def test_order_lookup_requires_identity_verification(isolated_business_db):
    missing_phone = await customer_support_node(
        {"messages": [HumanMessage(content="查询订单 ORD1001")]}
    )
    wrong_phone = await customer_support_node(
        {"messages": [HumanMessage(content="查询订单 ORD1001，手机号后四位 0000")]}
    )

    assert "手机号后四位" in missing_phone["messages"][-1].content
    assert "验证信息不匹配" in wrong_phone["messages"][-1].content


@pytest.mark.asyncio
async def test_ticket_requires_confirmation(isolated_business_db):
    first = await customer_support_node(
        {"messages": [HumanMessage(content="为 ORD1001 创建人工客服工单，手机号后四位 8821")]}
    )

    assert "请回复“确认”" in first["messages"][-1].content
    assert first["pending_ticket"]["order_id"] == "ORD1001"

    confirmed = await customer_support_node(
        {
            "messages": [HumanMessage(content="确认")],
            "pending_ticket": first["pending_ticket"],
        }
    )

    assert "工单已创建" in confirmed["messages"][-1].content
    assert confirmed["pending_ticket"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message", ["我还没确认", "不是", "好的", "是", "确认之前先解释", "我不同意"]
)
async def test_ambiguous_text_never_creates_ticket(isolated_business_db, message):
    first = await customer_support_node(
        {"messages": [HumanMessage(content="为 ORD1001 创建工单，手机号后四位 8821")]}
    )
    result = await customer_support_node(
        {
            "messages": [HumanMessage(content=message)],
            "pending_ticket": first["pending_ticket"],
        }
    )
    assert "工单已创建" not in result["messages"][-1].content
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM support_tickets").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_confirmation_without_pending_action_does_not_write(isolated_business_db):
    await customer_support_node({"messages": [HumanMessage(content="确认")]})
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM support_tickets").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_cancel_then_confirmation_does_not_write(isolated_business_db):
    first = await customer_support_node(
        {"messages": [HumanMessage(content="为 ORD1001 创建工单，手机号后四位 8821")]}
    )
    cancelled = await customer_support_node(
        {
            "messages": [HumanMessage(content="取消")],
            "pending_ticket": first["pending_ticket"],
        }
    )
    assert cancelled["pending_ticket"] is None
    await customer_support_node(
        {
            "messages": [HumanMessage(content="确认")],
            "pending_ticket": cancelled["pending_ticket"],
        }
    )
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM support_tickets").fetchone()[0] == 0
