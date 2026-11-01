"""Local STDIO MCP facade over the existing customer-support business tools."""

from __future__ import annotations

import hmac
import importlib
import logging
import os
import sys
from typing import Annotated, Any

from langchain_core.tools import BaseTool
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from customer_support.mcp_approval import ticket_token
from customer_support.tools import CUSTOMER_SUPPORT_TOOLS

logger = logging.getLogger(__name__)
mcp = FastMCP("ordercare-business-tools")
_business_tools: dict[str, BaseTool] = {tool.name: tool for tool in CUSTOMER_SUPPORT_TOOLS}


def _execute(name: str, arguments: dict[str, str]) -> dict[str, Any]:
    """Keep the production tool result fields while adding a common success flag."""
    logger.info("MCP business tool started name=%s", name)
    try:
        result = _business_tools[name].invoke(arguments)
    except Exception as exc:
        logger.exception("MCP business tool failed name=%s error_type=%s", name, type(exc).__name__)
        return {"ok": False, "error": "工具执行失败，请稍后重试。", "error_code": "MCP_TOOL_ERROR"}
    if not isinstance(result, dict):
        return {"ok": False, "error": "工具返回格式错误。", "error_code": "INVALID_TOOL_RESULT"}
    logger.info("MCP business tool completed name=%s", name)
    return {"ok": result.get("ok", True), **result}


@mcp.tool(name="get_order_status", description="验证订单号和手机号后四位后，查询订单及物流状态。")
def get_order_status(
    order_id: Annotated[str, Field(min_length=1, description="订单号，例如 ORD1001 或 OL099422")],
    phone_last4: Annotated[str, Field(pattern=r"^\d{4}$", description="订单绑定手机号后四位")],
) -> dict[str, Any]:
    return _execute("get_order_status", {"order_id": order_id, "phone_last4": phone_last4})


@mcp.tool(
    name="check_refund_eligibility",
    description="验证订单身份并判断是否符合退款资格；不会执行退款。",
)
def check_refund_eligibility(
    order_id: Annotated[str, Field(min_length=1, description="要检查的订单号")],
    phone_last4: Annotated[str, Field(pattern=r"^\d{4}$", description="订单绑定手机号后四位")],
) -> dict[str, Any]:
    return _execute("check_refund_eligibility", {"order_id": order_id, "phone_last4": phone_last4})


@mcp.tool(name="search_policy", description="检索售后政策知识库并返回政策原文、来源和引用。")
def search_policy(
    query: Annotated[str, Field(min_length=1, description="用户要查询的政策问题")],
) -> dict[str, Any]:
    return _execute("search_policy", {"query": query})


@mcp.tool(
    name="create_support_ticket",
    description="核验订单身份后创建售后工单；Agent 端需先取得人工确认。",
)
def create_support_ticket(
    order_id: Annotated[str, Field(min_length=1, description="售后订单号")],
    phone_last4: Annotated[str, Field(pattern=r"^\d{4}$", description="订单绑定手机号后四位")],
    category: Annotated[str, Field(min_length=1, description="工单类别，例如物流或质量")],
    summary: Annotated[str, Field(min_length=1, description="用户问题的简短描述")],
    approval_token: Annotated[str, Field(description="仅供 Agent 内部确认链使用的签名")] = "",
) -> dict[str, Any]:
    arguments = {
        "order_id": order_id,
        "phone_last4": phone_last4,
        "category": category,
        "summary": summary,
    }
    secret = os.getenv("ORDERCARE_MCP_APPROVAL_SECRET")
    if not secret or not hmac.compare_digest(approval_token, ticket_token(secret, arguments)):
        return {"ok": False, "error": "创建工单需要人工确认。", "error_code": "APPROVAL_REQUIRED"}
    return _execute("create_support_ticket", arguments)


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    # Native embedding imports can stall when first loaded inside an MCP request thread.
    importlib.import_module("customer_support.rag")

    mcp.run(transport="stdio")
