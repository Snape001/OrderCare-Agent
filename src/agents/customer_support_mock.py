"""Deterministic offline customer-support agent."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, MessagesState, StateGraph

from customer_support.confirmation import is_explicit_approval
from customer_support.policy import search_policy
from customer_support.store import (
    create_support_ticket,
    get_order_status,
    initialize_database,
    refund_eligibility,
)


class CustomerSupportState(MessagesState, total=False):
    pending_ticket: dict[str, str] | None
    pending_query: dict[str, str] | None


def _message_text(message: Any) -> str:
    content = message.content
    return content if isinstance(content, str) else str(content)


def _order_id(text: str) -> str | None:
    match = re.search(r"(?<![A-Z0-9])(?:ORD\d{4}|OL\d{6})(?![A-Z0-9])", text.upper())
    return match.group(0) if match else None


def _invalid_order_id(text: str) -> bool:
    """Spot an order-like value without treating a phone suffix as an order."""
    return bool(re.search(r"(?<![A-Z0-9])[A-Z]{1,4}\d{3,8}(?![A-Z0-9])", text.upper()))


def _phone_last4(text: str, order_id: str | None) -> str | None:
    explicit = re.search(
        r"(?:手机号后四位|手机后四位|后四位|尾号|手机号)[：:\s是为]*(\d{4})(?!\d)", text
    )
    if explicit:
        return explicit.group(1)
    candidates = re.findall(r"(?<![A-Za-z0-9])\d{4}(?![A-Za-z0-9])", text)
    order_suffix = order_id[-4:] if order_id else None
    return next((candidate for candidate in candidates if candidate != order_suffix), None)


def _ai(content: str) -> AIMessage:
    return AIMessage(content=content)


def _intent(text: str) -> str:
    """Choose one offline business path before considering broad policy terms."""
    compact = re.sub(r"\s+", "", text)
    has_policy_cue = any(word in compact for word in ("政策", "规则", "条件", "要求"))
    if "工单" in compact or "人工客服" in compact:
        if has_policy_cue or ("如何" in compact or "怎么" in compact) and "帮我" not in compact:
            return "policy"
        return "ticket"
    if any(
        word in compact
        for word in (
            "退款资格",
            "能退款",
            "可以退款",
            "能退货",
            "可以退货",
            "符合退款",
            "申请退款",
            "能不能退",
            "能否退",
            "能退吗",
            "可以退吗",
        )
    ):
        if (
            has_policy_cue
            and not _order_id(compact)
            and not any(
                word in compact for word in ("判断", "查询", "查", "我能", "我可以", "是否")
            )
        ):
            return "policy"
        return "refund"
    order_action = (
        (
            "订单" in compact
            and any(
                word in compact
                for word in ("查询", "查", "状态", "物流", "快递", "到哪", "发货", "延迟")
            )
        )
        or bool(
            re.search(r"(?:查询|查|看).{0,6}(?:物流|快递|包裹)", compact)
            or re.search(r"(?:物流|快递|包裹).{0,6}(?:状态|到哪|进度|更新)", compact)
        )
        or any(
            word in compact
            for word in (
                "物流状态",
                "查询物流",
                "查物流",
                "快递到哪",
                "包裹到哪",
                "物流到哪",
                "物流是否延迟",
            )
        )
    )
    if order_action and not has_policy_cue:
        return "order_status"
    if _order_id(compact) and not has_policy_cue:
        return "order_status"
    if (
        any(
            word in compact
            for word in (
                "你能帮",
                "你可以帮",
                "能帮助",
                "你能做",
                "你可以做",
                "哪些售后问题",
                "有什么功能",
            )
        )
        or ("介绍" in compact and ("你" in compact or "客服" in compact))
        or re.fullmatch(r"(?:你好|您好|嗨|哈喽|hello|hi)[！!。.？?，,\s]*", compact, re.IGNORECASE)
    ):
        return "greeting"
    if any(
        word in compact
        for word in (
            "退款",
            "退货",
            "退掉",
            "七天",
            "物流",
            "快递",
            "包裹",
            "运输",
            "保修",
            "维修",
            "售后",
            "进水",
            "发票",
            "开票",
            "补票",
            "报销",
            "配送",
            "机器人",
            "真人",
            "人工审核",
            "换货",
            "支付",
            "优惠券",
            "收货地址",
            "隐私",
            "验证码",
            "投诉",
        )
    ):
        return "policy"
    if any(
        word in compact.lower()
        for word in (
            "天气",
            "股票",
            "编程",
            "写代码",
            "写诗",
            "电影",
            "旅游",
            "数学",
            "新闻",
            "python",
        )
    ):
        return "out_of_scope"
    return "unclear"


def _query_reply(text: str, pending: dict[str, str]) -> CustomerSupportState:
    """Fill order and identity fields in the current checkpointed query."""
    order_id = _order_id(text)
    if not order_id and _invalid_order_id(text):
        updated = pending.copy()
        if phone_last4 := _phone_last4(text, None):
            updated["phone_last4"] = phone_last4
        return {
            "messages": [_ai("订单号格式不正确，请提供 ORD1001 或 OL099422 这样的订单号。")],
            "pending_query": updated,
        }

    old_order_id = pending.get("order_id")
    current_order_id = order_id or old_order_id
    phone_last4 = _phone_last4(text, order_id)
    if not phone_last4 and (not order_id or not old_order_id or order_id == old_order_id):
        phone_last4 = pending.get("phone_last4")
    updated = {"intent": pending["intent"]}
    if current_order_id:
        updated["order_id"] = current_order_id
    if phone_last4:
        updated["phone_last4"] = phone_last4

    if not current_order_id:
        return {"messages": [_ai("请提供订单号，例如 ORD1001。")], "pending_query": updated}
    if not phone_last4:
        return {
            "messages": [_ai("为保护隐私，请提供下单手机号后四位。")],
            "pending_query": updated,
        }

    if updated["intent"] == "refund":
        result = refund_eligibility(current_order_id, phone_last4)
        if not result["ok"]:
            updated.pop("phone_last4", None)
            return {
                "messages": [_ai("未找到订单或验证信息不匹配，请核对订单号和手机号后四位。")],
                "pending_query": updated,
            }
        conclusion = "可以申请" if result["eligible"] else "暂不符合"
        return {
            "messages": [
                _ai(
                    f"订单 {current_order_id} 的退款判断：{conclusion}。\n\n"
                    f"原因：{result['reason']}\n\n"
                    "政策来源：`data/policies/customer_service_policy.md`"
                )
            ],
            "pending_query": None,
        }

    result = get_order_status(current_order_id, phone_last4)
    if not result["ok"]:
        updated.pop("phone_last4", None)
        return {
            "messages": [_ai("未找到订单或验证信息不匹配，请核对订单号和手机号后四位。")],
            "pending_query": updated,
        }
    return {
        "messages": [
            _ai(
                f"订单 {current_order_id}：{result['product_name']}，当前状态为“{result['status']}”。"
            )
        ],
        "pending_query": None,
    }


async def customer_support_node(state: CustomerSupportState) -> CustomerSupportState:
    """Route a small set of testable customer-support intents without an API."""
    initialize_database()
    text = _message_text(state["messages"][-1]).strip()
    pending = state.get("pending_ticket")

    if pending:
        if any(word in text for word in ("取消", "不要", "否")):
            return {
                "messages": [_ai("已取消，本次不会创建客服工单。")],
                "pending_ticket": None,
            }
        if is_explicit_approval(text):
            result = create_support_ticket(
                order_id=pending["order_id"],
                category=pending["category"],
                summary=pending["summary"],
                idempotency_key=pending["idempotency_key"],
            )
            if not result["ok"]:
                return {"messages": [_ai(result["error"])], "pending_ticket": None}
            return {
                "messages": [
                    _ai(
                        f"工单已创建：{result['ticket_id']}，状态为{result['status']}。"
                        "客服人员会继续处理。"
                    )
                ],
                "pending_ticket": None,
            }
        return {
            "messages": [_ai("请回复“确认”创建工单，或回复“取消”。")],
            "pending_ticket": pending,
        }

    pending_query = state.get("pending_query")
    if pending_query:
        if re.fullmatch(r"(?:取消|取消查询|先不查了|不查了|算了|停止查询)[！!。.\s]*", text):
            return {"messages": [_ai("已取消当前查询。")], "pending_query": None}
        return _query_reply(text, pending_query)

    order_id = _order_id(text)
    phone_last4 = _phone_last4(text, order_id)
    intent = _intent(text)

    if intent == "ticket":
        if not order_id:
            return {"messages": [_ai("请提供订单号，例如 ORD1001。")]}
        if not phone_last4:
            return {"messages": [_ai("为保护隐私，请提供下单手机号后四位。")]}
        order = get_order_status(order_id, phone_last4)
        if not order["ok"]:
            return {"messages": [_ai(order["error"])]}
        pending_ticket = {
            "order_id": order_id,
            "category": "售后咨询",
            "summary": f"用户为订单 {order_id} 申请人工客服处理。",
            "idempotency_key": f"{order_id}-after-sales",
        }
        return {
            "messages": [
                _ai(f"即将为订单 {order_id} 创建售后工单。这是写入操作，请回复“确认”或“取消”。")
            ],
            "pending_ticket": pending_ticket,
        }

    if intent in ("order_status", "refund"):
        return _query_reply(text, {"intent": intent})

    if intent == "policy":
        policy = search_policy(text)
        reference = f"{policy['source']} > {policy['title']}"
        return {
            "messages": [
                _ai(
                    f"### {policy['title']}\n\n{policy['content']}\n\n"
                    f"来源：`{reference}`\n\n"
                    f"检索分数：`{policy['score']:.4f}`"
                )
            ]
        }

    if intent == "out_of_scope":
        return {
            "messages": [
                _ai(
                    "我目前只处理商城订单、物流、退款、售后工单及相关政策问题。请告诉我你的商城售后需求。"
                )
            ]
        }

    if intent == "unclear":
        return {
            "messages": [
                _ai("请问你想查询订单或物流、判断退款资格、了解售后政策，还是创建客服工单？")
            ]
        }

    return {
        "messages": [
            _ai(
                "你好，我可以帮助你：\n"
                "- 查询退款、物流、保修和发票政策；\n"
                "- 查询订单状态；\n"
                "- 判断退款资格；\n"
                "- 确认后创建客服工单。\n\n"
                "测试示例：`查询订单 ORD1001，手机号后四位 8821`"
            )
        ]
    }


builder = StateGraph(CustomerSupportState)
builder.add_node("customer_support", customer_support_node)
builder.set_entry_point("customer_support")
builder.add_edge("customer_support", END)
customer_support_mock = builder.compile()
customer_support_mock.name = "CustomerSupportMock"
