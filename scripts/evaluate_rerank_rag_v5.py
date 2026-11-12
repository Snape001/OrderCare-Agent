"""Compare frozen v5 Dense with reranked Hybrid and DeepSeek Rewrite + Hybrid."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluate_three_way_rag import latency_summary, rewrite_all, rewrite_summary  # noqa: E402

from customer_support.rag import DEFAULT_MODEL, PolicyKnowledgeBase  # noqa: E402
from evaluation.rag import digest, evaluate, load_dataset, metadata, summarize  # noqa: E402
from evaluation.rerank import MODEL_ID, MODEL_REVISION, get_reranker  # noqa: E402
from evaluation.three_way import (  # noqa: E402
    POLICY_TERMS_REWRITE_PROMPT,
    POLICY_TERMS_REWRITE_VERSION,
    save_json,
)

DATASET = Path("data/evaluation/rag/dataset-v5.json")
POLICY = Path("data/policies/v3")
OUTPUT = Path("data/evaluation/rag/rerank-comparison-v5")
OLD_RESULT = Path("data/evaluation/rag/three-way-comparison-v5/results.json")
TOP_K = 3


def rerank_search(kb: PolicyKnowledgeBase, reranker: Any, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Take two Top-3 routes, deduplicate, then score without rank fusion."""
    started = time.perf_counter()
    kb.ensure_index()
    dense = kb._dense_ranking(query, TOP_K)
    lexical = kb._lexical_ranking(query, TOP_K)
    dense_rows: list[dict[str, Any]] = []
    lexical_rows: list[dict[str, Any]] = []
    candidates: dict[str, dict[str, Any]] = {}
    for rank, (document, relevance) in enumerate(dense, 1):
        item = {
            "chunk_id": str(document.metadata["chunk_id"]),
            "source": str(document.metadata["source"]),
            "title": str(document.metadata["title"]),
            "content": document.page_content,
            "dense_rank": rank,
            "dense_relevance": float(relevance),
            "lexical_rank": None,
            "lexical_score": None,
        }
        dense_rows.append(dict(item))
        if relevance >= kb.relevance_threshold:
            candidates[str(item["chunk_id"])] = item
    for rank, (document, score) in enumerate(lexical, 1):
        item = {
            "chunk_id": str(document.metadata["chunk_id"]),
            "source": str(document.metadata["source"]),
            "title": str(document.metadata["title"]),
            "content": document.page_content,
            "dense_rank": None,
            "dense_relevance": None,
            "lexical_rank": rank,
            "lexical_score": float(score),
        }
        lexical_rows.append(dict(item))
        if score > 0:
            previous = candidates.get(str(item["chunk_id"]))
            if previous is None:
                candidates[str(item["chunk_id"])] = item
            else:
                previous["lexical_rank"] = rank
                previous["lexical_score"] = float(score)
    retrieval_ms = (time.perf_counter() - started) * 1000
    ordered = list(candidates.values())
    started = time.perf_counter()
    scores = reranker.score(query, [f"{row['title']}\n{row['content']}" for row in ordered])
    if len(scores) != len(ordered):
        raise ValueError("Reranker returned an unexpected number of scores")
    for row, score in zip(ordered, scores, strict=True):
        row["score"] = score
    ordered.sort(key=lambda row: (-row["score"], row["chunk_id"]))
    rerank_ms = (time.perf_counter() - started) * 1000
    diagnostics = {
        "rerank_query": query,
        "dense_candidates": dense_rows,
        "lexical_candidates": lexical_rows,
        "reranked_candidates": ordered,
        "candidate_retrieval_ms": retrieval_ms,
        "rerank_ms": rerank_ms,
    }
    return ordered[:TOP_K], diagnostics


