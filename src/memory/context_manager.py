"""Build a bounded model view without changing checkpointed graph state."""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenBudget:
    total: int = 4096
    system: int = 1024
    history: int = 1200
    memory: int = 640
    rag: int = 768
    tools: int = 720

    def __post_init__(self) -> None:
        if min(self.total, self.system, self.history, self.memory, self.rag, self.tools) < 1:
            raise ValueError("Context token budgets must be positive")


def count_tokens(messages: list[AnyMessage], model: Any = None) -> int:
    """Use model counting when possible; a conservative character estimate otherwise."""
    counter = getattr(model, "get_num_tokens_from_messages", None)
    if callable(counter):
        try:
            return int(counter(messages))
        except (ImportError, NotImplementedError, ValueError, TypeError):
            pass
    return sum(math.ceil(len(str(message.content)) * 1.25) + 12 for message in messages)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)


def query_terms(query: str) -> set[str]:
    """Use overlapping Chinese bigrams so word boundaries cannot hide a match."""
    terms = set(re.findall(r"[a-zA-Z]{3,}", query.lower()))
    for segment in re.findall(r"[\u4e00-\u9fff]+", query):
        terms.update(segment[index:index + 2] for index in range(len(segment) - 1))
    return terms


def _groups(messages: list[AnyMessage]) -> list[list[AnyMessage]]:
    """Keep an AI tool call and all corresponding results as one indivisible group."""
    groups: list[list[AnyMessage]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if isinstance(message, ToolMessage):
            index += 1  # Never send an orphan result to the model.
            continue
        if isinstance(message, AIMessage) and message.tool_calls:
            ids = {call["id"] for call in message.tool_calls if call.get("id")}
            group: list[AnyMessage] = [message]
            index += 1
            while index < len(messages) and isinstance(messages[index], ToolMessage):
                candidate = messages[index]
                if isinstance(candidate, ToolMessage) and candidate.tool_call_id in ids:
                    group.append(candidate)
                index += 1
            # An incomplete call may be the current pending action; preserve it only at the tail.
            if len(group) == len(ids) + 1 or index == len(messages):
                groups.append(group)
            continue
        groups.append([message])
        index += 1
    return groups


class ContextManager:
    def __init__(self, budget: TokenBudget) -> None:
        self.budget = budget

    def assemble(
        self,
        *,
        messages: list[AnyMessage],
        system: SystemMessage | None,
        state: dict[str, Any],
        memory: dict[str, Any] | None,
        model: Any = None,
    ) -> tuple[list[AnyMessage], SystemMessage | None]:
        current = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        if current is None:
            return messages, system
        query = _text(current.content)
        route = state.get("route") or {}
        intents = set(route.get("intents") or [])
        system_text = _text(system.content) if system else ""
        # The production rules are never truncated. Report an overrun if they exceed the allocation.
        extras: list[str] = []
        snapshot = memory or {}
        working = dict(snapshot.get("working") or {})
        if intents:
            working["intents"] = sorted(intents)
            working["task_progress"] = state.get("task_trace") or []
            current_order = (route.get("entities") or {}).get("order_id")
            if current_order:
                working["current_order"] = current_order
            elif not re.search(r"这个订单|该订单|之前的订单", query):
                working.pop("current_order", None)
        if working:
            safe_working = {
                key: working[key]
                for key in ("intents", "current_order", "task_progress", "verified")
                if key in working
            }
            if safe_working:
                extras.append(
                    "当前任务状态（仅用于续接，不作为订单事实）："
                    + json.dumps(safe_working, ensure_ascii=False)
                )
        compacted = snapshot.get("compaction") or {}
        if isinstance(compacted, dict):
            facts = {key: value for key, value in compacted.items() if isinstance(value, list) and value}
            if facts:
                extras.append("已压缩历史（动态业务事实须重新核验）：" + json.dumps(facts, ensure_ascii=False))
        summary = str(snapshot.get("summary") or "")[:200]
        if summary:
            extras.append("近期会话摘要：" + summary)
        terms = query_terms(query)
        notes = snapshot.get("notes") or []
        ranked = sorted(
            (note for note in notes if isinstance(note, dict) and note.get("value")),
            key=lambda note: (
                note.get("kind") == "preference",
                sum(term in str(note["value"]).lower() for term in terms),
                str(note.get("updated_at", "")),
            ),
            reverse=True,
        )
        for note in ranked:
            if (
                note.get("kind") != "preference"
                and terms
                and not any(term in str(note["value"]).lower() for term in terms)
            ):
                continue
            extras.append("历史偏好/售后摘要（需重新核验动态事实）：" + str(note["value"])[:160])
        memory_limit = max(
            0,
            min(
                self.budget.memory,
                self.budget.total
                - count_tokens([SystemMessage(content=system_text)], model)
                - count_tokens([current], model),
            ),
        )
        memory_text = ""
        for extra in extras:
            proposed = memory_text + ("\n" if memory_text else "") + extra
            if count_tokens([SystemMessage(content=proposed)], model) > memory_limit:
                continue
            memory_text = proposed
        assembled_system = (
            SystemMessage(content=system_text + ("\n" + memory_text if memory_text else ""))
            if system_text or memory_text
            else None
        )

        selected: set[int] = set()
        spent = count_tokens([assembled_system], model) if assembled_system else 0
        # Always retain the current request, even when the configured budget is too small.
        spent += count_tokens([current], model)
        history_spent = count_tokens([current], model)
        rag_spent = tool_spent = 0
        groups = _groups([m for m in messages if not isinstance(m, SystemMessage)])
        current_position = next(
            i for i, group in enumerate(groups) if any(m is current for m in group)
        )
        for position in range(len(groups) - 1, -1, -1):
            group = groups[position]
            if len(group) == 1 and group[0] is current:
                selected.add(id(group))
                continue
            names = {m.name for m in group if isinstance(m, ToolMessage)}
            category = "rag" if "search_policy" in names else "tools" if names else "history"
            if category in {"rag", "tools"} and position < current_position:
                continue
            cost = count_tokens(group, model)
            used = {"rag": rag_spent, "tools": tool_spent, "history": history_spent}[category]
            cap = {
                "rag": self.budget.rag,
                "tools": self.budget.tools,
                "history": self.budget.history,
            }[category]
            essential_result = category in {"rag", "tools"} and position > current_position
            if not essential_result and (used + cost > cap or spent + cost > self.budget.total):
                continue
            selected.add(id(group))
            spent += cost
            if category == "rag":
                rag_spent += cost
            elif category == "tools":
                tool_spent += cost
            else:
                history_spent += cost
        result = [item for group in groups if id(group) in selected for item in group]
        logger.info(
            "Context assembled estimated_tokens=%d budget=%d history=%d memory=%d rag=%d tools=%d kept_messages=%d",
            spent,
            self.budget.total,
            history_spent,
            count_tokens([SystemMessage(content=memory_text)], model) if memory_text else 0,
            rag_spent,
            tool_spent,
            len(result),
        )
        return result, assembled_system
