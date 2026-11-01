"""Discover local MCP tools and retain the production LangGraph tool-result shape."""

from __future__ import annotations

import json
import os
import secrets
import sys
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection, StdioConnection

from customer_support.mcp_approval import ticket_token
from customer_support.trace import trace_event

TOOL_NAMES = frozenset(
    {"get_order_status", "check_refund_eligibility", "search_policy", "create_support_ticket"}
)
_discovered_tool_names: tuple[str, ...] = ()


def discovered_tool_names() -> tuple[str, ...]:
    """Return names validated during this process's MCP startup discovery."""
    return _discovered_tool_names


def stdio_connection(approval_secret: str) -> StdioConnection:
    """Pass the current database configuration to the local child process."""
    environment = dict(os.environ)
    environment["ORDERCARE_MCP_APPROVAL_SECRET"] = approval_secret
    source_root = str(Path(__file__).resolve().parents[1])
    inherited_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_root + os.pathsep + inherited_path if inherited_path else source_root
    )
    return {
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-m", "customer_support.mcp_server"],
        "env": environment,
    }


def normalize_result(value: Any) -> dict[str, Any]:
    """Convert MCP text blocks into the JSON object expected by the existing Planner."""
    if isinstance(value, ToolMessage):
        value = value.content
    if isinstance(value, tuple) and len(value) == 2:
        value = value[0]
    if isinstance(value, list):
        text = [
            item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
            for item in value
            if (item.get("type") if isinstance(item, dict) else getattr(item, "type", None))
            == "text"
        ]
        if len(text) != 1:
            raise ValueError("MCP tool returned an unexpected number of text blocks")
        value = text[0]
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict) and set(value) == {"result"} and isinstance(value["result"], dict):
        value = value["result"]
    if not isinstance(value, dict) or not isinstance(value.get("ok"), bool):
        raise ValueError("MCP tool returned an invalid business result")
    return value


def _tool_wrapper(mcp_tool: BaseTool, approval_secret: str) -> StructuredTool:
    schema = deepcopy(mcp_tool.args_schema)
    if not isinstance(schema, dict):
        raise ValueError("MCP tool schema must be a JSON object")
    if mcp_tool.name == "create_support_ticket":
        schema["properties"].pop("approval_token", None)
        schema["required"] = [name for name in schema["required"] if name != "approval_token"]

    async def invoke(**arguments: Any) -> dict[str, Any]:
        started = perf_counter()
        if mcp_tool.name == "create_support_ticket":
            signed = ticket_token(approval_secret, arguments)
            arguments = {**arguments, "approval_token": signed}
        try:
            result = normalize_result(await mcp_tool.ainvoke(arguments))
        except Exception as exc:
            trace_event("mcp", server="ordercare-business-tools", tool=mcp_tool.name,
                        status="failed", error_type=type(exc).__name__,
                        duration_ms=round((perf_counter() - started) * 1000, 1))
            raise
        trace_event("mcp", server="ordercare-business-tools", tool=mcp_tool.name,
                    status="completed", duration_ms=round((perf_counter() - started) * 1000, 1))
        return result

    return StructuredTool(
        name=mcp_tool.name,
        description=mcp_tool.description,
        args_schema=schema,
        coroutine=invoke,
    )


async def load_business_mcp_tools() -> list[BaseTool]:
    """Fail startup if the STDIO server does not expose exactly four expected tools."""
    global _discovered_tool_names
    _discovered_tool_names = ()
    approval_secret = secrets.token_hex(32)
    connections: dict[str, Connection] = {"ordercare": stdio_connection(approval_secret)}
    client = MultiServerMCPClient(connections)
    discovered = await client.get_tools()
    names = [tool.name for tool in discovered]
    if len(names) != len(TOOL_NAMES) or set(names) != TOOL_NAMES:
        raise RuntimeError("Customer-support MCP server returned an unexpected tool set")
    _discovered_tool_names = tuple(sorted(names))
    return [_tool_wrapper(tool, approval_secret) for tool in discovered]
