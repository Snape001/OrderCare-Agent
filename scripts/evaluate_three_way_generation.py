"""Evaluate generation on paired changed-evidence cases without repeating model calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core import settings  # noqa: E402
from customer_support.policy import POLICY_PATH  # noqa: E402
from evaluation.generation import (  # noqa: E402
    JUDGE_VERSION,
    PROMPT_VERSION,
    GenerationRunner,
    generation_summary,
)
from evaluation.rag import digest, load_dataset  # noqa: E402
from evaluation.three_way import save_json, validated_dataset  # noqa: E402
from schema.models import DeepseekModelName  # noqa: E402

DEFAULT_OUTPUT = Path("data/evaluation/rag/three-way-comparison-v1")
CONTROLS = ("rag-001", "rag-031")


def evidence_signature(row: dict[str, Any]) -> tuple[tuple[str, str, str], ...]:
    return tuple((h["source"], h["title"], h["content"]) for h in row["hits"])


def selected_cases(report: dict[str, Any], all_cases: bool) -> list[str]:
    runs = {r["method"]: {c["id"]: c for c in r["cases"]} for r in report["runs"]}
    ordered = list(runs["hybrid"])
    if all_cases:
        return ordered
    selected = set(CONTROLS)
    for case_id in ordered:
        if len({evidence_signature(run[case_id]) for run in runs.values()}) > 1:
            selected.add(case_id)
    return [case_id for case_id in ordered if case_id in selected]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-paid-api", action="store_true")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--all", action="store_true", help="Generate all 40 cases per method")
    args = parser.parse_args()
    if not args.allow_paid_api:
        parser.error("DeepSeek generation requires explicit --allow-paid-api")
    retrieval_path = args.output / "results.json"
    retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
    if retrieval["status"] != "retrieval_complete" or len(retrieval["runs"]) != 3:
        parser.error("Complete three-way retrieval results are required")
    configuration = retrieval["metadata"]["configuration"]
    policy_path = Path(configuration.get("policy", POLICY_PATH))
    dataset_path = Path(configuration.get("dataset", "data/evaluation/rag/dataset-v1.json"))
    if retrieval["policy_integrity"]["current_policy_sha256"] != digest(policy_path):
        parser.error("Current policy changed since retrieval")
    dataset = (
        load_dataset(dataset_path, policy_path)
        if policy_path.is_dir()
        else validated_dataset(dataset_path, args.output / "frozen-policy-v1.md")
    )
    labels = {c["id"]: c for c in dataset["cases"]}
    case_ids = selected_cases(retrieval, args.all)
    manifest = {
        "retrieval_sha256": digest(retrieval_path),
        "dataset_sha256": digest(dataset_path),
        "policy_sha256": digest(policy_path),
        "policy_path": policy_path.as_posix(),
        "case_ids": case_ids,
        "prompt_version": PROMPT_VERSION,
        "judge_version": JUDGE_VERSION,
        "model": settings.DEEPSEEK_MODEL,
        "base_url": settings.DEEPSEEK_BASE_URL,
        "temperature": 0,
        "mode": "baseline",
        "implementation_sha256": digest(Path("src/evaluation/generation.py")),
    }
    cache_path = args.output / "generation-results.json"
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if cache.get("manifest") != manifest:
            parser.error("Generation cache manifest mismatch; use a new output directory")
    else:
        cache = {"manifest": manifest, "model_info": {}, "cases": {}}
    runner = GenerationRunner(
        "configured",
        settings.DEEPSEEK_MODEL,
        allow_paid=True,
        judge_enabled=args.judge,
        configured_model=DeepseekModelName.DEEPSEEK_CHAT,
        policy_path=policy_path,
    )
    runner.generator = runner.generator.model_copy(
        update={"temperature": 0, "max_tokens": 1536, "streaming": False}
    )
    runner.judge_model = runner.judge_model.model_copy(
        update={"temperature": 0, "max_tokens": 1800, "streaming": False}
    )
    cache["model_info"] = runner.model_info | {"actual_model": settings.DEEPSEEK_MODEL}
    save_json(cache_path, cache)
    try:
        for run in retrieval["runs"]:
            for source_row in run["cases"]:
                case_id = source_row["id"]
                if case_id not in case_ids:
                    continue
                key = f"{run['method']}:{case_id}"
                row = cache["cases"].setdefault(
                    key,
                    {
                        "id": case_id,
                        "method": run["method"],
                        "query": source_row["query"],
                        "split": source_row["split"],
                        "should_abstain": source_row["should_abstain"],
                        "hits": source_row["hits"],
                    },
                )
                if "generation" not in row:
                    row.update(runner.generate(labels[case_id], row["hits"], "baseline"))
                    save_json(cache_path, cache)
                    print(f"{key} generation={row['generation']['status']}", flush=True)
                if row["generation"]["status"] != "ok":
                    raise RuntimeError(f"Generation failed for {key}; no fallback or automatic retry")
                if args.judge and "judge" not in row:
                    row.update(runner.judge(labels[case_id], row))
                    save_json(cache_path, cache)
                    print(f"{key} judge={row['judge']['status']}", flush=True)
                    if row["judge"]["status"] != "ok" and "raw_response" not in row["judge"]:
                        raise RuntimeError(f"Judge API failed for {key}; no fallback or automatic retry")
    finally:
        runner.close()
        save_json(cache_path, cache)
    summaries = {}
    for run in retrieval["runs"]:
        rows = [cache["cases"][f"{run['method']}:{case_id}"] for case_id in case_ids]
        summaries[run["method"]] = generation_summary(rows)
    cache["summary"] = summaries
    save_json(cache_path, cache)
    print(json.dumps({k: v["all"] for k, v in summaries.items()}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
