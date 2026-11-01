"""Router/planner behavior and graph execution with deterministic model responses."""

import json

import pytest
from langchain_core.language_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import customer_support.store as store
from agents.customer_support_agent import build_customer_support_graph
from customer_support.routing import (
    Entities,
    Intent,
    Plan,
    Route,
    Step,
    missing_fields,
    next_task,
    validate_plan,
    validated_route,
)


class RoutedModel(FakeMessagesListChatModel):
    route_result: dict
    plan_result: dict | None = None
    plan_calls: int = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        if schema is Route:
            return RunnableLambda(lambda _: self.route_result)
        if schema is Plan:

            def planned(_):
                self.plan_calls += 1
                return self.plan_result

            return RunnableLambda(planned)
        raise AssertionError(schema)


def fake(route, responses, plan=None):
    return RoutedModel(responses=responses, route_result=route, plan_result=plan)


def tool_call(name, **args):
    return AIMessage(content="", tool_calls=[ToolCall(name=name, args=args, id=name)])


@pytest.fixture
def business_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DEFAULT_DB_PATH", tmp_path / "router.db")


@pytest.mark.asyncio
async def test_greeting_skips_planner():
    model = fake(
        {"intents": ["general"], "entities": {}, "conditional": False}, [AIMessage(content="你好")]
    )
    graph = build_customer_support_graph(model, enable_router=True)
    result = await graph.ainvoke({"messages": [HumanMessage(content="你好")]})
    assert model.plan_calls == 0
    assert result["plan"]["steps"][0]["action"] == "summarize"
    assert result["messages"][-1].content == "你好"


@pytest.mark.asyncio
async def test_policy_and_order_single_intent_use_existing_tools(business_db):
    policy = fake(
        {"intents": ["policy_query"], "entities": {}, "conditional": False},
        [
            tool_call("search_policy", query="七天无理由退货"),
            AIMessage(content="请看七天无理由退款政策"),
        ],
    )
    result = await build_customer_support_graph(policy, enable_router=True).ainvoke(
        {"messages": [HumanMessage(content="七天无理由退货政策？")]}
    )
    assert policy.plan_calls == 0
    assert any(isinstance(m, ToolMessage) and m.name == "search_policy" for m in result["messages"])
    order = fake(
        {
            "intents": ["order_query"],
            "entities": {"order_id": "FAKE", "phone_last4": "9999"},
            "conditional": False,
        },
        [
            tool_call("get_order_status", order_id="ORD1001", phone_last4="8821"),
            AIMessage(content="运输中"),
        ],
    )
    result = await build_customer_support_graph(order, enable_router=True).ainvoke(
        {"messages": [HumanMessage(content="查订单 ORD1001，手机号后四位 8821")]}
    )
    assert order.plan_calls == 0
    assert result["route"]["entities"]["order_id"] == "ORD1001"
    assert any(
        isinstance(m, ToolMessage) and m.name == "get_order_status" for m in result["messages"]
    )


@pytest.mark.asyncio
async def test_missing_fields_ask_without_tool_or_planner():
    model = fake(
        {"intents": ["refund_check", "repair_query"], "entities": {}, "conditional": True},
        [AIMessage(content="不应使用")],
    )
    result = await build_customer_support_graph(model, enable_router=True).ainvoke(
        {"messages": [HumanMessage(content="耳机坏了，能退就退，不行怎么修？")]}
    )
    assert model.plan_calls == 0
    assert "订单号" in result["messages"][-1].content
    assert "手机号后四位" in result["messages"][-1].content
    assert not any(isinstance(m, ToolMessage) for m in result["messages"])


def test_structured_plan_and_conditions():
    route = Route(
        intents=[Intent.ORDER, Intent.REFUND, Intent.REPAIR],
        entities=Entities(order_id="ORD1001", phone_last4="8821"),
        conditional=True,
    )
    plan = Plan(
        steps=[
            Step(id="order", action="get_order_status"),
            Step(id="refund", action="check_refund_eligibility", depends_on=["order"]),
            Step(
                id="repair", action="search_policy", depends_on=["refund"], when="refund_ineligible"
            ),
            Step(id="end", action="summarize"),
        ]
    )
    validate_plan(plan, route)
    messages = [
        HumanMessage(content="test"),
        ToolMessage(
            content=json.dumps({"ok": True, "eligible": True}),
            name="check_refund_eligibility",
            tool_call_id="r",
        ),
        ToolMessage(content=json.dumps({"ok": True}), name="get_order_status", tool_call_id="o"),
    ]
    assert next_task(plan, messages)[0] is None
    assert next_task(plan, messages)[1][2]["status"] == "skipped"
    messages[1] = ToolMessage(
        content=json.dumps({"ok": True, "eligible": False}),
        name="check_refund_eligibility",
        tool_call_id="r",
    )
    assert next_task(plan, messages)[0].action == "search_policy"
    messages[1] = ToolMessage(
        content=json.dumps({"ok": False}), name="check_refund_eligibility", tool_call_id="r"
    )
    assert next_task(plan, messages)[0] is None
    assert next_task(plan, messages)[1][1]["status"] == "failed"


