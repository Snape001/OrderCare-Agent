"""Compare dense, hybrid, and DeepSeek rewrite + hybrid on frozen RAG labels."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from core import settings  # noqa: E402
from core.llm import get_model  # noqa: E402
from customer_support.policy import POLICY_PATH, policy_files  # noqa: E402
from customer_support.rag import DEFAULT_MODEL, PolicyKnowledgeBase  # noqa: E402
from evaluation.llm import parse_json  # noqa: E402
from evaluation.rag import digest, evaluate, load_dataset, metadata  # noqa: E402
from evaluation.three_way import (  # noqa: E402
    REWRITE_PROMPT,
    REWRITE_VERSION,
    Rewrite,
    frozen_policy,
    read_rewrites,
    save_json,
    validate_rewrite,
    validated_dataset,
)
from schema.models import DeepseekModelName  # noqa: E402

DATASET = Path("data/evaluation/rag/dataset-v1.json")
OUTPUT = Path("data/evaluation/rag/three-way-comparison-v1")


def make_rewriter() -> Any:
    if not settings.DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY is required; no model fallback")
    return get_model(DeepseekModelName.DEEPSEEK_CHAT).model_copy(
        update={"temperature": 0, "max_tokens": 180, "streaming": False}
    )


def rewrite_all(cases: list[dict[str, Any]], cache_path: Path, dataset_sha: str) -> dict[str, Any]:
    manifest = {
        "dataset_sha256": dataset_sha,
        "rewrite_version": REWRITE_VERSION,
        "prompt": REWRITE_PROMPT,
        "provider": "deepseek",
        "model": settings.DEEPSEEK_MODEL,
        "base_url": settings.DEEPSEEK_BASE_URL,
        "temperature": 0,
        "max_tokens": 180,
    }
    cache = read_rewrites(cache_path, manifest)
    pending = [c for c in cases if c["id"] not in cache["cases"]]
    if not pending:
        return cache
    model = make_rewriter()
    for case in pending:
        started = time.perf_counter()
        response = model.invoke(
            [SystemMessage(content=REWRITE_PROMPT), HumanMessage(content=case["query"])]
        )
        proposed = Rewrite.model_validate(parse_json(response.content)).query
        issues = validate_rewrite(case["query"], proposed)
        cache["cases"][case["id"]] = {
            "original_query": case["query"],
            "proposed_query": proposed,
            "effective_query": case["query"] if issues else proposed,
            "validation_issues": issues,
            "raw_response": response.content,
            "usage": response.usage_metadata or {},
            "response_metadata": response.response_metadata,
            "latency_ms": (time.perf_counter() - started) * 1000,
        }
        save_json(cache_path, cache)
        print(f"{case['id']} rewrite cached ({len(cache['cases'])}/{len(cases)})", flush=True)
    return cache


def table(report: dict[str, Any]) -> str:
    lines = [
        "# 三种 RAG 检索方案对比",
        "",
        "| 方案 / 数据集 | Recall@2 | MRR@2 | nDCG@2 | 无答案空检索率 | 平均检索 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in report["runs"]:
        for split, item in {"all": run["summary"], **run["splits"]}.items():
            m = item["at_2"]
            fmt = lambda value: "null" if value is None else f"{value:.4f}"  # noqa: E731
            lines.append(
                f"| {run['method']} / {split} | {fmt(m['recall'])} | {fmt(m['mrr'])} | "
                f"{fmt(m['ndcg'])} | {fmt(item['no_answer_rejection_rate'])} | "
                f"{fmt(item['latency_ms']['mean'])} |"
            )
    rewrite = report.get("rewrite_summary", {})
    lines += [
        "",
        f"重写请求数：{rewrite.get('requests', 0)}；校验拒绝数：{rewrite.get('rejected', 0)}；"
        f"输入/输出 Token：{rewrite.get('input_tokens', 0)}/{rewrite.get('output_tokens', 0)}。",
        "",
        "证据充分性和生成指标须经单独的语义评审；未执行时记为 null。",
        "",
    ]
    return "\n".join(lines)


def failure_report(report: dict[str, Any]) -> str:
    lines = ["# 逐题检索差异与失败案例", ""]
    by_method = {r["method"]: {c["id"]: c for c in r["cases"]} for r in report["runs"]}
    cases = report["runs"][0]["cases"]
    for case in cases:
        case_id = case["id"]
        rows = {name: items[case_id] for name, items in by_method.items()}
        metrics = {name: row["retrieval"]["2"] for name, row in rows.items()}
        rankings = {name: [h["title"] for h in row["hits"]] for name, row in rows.items()}
        if len({tuple(v) for v in rankings.values()}) == 1 and all(
            not row["failures"] for row in rows.values()
        ):
            continue
        lines.append(f"## {case_id} / {case['split']} / {case['category']}")
        lines.append(f"问题：{case['query']}")
        for name, row in rows.items():
            lines.append(
                f"- {name}: {rankings[name]}；Recall={metrics[name]['recall']}，"
                f"MRR={metrics[name]['mrr']}；失败标记={row['failures']}"
            )
        if "rewrite_hybrid" in rows:
            rewrite = rows["rewrite_hybrid"].get("rewrite", {})
            lines.append(
                f"- 重写：{rewrite.get('proposed_query')}；校验问题："
                f"{rewrite.get('validation_issues', [])}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--cases", type=Path, default=DATASET)
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--allow-paid-api", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not args.allow_paid_api:
        parser.error("DeepSeek rewrite requires explicit --allow-paid-api")
    if args.output.exists() and not args.resume:
        parser.error("Output exists; use --resume to reuse cached rewrites")
    completed_path = args.output / "results.json"
    if args.resume and completed_path.exists():
        completed = json.loads(completed_path.read_text(encoding="utf-8"))
        if completed.get("status") == "retrieval_complete":
            if completed["policy_integrity"]["current_policy_sha256"] != digest(args.policy):
                parser.error("Policy changed since completed retrieval")
            if completed["metadata"]["sha256"][args.cases.as_posix()] != digest(args.cases):
                parser.error("Dataset changed since completed retrieval")
            if args.cases == DATASET and args.policy == POLICY_PATH:
                validated_dataset(args.cases, args.output / "frozen-policy-v1.md")
            else:
                load_dataset(args.cases, args.policy)
            print("Completed retrieval reused; no API calls", flush=True)
            return 0
    args.output.mkdir(parents=True, exist_ok=True)
    raw_dataset = json.loads(args.cases.read_text(encoding="utf-8"))
    snapshot = args.output / "frozen-policy-v1.md"
    if args.cases == DATASET and args.policy == POLICY_PATH:
        frozen_policy(snapshot, raw_dataset["policy_sha256"])
        dataset = validated_dataset(args.cases, snapshot)
    else:
        dataset = load_dataset(args.cases, args.policy)
    cases = dataset["cases"]
    index_path = args.output / "chroma-index"
    kb = PolicyKnowledgeBase(policy_path=args.policy, persist_directory=index_path)
    start = time.perf_counter()
    count = kb.ensure_index()
    index_ms = (time.perf_counter() - start) * 1000
    kb.search(cases[0]["query"], top_k=2)
    runs = []
    for method in ("dense", "hybrid"):
        runs.append(evaluate(cases, kb.search, method=method, top_k=2, repeats=1))
    config = {
        "top_k": 2,
        "repeats": 1,
        "methods": ["dense", "hybrid", "rewrite_hybrid"],
        "embedding": DEFAULT_MODEL,
        "threshold": kb.relevance_threshold,
        "lexical_threshold": kb.lexical_threshold,
        "lexical_weight": kb.lexical_weight,
        "chunk_size": 220,
        "chunk_overlap": 40,
        "index": index_path.as_posix(),
        "chunk_count": count,
        "index_init_ms": index_ms,
        "dataset": args.cases.as_posix(),
        "policy": args.policy.as_posix(),
    }
    report: dict[str, Any] = {
        "status": "retrieval_in_progress",
        "dataset_version": dataset["version"],
        "metadata": metadata(args.cases, config),
        "policy_integrity": {
            "dataset_expected_sha256": raw_dataset["policy_sha256"],
            "frozen_snapshot_sha256": digest(snapshot) if snapshot.exists() else None,
            "current_policy_sha256": digest(args.policy),
            "policy_path": args.policy.as_posix(),
            "indexed_sections_identical": True if snapshot.exists() else None,
            "source_file_sha256": {
                path.as_posix(): digest(path) for path in policy_files(args.policy)
            },
        },
        "index_manifest": json.loads(kb.manifest_path.read_text(encoding="utf-8")),
        "runs": runs,
        "generation_metrics": None,
        "evidence_sufficiency": None,
        "created_at_utc": datetime.now(UTC).isoformat(),
    }
    save_json(args.output / "results.json", report)
    cache = rewrite_all(cases, args.output / "rewrite-cache.json", digest(args.cases))
    by_query = {c["query"]: cache["cases"][c["id"]] for c in cases}

    def rewritten_search(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        return kb.search(by_query[query]["effective_query"], **kwargs)

    candidate = evaluate(cases, rewritten_search, method="hybrid", top_k=2, repeats=1)
    candidate["method"] = "rewrite_hybrid"
    for row in candidate["cases"]:
        row["rewrite"] = cache["cases"][row["id"]]
        row["effective_query"] = row["rewrite"]["effective_query"]
    report["runs"].append(candidate)
    entries = list(cache["cases"].values())
    report["rewrite_summary"] = {
        "requests": len(entries),
        "rejected": sum(bool(e["validation_issues"]) for e in entries),
        "mean_latency_ms": statistics.mean(e["latency_ms"] for e in entries),
        "input_tokens": sum(e["usage"].get("input_tokens", 0) or 0 for e in entries),
        "output_tokens": sum(e["usage"].get("output_tokens", 0) or 0 for e in entries),
    }
    report["status"] = "retrieval_complete"
    save_json(args.output / "results.json", report)
    (args.output / "metrics.md").write_text(table(report), encoding="utf-8")
    (args.output / "failures.md").write_text(failure_report(report), encoding="utf-8")
    print(table(report), flush=True)
    return int(any(run["summary"]["errors"] for run in report["runs"]))


if __name__ == "__main__":
    raise SystemExit(main())
