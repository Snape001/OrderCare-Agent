"""Reproducible offline phase-4 accounting; never calls a model API.

The three token counts deliberately separate Context Manager pruning from
the additional Redis-backed compaction summary. Historical v1 results are
left untouched.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from evaluate_compaction import MemoryStub
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage

from memory.compaction import AutomaticCompactor
from memory.context_manager import ContextManager, TokenBudget, count_tokens

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/evaluation/context-compaction-v2/dataset-v1.json"
OUTPUT = ROOT / "data/evaluation/context-compaction-v2/offline-results.json"
BUDGET = TokenBudget(total=900, system=220, history=250, memory=400, rag=250, tools=250)


def make_messages(rows: list[dict[str, Any]]) -> list[AnyMessage]:
    messages: list[AnyMessage] = []
    for row in rows:
        role = row["role"]
        if role == "user":
            messages.append(HumanMessage(content=row["content"]))
        elif role == "assistant":
            messages.append(AIMessage(content=row["content"]))
        elif role == "assistant_tool":
            messages.append(
                AIMessage(content="", tool_calls=[
                    {"name": row["name"], "args": {}, "id": row["id"]}
                ])
            )
        elif role == "tool":
            messages.append(
                ToolMessage(
                    content=json.dumps(row["content"], ensure_ascii=False),
                    name=row["name"],
                    tool_call_id=row["id"],
                )
            )
        else:
            raise ValueError(f"Unknown synthetic role: {role}")
    return messages


def model_view_tokens(view: list[AnyMessage], system: SystemMessage | None) -> int:
    return count_tokens(view + ([system] if system else []))


async def evaluate() -> dict[str, Any]:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    store = MemoryStub()
    compactor = AutomaticCompactor(store, threshold=0.8, summary_budget=1200)  # type: ignore[arg-type]
    manager = ContextManager(BUDGET)
    rows = []
    for case in data["cases"]:
        messages = make_messages(case["messages"])
        system = SystemMessage(content=case["system"])
        raw = count_tokens([system, *messages])
        plain_view, plain_system = manager.assemble(
            messages=messages, system=system, state={}, memory={}
        )
        context_only = model_view_tokens(plain_view, plain_system)
        started = perf_counter()
        summary, event = await compactor.maybe_compact(
            owner=case["id"], thread="fixed", messages=messages,
            system=system, total_budget=350,
        )
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        if summary is None:
            raise RuntimeError(f"Synthetic case {case['id']} did not compact")
        compacted_view, compacted_system = manager.assemble(
            messages=messages, system=system, state={}, memory={"compaction": summary}
        )
        with_compaction = model_view_tokens(compacted_view, compacted_system)
        summary_text = json.dumps(summary, ensure_ascii=False)
        facts = {fact: fact in summary_text for fact in case["required_facts"]}
        visible_text = str(compacted_system.content) if compacted_system else ""
        visible_text += "\n" + "\n".join(str(item.content) for item in compacted_view)
        visible_facts = {fact: fact in visible_text for fact in case["required_facts"]}
        rows.append({
            "id": case["id"],
            "raw_estimated_tokens": raw,
            "context_manager_only_estimated_tokens": context_only,
            "context_manager_plus_compaction_estimated_tokens": with_compaction,
            "context_manager_saving_rate": round((raw - context_only) / raw, 4),
            "compaction_incremental_token_delta": context_only - with_compaction,
            "compacted_history_saved_estimated_tokens": event["saved_tokens"],
            "fact_checks": facts,
            "fact_retention_rate": round(sum(facts.values()) / len(facts), 4),
            "model_visible_fact_checks": visible_facts,
            "model_visible_fact_retention_rate": round(
                sum(visible_facts.values()) / len(visible_facts), 4
            ),
            "summary_injected": "已压缩历史" in visible_text,
            "current_request_preserved": compacted_view[-1] is messages[-1],
            "system_rules_preserved": (
                compacted_system is not None and case["system"] in str(compacted_system.content)
            ),
            "compaction_elapsed_ms": elapsed_ms,
            "summary": summary,
            "api_calls": 0,
        })
    sums = {
        key: sum(int(row[key]) for row in rows)
        for key in (
            "raw_estimated_tokens", "context_manager_only_estimated_tokens",
            "context_manager_plus_compaction_estimated_tokens",
            "compaction_incremental_token_delta", "compacted_history_saved_estimated_tokens",
        )
    }
    checks = [value for row in rows for value in row["fact_checks"].values()]
    visible_checks = [
        value for row in rows for value in row["model_visible_fact_checks"].values()
    ]
    return {
        "dataset": DATASET.relative_to(ROOT).as_posix(),
        "dataset_version": data["version"],
        "token_method": "conservative character estimator, no model tokenizer",
        "context_budget": vars(BUDGET),
        "compactor_total_budget_for_trigger": 350,
        "compactor_summary_budget": 1200,
        "note": "Stress configuration forces compaction on short synthetic dialogue; production defaults are 4096 total, 384 summary and 80% threshold",
        "cases": rows,
        "totals": {
            **sums,
            "context_manager_saving_rate": round(
                (sums["raw_estimated_tokens"] - sums["context_manager_only_estimated_tokens"])
                / sums["raw_estimated_tokens"], 4,
            ),
            "compaction_incremental_saving_rate_vs_context_only": round(
                sums["compaction_incremental_token_delta"]
                / sums["context_manager_only_estimated_tokens"], 4,
            ),
            "critical_fact_retention_rate": round(sum(checks) / len(checks), 4),
            "model_visible_fact_retention_rate": round(
                sum(visible_checks) / len(visible_checks), 4
            ),
            "current_request_and_rules_preserved": all(
                row["current_request_preserved"] and row["system_rules_preserved"]
                for row in rows
            ),
            "api_calls": 0,
            "api_cost_cny": 0,
        },
    }


def main() -> None:
    result = asyncio.run(evaluate())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["totals"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
