"""Run frozen source-labelled RAG experiments; no LLM calls unless explicitly enabled."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from customer_support.rag import DEFAULT_MODEL, PolicyKnowledgeBase  # noqa: E402
from evaluation.rag import evaluate, load_dataset, markdown, metadata  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("data/evaluation/rag/dataset-v1.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--index", type=Path, default=Path(".tmp/rag-evaluation-index"))
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=["lexical", "dense", "hybrid"],
        default=["lexical", "dense", "hybrid"],
    )
    parser.add_argument("--top-k", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.50)
    parser.add_argument("--lexical-weight", type=float, default=1.0)
    parser.add_argument("--lexical-threshold", type=float, default=0.30)
    parser.add_argument("--expand-query", action="store_true")
    parser.add_argument("--split", choices=["all", "dev", "test"], default="all")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--generator-provider", choices=["ollama", "configured"], default="ollama")
    parser.add_argument("--judge-provider", choices=["ollama", "configured"], default="ollama")
    parser.add_argument("--ollama-model", default="qwen3:4b")
    parser.add_argument("--judge-ollama-model", default="qwen3:4b")
    parser.add_argument("--allow-paid-api", action="store_true")
    args = parser.parse_args()
    if args.generate and not args.judge:
        parser.error(
            "Legacy combined evaluation requires --judge; use evaluate_rag_generation.py for generation-only"
        )
    if args.top_k < 1 or args.repeats < 1 or not 0 <= args.threshold <= 1:
        parser.error("Positive top-k/repeats and threshold in [0,1] required")
    dataset = load_dataset(args.cases)
    cases = [c for c in dataset["cases"] if args.split == "all" or c["split"] == args.split]
    if not cases:
        parser.error("Selected split is empty")
    output = args.output or Path("data/evaluation/rag/runs") / datetime.now(UTC).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    if output.exists():
        parser.error("Output already exists; use a new directory to preserve previous experiments")
    output.mkdir(parents=True)
    kb = PolicyKnowledgeBase(
        persist_directory=args.index,
        relevance_threshold=args.threshold,
        lexical_weight=args.lexical_weight,
        lexical_threshold=args.lexical_threshold,
    )
    started = time.perf_counter()
    count = kb.ensure_index(force_rebuild=args.rebuild)
    build_ms = (time.perf_counter() - started) * 1000
    # Warm-up is excluded from per-query steady-state timing and recorded separately.
    started = time.perf_counter()
    kb.search(cases[0]["query"], top_k=args.top_k)
    warmup_ms = (time.perf_counter() - started) * 1000
    from evaluation.experiments import EXPANSION_VERSION, expand_query

    def search(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        effective = expand_query(query) if args.expand_query else query
        return kb.search(effective, **kwargs)

    generation = None
    generation_config = None
    if args.generate:
        from evaluation.llm import LLMEvaluator, make_model

        generator, gc = make_model(args.generator_provider, args.ollama_model, args.allow_paid_api)
        judge, jc = make_model(args.judge_provider, args.judge_ollama_model, args.allow_paid_api)
        generation = LLMEvaluator(generator, judge)
        generation_config = {"generator": gc, "judge": jc, "prompt_version": "claims-v1"}
    config = {
        "top_k": args.top_k,
        "repeats": args.repeats,
        "threshold": args.threshold,
        "lexical_threshold": args.lexical_threshold,
        "lexical_weight": args.lexical_weight,
        "query_expansion": EXPANSION_VERSION if args.expand_query else None,
        "methods": args.methods,
        "split": args.split,
        "embedding": DEFAULT_MODEL,
        "embedding_threads": 2,
        "chunk_size": 220,
        "chunk_overlap": 40,
        "fusion": "dense 1/(10+r); lexical min(1,2*s)/(10+r)",
        "index": args.index.as_posix(),
        "chunk_count": count,
        "index_init_ms": build_ms,
        "warmup_ms": warmup_ms,
        "generation": generation_config,
    }
    runs = []
    try:
        for method in args.methods:
            run = evaluate(
                cases,
                search,
                method=method,
                top_k=args.top_k,
                repeats=args.repeats,
                generate=generation,
            )
            for row in run["cases"]:
                row["effective_query"] = (
                    expand_query(row["query"]) if args.expand_query else row["query"]
                )
            runs.append(run)
            print(method, json.dumps(run["summary"], ensure_ascii=False), flush=True)
    finally:
        if generation is not None:
            generation.close()
    report = {
        "dataset_version": dataset["version"],
        "metadata": metadata(args.cases, config),
        "index_manifest": json.loads(kb.manifest_path.read_text(encoding="utf-8")),
        "runs": runs,
    }
    (output / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "summary.md").write_text(markdown(report), encoding="utf-8")
    print(f"Reports saved to {output}")
    return int(any(r["summary"]["errors"] or r["summary"]["generation"]["errors"] for r in runs))


if __name__ == "__main__":
    raise SystemExit(main())
