"""Compare dense, hybrid, and DeepSeek rewrite + hybrid on frozen RAG labels."""

from __future__ import annotations

import argparse
import json
import math
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
from evaluation.rag import digest, evaluate, load_dataset, metadata, summarize  # noqa: E402
from evaluation.three_way import (  # noqa: E402
    POLICY_TERMS_REWRITE_PROMPT,
    POLICY_TERMS_REWRITE_VERSION,
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

DATASET = Path("data/evaluation/rag/dataset-v3.json")
POLICY = Path("data/policies/v3")
OUTPUT = Path("data/evaluation/rag/three-way-comparison-v3")
DEFAULT_TOP_K = 3


def latency_summary(values: list[float]) -> dict[str, float | None]:
    ordered = sorted(values)
    return {
        "total_ms": sum(ordered),
        "mean_ms": statistics.mean(ordered) if ordered else None,
        "p95_ms": ordered[math.ceil(len(ordered) * 0.95) - 1] if ordered else None,
    }


def rewrite_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    usages = [entry.get("usage") or {} for entry in entries]
    input_values = [usage.get("input_tokens") for usage in usages]
    output_values = [usage.get("output_tokens") for usage in usages]
    usage_complete = all(value is not None for value in input_values + output_values)
    return {
        "requests": len(entries),
        "successful_requests": sum(entry.get("status") == "ok" for entry in entries),
        "api_errors": sum(entry.get("status") == "error" for entry in entries),
        "rejected": sum(bool(entry["validation_issues"]) for entry in entries),
        "input_tokens": sum(input_values) if usage_complete else None,
        "output_tokens": sum(output_values) if usage_complete else None,
        "usage_complete": usage_complete,
        "usage_missing_cases": [
            entry.get("case_id") for entry, usage in zip(entries, usages)
            if usage.get("input_tokens") is None or usage.get("output_tokens") is None
        ],
        "latency": latency_summary([float(entry["latency_ms"]) for entry in entries]),
    }


def make_rewriter() -> Any:
    if not settings.DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY is required; no model fallback")
    return get_model(DeepseekModelName.DEEPSEEK_CHAT).model_copy(
        update={"temperature": 0, "max_tokens": 180, "streaming": False}
    )


def rewrite_all(cases: list[dict[str, Any]], cache_path: Path, dataset_sha: str,
                prompt: str = REWRITE_PROMPT, version: str = REWRITE_VERSION) -> dict[str, Any]:
    manifest = {
        "dataset_sha256": dataset_sha,
        "rewrite_version": version,
        "prompt": prompt,
        "provider": "deepseek",
        "model": settings.DEEPSEEK_MODEL,
        "base_url": settings.DEEPSEEK_BASE_URL,
        "temperature": 0,
        "max_tokens": 180,
    }
    cache = read_rewrites(cache_path, manifest)
    pending = [
        c for c in cases
        if cache["cases"].get(c["id"], {}).get("status") != "ok"
    ]
    if not pending:
        return cache
    model = make_rewriter()
    for case in pending:
        started = time.perf_counter()
        try:
            response = model.invoke(
                [SystemMessage(content=prompt), HumanMessage(content=case["query"])]
            )
            proposed = Rewrite.model_validate(parse_json(response.content)).query
            issues = validate_rewrite(case["query"], proposed)
            cache["cases"][case["id"]] = {
                "status": "ok",
                "original_query": case["query"],
                "proposed_query": proposed,
                "effective_query": case["query"] if issues else proposed,
                "validation_issues": issues,
                "raw_response": response.content,
                "usage": response.usage_metadata,
                "response_metadata": response.response_metadata,
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        except Exception as exc:
            cache["cases"][case["id"]] = {
                "status": "error",
                "original_query": case["query"],
                "proposed_query": None,
                "effective_query": case["query"],
                "validation_issues": [],
                "error_type": type(exc).__name__,
                "usage": None,
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        save_json(cache_path, cache)
        print(f"{case['id']} rewrite cached ({len(cache['cases'])}/{len(cases)})", flush=True)
    return cache


def table(report: dict[str, Any]) -> str:
    k = report["metadata"]["configuration"]["top_k"]
    lines = [
        "# 三种 RAG 检索方案对比",
        "",
        f"| 方案 / 数据集 | Recall@{k} | Precision@{k} | MRR@{k} | nDCG@{k} | 无答案空检索率 | 检索均值 ms | 检索 P95 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in report["runs"]:
        for split, item in {"all": run["summary"], **run["splits"]}.items():
            m = item[f"at_{k}"]
            fmt = lambda value: "null" if value is None else f"{value:.4f}"  # noqa: E731
            lines.append(
                f"| {run['method']} / {split} | {fmt(m['recall'])} | {fmt(m['precision'])} | {fmt(m['mrr'])} | "
                f"{fmt(m['ndcg'])} | {fmt(item['no_answer_rejection_rate'])} | "
                f"{fmt(item['latency_ms']['mean'])} | {fmt(item['latency_ms']['p95'])} |"
            )
        for style, item in run.get("query_styles", {}).items():
            m = item[f"at_{k}"]
            fmt = lambda value: "null" if value is None else f"{value:.4f}"  # noqa: E731
            lines.append(
                f"| {run['method']} / style:{style} | {fmt(m['recall'])} | {fmt(m['precision'])} | "
                f"{fmt(m['mrr'])} | {fmt(m['ndcg'])} | "
                f"{fmt(item['no_answer_rejection_rate'])} | "
                f"{fmt(item['latency_ms']['mean'])} | {fmt(item['latency_ms']['p95'])} |"
            )
        if "new10" in run:
            item = run["new10"]
            m = item[f"at_{k}"]
            fmt = lambda value: "null" if value is None else f"{value:.4f}"  # noqa: E731
            lines.append(
                f"| {run['method']} / new10 | {fmt(m['recall'])} | {fmt(m['precision'])} | "
                f"{fmt(m['mrr'])} | {fmt(m['ndcg'])} | "
                f"{fmt(item['no_answer_rejection_rate'])} | "
                f"{fmt(item['latency_ms']['mean'])} | {fmt(item['latency_ms']['p95'])} |"
            )
    rewrite = report.get("rewrite_summary", {})
    lines += [
        "",
        f"Rewrite API 请求数：{rewrite.get('requests', 0)}（成功 {rewrite.get('successful_requests', 0)}，"
        f"失败 {rewrite.get('api_errors', 0)}）；校验回退数：{rewrite.get('rejected', 0)}；"
        f"输入/输出 Token：{rewrite.get('input_tokens')}/{rewrite.get('output_tokens')}"
        f"（usage 完整={rewrite.get('usage_complete')}）；",
        f"API 耗时总计/均值/P95：{rewrite.get('latency', {}).get('total_ms')} / "
        f"{rewrite.get('latency', {}).get('mean_ms')} / {rewrite.get('latency', {}).get('p95_ms')} ms。",
        "Rewrite 本地检索 API Token：0；端到端耗时按每题 Rewrite API + Hybrid 检索耗时统计。",
        "",
        "证据充分性和生成指标须经单独的语义评审；未执行时记为 null。",
        "",
        "## 耗时与 Token",
        "",
        f"索引构建耗时：{report['metadata']['configuration']['index_init_ms']:.1f} ms；"
        f"Chunk 数：{report['metadata']['configuration']['chunk_count']}。",
        "",
        "| 方案 | 检索总耗时 ms | 均值 ms/题 | P95 ms/题 | API 输入/输出 Token |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for run in report["runs"]:
        latency_total = sum(
            sum(row["retrieval_latency_ms"]) for row in run["cases"]
        )
        tokens = report["api_token_usage"]["rewrite_api"] if run["method"] == "rewrite_hybrid" else {
            "input_tokens": 0, "output_tokens": 0
        }
        lines.append(
            f"| {run['method']} | {latency_total:.1f} | "
            f"{run['summary']['latency_ms']['mean']:.1f} | "
            f"{run['summary']['latency_ms']['p95']:.1f} | "
            f"{tokens['input_tokens']}/{tokens['output_tokens']} |"
        )
    e2e = report["rewrite_hybrid_latency_by_group"]
    lines += [
        "",
        "| Rewrite 分组 | API 均值/P95 ms | Rewrite + Hybrid 均值/P95 ms |",
        "| --- | ---: | ---: |",
    ]
    for group, values in e2e.items():
        lines.append(
            f"| {group} | {values['rewrite_api']['mean_ms']:.1f}/"
            f"{values['rewrite_api']['p95_ms']:.1f} | "
            f"{values['end_to_end']['mean_ms']:.1f}/{values['end_to_end']['p95_ms']:.1f} |"
        )
    lines.append("")
    return "\n".join(lines)


def failure_report(report: dict[str, Any]) -> str:
    lines = ["# 逐题检索差异与失败案例", ""]
    by_method = {r["method"]: {c["id"]: c for c in r["cases"]} for r in report["runs"]}
    cases = report["runs"][0]["cases"]
    for case in cases:
        case_id = case["id"]
        rows = {name: items[case_id] for name, items in by_method.items()}
        metrics = {name: row["retrieval"][str(report["metadata"]["configuration"]["top_k"])] for name, row in rows.items()}
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
                f"Precision={metrics[name]['precision']}，MRR={metrics[name]['mrr']}，"
                f"nDCG={metrics[name]['ndcg']}；失败标记={row['failures']}"
            )
        if "rewrite_hybrid" in rows:
            rewrite = rows["rewrite_hybrid"].get("rewrite", {})
            lines.append(
                f"- 重写：{rewrite.get('proposed_query')}；校验问题："
                f"{rewrite.get('validation_issues', [])}"
            )
        lines.append("")
    return "\n".join(lines)


def new10_report(report: dict[str, Any]) -> str:
    """Show all three Top-3 rankings for every newly added challenge query."""
    k = report["metadata"]["configuration"]["top_k"]
    by_method = {run["method"]: {row["id"]: row for row in run["cases"]}
                 for run in report["runs"]}
    lines = ["# v5 新增 10 题逐题排名", "",
             "排名项为 `政策文件#章节`；`—` 表示无检索结果。", ""]
    for case_id in [row["id"] for row in report["runs"][0]["cases"]
                    if row["id"].startswith(tuple(f"pair-{i:02d}-" for i in range(21, 26)))]:
        case = by_method["dense"][case_id]
        lines.extend([f"## {case_id}", "", f"问题：{case['query']}", ""])
        for method in ("dense", "hybrid", "rewrite_hybrid"):
            row = by_method[method][case_id]
            ranked = [f"{hit['source'].rsplit('/', 1)[-1]}#{hit['title']}" for hit in row["hits"][:k]]
            metric = row["retrieval"][str(k)]
            lines.append(
                f"- {method}: {ranked or '—'}；Recall={metric['recall']:.4f}，"
                f"Precision={metric['precision']:.4f}，MRR={metric['mrr']:.4f}，"
                f"nDCG={metric['ndcg']:.4f}"
            )
        rewrite = by_method["rewrite_hybrid"][case_id]["rewrite"]
        lines.extend([f"- 重写：{rewrite['effective_query']}；校验问题：{rewrite['validation_issues']}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--cases", type=Path, default=DATASET)
    parser.add_argument("--policy", type=Path, default=POLICY)
    parser.add_argument("--allow-paid-api", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, choices=(1, 2, 3))
    parser.add_argument("--rewrite-prompt", choices=("conservative", "policy-terms"),
                        default="conservative")
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
            if (
                args.cases == Path("data/evaluation/rag/dataset-v1.json")
                and args.policy == POLICY_PATH
            ):
                validated_dataset(args.cases, args.output / "frozen-policy-v1.md")
            else:
                load_dataset(args.cases, args.policy)
            print("Completed retrieval reused; no API calls", flush=True)
            return 0
    args.output.mkdir(parents=True, exist_ok=True)
    raw_dataset = json.loads(args.cases.read_text(encoding="utf-8"))
    snapshot = args.output / "frozen-policy-v1.md"
    if args.cases == Path("data/evaluation/rag/dataset-v1.json") and args.policy == POLICY_PATH:
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
    kb.search(cases[0]["query"], top_k=args.top_k)
    runs = []
    for method in ("dense", "hybrid"):
        runs.append(evaluate(cases, kb.search, method=method, top_k=args.top_k, repeats=1))
    config = {
        "top_k": args.top_k,
        "repeats": 1,
        "methods": ["dense", "hybrid", "rewrite_hybrid"],
        "embedding": DEFAULT_MODEL,
        "threshold": kb.relevance_threshold,
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
    prompt, version = (
        (POLICY_TERMS_REWRITE_PROMPT, POLICY_TERMS_REWRITE_VERSION)
        if args.rewrite_prompt == "policy-terms" else (REWRITE_PROMPT, REWRITE_VERSION)
    )
    cache = rewrite_all(cases, args.output / "rewrite-cache.json", digest(args.cases), prompt, version)
    by_query = {c["query"]: cache["cases"][c["id"]] for c in cases}

    def rewritten_search(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        return kb.search(by_query[query]["effective_query"], **kwargs)

    candidate = evaluate(cases, rewritten_search, method="hybrid", top_k=args.top_k, repeats=1)
    candidate["method"] = "rewrite_hybrid"
    for row in candidate["cases"]:
        row["rewrite"] = cache["cases"][row["id"]]
        row["effective_query"] = row["rewrite"]["effective_query"]
        row["rewrite_latency_ms"] = row["rewrite"]["latency_ms"]
        row["end_to_end_latency_ms"] = row["rewrite_latency_ms"] + statistics.mean(row["retrieval_latency_ms"])
        row["rewrite_api_token_usage"] = row["rewrite"].get("usage")
    report["runs"].append(candidate)
    if dataset["version"].startswith("ordercare-rag-v5"):
        for run in report["runs"]:
            run["new10"] = summarize(
                [row for row in run["cases"] if row["id"].startswith(("pair-21-", "pair-22-", "pair-23-", "pair-24-", "pair-25-"))],
                args.top_k,
            )
    entries = [dict(cache["cases"][case["id"]], case_id=case["id"]) for case in cases]
    report["rewrite_summary"] = rewrite_summary(entries)
    report["api_token_usage"] = {
        "dense": {"input_tokens": 0, "output_tokens": 0},
        "hybrid": {"input_tokens": 0, "output_tokens": 0},
        "rewrite_api": {
            "input_tokens": report["rewrite_summary"]["input_tokens"],
            "output_tokens": report["rewrite_summary"]["output_tokens"],
            "usage_complete": report["rewrite_summary"]["usage_complete"],
        },
    }
    report["rewrite_hybrid_latency"] = latency_summary(
        [row["end_to_end_latency_ms"] for row in candidate["cases"]]
    )
    by_case_id = {row["id"]: row for row in candidate["cases"]}
    groups: dict[str, list[str]] = {"all": [case["id"] for case in cases]}
    for key in ("split", "query_style"):
        for value in sorted({str(case.get(key)) for case in cases}):
            groups[f"{key}:{value}"] = [
                case["id"] for case in cases if str(case.get(key)) == value
            ]
    report["rewrite_hybrid_latency_by_group"] = {
        group: {
            "rewrite_api": latency_summary([
                float(cache["cases"][case_id]["latency_ms"]) for case_id in ids
            ]),
            "end_to_end": latency_summary([
                float(by_case_id[case_id]["end_to_end_latency_ms"]) for case_id in ids
            ]),
        }
        for group, ids in groups.items()
    }
    report["status"] = "retrieval_complete"
    save_json(args.output / "results.json", report)
    (args.output / "metrics.md").write_text(table(report), encoding="utf-8")
    (args.output / "failures.md").write_text(failure_report(report), encoding="utf-8")
    if dataset["version"].startswith("ordercare-rag-v5"):
        (args.output / "new10.md").write_text(new10_report(report), encoding="utf-8")
    print(table(report), flush=True)
    return int(any(run["summary"]["errors"] for run in report["runs"]))


if __name__ == "__main__":
    raise SystemExit(main())
