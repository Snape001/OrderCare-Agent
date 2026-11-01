"""Generate/judge from frozen retrieval traces without rerunning retrieval or business tools."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from customer_support.prompts import SYSTEM_PROMPT  # noqa: E402
from evaluation.generation import (  # noqa: E402
    JUDGE_VERSION,
    PROMPT_VERSION,
    GenerationRunner,
    generation_summary,
)
from evaluation.rag import digest, load_dataset, metadata  # noqa: E402


def save(report: dict, output: Path) -> None:
    report["generation_summary"] = generation_summary(report["runs"][0]["cases"])
    temporary = output / "results.next.json"
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output / "results.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("data/evaluation/rag/baseline-v1/results.json")
    )
    parser.add_argument("--cases", type=Path, default=Path("data/evaluation/rag/dataset-v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["baseline", "structured"], default="baseline")
    parser.add_argument("--stage", choices=["generate", "judge", "both"], default="generate")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--provider", choices=["ollama", "configured"], default="ollama")
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--allow-paid-api", action="store_true")
    parser.add_argument("--split", choices=["all", "dev", "test"], default="all")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.stage in {"judge", "both"} and not args.judge:
        parser.error("Judge requires explicit --judge; generation alone is the default")
    if args.limit is not None and args.limit < 1:
        parser.error("limit must be positive")
    dataset = load_dataset(args.cases)
    source = json.loads(args.input.read_text(encoding="utf-8"))
    expected_hash = source.get("generation_manifest", {}).get("dataset_sha256") or source[
        "metadata"
    ]["sha256"].get(args.cases.as_posix())
    if expected_hash != digest(args.cases):
        parser.error("Frozen dataset checksum differs from source retrieval/answers")
    if args.stage == "judge":
        args.mode = source.get("generation_manifest", {}).get("mode", args.mode)
    source_run = next(r for r in source["runs"] if r["method"] == "hybrid")
    labels = {c["id"]: c for c in dataset["cases"]}
    rows = [
        copy.deepcopy(r)
        for r in source_run["cases"]
        if args.split == "all" or r["split"] == args.split
    ]
    if args.limit:
        rows = rows[: args.limit]
    for row in rows:
        case = labels[row["id"]]
        if row["query"] != case["query"] or row["status"] != "ok":
            parser.error("Invalid retrieval row")
        row.update(expected_facts=case["expected_facts"], expected_answer=case["expected_answer"])
        if args.stage != "judge":
            row["generation"] = {"status": "not_run"}
        for field in ("judge", "metrics", "diagnosis"):
            row.pop(field, None)
        if args.stage == "judge" and row.get("generation", {}).get("status") != "ok":
            parser.error("Judge-only input must contain successful generated answers")
    if not rows:
        parser.error("Empty selected split")
    manifest = {
        "input_sha256": digest(args.input),
        "dataset_sha256": digest(args.cases),
        "prompt_version": PROMPT_VERSION,
        "production_prompt": SYSTEM_PROMPT,
        "judge_version": JUDGE_VERSION,
        "mode": args.mode,
        "provider": args.provider,
        "model": args.model,
        "stage": args.stage,
        "judge_enabled": args.judge,
        "case_ids": [r["id"] for r in rows],
        "implementation_sha256": digest(Path("src/evaluation/generation.py")),
    }
    if args.resume:
        report = json.loads((args.output / "results.json").read_text(encoding="utf-8"))
        if report["generation_manifest"] != manifest:
            parser.error("Resume manifest mismatch; do not mix models/prompts/data/code")
    else:
        if args.output.exists():
            parser.error("Output exists; use --resume or a new output directory")
        args.output.mkdir(parents=True)
        report = {
            "dataset_version": dataset["version"],
            "metadata": copy.deepcopy(source["metadata"]),
            "generation_manifest": manifest,
            "runs": [{"method": "hybrid", "cases": rows}],
            "source_retrieval_summary": copy.deepcopy(source_run.get("summary")),
            "source_retrieval_splits": copy.deepcopy(source_run.get("splits")),
        }
        # Keep executable source and prompt snapshots alongside metrics for reproducibility.
        for name in ("generation.py", "llm.py"):
            (args.output / (name + ".txt")).write_text(
                Path("src/evaluation", name).read_text(encoding="utf-8"), encoding="utf-8"
            )
        report["generation_environment"] = metadata(
            args.cases, {"mode": args.mode, "stage": args.stage}
        )
    runner = GenerationRunner(args.provider, args.model, args.allow_paid_api, args.judge)
    if "model_info" in report and report["model_info"] != runner.model_info:
        runner.close()
        parser.error("Model identity changed; cannot resume")
    report["model_info"] = runner.model_info
    save(report, args.output)
    try:
        for row in report["runs"][0]["cases"]:
            case = labels[row["id"]]
            if args.stage in {"generate", "both"} and row.get("generation", {}).get(
                "status"
            ) not in {"ok", "error"}:
                print(f"{row['id']} generating...", flush=True)
                row.update(runner.generate(case, row["hits"], args.mode))
                save(report, args.output)
                print(
                    f"{row['id']} generation {row['generation']['status']} "
                    f"{row['generation'].get('latency_ms', 0) / 1000:.1f}s",
                    flush=True,
                )
            if (
                args.stage in {"judge", "both"}
                and row.get("generation", {}).get("status") == "ok"
                and "judge" not in row
            ):
                print(f"{row['id']} judging...", flush=True)
                row.update(runner.judge(case, row))
                save(report, args.output)
                print(
                    f"{row['id']} judge {row['judge']['status']} "
                    f"{row['judge'].get('latency_ms', 0) / 1000:.1f}s",
                    flush=True,
                )
    finally:
        runner.close()
        save(report, args.output)
    print(json.dumps(report["generation_summary"], ensure_ascii=False), flush=True)
    return int(
        any(
            r.get("generation", {}).get("status") == "error"
            or r.get("judge", {}).get("status") == "error"
            for r in report["runs"][0]["cases"]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
