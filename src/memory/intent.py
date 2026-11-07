"""Explicit, conservative requests to store a customer-supplied support event."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage

_request = re.compile(r"^\s*(?:请|麻烦|能否|可以)?\s*(?:帮我)?\s*(?:记住|记录|保存)(.*)$")
_trailing_request = re.compile(
    r"^(?P<event>.+?)[，,。；;]?\s*(?:请(?:帮我|替我)?|麻烦(?:帮我|替我)?|帮我|替我)"
    r"\s*(?:记住|记录|保存)(?P<reference>.*)$"
)
_reference = re.compile(r"^(?:这件事|这次售后情况|这次情况|这个问题)[。！？?]*$")
_event_words = (
    "售后", "问题", "故障", "坏", "破损", "无声", "没有声音", "延迟", "维修", "退款", "退货", "物流",
)
_additional_action = re.compile(r"(?:并|同时|然后).{0,10}(?:查|查询|申请退款|创建工单|提交工单)")


def requested_event(message: str, history: list[Any]) -> tuple[bool, str | None]:
    """Return whether recording was requested and a user-stated event, if available."""
    match = _request.match(message)
    trailing = _trailing_request.match(message) if match is None else None
    if match is None and trailing is None:
        return False, None
    content = (
        match.group(1) if match is not None else trailing.group("event")  # type: ignore[union-attr]
    ).strip(" ，。:：")
    if _reference.fullmatch(content):
        content = next(
            (
                str(item.content).strip()
                for item in reversed(history)
                if isinstance(item, HumanMessage)
                and str(item.content) != message
                and _request.match(str(item.content)) is None
                and any(word in str(item.content) for word in _event_words)
            ),
            "",
        )
    if (
        not 6 <= len(content) <= 220
        or not any(word in content for word in _event_words)
        or _additional_action.search(content)
    ):
        return True, None
    return True, "用户报告的历史售后情况：" + content