def test_router_anchors_entities_and_rejects_invalid_plan():
    route = validated_route(
        Route(
            intents=[Intent.ORDER, Intent.ORDER],
            entities=Entities(order_id="MADEUP", phone_last4="9999"),
        ),
        [HumanMessage(content="订单 ORD1001，尾号 8821")],
    )
    assert route.intents == [Intent.ORDER]
    assert missing_fields(route) == []
    assert route.entities.phone_last4 == "8821"
    invented = validated_route(
        Route(intents=[Intent.TICKET], entities=Entities(product_name="不存在的商品")),
        [HumanMessage(content="你好")],
    )
    assert invented.intents == [Intent.GENERAL]
    assert invented.entities.product_name is None
    with pytest.raises(ValueError, match="unrequested"):
        validate_plan(
            Plan(
                steps=[
                    Step(id="o", action="get_order_status"),
                    Step(id="x", action="create_support_ticket", depends_on=["o"]),
                ]
            ),
            route,
        )


@pytest.mark.asyncio
async def test_complex_plan_calls_existing_tool_and_preserves_hitl(business_db):
    model = fake(
        {"intents": ["order_query", "ticket_create"], "entities": {}, "conditional": False},
        [
            tool_call("get_order_status", order_id="ORD1001", phone_last4="8821"),
            tool_call(
                "create_support_ticket",
                order_id="ORD1001",
                phone_last4="8821",
                category="物流",
                summary="物流未更新",
            ),
            AIMessage(content="工单已创建"),
        ],
        {
            "steps": [
                {"id": "o", "action": "get_order_status"},
                {"id": "t", "action": "create_support_ticket", "depends_on": ["o"]},
            ]
        },
    )
    graph = build_customer_support_graph(model, enable_router=True)
    graph.checkpointer = MemorySaver()
    config = {"configurable": {"thread_id": "router-ticket"}}
    first = await graph.ainvoke(
        {"messages": [HumanMessage(content="查订单 ORD1001，手机号后四位 8821，再创建物流工单")]},
        config=config,
    )
    assert model.plan_calls == 1
    assert first["__interrupt__"]
    assert first["task_trace"][0]["status"] == "done"
    resumed = await graph.ainvoke(
        Command(resume={"decisions": [{"type": "approve"}]}), config=config
    )
    assert any(
        isinstance(m, ToolMessage) and m.name == "create_support_ticket"
        for m in resumed["messages"]
    )
    assert resumed["messages"][-1].content == "工单已创建"


@pytest.mark.asyncio
@pytest.mark.parametrize("eligible,repair_expected", [(True, False), (False, True)])
async def test_refund_branch_executes_only_needed_tool(
    business_db, monkeypatch, eligible, repair_expected
):
    import customer_support.tools as tools_module

    monkeypatch.setattr(
        tools_module,
        "refund_eligibility",
        lambda order_id, phone_last4: {"ok": True, "eligible": eligible, "reason": "test result"},
    )
    responses = [
        tool_call("get_order_status", order_id="ORD1001", phone_last4="8821"),
        tool_call("check_refund_eligibility", order_id="ORD1001", phone_last4="8821"),
    ]
    if repair_expected:
        responses.append(tool_call("search_policy", query="耳机维修政策"))
    responses.append(AIMessage(content="仅汇总真实工具结果"))
    model = fake(
        {
            "intents": ["refund_check", "repair_query"],
            "entities": {"product_name": "耳机", "issue": "左耳无声"},
            "conditional": True,
        },
        responses,
        {
            "steps": [
                {"id": "o", "action": "get_order_status"},
                {"id": "r", "action": "check_refund_eligibility", "depends_on": ["o"]},
                {
                    "id": "repair",
                    "action": "search_policy",
                    "depends_on": ["r"],
                    "when": "refund_ineligible",
                },
                {"id": "end", "action": "summarize"},
            ]
        },
    )
    graph = build_customer_support_graph(model, enable_router=True)
    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content="耳机左耳无声，订单 ORD1001，手机号后四位 8821，能退就退，不行怎么修？"
                )
            ]
        }
    )
    names = [m.name for m in result["messages"] if isinstance(m, ToolMessage)]
    assert names[:2] == ["get_order_status", "check_refund_eligibility"]
    assert ("search_policy" in names) is repair_expected
    assert model.plan_calls == 1
    assert not any(
        m.name == "create_support_ticket" for m in result["messages"] if isinstance(m, ToolMessage)
    )


def test_basic_routing_planning_metrics():
    from customer_support.routing import planning_correctness, planning_metrics, routing_metrics

    assert routing_metrics(
        [{Intent.GENERAL}, {Intent.ORDER, Intent.REFUND}], [{Intent.GENERAL}, {Intent.ORDER}]
    ) == {"exact_match_accuracy": 0.5}
    assert routing_metrics([], []) == {"exact_match_accuracy": None}
    route = Route(
        intents=[Intent.REFUND], entities=Entities(order_id="ORD1001", phone_last4="8821")
    )
    plan = Plan(steps=[Step(id="r", action="check_refund_eligibility")])
    result = ToolMessage(
        content=json.dumps({"ok": True, "eligible": False}),
        name="check_refund_eligibility",
        tool_call_id="r",
    )
    assert planning_correctness([plan], [plan]) == 1
    assert planning_correctness([plan], [Plan(steps=[Step(id="x", action="search_policy")])]) == 0
    assert planning_metrics([(plan, route, [HumanMessage(content="x"), result])]) == {
        "plan_validity": 1,
        "task_completion": 1,
    }
