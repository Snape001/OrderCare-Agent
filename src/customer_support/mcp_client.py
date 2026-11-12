"""Discover local MCP tools and retain the production LangGraph tool-result shape."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection, StdioConnection

from core.settings import settings
from customer_support.mcp_approval import ticket_token
from customer_support.trace import trace_event

TOOL_NAMES = frozenset(
    {"get_order_status", "check_refund_eligibility", "search_policy", "create_support_ticket"}
)
_discovered_tool_names: tuple[str, ...] = ()


class _ReadCache:
    """Bounded process-local TTL cache; stores only successful read results."""

    def __init__(self) -> None:
        self._values: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._values.get(key)
            if item is None:
                return None
            expires, value = item
            if expires <= time.monotonic():
                del self._values[key]
                return None
            self._values.move_to_end(key)
            return deepcopy(value)

    def put(self, key: str, value: dict[str, Any], ttl: int) -> None:
        with self._lock:
            self._values[key] = (time.monotonic() + ttl, deepcopy(value))
            self._values.move_to_end(key)
            while len(self._values) > settings.MCP_READ_CACHE_MAX_ENTRIES:
                self._values.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


class _Circuit:
    def __init__(self) -> None:
        self.failures = 0
        self.open_until = 0.0
        self.probe_running = False
        self.lock = threading.RLock()

    def enter(self) -> bool:
        with self.lock:
            now = time.monotonic()
            if self.open_until > now:
                return False
            if self.open_until:
                if self.probe_running:
                    return False
                self.probe_running = True
            return True

    def success(self) -> None:
        with self.lock:
            self.failures = 0
            self.open_until = 0.0
            self.probe_running = False

    def failure(self) -> None:
        with self.lock:
            self.probe_running = False
            self.failures += 1
            if self.failures >= settings.MCP_CIRCUIT_FAILURE_THRESHOLD:
                self.open_until = time.monotonic() + settings.MCP_CIRCUIT_RESET_SECONDS


_read_cache = _ReadCache()
_circuits = {name: _Circuit() for name in TOOL_NAMES}


def _cache_key(name: str, arguments: dict[str, Any]) -> str:
    return json.dumps([name, arguments], ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _unavailable(name: str, code: str, *, uncertain_write: bool = False) -> dict[str, Any]:
    if name == "create_support_ticket" and uncertain_write:
        message = "工单执行结果尚未确认，请先核查工单状态后再决定是否重试。"
        code = "TICKET_STATUS_UNKNOWN"
    else:
        message = "业务工具暂时不可用，请稍后重试或联系人工客服。"
    return {"ok": False, "error": message, "error_code": code}


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
        name = mcp_tool.name
        is_ticket = name == "create_support_ticket"
        # Policy result caching is shared at the search_policy entry point; keep only
        # the MCP transport circuit here. Order/refund results remain MCP-cached.
        cache_key = _cache_key(name, arguments) if name in {
            "get_order_status", "check_refund_eligibility"
        } else None
        if cache_key is not None:
            cached = _read_cache.get(cache_key)
            if cached is not None:
                trace_event("mcp", server="ordercare-business-tools", tool=name,
                            status="cache_hit", duration_ms=0)
                return cached
        circuit = _circuits[name]
        if not circuit.enter():
            trace_event("mcp", server="ordercare-business-tools", tool=name,
                        status="degraded", reason="circuit_open", duration_ms=0)
            return _unavailable(name, "CIRCUIT_OPEN")
        if mcp_tool.name == "create_support_ticket":
            signed = ticket_token(approval_secret, arguments)
            arguments = {**arguments, "approval_token": signed}
        try:
            timeout = (settings.MCP_TICKET_TIMEOUT_SECONDS if is_ticket
                       else settings.MCP_TOOL_TIMEOUT_SECONDS)
            result = normalize_result(await asyncio.wait_for(
                mcp_tool.ainvoke(arguments), timeout=timeout
            ))
        except Exception as exc:
            circuit.failure()
            code = "MCP_TOOL_TIMEOUT" if isinstance(exc, TimeoutError) else "MCP_TOOL_UNAVAILABLE"
            trace_event("mcp", server="ordercare-business-tools", tool=name,
                        status="degraded", reason=code, error_type=type(exc).__name__,
                        duration_ms=round((perf_counter() - started) * 1000, 1))
            return _unavailable(name, code, uncertain_write=is_ticket)
        infrastructure_error = result.get("error_code") in {
            "MCP_TOOL_ERROR", "INVALID_TOOL_RESULT"
        }
        if infrastructure_error:
            circuit.failure()
            trace_event("mcp", server="ordercare-business-tools", tool=name,
                        status="degraded", reason=result["error_code"],
                        duration_ms=round((perf_counter() - started) * 1000, 1))
            if is_ticket:
                return _unavailable(name, result["error_code"], uncertain_write=True)
            return _unavailable(name, result["error_code"])
        circuit.success()
        if cache_key is not None and result.get("ok") is True:
            _read_cache.put(cache_key, result, settings.MCP_BUSINESS_CACHE_TTL_SECONDS)
        trace_event("mcp", server="ordercare-business-tools", tool=name,
                    status="completed", cache="stored" if cache_key and result.get("ok") else "miss",
                    duration_ms=round((perf_counter() - started) * 1000, 1))
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
