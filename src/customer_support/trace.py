"""Request-scoped, allowlisted customer-support execution observations."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass
class TraceCollector:
    events: list[dict[str, Any]] = field(default_factory=list)
    question: str = ""
    answer: str = ""


_active: ContextVar[TraceCollector | None] = ContextVar("customer_trace", default=None)
_secret = re.compile(r"(?i)(?:sk-[a-z0-9_-]{8,}|bearer\s+[a-z0-9._-]+)")
_phone = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_last_four = re.compile(r"(手机号后四位|手机后四位|尾号)\s*[:：]?\s*(\d{4})")


def safe_text(value: Any, limit: int = 160) -> str:
    text = str(value)
    text = _secret.sub("[已脱敏密钥]", text)
    text = _phone.sub("[已脱敏手机号]", text)
    text = _last_four.sub(lambda match: match.group(1) + " **" + match.group(2)[-2:], text)
    return text[:limit]


def safe_args(arguments: dict[str, Any]) -> dict[str, Any]:
    """Never persist arbitrary model arguments or credentials."""
    result: dict[str, Any] = {}
    for key in ("order_id", "phone_last4", "query", "category", "summary"):
        if key not in arguments or arguments[key] is None:
            continue
        value = arguments[key]
        result[key] = (
            "**" + str(value)[-2:] if key == "phone_last4"
            else "[问题描述已隐藏]" if key == "summary"
            else safe_text(value)
        )
    return result


def safe_route(route: dict[str, Any] | BaseModel) -> dict[str, Any]:
    if isinstance(route, BaseModel):
        route = route.model_dump(mode="json")
    entities = route.get("entities", {})
    return {
        "intents": list(route.get("intents", []))[:6],
        "conditional": bool(route.get("conditional", False)),
        "entities": safe_args(entities) | {
            key: safe_text(entities[key]) if key == "product_name" else "[问题描述已隐藏]"
            for key in ("product_name", "issue")
            if key in entities and entities[key] is not None
        },
    }


def safe_plan(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not isinstance(value.get("steps"), list):
        return None
    return {"steps": [
        {key: step[key] for key in ("id", "action", "depends_on", "when") if key in step}
        for step in value["steps"][:6] if isinstance(step, dict)
    ]}


def safe_task_trace(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {key: step[key] for key in ("id", "action", "status") if key in step}
        for step in value[:6] if isinstance(step, dict)
    ]


def safe_tool_result(name: str, response: Any) -> dict[str, Any]:
    content = getattr(response, "content", response)
    try:
        value = json.loads(content) if isinstance(content, str) else content
    except (TypeError, ValueError):
        return {"status": "unparsed"}
    if not isinstance(value, dict):
        return {"status": "unparsed"}
    result = {key: value[key] for key in ("ok", "eligible", "duplicate", "error_code") if key in value}
    if name == "search_policy":
        refs = value.get("references", [])
        result["query_results"] = [
            {
                key: hit[key]
                for key in ("source", "title", "chunk_id", "score", "dense_relevance", "lexical_score")
                if key in hit
            }
            for hit in refs[:10]
            if isinstance(hit, dict)
        ]
    elif name == "get_order_status":
        result.update({key: safe_text(value[key]) for key in ("status",) if key in value})
    elif name == "create_support_ticket":
        result.update({key: safe_text(value[key]) for key in ("ticket_id", "status") if key in value})
    return result


@contextmanager
def trace_scope(collector: TraceCollector) -> Iterator[None]:
    token = _active.set(collector)
    try:
        yield
    finally:
        _active.reset(token)


def trace_event(kind: str, **payload: Any) -> None:
    collector = _active.get()
    if collector is not None:
        collector.events.append({"kind": kind, **payload})
