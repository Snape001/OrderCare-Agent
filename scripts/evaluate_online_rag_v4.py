"""Compare v3 Dense with the real STDIO MCP search_policy Hybrid tool."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

from customer_support.mcp_client import normalize_result  # noqa: E402
from customer_support.rag import RETRIEVAL_CANDIDATES, PolicyKnowledgeBase  # noqa: E402
from evaluation.rag import digest, load_dataset, retrieval_metrics  # noqa: E402

POLICY = Path("data/policies/v3")
DATASET = Path("data/evaluation/rag/dataset-v4.json")
OUTPUT = Path("data/evaluation/rag/online-comparison-v4")
METRICS = ("recall", "precision", "mrr", "ndcg")


def timing(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "total_ms": sum(ordered),
        "mean_ms": statistics.mean(ordered),
        "p95_ms": ordered[math.ceil(len(ordered) * 0.95) - 1],
    }


def grouped(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups = {
        "all": rows,
        **{split: [row for row in rows if row["split"] == split] for split in ("dev", "test")},
        **{style: [row for row in rows if row["query_style"] == style]
           for style in ("formal", "colloquial")},
    }
    return {
        name: {
            "count": len(items),
            "dense": {metric: statistics.mean(row["dense_metrics"][metric] for row in items)
                      for metric in METRICS},
            "hybrid": {metric: statistics.mean(row["hybrid_metrics"][metric] for row in items)
                       for metric in METRICS},
            "dense_retrieval": timing([row["dense_retrieval_ms"] for row in items]),
            "hybrid_retrieval": timing([row["hybrid_retrieval_ms"] for row in items]),
            "mcp_roundtrip": timing([row["mcp_roundtrip_ms"] for row in items]),
        }
        for name, items in groups.items()
    }


def render(report: dict[str, Any]) -> str:
    lines = [
        "# v4 在线 RAG 检索挑战集", "",
        "40 道可答题、20 组 Formal/Colloquial 配对题；语料为 v3 的 36 份政策。",
        "题目经过检索表现筛选，因此这是定向挑战集，dev/test 均不是无偏留出集。", "",
        "| 分支 / 分组 | Recall@3 | Precision@3 | MRR@3 | nDCG@3 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for group, item in report["summary"].items():
        for method in ("dense", "hybrid"):
            m = item[method]
            lines.append(
                f"| {method} / {group} | {m['recall']:.4f} | {m['precision']:.4f} | "
                f"{m['mrr']:.4f} | {m['ndcg']:.4f} |"
            )
    lines += [
        "", "## 逐题胜负与用时", "",
        f"Hybrid 对 Dense 的 Recall@3 胜/负/平：{report['wins']}/"
        f"{report['losses']}/{report['ties']}。",
        f"索引构建 {report['index_init_ms']:.1f} ms；进程内预热 "
        f"{report['local_warmup_ms']:.1f} ms；MCP 启动 "
        f"{report['mcp_startup_ms']:.1f} ms；MCP 预热 "
        f"{report['mcp_warmup_ms']:.1f} ms。", "",
        "| 分组 | Dense 检索均值/P95 ms | Hybrid 本地检索均值/P95 ms | MCP 往返均值/P95 ms |",
        "| --- | ---: | ---: | ---: |",
    ]
    for group, item in report["summary"].items():
        def value(key: str) -> str:
            return f"{item[key]['mean_ms']:.1f}/{item[key]['p95_ms']:.1f}"
        lines.append(
            f"| {group} | {value('dense_retrieval')} | {value('hybrid_retrieval')} | "
            f"{value('mcp_roundtrip')} |"
        )
    lines += [
        "", "MCP 往返包含进程间传输，不能直接与进程内算法耗时比较；"
        "本实验无 DeepSeek、Rewrite、生成或评审 API 调用，API Token 为 0。", "",
        "| 题目 | Dense Recall@3 | Hybrid Recall@3 | 结果 |",
        "| --- | ---: | ---: | --- |",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['id']} | {row['dense_metrics']['recall']:.0f} | "
            f"{row['hybrid_metrics']['recall']:.0f} | {row['outcome']} |"
        )
    return "\n".join(lines) + "\n"


async def evaluate(output: Path) -> dict[str, Any]:
    dataset = load_dataset(DATASET, POLICY)
    cases = dataset["cases"]
    if RETRIEVAL_CANDIDATES != 3:
        raise ValueError("Dense and BM25 must each use Top-3 candidates")
    index = output / "chroma-index"
    kb = PolicyKnowledgeBase(policy_path=POLICY, persist_directory=index)
    started = time.perf_counter()
    chunk_count = kb.ensure_index()
    index_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    kb.search(cases[0]["query"], top_k=3, method="hybrid")
    local_warmup_ms = (time.perf_counter() - started) * 1000
    environment = dict(os.environ)
    # Keep the same relative source names in both processes; they enter the index fingerprint.
    environment["ORDERCARE_EVAL_POLICY_PATH"] = POLICY.as_posix()
    environment["ORDERCARE_EVAL_CHROMA_PATH"] = str(index.resolve())
    environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "customer_support.mcp_server"],
        env=environment, cwd=ROOT,
    )
    rows: list[dict[str, Any]] = []
    startup = time.perf_counter()
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = {tool.name for tool in (await session.list_tools()).tools}
        if "search_policy" not in tools:
            raise RuntimeError("MCP search_policy tool unavailable")
        startup_ms = (time.perf_counter() - startup) * 1000
        started = time.perf_counter()
        warmup = normalize_result((await session.call_tool(
            "search_policy", {"query": cases[0]["query"]}
        )).content)
        mcp_warmup_ms = (time.perf_counter() - started) * 1000
        if not warmup.get("ok"):
            raise RuntimeError("MCP warmup failed")
        for case in cases:
            query = case["query"]
            started = time.perf_counter()
            dense = kb.search(query, top_k=3, method="dense")
            dense_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            local_hybrid = kb.search(query, top_k=3, method="hybrid")
            hybrid_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            response = normalize_result((await session.call_tool(
                "search_policy", {"query": query}
            )).content)
            roundtrip_ms = (time.perf_counter() - started) * 1000
            if not response.get("ok"):
                raise RuntimeError(f"MCP search failed for {case['id']}")
            online = response["references"]
            if [hit["chunk_id"] for hit in online] != [hit["chunk_id"] for hit in local_hybrid]:
                raise ValueError(f"MCP ranking differs from local Hybrid: {case['id']}")
            if any(not hit["source"].replace("\\", "/").startswith(POLICY.as_posix())
                   for hit in online):
                raise ValueError(f"MCP did not use the v3 policy corpus: {case['id']}")
            dm = retrieval_metrics(case, dense, 3)
            hm = retrieval_metrics(case, online, 3)
            outcome = ("win" if hm["recall"] > dm["recall"] else
                       "loss" if hm["recall"] < dm["recall"] else "tie")
            rows.append({
                "id": case["id"], "pair_id": case["pair_id"], "query": query,
                "split": case["split"], "query_style": case["query_style"],
                "category": case["category"], "gold_chunk_ids": [
                    item["chunk_id"] for item in case["relevant_chunks"]
                ],
                "dense_hits": dense, "hybrid_hits": online,
                "dense_metrics": dm, "hybrid_metrics": hm, "outcome": outcome,
                "dense_retrieval_ms": dense_ms, "hybrid_retrieval_ms": hybrid_ms,
                "mcp_roundtrip_ms": roundtrip_ms,
            })
            print(f"{case['id']}: {outcome}", flush=True)
    summary = grouped(rows)
    if not all(
        summary["all"]["hybrid"][metric] > summary["all"]["dense"][metric]
        for metric in ("recall", "precision")
    ):
        raise AssertionError("Hybrid did not beat Dense on both required @3 metrics")
    return {
        "status": "complete", "dataset_sha256": digest(DATASET),
        "policy_sha256": digest(POLICY), "case_count": len(cases),
        "policy_file_count": len(list(POLICY.glob("*.md"))),
        "gold_source_count": len({doc["source"] for case in cases
                                  for doc in case["relevant_documents"]}),
        "chunk_count": chunk_count, "candidate_limit_each_route": 3,
        "index_init_ms": index_ms, "local_warmup_ms": local_warmup_ms,
        "mcp_startup_ms": startup_ms, "mcp_warmup_ms": mcp_warmup_ms,
        "mcp_parity_checked": True, "api_tokens": 0,
        "wins": sum(row["outcome"] == "win" for row in rows),
        "losses": sum(row["outcome"] == "loss" for row in rows),
        "ties": sum(row["outcome"] == "tie" for row in rows),
        "summary": summary, "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(evaluate(args.output))
    (args.output / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output / "report.md").write_text(render(result), encoding="utf-8")
    print("Online MCP evaluation complete", flush=True)


if __name__ == "__main__":
    main()
