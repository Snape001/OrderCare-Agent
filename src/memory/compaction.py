"""Offline, extractive compaction of older checkpoint messages into Redis."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage

from memory.context_manager import _groups, count_tokens
from memory.layers import LayeredMemory

logger = logging.getLogger(__name__)
_active_compactor: AutomaticCompactor | None = None


def set_compactor(compactor: AutomaticCompactor | None) -> None:
    global _active_compactor
    _active_compactor = compactor


def get_compactor() -> AutomaticCompactor | None:
    return _active_compactor


FIELDS = (
    "goals",
    "constraints",
    "preferences",
    "decisions",
    "completed_steps",
    "open_issues",
    "entities",
    "citations",
)
_sensitive = re.compile(
    r"(?i)(?:sk-[\w-]{8,}|bearer\s+[\w.-]+|手机号后四位\s*[:：]?\s*\d{4}|(?<![A-Za-z0-9])\d{4,}(?![A-Za-z0-9]))"
)
_order = re.compile(r"\b(?:ORD\d+|OL\d{6})\b", re.I)
_payment = re.compile(r"付款方式|银行卡|信用卡|储蓄卡|卡号|支付账户|支付宝|微信支付", re.I)


def _clean(text: str) -> str:
    return _sensitive.sub("[已脱敏]", text).strip()


def _fingerprint(message: AnyMessage) -> str:
    payload = json.dumps(
        [message.type, message.id, str(message.content), getattr(message, "tool_call_id", "")],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _extract(messages: list[AnyMessage], old: dict[str, list[str]]) -> dict[str, list[str]] | None:
    summary = {field: list(old.get(field, [])) for field in FIELDS}

    def add(field: str, value: str) -> None:
        value = _clean(value)
        if value and value not in summary[field]:
            summary[field].append(value)

    for message in messages:
        if isinstance(message, HumanMessage):
            raw = str(message.content)
            # A free-text payment statement may contain account details in many
            # formats. Drop the whole message instead of attempting partial redaction.
            if _payment.search(raw):
                continue
            text = _clean(raw)
            # Skip long free text rather than saving a partial, misleading fact.
            if len(text) > 180:
                return None
            add("goals", text)
            if re.search(r"不要|必须|只能|如果|优先", text):
                add("constraints", text)
            if re.search(r"偏好|喜欢|希望", text):
                add("preferences", text)
            if re.search(r"确认|同意|取消", text):
                add("decisions", text)
            if "？" in text or "?" in text:
                add("open_issues", text)
            for entity in _order.findall(text):
                add("entities", entity.upper())
        elif isinstance(message, ToolMessage):
            try:
                result = json.loads(str(message.content))
            except (ValueError, TypeError):
                continue
            if not isinstance(result, dict):
                continue
            status = {key: result[key] for key in ("ok", "eligible", "error_code") if key in result}
            if status:
                add("completed_steps", f"{message.name}: {json.dumps(status, ensure_ascii=False)}")
            if message.name == "search_policy":
                for ref in result.get("references", [])[:3]:
                    if isinstance(ref, dict):
                        source = str(ref.get("source", ""))
                        title = str(ref.get("title", ""))
                        if source and title:
                            add("citations", f"{source}#{title}")
    return summary


class AutomaticCompactor:
    def __init__(
        self, store: LayeredMemory, threshold: float = 0.8, summary_budget: int = 384
    ) -> None:
        if not 0 < threshold <= 1:
            raise ValueError("CONTEXT_COMPACTION_THRESHOLD must be between 0 and 1")
        self.store = store
        self.threshold = threshold
        self.summary_budget = summary_budget

    async def maybe_compact(
        self,
        *,
        owner: str,
        thread: str,
        messages: list[AnyMessage],
        system: SystemMessage | None,
        total_budget: int,
        model: Any = None,
    ) -> tuple[dict[str, list[str]] | None, dict[str, int | float | bool]]:
        before = count_tokens(messages + ([system] if system else []), model)
        metrics: dict[str, int | float | bool] = {
            "triggered": False,
            "before_tokens": before,
            "saved_tokens": 0,
            "retention_rate": 1.0,
        }
        if before < total_budget * self.threshold:
            return None, metrics
        session = await self.store.session(owner, thread)
        saved = session.get("compaction") or {}
        previous = saved.get("summary") or {}
        cursor = str(saved.get("cursor") or "")
        groups = _groups([m for m in messages if not isinstance(m, SystemMessage)])
        human_positions = [
            i for i, group in enumerate(groups) if any(isinstance(m, HumanMessage) for m in group)
        ]
        if len(human_positions) < 3:
            return previous or None, metrics
        eligible = [m for group in groups[: human_positions[-2]] for m in group]
        if not eligible:
            return previous or None, metrics
        start = 0
        if cursor:
            index_text, separator, digest = cursor.partition(":")
            if separator:
                index = int(index_text) if index_text.isdigit() else -1
                if index < 0 or index >= len(eligible) or _fingerprint(eligible[index]) != digest:
                    return previous or None, metrics
                start = index + 1
            else:
                # Legacy content-only cursors can collide with a later identical
                # message. Reprocessing is safe (facts are deduplicated); skipping
                # unseen history is not, so use the earliest matching occurrence.
                positions = [i for i, message in enumerate(eligible) if _fingerprint(message) == cursor]
                if not positions:
                    return previous or None, metrics
                start = positions[0] + 1
        new = eligible[start:]
        if not new:
            return previous or None, metrics
        summary = _extract(new, previous)
        if summary is None:
            return previous or None, metrics
        summary_text = json.dumps(summary, ensure_ascii=False)
        if count_tokens([SystemMessage(content=summary_text)], model) > self.summary_budget:
            return previous or None, metrics
        new_cursor = f"{len(eligible) - 1}:{_fingerprint(new[-1])}"
        stored = await self.store.save_compaction(owner, thread, cursor, new_cursor, summary)
        if not stored:
            latest = await self.store.session(owner, thread)
            return (latest.get("compaction") or {}).get("summary"), metrics
        saved_tokens = max(
            0, count_tokens(new, model) - count_tokens([SystemMessage(content=summary_text)], model)
        )
        metrics.update(triggered=True, saved_tokens=saved_tokens)
        logger.info(
            "Context compacted before_tokens=%d saved_tokens=%d facts=%d",
            before,
            saved_tokens,
            sum(len(v) for v in summary.values()),
        )
        return summary, metrics
