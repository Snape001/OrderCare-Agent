"""Offline synthetic compaction check; no Redis service or LLM API required."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage

from memory.compaction import AutomaticCompactor
from memory.context_manager import ContextManager, TokenBudget, count_tokens


class MemoryStub:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], dict] = {}
        self.lock = asyncio.Lock()

    async def session(self, owner: str, thread: str) -> dict:
        return self.data.get((owner, thread), {}).copy()

    async def save_compaction(
        self,
        owner: str,
        thread: str,
        expected_cursor: str,
        cursor: str,
        summary: dict[str, list[str]],
    ) -> bool:
        async with self.lock:
            value = self.data.get((owner, thread), {})
            if (value.get("compaction") or {}).get("cursor", "") != expected_cursor:
                return False
            self.data[(owner, thread)] = {"compaction": {"cursor": cursor, "summary": summary}}
            return True


async def evaluate() -> dict:
    store = MemoryStub()
    compactor = AutomaticCompactor(store, threshold=0.8, summary_budget=1200)  # type: ignore[arg-type]
    messages: list[AnyMessage] = [
        HumanMessage(content="我的目标是维修耳机，如果不能退货，请保留政策引用 ORD1001"),
        AIMessage(content="", tool_calls=[{"name": "search_policy", "args": {}, "id": "policy"}]),
        ToolMessage(
            content=json.dumps(
                {
                    "ok": True,
                    "references": [{"source": "policy.md", "title": "维修规则"}],
                    "content": "售后政策证据" * 100,
                },
                ensure_ascii=False,
            ),
            name="search_policy",
            tool_call_id="policy",
        ),
        AIMessage(content="已查到政策"),
        HumanMessage(content="我希望使用文字客服"),
        AIMessage(content="已记录"),
        HumanMessage(content="现在继续办理维修"),
        AIMessage(content="请确认后续步骤"),
        HumanMessage(content="下一步是什么？"),
    ]
    system = SystemMessage(content="系统规则：订单与退款状态必须实时查询，工单写入需要确认。")
    raw_tokens = count_tokens([system, *messages])
    summary, metrics = await compactor.maybe_compact(
        owner="synthetic-owner",
        thread="synthetic-thread",
        messages=messages,
        system=system,
        total_budget=700,
    )
    assert summary is not None
    view, assembled_system = ContextManager(
        TokenBudget(
            total=1600,
            system=250,
            history=250,
            memory=900,
            rag=200,
            tools=200,
        )
    ).assemble(messages=messages, system=system, state={}, memory={"compaction": summary})
    compacted_tokens = count_tokens(view + ([assembled_system] if assembled_system else []))
    facts = {
        "order_id": "ORD1001" in summary["entities"],
        "citation": "policy.md#维修规则" in summary["citations"],
        "preference": any("文字客服" in item for item in summary["preferences"]),
    }
    continuity = (
        view[-1] is messages[-1]
        and assembled_system is not None
        and "订单与退款状态必须实时查询" in str(assembled_system.content)
        and all(facts.values())
    )
    return {
        "dataset": "synthetic-offline-v1",
        "questions": 4,
        "raw_estimated_tokens": raw_tokens,
        "assembled_estimated_tokens": compacted_tokens,
        "token_saving_rate": round(max(0, raw_tokens - compacted_tokens) / raw_tokens, 4),
        "critical_fact_retention_rate": round(sum(facts.values()) / len(facts), 4),
        "task_continuity": continuity,
        "facts": facts,
        "triggered": metrics["triggered"],
        "api_calls": 0,
    }


def main() -> None:
    result = asyncio.run(evaluate())
    target = Path("data/evaluation/context-compaction-v1")
    target.mkdir(parents=True, exist_ok=True)
    (target / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