def grouped_latency(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    return latency_summary([float(row[field]) for row in rows])


def result_table(report: dict[str, Any]) -> str:
    lines = [
        "# v5 50 题：Dense 与重排检索", "",
        "| 分组 | 方法 | Recall@3 | Precision@3 | MRR@3 | nDCG@3 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for run in report["runs"]:
        groups = {"all": run["summary"], **run["splits"]}
        groups.update({f"style:{key}": value for key, value in run["query_styles"].items()})
        groups["new10"] = run["new10"]
        for group, item in groups.items():
            m = item["at_3"]
            lines.append(
                f"| {group} | {run['method']} | {m['recall']:.4f} | {m['precision']:.4f} | "
                f"{m['mrr']:.4f} | {m['ndcg']:.4f} |"
            )
    lines += ["", "## 耗时与 Token", ""]
    for name, value in report["timing_ms"].items():
        if isinstance(value, dict):
            lines.append(f"- {name}: 总计 {value['total_ms']:.1f} ms，均值 {value['mean_ms']:.1f} ms，P95 {value['p95_ms']:.1f} ms")
        elif value is None:
            lines.append(f"- {name}: 未单独预下载")
        else:
            lines.append(f"- {name}: {value:.1f} ms")
    rewrite = report["rewrite_summary"]
    lines += [
        f"- DeepSeek 请求：{rewrite['requests']}，成功 {rewrite['successful_requests']}，失败 {rewrite['api_errors']}，校验回退 {rewrite['rejected']}",
        f"- 实际 API 输入/输出 Token：{rewrite['input_tokens']}/{rewrite['output_tokens']}；用量完整：{rewrite['usage_complete']}；缺失：{rewrite['usage_missing_cases']}",
        "- Dense 与本地重排 API Token：0。模型下载与加载为一次性开销；逐题端到端包含改写 API、候选检索和重排。",
        "", "## 逐题胜负（Recall@3）", "",
    ]
    for method, counts in report["wins_vs_dense"].items():
        lines.append(f"- {method}: 胜 {counts['win']}，负 {counts['loss']}，平 {counts['tie']}")
    lines += [
        "", "| 题目 | Dense Recall | 重排 Hybrid Recall / 胜负 | Rewrite + 重排 Recall / 胜负 |",
        "| --- | ---: | --- | --- |",
    ]
    dense_rows, hybrid_rows, rewrite_rows = (run["cases"] for run in report["runs"])
    for dense, hybrid, rewrite_row in zip(dense_rows, hybrid_rows, rewrite_rows, strict=True):
        lines.append(
            f"| {dense['id']} | {dense['retrieval']['3']['recall']:.1f} | "
            f"{hybrid['retrieval']['3']['recall']:.1f} / {hybrid['versus_dense_recall']} | "
            f"{rewrite_row['retrieval']['3']['recall']:.1f} / {rewrite_row['versus_dense_recall']} |"
        )
    lines += [
        "", "本数据集按既往检索表现筛选；dev/test 仅供分组分析，不能视为无偏留出集。",
        "逐题候选、排名、命中和改写记录见 results.json。", "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--allow-paid-api", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--model-prefetch-ms", type=float, default=None,
                        help="Measured one-time model transfer before this run, if prefetched")
    args = parser.parse_args()
    if not args.allow_paid_api:
        parser.error("DeepSeek rewrite requires explicit --allow-paid-api")
    if args.model_prefetch_ms is not None and args.model_prefetch_ms < 0:
        parser.error("--model-prefetch-ms must be nonnegative")
    if args.output.exists() and not args.resume:
        parser.error("Output exists; use --resume for this experiment's cache")
    dataset = load_dataset(DATASET, POLICY)
    cases = dataset["cases"]
    if len(cases) != 50:
        parser.error("v5 requires exactly 50 cases")
    args.output.mkdir(parents=True, exist_ok=True)
    kb = PolicyKnowledgeBase(policy_path=POLICY, persist_directory=args.output / "chroma-index")
    started = time.perf_counter()
    chunk_count = kb.ensure_index()
    index_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    reranker = get_reranker()
    reranker_init_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    reranker.score(cases[0]["query"], [cases[0]["expected_answer"]])
    warmup_ms = (time.perf_counter() - started) * 1000
    kb.search(cases[0]["query"], top_k=TOP_K, method="dense")
    dense_run = evaluate(cases, kb.search, method="dense", top_k=TOP_K, repeats=1)
    if OLD_RESULT.exists():
        old = json.loads(OLD_RESULT.read_text(encoding="utf-8"))
        old_rows = next(run for run in old["runs"] if run["method"] == "dense")["cases"]
        if old["metadata"]["sha256"][DATASET.as_posix()] != digest(DATASET):
            raise ValueError("Historical Dense dataset hash differs")
        for before, after in zip(old_rows, dense_run["cases"], strict=True):
            if before["id"] != after["id"] or [h["chunk_id"] for h in before["hits"]] != [h["chunk_id"] for h in after["hits"]]:
                raise ValueError(f"Dense baseline changed: {after['id']}")
    diagnostics: dict[str, dict[str, Any]] = {}

    def hybrid_search(query: str, **_: Any) -> list[dict[str, Any]]:
        hits, detail = rerank_search(kb, reranker, query)
        diagnostics[query] = detail
        return hits

    hybrid_run = evaluate(cases, hybrid_search, method="hybrid", top_k=TOP_K, repeats=1)
    hybrid_run["method"] = "rerank_hybrid"
    for row in hybrid_run["cases"]:
        row.update(diagnostics[row["query"]])
    cache = rewrite_all(
        cases, args.output / "rewrite-cache.json", digest(DATASET),
        POLICY_TERMS_REWRITE_PROMPT, POLICY_TERMS_REWRITE_VERSION,
    )
    if len(cache["cases"]) != len(cases):
        raise ValueError("Rewrite cache is incomplete")
    by_query = {case["query"]: cache["cases"][case["id"]] for case in cases}
    rewritten_details: dict[str, dict[str, Any]] = {}

    def rewritten_search(query: str, **_: Any) -> list[dict[str, Any]]:
        rewrite = by_query[query]
        hits, detail = rerank_search(kb, reranker, rewrite["effective_query"])
        rewritten_details[query] = detail
        return hits

    rewrite_run = evaluate(cases, rewritten_search, method="hybrid", top_k=TOP_K, repeats=1)
    rewrite_run["method"] = "rewrite_rerank_hybrid"
    for row in rewrite_run["cases"]:
        rewrite = cache["cases"][row["id"]]
        row.update(rewritten_details[row["query"]])
        row["rewrite"] = rewrite
        row["effective_query"] = rewrite["effective_query"]
        row["end_to_end_latency_ms"] = float(rewrite["latency_ms"]) + row["retrieval_latency_ms"][0]
    runs = [dense_run, hybrid_run, rewrite_run]
    for run in runs:
        run["new10"] = summarize([row for row in run["cases"] if row["id"].startswith(tuple(f"pair-{i:02d}-" for i in range(21, 26)))], TOP_K)
    entries = [dict(cache["cases"][case["id"]], case_id=case["id"]) for case in cases]
    rewrite_stats = rewrite_summary(entries)
    timing: dict[str, Any] = {
        "index_build": index_ms,
        "model_prefetch_transfer_observed": args.model_prefetch_ms,
        "model_download_and_file_lookup": reranker.download_ms,
        "model_load": reranker.load_ms,
        "model_hash_and_initialization_total": reranker_init_ms,
        "model_warmup": warmup_ms,
        "dense_retrieval": latency_summary([row["retrieval_latency_ms"][0] for row in dense_run["cases"]]),
        "hybrid_candidate_retrieval": grouped_latency(hybrid_run["cases"], "candidate_retrieval_ms"),
        "hybrid_rerank": grouped_latency(hybrid_run["cases"], "rerank_ms"),
        "hybrid_end_to_end": latency_summary([row["retrieval_latency_ms"][0] for row in hybrid_run["cases"]]),
        "rewrite_api": rewrite_stats["latency"],
        "rewrite_candidate_retrieval": grouped_latency(rewrite_run["cases"], "candidate_retrieval_ms"),
        "rewrite_rerank": grouped_latency(rewrite_run["cases"], "rerank_ms"),
        "rewrite_end_to_end": grouped_latency(rewrite_run["cases"], "end_to_end_latency_ms"),
    }
    wins: dict[str, dict[str, int]] = {}
    for run in (hybrid_run, rewrite_run):
        counts = {"win": 0, "loss": 0, "tie": 0}
        for baseline, candidate in zip(dense_run["cases"], run["cases"], strict=True):
            delta = candidate["retrieval"]["3"]["recall"] - baseline["retrieval"]["3"]["recall"]
            outcome = "win" if delta > 0 else "loss" if delta < 0 else "tie"
            counts[outcome] += 1
            candidate["versus_dense_recall"] = outcome
        wins[run["method"]] = counts
    report = {
        "status": "retrieval_complete",
        "dataset_version": dataset["version"],
        "created_at_utc": datetime.now(UTC).isoformat(),
        "metadata": metadata(DATASET, {
            "dataset": DATASET.as_posix(), "policy": POLICY.as_posix(),
            "top_k": TOP_K, "candidate_limit_each_route": TOP_K,
            "methods": [run["method"] for run in runs],
            "embedding": DEFAULT_MODEL, "threshold": kb.relevance_threshold,
            "reranker": MODEL_ID, "reranker_revision": MODEL_REVISION,
            "reranker_model_sha256": reranker.model_sha256,
            "reranker_tokenizer_sha256": reranker.tokenizer_sha256,
            "chunk_count": chunk_count,
        }),
        "policy_sha256": digest(POLICY),
        "dataset_sha256": digest(DATASET),
        "dense_matches_prior_v5": OLD_RESULT.exists(),
        "runs": runs,
        "rewrite_summary": rewrite_stats,
        "timing_ms": timing,
        "wins_vs_dense": wins,
    }
    save_json(args.output / "results.json", report)
    (args.output / "report.md").write_text(result_table(report), encoding="utf-8")
    print(result_table(report), flush=True)
    return int(any(run["summary"]["errors"] for run in runs))


if __name__ == "__main__":
    raise SystemExit(main())
