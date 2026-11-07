"""Offline three-way compaction comparison using the frozen v2 synthetic data.

Never imports or calls a model Provider. The online Agent continues to use its
existing ContextManager. This script creates a new result file per invocation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from evaluate_compaction import MemoryStub
from evaluate_compaction_phase4 import BUDGET, DATASET, ROOT, make_messages, model_view_tokens
from langchain_core.messages import AnyMessage, SystemMessage, ToolMessage

from memory.compaction import AutomaticCompactor
from memory.context_compaction_candidate import CandidateBudget, CompactedContextAssembler
from memory.context_manager import ContextManager, count_tokens

OUTPUT = ROOT / "data/evaluation/context-compaction-v2/candidate-replacement-v1.json"
LLM_RESULTS = ROOT / "data/evaluation/context-compaction-v2/llm-results.json"


def _visible(view: list[AnyMessage], system: SystemMessage | None) -> str:
    return (str(system.content) if system else "") + "\n" + "\n".join(
        str(message.content) for message in view
    )


def _fact_checks(
    facts: list[str], view: list[AnyMessage], system: SystemMessage | None
) -> dict[str, bool]:
    text = _visible(view, system)
    result = {}
    for fact in facts:
        if "#" in fact:
            source, section = fact.split("#", 1)
            result[fact] = source in text and section in text
        elif fact == "get_order_status":
            result[fact] = fact in text or any(
                isinstance(message, ToolMessage) and message.name == fact for message in view
            )
        else:
            result[fact] = fact in text
    return result


async def evaluate(
    summary_budget: int = 320, recent_turns: int = 2, summary_source: str = "extractive"
) -> dict[str, Any]:
    cases = json.loads(DATASET.read_text(encoding="utf-8"))["cases"]
    if summary_source not in {"extractive", "saved_deepseek"}:
        raise ValueError("Unknown summary source")
    saved_llm = (
        {row["id"]: row["calls"][1]["parsed"] for row in
         json.loads(LLM_RESULTS.read_text(encoding="utf-8"))["results"]}
        if summary_source == "saved_deepseek" else {}
    )
    store = MemoryStub()
    compactor = AutomaticCompactor(store, summary_budget=1200)  # type: ignore[arg-type]
    manager = ContextManager(BUDGET)
    candidate = CompactedContextAssembler(
        BUDGET, CandidateBudget(summary=summary_budget, recent_turns=recent_turns)
    )
    rows = []
    for case in cases:
        messages = make_messages(case["messages"])
        system = SystemMessage(content=case["system"])
        summary, _ = await compactor.maybe_compact(
            owner=case["id"], thread="fixed", messages=messages,
            system=system, total_budget=350,
        )
        record = (await store.session(case["id"], "fixed")).get("compaction")
        if summary is None or not record:
            raise RuntimeError(f"No cursor-backed summary for {case['id']}")
        if summary_source == "saved_deepseek":
            record = {**record, "summary": saved_llm[case["id"]]}
        baseline_view, baseline_system = manager.assemble(
            messages=messages, system=system, state={}, memory={}
        )
        replacement = candidate.assemble(
            messages=messages, system=system, state={}, memory={},
            compaction_record=record,
        )
        raw_tokens = count_tokens([system, *messages])
        baseline_tokens = model_view_tokens(baseline_view, baseline_system)
        candidate_tokens = model_view_tokens(replacement.messages, replacement.system)
        fact_checks = {
            "raw": _fact_checks(case["required_facts"], messages, system),
            "dynamic_only": _fact_checks(
                case["required_facts"], baseline_view, baseline_system
            ),
            "replacement": _fact_checks(
                case["required_facts"], replacement.messages, replacement.system
            ),
        }
        rows.append({
            "id": case["id"],
            "raw_estimated_tokens": raw_tokens,
            "dynamic_only_estimated_tokens": baseline_tokens,
            "replacement_estimated_tokens": candidate_tokens,
            "token_reduction_vs_raw": round((raw_tokens - candidate_tokens) / raw_tokens, 4),
            "token_delta_vs_dynamic_only": candidate_tokens - baseline_tokens,
            "fact_checks": fact_checks,
            "candidate_metrics": replacement.metrics,
            "current_request_preserved": replacement.messages[-1] is messages[-1],
            "system_rules_preserved": replacement.system is not None
            and case["system"] in str(replacement.system.content),
            "context_budget_exceeded": candidate_tokens > BUDGET.total,
        })
    totals: dict[str, Any] = {
        key: sum(int(row[key]) for row in rows)
        for key in (
            "raw_estimated_tokens", "dynamic_only_estimated_tokens",
            "replacement_estimated_tokens", "token_delta_vs_dynamic_only",
        )
    }
    totals.update({
        "summary_injection_rate": round(
            sum(bool(row["candidate_metrics"]["summary_injected"]) for row in rows)
            / len(rows), 4,
        ),
        "token_reduction_vs_raw": round(
            (totals["raw_estimated_tokens"] - totals["replacement_estimated_tokens"])
            / totals["raw_estimated_tokens"], 4,
        ),
        "context_budget_overrun_rate": round(
            sum(row["context_budget_exceeded"] for row in rows) / len(rows), 4
        ),
        "fact_retention": {
            scheme: f"{sum(sum(checks.values()) for checks in
                           (row['fact_checks'][scheme] for row in rows))}/"
                    f"{sum(len(row['fact_checks'][scheme]) for row in rows)}"
            for scheme in ("raw", "dynamic_only", "replacement")
        },
        "source_duplicate_fact_rate": round(
            sum(int(row["candidate_metrics"].get("source_duplicate_facts", 0)) for row in rows)
            / max(1, sum(int(row["candidate_metrics"].get("summary_facts_available", 0))
                         for row in rows)), 4,
        ),
        "post_assembly_duplicate_fact_rate": round(
            sum(int(row["candidate_metrics"].get("post_assembly_duplicate_facts", 0))
                for row in rows)
            / max(1, sum(int(row["candidate_metrics"].get("summary_facts_selected", 0))
                         for row in rows)), 4,
        ),
        "api_calls": 0,
    })
    return {
        "dataset": DATASET.relative_to(ROOT).as_posix(),
        "candidate_code": "src/memory/context_compaction_candidate.py",
        "online_agent_changed": False,
        "config": {"context_budget": vars(BUDGET), "summary_budget": summary_budget,
                   "recent_turns": recent_turns, "forced_trigger_total_budget": 350,
                   "summary_source": summary_source},
        "cases": rows, "totals": totals,
        "limitations": [
            "Strict string-based fact checks; no LLM Judge or new DeepSeek calls",
            "Short synthetic dialogues forced to compact; production default threshold does not trigger",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-budget", type=int, default=320)
    parser.add_argument("--recent-turns", type=int, default=2)
    parser.add_argument("--summary-source", choices=("extractive", "saved_deepseek"),
                        default="extractive")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.summary_budget, args.recent_turns,
                                  args.summary_source))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(result["totals"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
