"""Create paired generation reports offline, with explicit evidence provenance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from evaluation.generation_report import (  # noqa: E402
    compare_generation,
    comparison_markdown,
    prepare_report,
    summary_markdown,
)
from evaluation.rag import digest, load_dataset  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error("Output exists; choose a new directory")
    labels = {
        c["id"]: c for c in load_dataset(Path("data/evaluation/rag/dataset-v1.json"))["cases"]
    }
    audit = json.loads(args.evidence.read_text(encoding="utf-8"))
    reports = [
        prepare_report(json.loads(path.read_text(encoding="utf-8")), audit, labels)
        for path in (args.baseline, args.candidate)
    ]
    comparison = compare_generation(*reports)
    comparison["inputs_sha256"] = {
        str(p): digest(p) for p in (args.baseline, args.candidate, args.evidence)
    }
    args.output.mkdir(parents=True)
    for name, report in zip(("baseline", "candidate"), reports, strict=True):
        (args.output / f"{name}-reviewed.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (args.output / f"{name}-summary.md").write_text(summary_markdown(report), encoding="utf-8")
    (args.output / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output / "comparison.md").write_text(comparison_markdown(comparison), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
