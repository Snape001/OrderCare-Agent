"""Compare three model views using saved DeepSeek output; no API calls."""

from __future__ import annotations

import json
from typing import Any

from evaluate_compaction_phase4 import BUDGET, DATASET, ROOT, make_messages, model_view_tokens
from langchain_core.messages import AnyMessage, SystemMessage

from memory.context_manager import ContextManager, TokenBudget, count_tokens

LLM_RESULTS = ROOT / "data/evaluation/context-compaction-v2/llm-results.json"
OFFLINE_RESULTS = ROOT / "data/evaluation/context-compaction-v2/offline-results.json"
OUTPUT = ROOT / "data/evaluation/context-compaction-v2/three-context-comparison.json"


def visible_text(view: list[AnyMessage], system: SystemMessage | None) -> str:
    return (str(system.content) if system else "") + "\n" + "\n".join(
        str(message.content) for message in view
    )


def main() -> None:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))["cases"]
    live = {row["id"]: row for row in json.loads(LLM_RESULTS.read_text(encoding="utf-8"))["results"]}
    offline = {
        row["id"]: row
        for row in json.loads(OFFLINE_RESULTS.read_text(encoding="utf-8"))["cases"]
    }
    manager = ContextManager(BUDGET)
    rows: list[dict[str, Any]] = []
    for case in dataset:
        messages = make_messages(case["messages"])
        system = SystemMessage(content=case["system"])
        raw_text = visible_text(messages, system)
        plain_view, plain_system = manager.assemble(
            messages=messages, system=system, state={}, memory={}
        )
        plain_text = visible_text(plain_view, plain_system)
        summary = live[case["id"]]["calls"][1]["parsed"]
        summary_tokens = count_tokens([
            SystemMessage(content=json.dumps(summary, ensure_ascii=False))
        ])
        compact_view, compact_system = manager.assemble(
            messages=messages, system=system, state={}, memory={"compaction": summary}
        )
        compact_text = visible_text(compact_view, compact_system)
        rows.append({
            "id": case["id"],
            "raw_estimated_tokens": count_tokens([system, *messages]),
            "context_manager_only_estimated_tokens": model_view_tokens(
                plain_view, plain_system
            ),
            "context_manager_plus_llm_summary_estimated_tokens": model_view_tokens(
                compact_view, compact_system
            ),
            "context_manager_plus_production_summary_estimated_tokens": offline[
                case["id"]
            ]["context_manager_plus_compaction_estimated_tokens"],
            "llm_summary_estimated_tokens": summary_tokens,
            "llm_summary_injected": "已压缩历史" in compact_text,
            "production_default_triggered": (
                count_tokens([system, *messages]) >= TokenBudget().total * 0.8
            ),
            "llm_summary_fits_production_summary_budget": summary_tokens <= 384,
            "lexical_fact_checks": {
                scheme: {fact: fact in text for fact in case["required_facts"]}
                for scheme, text in (
                    ("raw", raw_text), ("context_manager_only", plain_text),
                    ("context_manager_plus_llm_summary", compact_text),
                )
            },
            "current_request_preserved": all(
                case["messages"][-1]["content"] in text
                for text in (raw_text, plain_text, compact_text)
            ),
        })
    totals = {
        key: sum(int(row[key]) for row in rows)
        for key in (
            "raw_estimated_tokens", "context_manager_only_estimated_tokens",
            "context_manager_plus_llm_summary_estimated_tokens",
            "context_manager_plus_production_summary_estimated_tokens",
            "llm_summary_estimated_tokens",
        )
    }
    result = {
        "dataset": DATASET.relative_to(ROOT).as_posix(),
        "model_output": LLM_RESULTS.relative_to(ROOT).as_posix(),
        "token_method": "same conservative character estimator for all three model views",
        "comparison_config": {
            "total_budget": BUDGET.total,
            "memory_budget": BUDGET.memory,
            "forced_compaction_trigger_budget": 350,
            "production_defaults": {
                "total_budget": TokenBudget().total,
                "summary_budget": 384,
                "threshold": 0.8,
            },
        },
        "cases": rows,
        "totals": totals,
        "limitation": "Only summary-context continuation was sent to DeepSeek; raw and pruned model answers were not generated under the approved six-call budget.",
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(totals, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
