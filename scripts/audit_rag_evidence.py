"""Explicitly run an answer-blind evidence audit against saved generation contexts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from evaluation.evidence import (  # noqa: E402
    AUDIT_VERSION,
    EvidenceAudit,
    audit_metrics,
    context_digest,
    evidence_messages,
)
from evaluation.generation import GenerationRunner  # noqa: E402
from evaluation.llm import parse_json  # noqa: E402
from evaluation.rag import digest, load_dataset  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--judge", action="store_true")
    p.add_argument("--model", default="qwen3:4b")
    p.add_argument("--provider", choices=["ollama", "configured"], default="ollama")
    p.add_argument("--allow-paid-api", action="store_true")
    args = p.parse_args()
    if not args.judge:
        p.error("Evidence audit requires explicit --judge")
    if args.output.exists():
        p.error("Output exists; preserve previous audits")
    dataset_path = Path("data/evaluation/rag/dataset-v1.json")
    dataset = load_dataset(dataset_path)
    source = json.loads(args.input.read_text(encoding="utf-8"))
    if source["generation_manifest"]["dataset_sha256"] != digest(dataset_path):
        p.error("Dataset changed")
    rows = source["runs"][0]["cases"]
    if any("context" not in r for r in rows):
        p.error("All selected cases must have saved contexts")
    labels = {c["id"]: c for c in dataset["cases"]}
    runner = GenerationRunner(args.provider, args.model, args.allow_paid_api, True)
    model = runner.judge_model
    if args.provider == "ollama":
        model = model.model_copy(
            update={"format": EvidenceAudit.model_json_schema(), "num_predict": 1000}
        )
    report: dict[str, Any] = {
        "audit_version": AUDIT_VERSION,
        "dataset_sha256": digest(dataset_path),
        "input_sha256": digest(args.input),
        "model_info": dict(
            runner.model_info, audit_max_tokens=1000 if args.provider == "ollama" else None
        ),
        "implementation_sha256": digest(Path("src/evaluation/evidence.py")),
        "cases": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".source.txt").write_text(
        Path("src/evaluation/evidence.py").read_text(encoding="utf-8"), encoding="utf-8"
    )

    def save() -> None:
        temporary = args.output.with_suffix(".next.json")
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(args.output)

    try:
        for row in rows:
            case = labels[row["id"]]
            item: dict[str, Any] = {
                "id": case["id"],
                "context_sha256": context_digest(row["context"]),
                "metrics": {"evidence_sufficiency": None, "fact_evidence_coverage": None},
                "status": "error",
            }
            if case["should_abstain"]:
                item.update(
                    status="ok",
                    origin="frozen_no_answer_label",
                    metrics={
                        "evidence_sufficiency": 0.0,
                        "fact_evidence_coverage": None,
                        "fact_support_values": [],
                        "missing_facts": case["expected_facts"],
                    },
                )
            else:
                try:
                    messages = evidence_messages(case, row["context"])
                    if args.provider != "ollama":
                        messages[0].content += "\nJSON schema: " + json.dumps(
                            EvidenceAudit.model_json_schema()
                        )
                    item["prompt_messages"] = [
                        {"type": m.type, "content": m.content} for m in messages
                    ]
                    raw = runner.call(model, messages)
                    item["judge"] = raw
                    if raw["response_metadata"].get("done_reason") == "length":
                        raise ValueError("Evidence judge output truncated")
                    verdict = EvidenceAudit.model_validate(parse_json(raw["raw_response"]))
                    item.update(
                        status="ok",
                        origin="answer_blind_llm_judge",
                        parsed=verdict.model_dump(),
                        metrics=audit_metrics(case, row["context"], verdict),
                    )
                except Exception as exc:
                    item["error_type"] = type(exc).__name__
            report["cases"].append(item)
            save()
            print(f"{case['id']} evidence audit {item['status']}", flush=True)
    finally:
        runner.close()
        save()
    return int(any(r["status"] != "ok" for r in report["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
