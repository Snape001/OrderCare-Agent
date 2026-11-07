"""Small structured router/planner for the existing customer-support agent loop."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any, Literal

from langchain.agents.middleware import AgentState
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel, ConfigDict, Field


class Intent(StrEnum):
    GENERAL = "general"
    POLICY = "policy_query"
    ORDER = "order_query"
    REFUND = "refund_check"
    REPAIR = "repair_query"
    TICKET = "ticket_create"


class Entities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str | None = None
    phone_last4: str | None = None
    product_name: str | None = None
    issue: str | None = None


class Route(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intents: list[Intent] = Field(min_length=1, max_length=6)
    entities: Entities = Field(default_factory=Entities)
    conditional: bool = False


Action = Literal[
    "get_order_status",
    "check_refund_eligibility",
    "search_policy",
    "create_support_ticket",
    "summarize",
]
Condition = Literal["always", "refund_eligible", "refund_ineligible"]


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=20)
    action: Action
    depends_on: list[str] = Field(default_factory=list, max_length=3)
    when: Condition = "always"


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[Step] = Field(min_length=1, max_length=6)


class RoutedState(AgentState):
    route: dict[str, Any]
    plan: dict[str, Any]
    task_trace: list[dict[str, Any]]


ROUTER_PROMPT = (
    "识别客服用户本轮意图，输出符合JSON schema的短结果。可有多个意图。"
    "policy_query是政策，repair_query是维修政策，order_query查具体订单，refund_check查具体退款资格，"
    "ticket_create仅当用户明确要求创建工单或人工办理时使用。"
    "‘如果物流延迟怎么办’是假设性政策咨询，只标policy_query，conditional=false；"
    "不得因此查询订单、判断退款或创建工单。"
    "‘检查这个订单是否延迟’才标order_query，缺少订单号/手机号后四位应追问。"
    "is_delivery_late是订单查询的返回字段，不是独立工具。"
    "抽取明确给出的订单号、手机号后四位、商品名和问题描述；没有则null。"
    "只有多个业务动作存在‘能退/不能退则维修’等执行依赖时conditional=true。不要编造实体。"
)
PLANNER_PROMPT = (
    "将Router确认的多个意图排成最多6个顺序任务。输入列有allowed_actions；"
    "只能规划其中的业务动作，summarize可选。假设性政策条件不是执行条件，"
    "不得据此添加订单查询、退款或工单。"
    "depends_on引用此前id；when只能是always/refund_eligible/refund_ineligible。"
    "只有用户明确请求工单才规划create_support_ticket；不得规划实际退款执行（系统无退款写工具）。"
    "条件维修只在refund_ineligible时search_policy；能退款时只说明资格及待确认流程。"
    "不要增加不必要的任务；最后可summarize。输出简短JSON。"
)


def latest_user(state: dict[str, Any]) -> HumanMessage | None:
    return next(
        (m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)), None
    )


def validated_route(route: Route, messages: list[Any]) -> Route:
    """Keep model labels, but anchor sensitive identifiers in actual user text."""
    text = "\n".join(str(m.content) for m in messages if isinstance(m, HumanMessage))
    ids = re.findall(r"\b(?:ORD|OL)\d{4,6}\b", text, flags=re.I)
    digits = re.findall(r"(?:后四位|尾号|手机号)[^\d]{0,8}(\d{4})", text)
    route.entities.order_id = ids[-1].upper() if ids else None
    route.entities.phone_last4 = digits[-1] if digits else None
    for field in ("product_name", "issue"):
        value = getattr(route.entities, field)
        if value and re.sub(r"\s+", "", value) not in re.sub(r"\s+", "", text):
            setattr(route.entities, field, None)
    current = str(next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""))
    delay = "物流" in current and any(word in current for word in ("延迟", "晚到", "迟到"))
    hypothetical = any(word in current for word in ("如果", "假如", "万一", "要是"))
    advice = any(word in current for word in ("怎么办", "怎么处理", "如何处理", "有什么办法"))
    actual_check = any(
        word in current for word in ("检查", "查询", "查一下", "查查", "是否延迟", "有没有延迟")
    )
    explicit_action = any(
        word in current
        for word in (
            "退款资格", "帮我退款", "申请退款", "创建工单", "新建工单",
            "提交工单", "创建售后", "转人工",
        )
    )
    if delay and hypothetical and advice and not actual_check and not explicit_action:
        route.intents = [Intent.POLICY]
        route.conditional = False
    elif delay and actual_check:
        if not advice and not explicit_action:
            route.intents = [Intent.ORDER]
            route.conditional = False
        elif Intent.ORDER not in route.intents:
            route.intents.append(Intent.ORDER)
    if Intent.TICKET in route.intents and not re.search(
        r"(?:创建|新建|提交|开|建).{0,8}工单|创建售后|(?:转|找)人工|人工处理|客服处理|帮我办理",
        current,
    ):
        route.intents.remove(Intent.TICKET)
    if not route.intents:
        route.intents = [Intent.GENERAL]
    route.intents = list(dict.fromkeys(route.intents))
    if len(route.intents) > 1 and Intent.GENERAL in route.intents:
        route.intents.remove(Intent.GENERAL)
    return route


def missing_fields(route: Route) -> list[str]:
    if any(i in route.intents for i in (Intent.ORDER, Intent.REFUND, Intent.TICKET)):
        missing = []
        if not route.entities.order_id:
            missing.append("订单号")
        if not route.entities.phone_last4:
            missing.append("手机号后四位")
        return missing
    return []


def allowed_actions(route: Route) -> set[str]:
    """Return only business actions authorized by the validated route."""
    allowed = {
        Intent.ORDER: "get_order_status",
        Intent.REFUND: "check_refund_eligibility",
        Intent.POLICY: "search_policy",
        Intent.REPAIR: "search_policy",
        Intent.TICKET: "create_support_ticket",
    }
    return {allowed[i] for i in route.intents if i in allowed}


def validate_plan(plan: Plan, route: Route) -> Plan:
    seen: set[str] = set()
    actions = allowed_actions(route)
    if not actions.issubset({s.action for s in plan.steps}):
        raise ValueError("Plan omits a requested intent")
    for step in plan.steps:
        if step.id in seen or any(d not in seen for d in step.depends_on):
            raise ValueError("Plan has duplicate/forward dependencies")
        if step.action not in actions and step.action != "summarize":
            raise ValueError("Plan adds an unrequested business action")
        if step.when != "always" and (
            "check_refund_eligibility" not in [s.action for s in plan.steps if s.id in seen]
            or Intent.REFUND not in route.intents
        ):
            raise ValueError("Conditional step requires prior refund check")
        seen.add(step.id)
    if Intent.ORDER in route.intents and Intent.REFUND in route.intents:
        actions_in_order = [s.action for s in plan.steps]
        if actions_in_order.index("get_order_status") > actions_in_order.index(
            "check_refund_eligibility"
        ):
            raise ValueError("Order lookup must precede refund check")
    if route.conditional and Intent.REPAIR in route.intents and Intent.REFUND in route.intents:
        if Intent.POLICY not in route.intents and any(
            s.action == "search_policy" and s.when != "refund_ineligible" for s in plan.steps
        ):
            raise ValueError("Repair policy must only run after refund ineligibility")
        if not any(
            s.action == "search_policy" and s.when == "refund_ineligible" for s in plan.steps
        ):
            raise ValueError("Conditional repair must wait for failed refund check")
    return plan


def simple_plan(route: Route) -> Plan:
    action = {
        Intent.GENERAL: "summarize",
        Intent.POLICY: "search_policy",
        Intent.ORDER: "get_order_status",
        Intent.REFUND: "check_refund_eligibility",
        Intent.REPAIR: "search_policy",
        Intent.TICKET: "create_support_ticket",
    }[route.intents[0]]
    return Plan(steps=[Step(id="s1", action=action)])


def tool_result(messages: list[Any], name: str) -> dict[str, Any] | None:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, ToolMessage) and message.name == name:
            try:
                value = json.loads(str(message.content))
            except ValueError:
                return {"ok": False, "error": "Invalid tool result"}
            return (
                value if isinstance(value, dict) else {"ok": False, "error": "Invalid tool result"}
            )
    return None


def next_task(plan: Plan, messages: list[Any]) -> tuple[Step | None, list[dict[str, Any]]]:
    """Compute task status from checkpointed tool messages; never infer success from prose."""
    refund = tool_result(messages, "check_refund_eligibility")
    trace: list[dict[str, Any]] = []
    for step in plan.steps:
        if step.action == "summarize":
            trace.append({"id": step.id, "action": step.action, "status": "ready"})
            continue
        if step.when != "always":
            if refund is None:
                return None, trace
            if refund.get("ok") is not True or not isinstance(refund.get("eligible"), bool):
                trace.append({"id": step.id, "action": step.action, "status": "blocked"})
                continue
            if (step.when == "refund_eligible") != refund["eligible"]:
                trace.append({"id": step.id, "action": step.action, "status": "skipped"})
                continue
        result = tool_result(messages, step.action)
        if result is None:
            trace.append({"id": step.id, "action": step.action, "status": "pending"})
            return step, trace
        status = "done" if result.get("ok", True) is True else "failed"
        trace.append({"id": step.id, "action": step.action, "status": status})
        if status == "failed":
            return None, trace
    return None, trace


def task_guidance(route: Route, plan: Plan, trace: list[dict[str, Any]]) -> str:
    return (
        "本轮意图与任务："
        + json.dumps(
            {
                "route": route.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
                "trace": trace,
            },
            ensure_ascii=False,
        )
        + "。只依据实际工具结果答复。退款资格通过不等于退款已执行，本系统没有执行退款工具。"
        "创建工单必须调用原有工具并等待人工确认，不得声称已创建。"
    )


def routing_metrics(
    expected: list[set[Intent]], predicted: list[set[Intent]]
) -> dict[str, float | None]:
    if len(expected) != len(predicted):
        raise ValueError("Route labels and predictions differ in length")
    return {
        "exact_match_accuracy": sum(a == b for a, b in zip(expected, predicted, strict=True))
        / len(expected)
        if expected
        else None
    }


def planning_metrics(cases: list[tuple[Plan, Route, list[Any]]]) -> dict[str, float | None]:
    if not cases:
        return {"plan_validity": None, "task_completion": None}
    valid = 0
    completed = 0
    relevant = 0
    for plan, route, messages in cases:
        try:
            validate_plan(plan, route)
        except ValueError:
            continue
        valid += 1
        _, trace = next_task(plan, messages)
        by_id = {t["id"]: t["status"] for t in trace}
        refund = tool_result(messages, "check_refund_eligibility")
        for step in plan.steps:
            if step.action == "summarize":
                continue
            if step.when != "always" and refund and refund.get("ok") is True:
                if (
                    isinstance(refund.get("eligible"), bool)
                    and (step.when == "refund_eligible") != refund["eligible"]
                ):
                    continue
            relevant += 1
            completed += by_id.get(step.id) == "done"
    return {
        "plan_validity": valid / len(cases),
        "task_completion": completed / relevant if relevant else None,
    }


def planning_correctness(expected: list[Plan], predicted: list[Plan]) -> float | None:
    if len(expected) != len(predicted):
        raise ValueError("Plan labels and predictions differ in length")
    if not expected:
        return None

    def signature(plan: Plan) -> list[tuple[str, str, tuple[int, ...]]]:
        positions = {step.id: index for index, step in enumerate(plan.steps)}
        return [
            (step.action, step.when, tuple(positions.get(dep, -1) for dep in step.depends_on))
            for step in plan.steps
        ]

    return sum(
        signature(a) == signature(b) for a, b in zip(expected, predicted, strict=True)
    ) / len(expected)
