"""Explicitly gated, small DeepSeek compaction quality experiment.

Default invocation only prints the six-call budget. --execute makes paid API
calls after the operator has approved the stated cost. This does not change
the production extractive compactor or historical evaluation results.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage

from memory.compaction import _clean, _payment
from memory.context_manager import count_tokens

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/evaluation/context-compaction-v2/dataset-v1.json"
OUTPUT = ROOT / "data/evaluation/context-compaction-v2/llm-results.json"
ESTIMATE_OUTPUT = ROOT / "data/evaluation/context-compaction-v2/api-estimate.json"
MAX_INPUT_PER_CALL = 3000
MAX_OUTPUT_PER_CALL = 320
CALLS_PER_CASE = 3
EXPERIMENT_MODEL = "deepseek-flash"
# DeepSeek official cache-miss rates, CNY per one million tokens (2026-11-06).
PEAK_INPUT_CNY_PER_M = 2.0
PEAK_OUTPUT_CNY_PER_M = 8.0
OFFPEAK_INPUT_CNY_PER_M = 1.0
OFFPEAK_OUTPUT_CNY_PER_M = 4.0


def prompts(case: dict[str, Any]) -> list[tuple[str, str]]:
    history = case["messages"][:-1]
    midpoint = len(history) // 2
    parts = [history[:midpoint], history[midpoint:]]
    rule = (
        "你是客服对话的实验性摘要器。仅依据输入保留目标、约束、已确认决策、"
        "工具结果、未解决事项、订单与政策引用。动态订单状态仅作历史线索。"
        "不得编造事实，不输出手机号、支付详情或模型思考。"
        "输出 JSON 对象，字段为 goals, constraints, decisions, completed_steps, "
        "open_issues, entities, citations；各字段是字符串数组。"
    )
    first = _clean(json.dumps([
        row for row in parts[0] if not _payment.search(str(row.get("content", "")))
    ], ensure_ascii=False))
    second = _clean(json.dumps([
        row for row in parts[1] if not _payment.search(str(row.get("content", "")))
    ], ensure_ascii=False))
    return [
        (rule, "请总结第一段历史：" + first),
        (rule, "请把既有摘要与新增历史增量合并，去重并保留约束。\n既有摘要：{previous}"
         "\n新增历史：" + second),
        (
            "仅依据下列系统规则与历史摘要回答当前问题；缺少实时资格时说明需重新查询。"
            "输出简短 JSON：{\"answer\": \"...\"}。\n" + case["system"],
            "历史摘要：{previous}\n当前问题：" + _clean(case["messages"][-1]["content"]),
        ),
    ]


def estimate() -> dict[str, Any]:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    calls = len(data["cases"]) * CALLS_PER_CASE
    for case in data["cases"]:
        for system, user in prompts(case):
            # Reserve an entire first-summary output for each {previous} slot.
            reserved = user.replace("{previous}", "中" * MAX_OUTPUT_PER_CALL)
            estimate_tokens = count_tokens([
                SystemMessage(content=system), HumanMessage(content=reserved)
            ])
            if estimate_tokens > MAX_INPUT_PER_CALL:
                raise ValueError(f"{case['id']} prompt exceeds input cap: {estimate_tokens}")
    max_input = calls * MAX_INPUT_PER_CALL
    max_output = calls * MAX_OUTPUT_PER_CALL
    return {
        "model": EXPERIMENT_MODEL,
        "temperature": 0,
        "cases": len(data["cases"]),
        "max_api_calls": calls,
        "max_input_tokens": max_input,
        "max_output_tokens": max_output,
        "max_peak_cost_cny": round(
            (max_input * PEAK_INPUT_CNY_PER_M + max_output * PEAK_OUTPUT_CNY_PER_M)
            / 1_000_000, 6,
        ),
        "max_offpeak_cost_cny": round(
            (max_input * OFFPEAK_INPUT_CNY_PER_M
             + max_output * OFFPEAK_OUTPUT_CNY_PER_M) / 1_000_000, 6,
        ),
        "pricing_source": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
        "real_api_calls_made_by_estimate": 0,
    }


def execute() -> dict[str, Any]:
    from langchain_openai import ChatOpenAI

    if OUTPUT.exists():
        raise FileExistsError("Phase-4 LLM results already exist; refusing repeated API calls")
    load_dotenv(ROOT / ".env", override=False)
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is required; no fallback is available")
    budget = estimate()
    model = ChatOpenAI(
        model=budget["model"],
        api_key=key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0,
        max_tokens=MAX_OUTPUT_PER_CALL,
        timeout=30,
        max_retries=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
    cases = json.loads(DATASET.read_text(encoding="utf-8"))["cases"]
    results: list[dict[str, Any]] = []
    actual_usage: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0}
    try:
        for case in cases:
            previous = "{}"
            calls: list[dict[str, Any]] = []
            results.append({"id": case["id"], "calls": calls})
            for step, (system, user) in enumerate(prompts(case), 1):
                user = user.replace("{previous}", previous)
                messages: list[AnyMessage] = [
                    SystemMessage(content=system), HumanMessage(content=user)
                ]
                if count_tokens(messages) > MAX_INPUT_PER_CALL:
                    raise ValueError(f"{case['id']} step {step} exceeds input cap")
                started = perf_counter()
                try:
                    response = model.invoke(messages)
                except Exception as exc:
                    calls.append({"step": step, "error_type": type(exc).__name__})
                    raise
                raw = str(response.content)
                call = {
                    "step": step,
                    "raw_output": raw,
                    "usage_metadata": response.usage_metadata,
                    "response_metadata": {
                        key: response.response_metadata.get(key)
                        for key in ("model_name", "finish_reason", "token_usage")
                    },
                    "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                }
                usage: dict[str, Any] = dict(response.usage_metadata or {})
                actual_usage["input_tokens"] += int(usage.get("input_tokens", 0))
                actual_usage["output_tokens"] += int(usage.get("output_tokens", 0))
                try:
                    parsed = json.loads(raw)
                    if not isinstance(parsed, dict):
                        raise ValueError("JSON object required")
                    if step < 3 and not all(
                        isinstance(parsed.get(field), list)
                        for field in ("goals", "constraints", "decisions", "completed_steps",
                                      "open_issues", "entities", "citations")
                    ):
                        raise ValueError("summary schema invalid")
                    call["parsed"] = parsed
                except (ValueError, TypeError) as exc:
                    call["parse_error"] = str(exc)
                    calls.append(call)
                    raise RuntimeError(f"{case['id']} step {step}: invalid model JSON") from exc
                calls.append(call)
                if step < 3:
                    previous = json.dumps(parsed, ensure_ascii=False)
            final_summary = calls[1]["parsed"]
            summary_text = json.dumps(final_summary, ensure_ascii=False)
            results[-1]["lexical_fact_checks"] = {
                fact: fact in summary_text for fact in case["required_facts"]
            }
            results[-1]["semantic_fact_retention_rate"] = None
            results[-1]["hallucination_rate"] = None
            results[-1]["task_continuity"] = None
            results[-1]["human_review_required"] = True
    finally:
        actual_usage["api_calls"] = sum(
            "usage_metadata" in call for row in results for call in row["calls"]
        )
        actual_usage["peak_price_estimate_cny"] = round(
            (actual_usage["input_tokens"] * PEAK_INPUT_CNY_PER_M
             + actual_usage["output_tokens"] * PEAK_OUTPUT_CNY_PER_M) / 1_000_000, 6
        )
        actual_usage["note"] = "Estimate from total usage; cache discount not applied"
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps({"budget": budget, "actual_usage": actual_usage, "results": results},
                       ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    return {"budget": budget, "actual_usage": actual_usage, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Make up to six paid DeepSeek calls")
    args = parser.parse_args()
    if args.execute:
        result = execute()
        print(json.dumps({"calls_completed": sum(len(row["calls"]) for row in result["results"]),
                          "output": str(OUTPUT)}, ensure_ascii=False))
    else:
        budget = estimate()
        ESTIMATE_OUTPUT.write_text(
            json.dumps(budget, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(budget, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
