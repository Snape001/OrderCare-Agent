"""Opt-in real Ollama tool-call verification; never runs in the default pytest suite."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import httpx
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def trace(result: dict) -> dict:
    messages = result.get("messages", [])
    proposed = [
        call["name"] for msg in messages if isinstance(msg, AIMessage) for call in msg.tool_calls
    ]
    executed = [msg.name for msg in messages if isinstance(msg, ToolMessage)]
    return {"proposed": proposed, "executed": executed}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--report", type=Path, default=Path("reports/ollama-verification.json"))
    args = parser.parse_args()
    os.environ["OLLAMA_MODEL"] = args.model
    from agents.customer_support_agent import build_customer_support_graph
    from customer_support import store

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(args.base_url.rstrip("/") + "/api/tags")
            response.raise_for_status()
            models = {item.get("name") for item in response.json().get("models", [])}
        if args.model not in models:
            raise RuntimeError(f"model {args.model} not installed")
    except (httpx.HTTPError, RuntimeError) as exc:
        print(f"Ollama verification unavailable: {type(exc).__name__}: {exc}")
        return 2

    model = ChatOllama(
        model=args.model,
        base_url=args.base_url,
        temperature=0,
        reasoning=False,
        client_kwargs={"timeout": args.timeout},
    )
    graph = build_customer_support_graph(model, provider="ollama", force_routing=False)
    graph.checkpointer = MemorySaver()
    report = {"provider": "ollama", "model": args.model, "cases": []}

    async def run_case(name: str, message: str, expected_tool: str | None, *, failed=False):
        config = {"configurable": {"thread_id": str(uuid4())}}
        try:
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=message)]}, config=config
            )
            calls = trace(result)
            answer = str(result["messages"][-1].content)
            passed = (
                expected_tool is None and not calls["proposed"] and not calls["executed"]
            ) or (expected_tool in calls["proposed"] and expected_tool in calls["executed"])
            if failed:
                tool_results = [m for m in result["messages"] if isinstance(m, ToolMessage)]
                passed = passed and any(
                    '"ok": false' in str(m.content).lower() for m in tool_results
                )
                passed = passed and "运输中" not in answer and "无线耳机" not in answer
            report["cases"].append({"case": name, "passed": passed, **calls})
        except Exception as exc:
            report["cases"].append(
                {"case": name, "passed": False, "error_type": type(exc).__name__}
            )
        case = report["cases"][-1]
        print(
            f"{name}: {'PASS' if case['passed'] else 'FAIL'}; proposed={case.get('proposed', [])}; executed={case.get('executed', [])}; error={case.get('error_type', '')}",
            flush=True,
        )

    with TemporaryDirectory() as tmp:
        store.DEFAULT_DB_PATH = Path(tmp) / "business.db"
        store.initialize_database()
        await run_case("greeting", "嗨，你主要能帮我处理哪类商城售后？", None)
        await run_case("policy", "买的耳机拆封后想退，有什么限制？", "search_policy")
        await run_case(
            "order", "麻烦看看 ORD1001 的包裹走到哪儿了，我的手机尾号是 8821", "get_order_status"
        )
        await run_case(
            "refund", "ORD1002 这件商品还退得了吗？手机尾号 8821", "check_refund_eligibility"
        )
        await run_case(
            "failed_order", "查一下 ORD9999 的进度，手机尾号 8821", "get_order_status", failed=True
        )

        config = {"configurable": {"thread_id": str(uuid4())}}
        try:
            first = await graph.ainvoke(
                {
                    "messages": [
                        HumanMessage(
                            content="我想请人工处理 ORD1001 的物流问题，手机尾号 8821，请开工单"
                        )
                    ]
                },
                config=config,
            )
            calls = trace(first)
            interrupted = bool(first.get("__interrupt__"))
            with closing(store._connect()) as db:
                before = db.execute("SELECT COUNT(*) FROM support_tickets").fetchone()[0]
            if interrupted:
                await graph.ainvoke(
                    Command(resume={"decisions": [{"type": "reject"}]}), config=config
                )
            with closing(store._connect()) as db:
                after = db.execute("SELECT COUNT(*) FROM support_tickets").fetchone()[0]
            report["cases"].append(
                {
                    "case": "ticket_rejection",
                    "passed": interrupted
                    and before == after == 0
                    and "create_support_ticket" in calls["proposed"],
                    "interrupted": interrupted,
                    **calls,
                }
            )
        except Exception as exc:
            report["cases"].append(
                {"case": "ticket_rejection", "passed": False, "error_type": type(exc).__name__}
            )
        print(
            f"ticket_rejection: {'PASS' if report['cases'][-1]['passed'] else 'FAIL'}", flush=True
        )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {args.report}")
    return 0 if all(case["passed"] for case in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
