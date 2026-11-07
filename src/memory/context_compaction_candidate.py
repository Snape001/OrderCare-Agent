"""Opt-in assembly: replace cursor-covered history with a bounded summary.

Checkpoint messages remain untouched; only the model view is assembled
differently when CONTEXT_COMPACTION_ENABLED is explicitly enabled.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage

from memory.compaction import _fingerprint
from memory.context_manager import ContextManager, TokenBudget, _groups, count_tokens, query_terms


@dataclass(frozen=True)
class CandidateBudget:
    summary: int = 320
    long_term: int = 120
    recent_turns: int = 2

    def __post_init__(self) -> None:
        if min(self.summary, self.long_term, self.recent_turns) < 1:
            raise ValueError("Candidate budgets and recent turns must be positive")


@dataclass
class CandidateView:
    messages: list[AnyMessage]
    system: SystemMessage | None
    metrics: dict[str, int | float | bool | str]


def _cursor_end(messages: list[AnyMessage], cursor: str) -> int | None:
    """Return the covered prefix length only for a verified group boundary."""
    groups = _groups([message for message in messages if not isinstance(message, SystemMessage)])
    flat = [message for group in groups for message in group]
    if not cursor or not flat:
        return None
    index_text, separator, digest = cursor.partition(":")
    if separator:
        index = int(index_text) if index_text.isdigit() and len(index_text) < 9 else -1
        if index < 0 or index >= len(flat) or _fingerprint(flat[index]) != digest:
            return None
    else:
        matches = [index for index, message in enumerate(flat) if _fingerprint(message) == cursor]
        if not matches:
            return None
        index = matches[0]  # Legacy cursor: reprocess ambiguity rather than skip history.
    boundaries = {id(group[-1]) for group in groups}
    return index + 1 if id(flat[index]) in boundaries else None


def _fact_lines(summary: dict[str, Any], visible: str) -> tuple[list[str], int, int]:
    """Prioritize constraints and citations, de-duplicate repeated field values."""
    priority = (
        ("constraints", "约束"), ("entities", "实体"), ("citations", "引用"),
        ("goals", "目标"), ("open_issues", "待办"), ("decisions", "决定"),
        ("completed_steps", "已完成"), ("preferences", "偏好"),
    )
    seen: set[str] = set()
    lines: list[str] = []
    original = duplicates = 0
    for field, label in priority:
        values = summary.get(field) or []
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, str) or not value.strip():
                continue
            fact = value.strip()
            original += 1
            if fact in seen or fact in visible:
                duplicates += 1
                continue
            seen.add(fact)
            lines.append(f"{label}：{fact}")
    return lines, original, duplicates


def _protected_state(state: dict[str, Any]) -> str:
    """Carry explicit approval and plan state; never include arbitrary model text."""
    safe: dict[str, Any] = {}
    for name in ("approval", "pending_approval", "interrupt"):
        value = state.get(name)
        if isinstance(value, dict):
            safe[name] = {key: value[key] for key in ("status", "action", "decision") if key in value}
    plan = state.get("plan")
    if isinstance(plan, dict):
        steps = plan.get("steps") or []
        safe["plan_actions"] = [
            step.get("action") for step in steps if isinstance(step, dict) and step.get("action")
        ]
    return "\n当前审批与任务状态：" + json.dumps(safe, ensure_ascii=False) if safe else ""


class CompactedContextAssembler:
    def __init__(self, token_budget: TokenBudget, candidate_budget: CandidateBudget) -> None:
        self.token_budget = token_budget
        self.candidate_budget = candidate_budget

    def assemble(
        self,
        *,
        messages: list[AnyMessage],
        system: SystemMessage | None,
        state: dict[str, Any],
        memory: dict[str, Any] | None,
        compaction_record: dict[str, Any] | None,
        model: Any = None,
    ) -> CandidateView:
        snapshot = memory or {}

        def fallback(reason: str, cursor_valid: bool = False) -> CandidateView:
            baseline, baseline_system = ContextManager(self.token_budget).assemble(
                messages=messages, system=system, state=state,
                memory={key: value for key, value in snapshot.items() if key != "compaction"},
                model=model,
            )
            return CandidateView(baseline, baseline_system, {
                "cursor_valid": cursor_valid, "summary_injected": False,
                "covered_messages": 0, "reason": reason,
            })

        cursor = str((compaction_record or {}).get("cursor") or "")
        summary = (compaction_record or {}).get("summary")
        covered = _cursor_end(messages, cursor) if isinstance(summary, dict) else None
        groups = _groups([message for message in messages if not isinstance(message, SystemMessage)])
        flat = [message for group in groups for message in group]
        current = next((message for message in reversed(flat) if isinstance(message, HumanMessage)), None)
        if covered is None or current is None or not any(
            message is current for message in flat[covered:]
        ):
            return fallback("missing_or_invalid_cursor")

        protected = _protected_state(state)
        protected_system = SystemMessage(
            content=(str(system.content) if system else "") + protected
        ) if system or protected else None
        uncovered = flat[covered:]
        core, core_system = ContextManager(self.token_budget).assemble(
            messages=uncovered, system=protected_system, state=state,
            memory={"working": snapshot.get("working") or {}}, model=model,
        )
        # recent_turns counts the latest N user turns including the current one.
        # Verify against the full checkpoint view so a cursor cannot silently
        # consume a turn that the candidate promises to retain verbatim.
        recent_groups = groups
        human_indices = [
            index for index, group in enumerate(recent_groups)
            if any(isinstance(message, HumanMessage) for message in group)
        ]
        recent_start = human_indices[-self.candidate_budget.recent_turns] \
            if len(human_indices) >= self.candidate_budget.recent_turns else 0
        protected_recent = [
            message for group in recent_groups[recent_start:] for message in group
        ]
        recent_kept = all(any(item is message for item in core) for message in protected_recent)
        if not recent_kept:
            result = fallback("recent_turns_not_preserved", cursor_valid=True)
            result.metrics["recent_turns_preserved"] = False
            return result
        visible = "\n".join(str(message.content) for message in core)
        assert isinstance(summary, dict)
        lines, fact_count, duplicate_count = _fact_lines(summary, visible)
        prefix = "压缩历史（仅作线索；动态订单状态须重新核验）："
        selected: list[str] = []
        base = str(core_system.content) if core_system else ""
        core_tokens = count_tokens(core + ([core_system] if core_system else []), model)
        for line in lines:
            proposed_summary = prefix + "\n" + "\n".join([*selected, line])
            proposed_system = SystemMessage(content=base + "\n" + proposed_summary)
            added = count_tokens([proposed_system], model) - (
                count_tokens([core_system], model) if core_system else 0
            )
            if added <= self.candidate_budget.summary and core_tokens + added <= self.token_budget.total:
                selected.append(line)
        essential = [
            line for line in lines if line.startswith(("约束：", "实体：", "引用："))
        ]
        if not selected or any(line not in selected for line in essential):
            return fallback("summary_budget_insufficient", cursor_valid=True)
        summary_text = prefix + "\n" + "\n".join(selected) if selected else ""
        assembled_text = base + ("\n" + summary_text if summary_text else "")

        # Long-term notes are lower priority than recent turns and the summary.
        query = str(current.content)
        terms = query_terms(query)
        short_summary = str(snapshot.get("summary") or "")[:200]
        note_source = ([{"value": short_summary, "updated_at": "9999"}] if short_summary else [])
        note_source.extend(snapshot.get("notes") or [])
        notes = sorted(
            (note for note in note_source if isinstance(note, dict)
             and isinstance(note.get("value"), str)),
            key=lambda note: (
                note.get("kind") == "preference",
                note.get("kind") == "episode",
                float(note.get("score", 0.0)),
                sum(term in note["value"].lower() for term in terms),
                str(note.get("updated_at", "")),
            ), reverse=True,
        )
        long_spent = 0
        for note in notes:
            value = str(note["value"])
            if note.get("kind") not in {"preference", "episode"} and terms and not any(
                term in value.lower() for term in terms
            ):
                continue
            if value in assembled_text:
                continue
            candidate = "\n历史偏好/售后线索（动态事实须重新核验）：" + value[:160]
            proposed = SystemMessage(content=assembled_text + candidate)
            previous = SystemMessage(content=assembled_text)
            delta = count_tokens([proposed], model) - count_tokens([previous], model)
            if (
                long_spent + delta <= self.candidate_budget.long_term
                and count_tokens(core + [proposed], model) <= self.token_budget.total
            ):
                assembled_text += candidate
                long_spent += delta

        final_system = SystemMessage(content=assembled_text) if assembled_text else None
        total = count_tokens(core + ([final_system] if final_system else []), model)
        return CandidateView(core, final_system, {
            "cursor_valid": True,
            "summary_injected": bool(selected),
            "covered_messages": covered,
            "summary_facts_available": fact_count,
            "summary_facts_selected": len(selected),
            "source_duplicate_facts": duplicate_count,
            "post_assembly_duplicate_facts": sum(
                line.partition("：")[2] in visible for line in selected
            ),
            "recent_turns_preserved": recent_kept,
            "estimated_tokens": total,
            "budget_overrun": total > self.token_budget.total,
            "reason": "ok" if selected else "summary_not_injected",
        })
